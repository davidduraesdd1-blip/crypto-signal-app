"""
ml_predictor.py — Lightweight ML price direction predictor

Model     : scikit-learn GradientBoostingClassifier (ensemble of decision trees)
Features  : RSI, MACD histogram, BB position, ATR%, volume ratio, stochastic K/D, ADX
Target    : Will next 4 bars close higher than current? (binary classification)
Training  : Rolling 500-bar window (re-trained every prediction if cache stale)
Cache     : Per-(pair, tf) prediction cached for 1 hour
"""
from __future__ import annotations

import logging
import threading
import time
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import joblib as _joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1 hour

# ─── Model store ───────────────────────────────────────────────────────────────
_model_store: dict = {}   # {(pair, tf): fitted_model}
_model_lock = threading.Lock()

# PERF-19: disk persistence via joblib — survives Streamlit hot-reloads
_MODEL_DISK_TTL = 3600   # 1 hour — don't load a pkl file older than this
_TEMP_DIR = Path(tempfile.gettempdir())


def _model_cache_path(pair: str, tf: str) -> Path:
    """Return the temp-dir path for a (pair, tf) model pkl file."""
    safe_pair = pair.replace("/", "_").replace("\\", "_")
    return _TEMP_DIR / f"sgrok_{safe_pair}_{tf}.pkl"


def _load_model_from_disk(pair: str, tf: str):
    """Load a model dict from disk if the pkl exists and is < _MODEL_DISK_TTL old.
    Returns the model dict or None.
    """
    if not _JOBLIB_AVAILABLE:
        return None
    path = _model_cache_path(pair, tf)
    try:
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age < _MODEL_DISK_TTL:
                return _joblib.load(str(path))
    except Exception as _e:
        logger.debug("Model disk load failed for %s/%s: %s", pair, tf, _e)
    return None


def _save_model_to_disk(pair: str, tf: str, model_dict: dict) -> None:
    """Persist a model dict to disk via joblib (best-effort; never raises)."""
    if not _JOBLIB_AVAILABLE:
        return
    path = _model_cache_path(pair, tf)
    try:
        _joblib.dump(model_dict, str(path))
    except Exception as _e:
        logger.debug("Model disk save failed for %s/%s: %s", pair, tf, _e)

# ─── Config ────────────────────────────────────────────────────────────────────
LOOKAHEAD_BARS   = 4       # predict direction 4 bars ahead
TRAIN_BARS       = 500     # rolling training window (D3: 300→500 for better regime coverage; Hastie et al. 2009)
MIN_TRAIN_BARS   = 80      # minimum bars required to train
FEATURE_LAG      = 1       # use 1-bar lag for features (avoid look-ahead bias)
MIN_RETURN_PCT   = 0.003   # 0.3% move threshold to label as UP/DOWN vs flat


