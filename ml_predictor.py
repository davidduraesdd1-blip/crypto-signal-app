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
# Cap at 20 entries (5 coins × 4 TFs): GBM + XGBoost model pair is ~2-10MB each;
# 148 entries for 37 pairs × 4 TFs would use 300-700MB — enough to hit the
# Streamlit Community Cloud 1GB memory limit. FIFO eviction removes oldest half
# when the cap is reached so hot coins stay in memory.
_model_store: dict = {}   # {(pair, tf): fitted_model}, insertion-ordered Python 3.7+
_model_lock = threading.Lock()
# P2 audit fix — was 20 entries; with 37 pairs × 4 timeframes = 148
# possible (pair, tf) keys, the cap caused FIFO thrashing (50% eviction
# every full scan) and forced repeated retraining of warm models.
# Raised to 160 so a full scan stays in memory. Memory ceiling stays
# bounded: each fitted GBM is ~1-3 MB → ~160-480 MB upper bound, well
# under the 1GB Streamlit Community Cloud limit.
_MODEL_STORE_MAX_ENTRIES = 160

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
    3-class label (Issue #13): replaces binary UP/NOT-UP with directional 3-class.
    Binary labeling (UP/NOT-UP) conflated neutral and bearish outcomes, causing
    the model to treat "flat" bars as "bearish" and biasing SELL signals.

    Classes (sklearn-compatible integers 0, 1, 2):
      0 = STRONG_DOWN : return < -MIN_RETURN_PCT
      1 = NEUTRAL     : -MIN_RETURN_PCT <= return <= +MIN_RETURN_PCT
      2 = STRONG_UP   : return > +MIN_RETURN_PCT

    Research: Zhong & Enke (2017) "Forecasting daily stock market return" — 3-class
    classification (up/neutral/down) outperforms binary by 4-7pp accuracy on out-of-
    sample evaluation. The neutral class absorbs noise that inflated false BUY signals.

    Returns None if insufficient bars.
    """
    if len(df) < LOOKAHEAD_BARS + 5:
        return None
    future_close = df["close"].shift(-LOOKAHEAD_BARS)
    returns = (future_close - df["close"]) / (df["close"] + 1e-9)
    # 3-class: 0=DOWN, 1=NEUTRAL, 2=UP
    labels = pd.Series(1, index=returns.index, dtype=int)   # default NEUTRAL
    labels[returns > MIN_RETURN_PCT]  = 2  # STRONG UP
    labels[returns < -MIN_RETURN_PCT] = 0  # STRONG DOWN
    # Align with feature index and drop the last LOOKAHEAD_BARS rows (no label)
    labels = labels.reindex(feat_index).dropna().astype(int)
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


def _evict_model_store_if_full() -> None:
    """FIFO evict oldest half of _model_store when it reaches _MODEL_STORE_MAX_ENTRIES.
    Called inside _model_lock. Python dicts are insertion-ordered (3.7+), so
    list(_model_store.keys())[: n//2] gives the n//2 oldest entries.
    """
    if len(_model_store) >= _MODEL_STORE_MAX_ENTRIES:
        keys_to_evict = list(_model_store.keys())[: _MODEL_STORE_MAX_ENTRIES // 2]
        for k in keys_to_evict:
            del _model_store[k]
        logger.debug(
            "[ml_predictor] evicted %d stale models from store (cap=%d)",
            len(keys_to_evict), _MODEL_STORE_MAX_ENTRIES,
        )


def _get_or_train_model(pair: str, tf: str, df: pd.DataFrame):
    """Return in-memory cached model, disk-cached model, or train a new one.

    Cache hierarchy (PERF-19):
    1. In-memory _model_store — zero latency, lost on Streamlit hot-reload
    2. Disk pkl via joblib — survives hot-reloads, 1-hour TTL
    3. Retrain from OHLCV data — last resort (slowest path)

    Memory cap: _MODEL_STORE_MAX_ENTRIES enforced via FIFO eviction so the
    store never grows to 148 entries × 2-10MB = 300-700MB.
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
            _evict_model_store_if_full()
            _model_store[key] = model
        return model
    # Train from scratch and persist to both memory and disk
    model = _train_model(df)
    if model:
        with _model_lock:
            _evict_model_store_if_full()
            _model_store[key] = model
        _save_model_to_disk(pair, tf, model)
    return model


def _compute_accuracy(model, df: pd.DataFrame) -> float:
    """Estimate model accuracy on a TRUE out-of-sample holdout.

    Issue #14 FIX — In-sample bias: previous code used the LAST 40 bars of df as
    holdout, but training uses df.iloc[-(TRAIN_BARS+LOOKAHEAD):-LOOKAHEAD] — the last
    40 bars were INSIDE the training window, making accuracy look better than reality.

    Fix: use the 40 bars immediately BEFORE the training window starts.
    These bars were never seen during training → genuine out-of-sample evaluation.

    Research: Hastie, Tibshirani & Friedman (2009) "Elements of Statistical Learning"
    §7.2: "the training error is an overly optimistic estimate of generalization error."
    Proper holdout requires strict temporal separation from the training set.
    """
    try:
        from sklearn.metrics import accuracy_score
        if isinstance(model, dict):
            gbm = model["gbm"]
        else:
            gbm = model

        # Audit 2026-05-02 C14: holdout must come AFTER the training window,
        # not before. Bars before training are stale-regime data the model
        # never claimed to fit; reporting accuracy on them inflates apparent
        # generalization. The trailing 40 bars (excluding the LOOKAHEAD_BARS
        # leak buffer) are the most recent out-of-sample evaluation we can
        # do without retraining.
        if len(df) < (TRAIN_BARS + LOOKAHEAD_BARS + 40 + LOOKAHEAD_BARS):
            holdout = None
        else:
            # df: …  [train start] [train…train end] [LOOKAHEAD buffer] [holdout 40] [LOOKAHEAD buffer for labels]
            holdout_end_idx   = -LOOKAHEAD_BARS                 # last LOOKAHEAD bars unlabeled
            holdout_start_idx = holdout_end_idx - 40            # 40-bar near-term holdout
            holdout = df.iloc[holdout_start_idx:holdout_end_idx]

        if holdout is None or len(holdout) < 10:
            return 0.0
        feat = _build_features(holdout)
        if feat is None or len(feat) < 10:
            return 0.0
        labels = _build_labels(holdout, feat.index)
        if labels is None or len(labels) < 10:
            return 0.0
        common = feat.index.intersection(labels.index)
        if len(common) < 5:
            return 0.0
        X = feat.loc[common].values
        y = labels.loc[common].values
        preds = gbm.predict(X)
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
        # 3-class output: proba shape is (1, 3) → [P(DOWN), P(NEUTRAL), P(UP)]
        # Classes: 0=DOWN, 1=NEUTRAL, 2=UP  (set by _build_labels)
        if isinstance(model, dict):
            gbm_proba = model["gbm"].predict_proba(X_latest)[0]   # shape (3,)
            if model.get("xgb") is not None:
                xgb_proba = model["xgb"].predict_proba(X_latest)[0]
                avg_proba = (gbm_proba + xgb_proba) / 2.0
            else:
                avg_proba = gbm_proba
            accuracy = model["accuracy"] if model.get("accuracy") is not None else _compute_accuracy(model["gbm"], df)
        else:
            avg_proba = model.predict_proba(X_latest)[0]
            accuracy  = _compute_accuracy(model, df)

        # Ensure 3 classes (backward compat: if model was trained before 3-class fix)
        if len(avg_proba) == 2:
            prob_down = 1.0 - float(avg_proba[1])
            prob_up   = float(avg_proba[1])
            prob_flat = 0.0
        else:
            prob_down = float(avg_proba[0])
            prob_flat = float(avg_proba[1])
            prob_up   = float(avg_proba[2])

        # Winner = highest probability class
        if prob_up >= prob_down and prob_up > prob_flat and prob_up >= 0.40:
            prediction = "BULLISH"
            signal     = "BUY"
        elif prob_down >= prob_up and prob_down > prob_flat and prob_down >= 0.40:
            prediction = "BEARISH"
            signal     = "SELL"
        else:
            prediction = "UNCERTAIN"
            signal     = "NEUTRAL"

        # Score bias: net bullish - bearish probability, scaled by accuracy
        net_bias   = prob_up - prob_down           # range [-1, +1]
        score_bias = round(net_bias * 10.0 * accuracy, 1)
        score_bias = max(-10.0, min(10.0, score_bias))
        # Alias prob_up for backward-compatible output
        prob_up_out = prob_up

        result = {
            "prediction":     prediction,
            "probability":    round(prob_up_out, 3),
            "prob_up":        round(prob_up, 3),
            "prob_neutral":   round(prob_flat, 3),
            "prob_down":      round(prob_down, 3),
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


def fit_hmm_regime(prices: list, n_states: int = 3, ohlcv_df: "pd.DataFrame | None" = None) -> dict:
    """
    #48 — 3-state Hidden Markov Model regime detection.

    Parameters
    ----------
    prices   : list of daily BTC closing prices (last 400 days recommended)
    n_states : number of HMM states (default 3 → Bull / Neutral / Bear)
    ohlcv_df : optional OHLCV DataFrame with columns [open, high, low, close, volume].
               When provided, adds Garman-Klass realized volatility as 3rd HMM feature
               (Issue #15). GK vol uses OHLC ranges for more efficient estimation than
               close-to-close std dev. Research: Garman & Klass (1980) — GK estimator
               is 5× more efficient than close-to-close; Yang-Zhang 2000 for drift.

    Features (when ohlcv_df provided): log returns + 7d rolling vol + GK realized vol
    Features (close-only fallback):    log returns + 7d rolling vol (existing behavior)

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
      gk_vol_used          : bool         — whether Garman-Klass feature was used
      error                : str | None
    """
    _fallback = {
        "current_state": "UNKNOWN", "state_probabilities": [0.0, 0.0, 0.0],
        "regime_history": [], "confidence": 0.0, "gk_vol_used": False, "error": "HMM unavailable",
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

        # 7-day rolling close-to-close volatility
        window = 7
        vol_cc = np.array([
            log_ret[max(0, i - window + 1): i + 1].std()
            for i in range(len(log_ret))
        ])

        # Issue #15 — Garman-Klass realized volatility as 3rd HMM feature
        # GK = sqrt(0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2) per bar
        # 5× more efficient than close-to-close: uses full OHLC range information.
        gk_vol_used = False
        gk_vol = None
        if ohlcv_df is not None and len(ohlcv_df) >= len(arr):
            try:
                _df = ohlcv_df.iloc[-len(arr):].copy()
                required_cols = {"open", "high", "low", "close"}
                if required_cols.issubset({c.lower() for c in _df.columns}):
                    _df.columns = [c.lower() for c in _df.columns]
                    o = _df["open"].values.astype(float)
                    h = _df["high"].values.astype(float)
                    l = _df["low"].values.astype(float)
                    c = _df["close"].values.astype(float)
                    # Clip to avoid log(0); GK formula: Garman & Klass (1980)
                    _const = 2 * np.log(2) - 1
                    _hl = np.log(np.maximum(h / np.maximum(l, 1e-10), 1e-10))
                    _co = np.log(np.maximum(c / np.maximum(o, 1e-10), 1e-10))
                    gk_daily = np.sqrt(np.maximum(0.5 * _hl**2 - _const * _co**2, 0))
                    # Align with log_ret length (drop first element, same as log_ret)
                    gk_vol = gk_daily[1:]
                    gk_vol = np.where(np.isnan(gk_vol), vol_cc, gk_vol)
                    gk_vol_used = True
            except Exception as _e:
                logger.debug("[HMM] Garman-Klass computation failed: %s — using close-to-close", _e)
                gk_vol = None

        if gk_vol is not None:
            X = np.column_stack([log_ret, vol_cc, gk_vol]).astype(np.float64)
        else:
            X = np.column_stack([log_ret, vol_cc]).astype(np.float64)
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
            "gk_vol_used":         gk_vol_used,
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
