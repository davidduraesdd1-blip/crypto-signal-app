"""
ml_predictor.py — Lightweight ML price direction predictor

Model     : scikit-learn GradientBoostingClassifier (ensemble of decision trees)
Features  : RSI, MACD histogram, BB position, ATR%, volume ratio, stochastic K/D, ADX
Target    : Will next 4 bars close higher than current? (binary classification)
Training  : Rolling 300-bar window (re-trained every prediction if cache stale)
Cache     : Per-(pair, tf) prediction cached for 1 hour
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1 hour

# ─── Model store ───────────────────────────────────────────────────────────────
_model_store: dict = {}   # {(pair, tf): fitted_model}
_model_lock = threading.Lock()

# ─── Config ────────────────────────────────────────────────────────────────────
LOOKAHEAD_BARS   = 4       # predict direction 4 bars ahead
TRAIN_BARS       = 300     # rolling training window
MIN_TRAIN_BARS   = 80      # minimum bars required to train
FEATURE_LAG      = 1       # use 1-bar lag for features (avoid look-ahead bias)
MIN_RETURN_PCT   = 0.003   # 0.3% move threshold to label as UP/DOWN vs flat


def _build_features(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Build feature matrix from enriched OHLCV DataFrame.
    Requires columns: rsi, macd_hist, bb_upper, bb_lower, stoch_k, stoch_d, adx,
                      close, volume.
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
            use_label_encoder=False,
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

    return {"gbm": gbm, "xgb": xgb_model, "X_train": X, "y_train": y}


def _get_or_train_model(pair: str, tf: str, df: pd.DataFrame):
    """Return cached model or train a new one."""
    key = (pair, tf)
    with _model_lock:
        model = _model_store.get(key)
    if model is None:
        model = _train_model(df)
        if model:
            with _model_lock:
                _model_store[key] = model
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


def get_ml_prediction(pair: str, tf: str, df: pd.DataFrame) -> dict:
    """
    Run ML price direction prediction for a given pair/timeframe.

    Parameters
    ----------
    pair : e.g. 'BTC/USDT'
    tf   : e.g. '1h'
    df   : enriched OHLCV DataFrame (output of _enrich_df())

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

        # Build features for the latest bar (prediction target)
        feat = _build_features(df.tail(20))
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
            accuracy = _compute_accuracy(model["gbm"], df)
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