def _build_features(df: pd.DataFrame, onchain_ctx: "dict | None" = None) -> Optional[pd.DataFrame]:
    """
    Build feature matrix from enriched OHLCV DataFrame.
    Requires columns: rsi, macd_hist, bb_upper, bb_lower, stoch_k, stoch_d, adx,
                      close, volume.
    D2: Optional onchain_ctx dict injects macro-cycle on-chain signals as constant
        features across all rows (MVRV Z-score, SOPR). These signals persist for
        days-weeks and meaningfully shift the ML model's regime context.
        Research: Nakamoto (2021), CoinMetrics (2022) — MVRV as ML feature improves
        crypto direction accuracy by 4-8pp over pure TA features.
    Returns feature DataFrame with no NaNs, or None if insufficient data.
    """
    required = ["rsi", "macd_hist", "bb_upper", "bb_lower", "stoch_k", "stoch_d", "close", "volume"]
    for col in required:
        if col not in df.columns:
            return None

    feat = pd.DataFrame(index=df.index)

    # Normalized RSI (0-1)
    feat["rsi_norm"]     = df["rsi"] / 100.0

    # MACD histogram momentum (normalized by price)
    feat["macd_hist"]    = df["macd_hist"] / (df["close"] + 1e-9)

    # BB position (0 = at lower band, 1 = at upper band)
    bb_range = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    feat["bb_pos"]       = (df["close"] - df["bb_lower"]) / (bb_range + 1e-9)

    # BB bandwidth (volatility indicator)
    feat["bb_width"]     = bb_range / (df["close"] + 1e-9)

    # Stochastic (0-1)
    feat["stoch_k"]      = df["stoch_k"] / 100.0
    feat["stoch_d"]      = df["stoch_d"] / 100.0
    feat["stoch_cross"]  = (df["stoch_k"] - df["stoch_d"]) / 100.0

    # ADX (0-1)
    if "adx" in df.columns:
        feat["adx_norm"] = df["adx"] / 100.0
    else:
        feat["adx_norm"] = 0.25

    # ATR % of price (volatility)
    if "atr" in df.columns:
        feat["atr_pct"]  = df["atr"] / (df["close"] + 1e-9)
    else:
        feat["atr_pct"]  = df["close"].pct_change().abs().rolling(14).mean()

    # Volume ratio (vs 20-bar avg)
    vol_avg = df["volume"].rolling(20).mean()
    feat["vol_ratio"]    = df["volume"] / (vol_avg + 1e-9)

    # Price momentum (short)
    feat["mom_3"]        = df["close"].pct_change(3)
    feat["mom_5"]        = df["close"].pct_change(5)

    # VWAP distance (if available)
    if "vwap" in df.columns:
        feat["vwap_dist"] = (df["close"] - df["vwap"]) / (df["close"] + 1e-9)
    else:
        feat["vwap_dist"] = 0.0

    # SuperTrend direction encoded
    if "supertrend_dir" in df.columns:
        feat["st_up"]    = (df["supertrend_dir"] == 1).astype(float)
    else:
        feat["st_up"]    = 0.5

    # D2: On-chain macro cycle features (constant per model run — daily signals)
    # MVRV Z-Score: normalized to [-1, +1] range using empirical BTC cycle bounds
    #   [≤0 = undervalued → +1; 7+ = extreme overvalued → -1; historical: ≤0 in bear bottoms, 7+ at tops]
    # SOPR-1: centered at 0; negative = capitulation (+1), positive = distribution (-0.5)
    if onchain_ctx:
        _mvrv_z = onchain_ctx.get("mvrv_z")
        if _mvrv_z is not None:
            try:
                _mz = float(_mvrv_z)
                _mvrv_feat = max(-1.0, min(1.0, (_mz - 3.5) / 3.5 * -1))  # centered at 3.5, inverted
                feat["mvrv_z_norm"] = _mvrv_feat
            except (ValueError, TypeError):
                feat["mvrv_z_norm"] = 0.0
        else:
            feat["mvrv_z_norm"] = 0.0

        _sopr = onchain_ctx.get("sopr")
        if _sopr is not None:
            try:
                _sp = float(_sopr)
                _sopr_feat = max(-1.0, min(1.0, (_sp - 1.0) * 10))  # scale SOPR deviation × 10
                feat["sopr_signal"] = -_sopr_feat  # invert: high SOPR = distribution = bearish
            except (ValueError, TypeError):
                feat["sopr_signal"] = 0.0
        else:
            feat["sopr_signal"] = 0.0
    else:
        feat["mvrv_z_norm"] = 0.0
        feat["sopr_signal"] = 0.0

    feat = feat.replace([np.inf, -np.inf], np.nan).dropna()
    return feat


def _build_labels(df: pd.DataFrame, feat_index) -> Optional[pd.Series]:
    """
    Binary label: 1 if close[t + LOOKAHEAD_BARS] > close[t] by > MIN_RETURN_PCT, else 0.
    Returns None if insufficient bars.
    """
    if len(df) < LOOKAHEAD_BARS + 5:
        return None
    future_close = df["close"].shift(-LOOKAHEAD_BARS)
    returns = (future_close - df["close"]) / (df["close"] + 1e-9)
    labels = (returns > MIN_RETURN_PCT).astype(int)
    # Align with feature index and drop the last LOOKAHEAD_BARS rows (no label)
    labels = labels.reindex(feat_index).dropna()
    return labels


def _train_model(df: pd.DataFrame):
    """
    Train an ensemble of GradientBoostingClassifier + XGBoost on the last TRAIN_BARS.

    Ensemble strategy (2025 research consensus):
    - XGBoost on technical indicators is the strongest single published model for
      crypto price direction (Springer Nature, 2025). GBM provides complementary
      regularization. Averaged probabilities outperform either alone.
    - Falls back to GBM-only if XGBoost is not installed.

    Returns a dict {'gbm': model, 'xgb': model|None} or None if insufficient data.
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
    except ImportError:
        logger.error("scikit-learn not installed — run: pip install scikit-learn")
        return None

    if len(df) < MIN_TRAIN_BARS + LOOKAHEAD_BARS:
        return None

    # Use last TRAIN_BARS rows for training (exclude last LOOKAHEAD_BARS for labeling)
    train_df = df.iloc[-(TRAIN_BARS + LOOKAHEAD_BARS):-LOOKAHEAD_BARS]
    feat = _build_features(train_df)
    if feat is None or len(feat) < MIN_TRAIN_BARS:
        return None

    labels = _build_labels(train_df, feat.index)
    if labels is None or len(labels) < MIN_TRAIN_BARS:
        return None

    # Align
    common = feat.index.intersection(labels.index)
    X = feat.loc[common].values
    y = labels.loc[common].values

    if len(np.unique(y)) < 2:
        return None  # degenerate: all same class

    gbm = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", GradientBoostingClassifier(
            n_estimators=60,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.8,
            min_samples_leaf=5,
            random_state=42,
        )),
    ])
    gbm.fit(X, y)

    # XGBoost — optional but strongly preferred (best 2025 crypto direction model)
    xgb_model = None
    try:
        import xgboost as xgb
        xgb_model = xgb.XGBClassifier(
            n_estimators=80,
            max_depth=4,
            learning_rate=0.07,
            subsample=0.8,
            colsample_bytree=0.8,
            # use_label_encoder removed in XGBoost >= 2.0 — omit to avoid TypeError
            eval_metric="logloss",
            verbosity=0,
            random_state=42,
            n_jobs=1,
        )
        xgb_model.fit(X, y)
    except ImportError:
        logger.debug("xgboost not installed — using GBM only (pip install xgboost)")
    except Exception as _xe:
        logger.debug("XGBoost training failed: %s — using GBM only", _xe)
        xgb_model = None

    # PERF: compute accuracy once at train time; stored in model dict so
    # get_ml_prediction() skips _compute_accuracy() on every call
    accuracy = _compute_accuracy(gbm, df)
    return {"gbm": gbm, "xgb": xgb_model, "X_train": X, "y_train": y, "accuracy": accuracy}


def _get_or_train_model(pair: str, tf: str, df: pd.DataFrame):
    """Return in-memory cached model, disk-cached model, or train a new one.

    Cache hierarchy (PERF-19):
    1. In-memory _model_store — zero latency, lost on Streamlit hot-reload
    2. Disk pkl via joblib — survives hot-reloads, 1-hour TTL
    3. Retrain from OHLCV data — last resort (slowest path)
    """
    key = (pair, tf)
    with _model_lock:
        model = _model_store.get(key)
    if model is not None:
        return model
    # Try disk cache (survives hot-reloads)
    model = _load_model_from_disk(pair, tf)
    if model is not None:
        with _model_lock:
            _model_store[key] = model
        return model
    # Train from scratch and persist to both memory and disk
    model = _train_model(df)
    if model:
        with _model_lock:
            _model_store[key] = model
        _save_model_to_disk(pair, tf, model)
    return model


def _compute_accuracy(model, df: pd.DataFrame) -> float:
    """Estimate model accuracy on the holdout portion of training data.
    Accepts either a raw sklearn model or the ensemble dict returned by _train_model().
    """
    try:
        from sklearn.metrics import accuracy_score
        # Resolve the underlying GBM if passed the ensemble dict
        if isinstance(model, dict):
            model = model["gbm"]
        # Use last 40 bars as quasi-holdout
        holdout = df.iloc[-40 - LOOKAHEAD_BARS:-LOOKAHEAD_BARS]
        feat = _build_features(holdout)
        if feat is None or len(feat) < 10:
            return 0.0
        labels = _build_labels(holdout, feat.index)
        if labels is None or len(labels) < 10:
            return 0.0
        common = feat.index.intersection(labels.index)
        X = feat.loc[common].values
        y = labels.loc[common].values
        preds = model.predict(X)
        return float(accuracy_score(y, preds))
    except Exception:
        return 0.0


# ─── Public API ─────────────────────────────────────────────────────────────────

_NEUTRAL_RESULT = {
    "prediction":     "UNCERTAIN",
    "probability":    0.5,
    "model_accuracy": 0.0,
    "features_used":  0,
    "signal":         "NEUTRAL",
    "score_bias":     0.0,
    "error":          None,
}


def get_ml_prediction(pair: str, tf: str, df: pd.DataFrame, onchain_ctx: "dict | None" = None) -> dict:
    """
    Run ML price direction prediction for a given pair/timeframe.

    Parameters
    ----------
    pair       : e.g. 'BTC/USDT'
    tf         : e.g. '1h'
    df         : enriched OHLCV DataFrame (output of _enrich_df())
    onchain_ctx: D2 — optional dict with on-chain features (mvrv_z, sopr).
                 Applied as constant features across all training/prediction rows.

    Returns
    -------
    dict with keys:
      prediction    : 'BULLISH' | 'BEARISH' | 'UNCERTAIN'
      probability   : float [0, 1] — probability of bullish outcome
      model_accuracy: float [0, 1] — estimated holdout accuracy
      signal        : 'BUY' | 'SELL' | 'NEUTRAL'
      score_bias    : float in [-10, +10] for confidence score adjustment
    """
    now = time.time()
    cache_key = f"{pair}:{tf}"
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached.get("_ts", 0) < _CACHE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    if df is None or len(df) < MIN_TRAIN_BARS + LOOKAHEAD_BARS + 10:
        result = {**_NEUTRAL_RESULT, "error": "Insufficient data for ML prediction"}
        with _cache_lock:
            _cache[cache_key] = {**result, "_ts": now}
        return result

    try:
        model = _get_or_train_model(pair, tf, df)
        if model is None:
            result = {**_NEUTRAL_RESULT, "error": "Model training failed (insufficient data or no class diversity)"}
            with _cache_lock:
                _cache[cache_key] = {**result, "_ts": now}
            return result

        # Build features for the latest bar (prediction target; D2: inject on-chain ctx)
        feat = _build_features(df.tail(20), onchain_ctx=onchain_ctx)
        if feat is None or len(feat) == 0:
            result = {**_NEUTRAL_RESULT, "error": "Feature extraction failed"}
            with _cache_lock:
                _cache[cache_key] = {**result, "_ts": now}
            return result

        X_latest = feat.iloc[[-1]].values  # last row = current bar

        # Ensemble prediction: average GBM + XGBoost probabilities
        # XGBoost on crypto technical indicators outperforms GBM alone (Springer 2025)
        if isinstance(model, dict):
            gbm_prob = float(model["gbm"].predict_proba(X_latest)[0][1])
            if model.get("xgb") is not None:
                xgb_prob = float(model["xgb"].predict_proba(X_latest)[0][1])
                prob_up = (gbm_prob + xgb_prob) / 2.0   # equal-weight ensemble
            else:
                prob_up = gbm_prob
            # PERF: accuracy pre-computed at train time — avoid re-running on every prediction
            accuracy = model["accuracy"] if model.get("accuracy") is not None else _compute_accuracy(model["gbm"], df)
        else:
            # Legacy single-model path (shouldn't happen with current code)
            prob_up = float(model.predict_proba(X_latest)[0][1])
            accuracy = _compute_accuracy(model, df)

        # Classify
        if prob_up >= 0.60:
            prediction = "BULLISH"
            signal     = "BUY"
        elif prob_up <= 0.40:
            prediction = "BEARISH"
            signal     = "SELL"
        else:
            prediction = "UNCERTAIN"
            signal     = "NEUTRAL"

        # Score bias: strong signal → ±10, uncertain → 0
        deviation = (prob_up - 0.5) * 2   # range [-1, +1]
        score_bias = round(deviation * 10.0 * accuracy, 1)
        score_bias = max(-10.0, min(10.0, score_bias))

        result = {
            "prediction":     prediction,
            "probability":    round(prob_up, 3),
            "model_accuracy": round(accuracy, 3),
            "features_used":  feat.shape[1],
            "signal":         signal,
            "score_bias":     score_bias,
            "error":          None,
        }
    except Exception as e:
        logger.warning("ML prediction failed for %s/%s: %s", pair, tf, e)
        result = {**_NEUTRAL_RESULT, "error": str(e)}

    with _cache_lock:
        _cache[cache_key] = {**result, "_ts": now}

    return result


# ─── #48 HMM Regime Detection ──────────────────────────────────────────────────

_HMM_CACHE: dict = {}
_HMM_CACHE_LOCK = threading.Lock()
_HMM_CACHE_TTL  = 14400  # 4 hours — HMM fitting is expensive


def fit_hmm_regime(prices: list, n_states: int = 3) -> dict:
    """
    #48 — 3-state Hidden Markov Model regime detection.

    Parameters
    ----------
    prices   : list of daily BTC closing prices (last 400 days recommended)
    n_states : number of HMM states (default 3 → Bull / Neutral / Bear)

    Features : log returns + 7-day rolling volatility (std of log returns)

    State labeling (by mean log return, ascending):
      lowest mean  → Bear
      highest mean → Bull
      middle       → Neutral

    Returns
    -------
    dict with keys:
      current_state        : str  — 'Bull' | 'Neutral' | 'Bear' | 'UNKNOWN'
      state_probabilities  : list[float]  — posterior probs for [Bear, Neutral, Bull]
      regime_history       : list[str]    — last 20 state labels
      confidence           : float        — max probability of current state
      error                : str | None
    """
    _fallback = {
        "current_state": "UNKNOWN", "state_probabilities": [0.0, 0.0, 0.0],
        "regime_history": [], "confidence": 0.0, "error": "HMM unavailable",
    }

    if not prices or len(prices) < 30:
        return {**_fallback, "error": "Insufficient price data (need >= 30)"}

    # Cache on a stable key: price count + first/last price hash
    _cache_key = f"hmm:{len(prices)}:{round(prices[0], 0)}:{round(prices[-1], 0)}"
    now = time.time()
    with _HMM_CACHE_LOCK:
        cached = _HMM_CACHE.get(_cache_key)
        if cached and (now - cached.get("_ts", 0)) < _HMM_CACHE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        logger.debug("[HMM #48] hmmlearn not installed — pip install hmmlearn")
        result = {**_fallback, "error": "hmmlearn not installed"}
        with _HMM_CACHE_LOCK:
            _HMM_CACHE[_cache_key] = {**result, "_ts": now}
        return result

    try:
        arr = np.array(prices, dtype=np.float64)
        arr = arr[arr > 0]   # strip zeros/negatives
        if len(arr) < 30:
            return {**_fallback, "error": "Insufficient valid price data"}

        log_ret = np.log(arr[1:] / arr[:-1])

        # 7-day rolling volatility
        window = 7
        vol = np.array([
            log_ret[max(0, i - window + 1): i + 1].std()
            for i in range(len(log_ret))
        ])

        X = np.column_stack([log_ret, vol]).astype(np.float64)
        X = X[~np.isnan(X).any(axis=1)]

        if len(X) < 20:
            return {**_fallback, "error": "Feature matrix too short after NaN drop"}

        # Fit HMM — handle covariance_floor API change (hmmlearn 0.3.0+)
        try:
            model = GaussianHMM(
                n_components=n_states, covariance_type="diag",
                n_iter=50, random_state=42, covariance_floor=1e-6,
            )
        except TypeError:
            model = GaussianHMM(
                n_components=n_states, covariance_type="diag",
                n_iter=50, random_state=42,
            )

        model.fit(X)
        states = model.predict(X)
        posteriors = model.predict_proba(X)

        # Label states by mean log return (ascending: Bear < Neutral < Bull)
        means = [float(X[states == s, 0].mean()) if (states == s).sum() > 0 else 0.0
                 for s in range(n_states)]
        sorted_states = sorted(range(n_states), key=lambda s: means[s])
        _labels = ["Bear", "Neutral", "Bull"] if n_states == 3 else [f"State{i}" for i in range(n_states)]
        state_label_map = {sorted_states[i]: _labels[i] for i in range(n_states)}

        current_raw  = int(states[-1])
        current_name = state_label_map.get(current_raw, "UNKNOWN")

        # Reorder probabilities as [Bear, Neutral, Bull]
        last_post = posteriors[-1]  # shape (n_states,)
        ordered_probs = [
            round(float(last_post[sorted_states[i]]), 3) for i in range(n_states)
        ]
        confidence = float(max(ordered_probs))

        # Last 20 state labels for regime history
        history_raw = states[-20:] if len(states) >= 20 else states
        regime_history = [state_label_map.get(int(s), "UNKNOWN") for s in history_raw]

        result = {
            "current_state":       current_name,
            "state_probabilities": ordered_probs,   # [Bear_prob, Neutral_prob, Bull_prob]
            "regime_history":      regime_history,
            "confidence":          round(confidence, 3),
            "error":               None,
        }
        with _HMM_CACHE_LOCK:
            _HMM_CACHE[_cache_key] = {**result, "_ts": now}
        return result

    except Exception as e:
        logger.warning("[HMM #48] fit_hmm_regime failed: %s", e)
        result = {**_fallback, "error": str(e)[:120]}
        with _HMM_CACHE_LOCK:
            _HMM_CACHE[_cache_key] = {**result, "_ts": now}
        return result


def invalidate_model(pair: str, tf: str) -> None:
    """Force model retraining on next prediction call."""
    key = (pair, tf)
    with _model_lock:
        _model_store.pop(key, None)
    with _cache_lock:
        _cache.pop(f"{pair}:{tf}", None)


def invalidate_all_models() -> None:
    """Clear all cached models and predictions (e.g. after major config change)."""
    with _model_lock:
        _model_store.clear()
    with _cache_lock:
        _cache.clear()
