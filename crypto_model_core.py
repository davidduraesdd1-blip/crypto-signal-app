"""
crypto_model_core.py
Importable module — v5.9.13 signal engine + v5.9 backtest/logging functions.
Bug fixes applied. config_overrides.json supported for UI-driven configuration.
"""

import ccxt
import pandas as pd
import numpy as np
import json
import requests
from datetime import datetime, timedelta, timezone
import time
import os
import logging
import itertools
import concurrent.futures
import threading
from statsmodels.tsa.stattools import coint
import database as _db

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

VERSION = "v5.9.13-phase9-complete"

_log_lock     = threading.Lock()  # Protects CSV file writes from parallel scan workers
_weights_lock = threading.Lock()  # Protects global weights dict from parallel scan workers
_last_drift_result: dict = {}     # F6/F7: last concept drift check result; read by UI via get_drift_status()

# ──────────────────────────────────────────────
# CONFIGURATION DEFAULTS
# ──────────────────────────────────────────────
PAIRS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'BNB/USDT']
TIMEFRAMES = ['1h', '4h', '1d', '1w']
OHLCV_LIMIT = 500  # Increased from 200 — Ichimoku needs 52-bar warmup, 500 gives 448 usable bars on 1h (~18.7 days)
TA_EXCHANGE = 'kraken'
PAPER_EXCHANGE = 'krakenfutures'

VOLUME_MULTIPLIER = 1.2
RISK_PER_TRADE_PCT = 1.0
PORTFOLIO_SIZE_USD = 10000.0
MAX_POSITION_PCT_CAP = 50.0
MAX_OPEN_PER_PAIR = 1
MAX_TOTAL_EXPOSURE_PCT = 50.0
DRAWDOWN_CIRCUIT_BREAKER_PCT = 15.0  # Pause new signals if portfolio drawdown exceeds this %
TRAILING_STOP_ENABLED = True         # Moves stop loss with price to lock in profits

HIGH_CONF_THRESHOLD = 68.0
HIGH_MTF_THRESHOLD = 35.0
ALERT_THRESHOLD = 68.0

# Regime-aware HIGH_CONF thresholds — different market conditions require
# different confidence bars.  Trending markets are more reliable for
# directional signals (lower bar); ranging and volatile markets produce more
# false signals (higher bar).
_REGIME_HIGH_CONF_THRESHOLDS: dict = {
    "TrendFollow":   65.0,   # strong trend — directional momentum reliable
    "MeanReversion": 72.0,   # ranging market — more noise, stricter bar
    "Breakout":      75.0,   # breakout setup — require strong confirmation
    "Volatile":      78.0,   # high volatility — strict filter, many false signals
    "Trending":      65.0,   # alias for TrendFollow
    "Ranging":       72.0,   # alias for MeanReversion
    "Neutral":       68.0,   # unknown/mixed — use flat default
}

CORR_THRESHOLD = 0.75
CORR_REDUCTION_FACTOR = 0.5
CORR_LOOKBACK_DAYS = 30

SUPER_TREND_PERIOD = 10
SUPER_TREND_MULTIPLIER = 3.0
SR_LOOKBACK = 20
VOLUME_BREAKOUT_MULTIPLIER = 1.5
ADX_TREND_THRESHOLD = 25
ADX_RANGE_THRESHOLD = 20

BACKTEST_HOLD_DAYS = 14
# Fee & slippage model (OKX perpetual futures defaults)
TAKER_FEE_PCT  = 0.0005   # 0.05%  — market order / stop fill
MAKER_FEE_PCT  = 0.0002   # 0.02%  — limit order / target fill
SLIPPAGE_PCT   = 0.0005   # 0.05%  — market impact per side (conservative)

STAT_ARB_LOOKBACK = 100
STAT_ARB_Z_THRESHOLD = 2.0
STAT_ARB_Z_EXIT = 0.5

KRAKEN_TESTNET_KEYS = "kraken_testnet_keys.json"
CSV_FILENAME_BASE = "crypto_scan_v5.9.13-phase9"
EXCEL_FILENAME_BASE = "crypto_dashboard_v5.9.13"
DYNAMIC_WEIGHTS_FILE = "dynamic_weights.json"
RISK_MODE_ATR = {'Trending': 2.5, 'Ranging': 1.5, 'Neutral': 2.0}
RISK_MODE_POSITION = {'Trending': 1.2, 'Ranging': 0.7, 'Neutral': 1.0}

# ── Leverage recommendation ────────────────────────────────────────────────────
MAX_LEVERAGE_CAP       = 10       # Hard cap — never recommend above this
HIGH_VOL_ATR_THRESHOLD = 0.025   # ATR/price > 2.5% = high volatility
# ── Triple take-profit ATR multipliers ────────────────────────────────────────
TP1_MULT = 1.5   # First target  — exit 40% of position (R:R 1.5:1)
TP2_MULT = 2.5   # Second target — exit 40% of position (R:R 2.5:1)
TP3_MULT = 4.0   # Third target  — trail 20% of position (R:R 4.0:1)
# ── MTF confirmation gate ─────────────────────────────────────────────────────
MTF_GATE_ENABLED = True  # Downgrade STRONG signals if higher TF disagrees

# ──────────────────────────────────────────────
# CONFIG OVERRIDES (UI-driven)
# ──────────────────────────────────────────────
_CONFIG_FILE = "config_overrides.json"

def load_config_overrides():
    if not os.path.exists(_CONFIG_FILE):
        return
    try:
        with open(_CONFIG_FILE, 'r') as f:
            overrides = json.load(f)
        g = globals()
        for key, val in overrides.items():
            if key in g:
                g[key] = val
    except Exception as e:
        logging.warning(f"Config override load failed: {e}")

load_config_overrides()

# ──────────────────────────────────────────────
# DYNAMIC WEIGHTS
# ──────────────────────────────────────────────
DEFAULT_WEIGHTS = {
    'core': 0.25, 'momentum': 0.15, 'stoch': 0.10,
    'adx': 0.08, 'vwap_ich': 0.08, 'fib': 0.08,
    'div': 0.05, 'supertrend': 0.667, 'sr_breakout': 0.667,
    'regime': 0.667, 'bonus': 0.5, 'fng': 0.10,
    'onchain': 0.12, 'agents': 0.25, 'stat_arb': 0.15
}

def _load_weights():
    loaded = _db.load_weights()
    if loaded:
        return loaded
    # Fallback: read legacy JSON file if DB is empty (e.g. first run before migration)
    if os.path.exists(DYNAMIC_WEIGHTS_FILE):
        try:
            with open(DYNAMIC_WEIGHTS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.debug(f"Could not load dynamic weights from file: {e}")
    return DEFAULT_WEIGHTS.copy()

weights = _load_weights()


def _get_weights() -> dict:
    """Thread-safe snapshot of current weights for use in parallel scan workers."""
    with _weights_lock:
        return dict(weights)


def save_weights():
    with _weights_lock:
        _db.save_weights(weights, source='manual')

# ──────────────────────────────────────────────
# PAPER TRADING
# ──────────────────────────────────────────────
def load_positions():
    return _db.load_positions()

def save_positions(positions):
    _db.save_positions(positions)

def log_closed_trade(trade):
    _db.log_closed_trade(trade)

def update_positions(current_prices):
    positions = load_positions()
    closed = []
    for pair, pos in list(positions.items()):
        real_price = current_prices.get(pair)
        if not real_price:
            continue
        entry = pos['entry']
        direction = pos['direction']
        target = pos['target']
        stop = pos['stop']
        entry_time = datetime.fromisoformat(pos['entry_time'])
        size_pct = pos['size_pct']
        pnl_pct = 0
        reason = "Open"

        if direction == "BUY":
            gross = (real_price - entry) / entry * 100
            pnl_pct = gross - (TAKER_FEE_PCT + SLIPPAGE_PCT + TAKER_FEE_PCT) * 100
            if real_price >= target: reason = "Target Hit"
            elif real_price <= stop: reason = "Stop Hit"
        else:
            gross = (entry - real_price) / entry * 100
            pnl_pct = gross - (TAKER_FEE_PCT + SLIPPAGE_PCT + TAKER_FEE_PCT) * 100
            if real_price <= target: reason = "Target Hit"
            elif real_price >= stop: reason = "Stop Hit"

        if (datetime.now() - entry_time).days >= BACKTEST_HOLD_DAYS:
            reason = "Timeout"

        if reason != "Open":
            record = {
                'pair': pair, 'entry_time': pos['entry_time'],
                'close_time': datetime.now().isoformat(), 'direction': direction,
                'entry': entry, 'exit': real_price, 'pnl_pct': pnl_pct,
                'size_pct': size_pct, 'reason': reason
            }
            closed.append(record)
            log_closed_trade(record)
            del positions[pair]
        else:
            positions[pair]['current_pnl_pct'] = pnl_pct

    save_positions(positions)
    return closed

def simulate_entry(pair, direction, entry, exit_, size_pct):
    positions = load_positions()
    open_count = sum(1 for p in positions.values() if p.get('pair') == pair)
    if open_count >= MAX_OPEN_PER_PAIR:
        return
    total_exposure = sum(p.get('size_pct', 0) for p in positions.values()) + size_pct
    if total_exposure > MAX_TOTAL_EXPOSURE_PCT:
        return
    positions[pair] = {
        'pair': pair, 'direction': direction, 'entry': entry, 'target': exit_,
        'stop': entry * (1 - 0.025) if direction == "BUY" else entry * (1 + 0.025),
        'entry_time': datetime.now().isoformat(), 'size_pct': size_pct, 'current_pnl_pct': 0.0
    }
    save_positions(positions)

# ──────────────────────────────────────────────
# DRAWDOWN CIRCUIT BREAKER
# ──────────────────────────────────────────────
def check_drawdown_circuit_breaker() -> dict:
    """
    Computes current portfolio drawdown from closed paper trades (SQLite).
    If drawdown exceeds DRAWDOWN_CIRCUIT_BREAKER_PCT, returns TRIGGERED status
    that run_scan() uses to downgrade BUY/SELL signals to NEUTRAL.

    Returns:
        {'triggered': bool, 'drawdown_pct': float, 'threshold_pct': float, 'peak_equity': float}
    """
    return _db.check_drawdown_circuit_breaker(PORTFOLIO_SIZE_USD, DRAWDOWN_CIRCUIT_BREAKER_PCT)


# ──────────────────────────────────────────────
# EXCHANGE HELPERS
# ──────────────────────────────────────────────
def get_exchange_instance(name='kraken'):
    try:
        ex_class = getattr(ccxt, name)
        ex = ex_class({'enableRateLimit': True, 'timeout': 15000})
        ex.load_markets()
        return ex
    except Exception as e:
        logging.warning(f"Exchange {name} failed: {str(e)[:60]}")
        return None

def robust_fetch_ticker(ex, pair):
    try:
        t = ex.fetch_ticker(pair)
        return {'ask': t.get('ask'), 'bid': t.get('bid'), 'last': t.get('last')}
    except Exception:
        return None

def robust_fetch_ohlcv(ex, pair, timeframe, limit=None):
    if limit is None:
        limit = OHLCV_LIMIT
    try:
        ohlcv = ex.fetch_ohlcv(pair, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logging.warning(f"OHLCV failed {pair} {timeframe}: {str(e)[:60]}")
        return pd.DataFrame()

# ──────────────────────────────────────────────
# PHASE 1: FEAR & GREED
# ──────────────────────────────────────────────
def fetch_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.status_code != 200:
            logging.warning(f"Fear & Greed API returned HTTP {r.status_code}")
            return 50, "Neutral"
        data = r.json()['data'][0]
        return int(data['value']), data['value_classification']
    except Exception as e:
        logging.warning(f"Fear & Greed fetch failed: {e}")
        return 50, "Neutral"

# ──────────────────────────────────────────────
# PHASE 2: ON-CHAIN METRICS (real — CoinGecko free API)
# ──────────────────────────────────────────────
def fetch_onchain_metrics(pair='BTC/USDT'):
    """Fetch real on-chain proxy metrics via CoinGecko. Falls back to neutral values on failure."""
    try:
        import data_feeds as _df
        return _df.get_onchain_metrics(pair)
    except Exception:
        return {'sopr': 1.0, 'mvrv_z': 0.0, 'net_flow': 0.0, 'whale_activity': False, 'source': 'fallback'}

def get_onchain_bias(sopr, mvrv_z, net_flow, whale_activity, adx, **kwargs):
    bias = 0.0
    if sopr > 1.05: bias += 10
    if sopr < 0.95: bias -= 12
    if mvrv_z > 3.5: bias -= 15
    if mvrv_z < -0.5: bias += 18
    if net_flow > 150: bias -= 12
    if net_flow < -150: bias += 15
    if whale_activity: bias += 20
    if mvrv_z > 7 or net_flow > 500: bias -= 25
    return round(bias, 1)

# ──────────────────────────────────────────────
# PHASE 3: MULTI-AGENT VOTING
# ──────────────────────────────────────────────
def agent_vote_trend(adx, supertrend_up, macd_line, macd_signal_val):
    score = 0
    if adx > 35:
        score += 40 if supertrend_up == (macd_line > macd_signal_val) else -40
    elif adx > 25:
        score += 20 if macd_line > macd_signal_val else -20
    reason = f"Trend: ADX {adx:.1f}, ST {'Up' if supertrend_up else 'Dn'}, MACD {'Bull' if macd_line > macd_signal_val else 'Bear'}"
    return round(score, 1), reason

def agent_vote_momentum(rsi, stoch_k, stoch_d, hist, prev_hist):
    score = 0
    if rsi < 35: score += 35
    if rsi > 65: score -= 35
    if stoch_k < 25 and stoch_k > stoch_d: score += 25
    if stoch_k > 75 and stoch_k < stoch_d: score -= 25
    if hist > 0 and hist > prev_hist: score += 20
    if hist < 0 and hist < prev_hist: score -= 20
    reason = f"Momentum: RSI {rsi:.1f}, Stoch {stoch_k:.1f}/{stoch_d:.1f}"
    return round(score, 1), reason

def agent_vote_meanrev(bb_pos, fib_closest, rsi, regime):
    score = 0
    if regime == "Ranging":
        if bb_pos < 0.2 and rsi < 35: score += 45
        if bb_pos > 0.8 and rsi > 65: score -= 45
    if fib_closest in ['61.8%', '78.6%'] and rsi < 40: score += 30
    if fib_closest in ['23.6%', '38.2%'] and rsi > 60: score -= 30
    reason = f"MeanRev: BB {bb_pos:.2f}, Fib {fib_closest}, {regime}"
    return round(score, 1), reason

def agent_vote_sentiment(fng_value, fng_category, onchain_bias):
    score = 0
    if fng_value < 25: score += 35
    elif fng_value < 45: score += 15
    elif fng_value > 75: score -= 35
    elif fng_value > 55: score -= 15
    score += onchain_bias * 0.8
    reason = f"Sentiment: F&G {fng_value} ({fng_category}), Onchain {onchain_bias:.1f}"
    return round(score, 1), reason

def agent_vote_risk(adx, atr_val, corr_value, position_pct):
    score = 0
    if adx < 20: score -= 25
    if position_pct > 60: score -= 20
    if corr_value and corr_value > 0.9: score -= 15
    reason = f"Risk: ADX {adx:.1f}, Corr {corr_value or 'N/A'}, Pos {position_pct}%"
    return round(score, 1), reason


# ── T2-B: HMM Regime Detection ─────────────────────────────────────────────
def detect_hmm_regime(df) -> str:
    """3-state Gaussian HMM regime detection with multi-dimensional features.

    Features (3D): [log_return, rolling_volatility_20, rolling_trend_strength_20]
    - log_return:        daily price change direction
    - volatility:        20-bar rolling std of log-returns (regime intensity)
    - trend_strength:    |20-bar EMA slope| / price (normalized directional momentum)

    State labeling: states sorted by (mean_return, -volatility):
      - High return + high vol → Trending (strong directional move)
      - Low return + high vol  → Ranging  (choppy/bearish)
      - Low return + low vol   → Neutral  (consolidation/sideways)

    Regime smoothing: uses majority vote over last 3 bars to reduce whipsaws.
    Falls back to ADX-based detection if hmmlearn unavailable or < 80 bars.
    Returns: 'Trending', 'Ranging', 'Neutral', or None (caller uses ADX fallback).
    """
    try:
        from hmmlearn.hmm import GaussianHMM
        min_bars = 80
        if len(df) < min_bars:
            return None

        close = df['close'].values.astype(np.float64)
        log_ret = np.log(close[1:] / np.maximum(close[:-1], 1e-10))

        if len(log_ret) < min_bars - 1:
            return None

        # Rolling 20-bar volatility (std of log-returns)
        roll = 20
        vol = np.array([
            log_ret[max(0, i - roll): i + 1].std() if i >= roll - 1 else np.nan
            for i in range(len(log_ret))
        ])

        # Rolling 20-bar EMA slope / price (normalized trend strength)
        ema = pd.Series(close[1:]).ewm(span=roll, adjust=False).mean().values
        ema_slope = np.gradient(ema) / np.maximum(ema, 1e-10)

        # Stack features; trim NaN warmup period
        start = roll
        X = np.column_stack([
            log_ret[start:],
            vol[start:],
            np.abs(ema_slope[start:]),
        ]).astype(np.float64)

        if len(X) < 40 or np.isnan(X).any():
            return None

        # BUG-R22: covariance_floor renamed from min_covar in hmmlearn >= 0.3.0
        try:
            model = GaussianHMM(n_components=3, covariance_type='diag', n_iter=80,
                                random_state=42, covariance_floor=1e-6)
        except TypeError:
            model = GaussianHMM(n_components=3, covariance_type='diag', n_iter=80,
                                random_state=42)

        model.fit(X)
        states = model.predict(X)

        # Characterize states by (mean_return, mean_volatility) for labeling
        state_props = {}
        for s in range(3):
            mask = states == s
            if mask.sum() < 3:
                state_props[s] = (0.0, 0.0)
                continue
            state_props[s] = (float(X[mask, 0].mean()), float(X[mask, 1].mean()))

        # BUG-LOG02: sort by (mean_return ASC, volatility DESC) for deterministic tie-breaking
        # Trending: highest return; Ranging: lowest return (or highest vol when tied); Neutral: remainder
        sorted_by_ret = sorted(state_props, key=lambda s: (state_props[s][0], -state_props[s][1]))
        bear_state = sorted_by_ret[0]    # most negative return = Ranging/bearish
        bull_state = sorted_by_ret[-1]   # most positive return = Trending/bullish
        sidew_states = [s for s in range(3) if s != bull_state and s != bear_state]
        sidew_state = sidew_states[0] if sidew_states else bull_state

        # Smoothing: majority vote over last 3 bars to reduce false regime switches
        recent = states[-3:] if len(states) >= 3 else states[-1:]
        from collections import Counter
        smoothed_state = Counter(recent.tolist()).most_common(1)[0][0]

        if smoothed_state == bull_state:
            return "Trending"
        elif smoothed_state == bear_state:
            return "Ranging"
        else:
            return "Neutral"

    except ImportError:
        return None
    except Exception as _hmm_exc:
        logging.debug(f"[HMM] regime detection failed: {_hmm_exc}")
        return None


# ── T3-A: LightGBM Signal Agent ────────────────────────────────────────────
def agent_vote_lgbm(df, hold_bars: int = 5):
    """
    6th ensemble agent: LightGBM classifier trained on indicator features vs
    actual trade outcomes from resolved feedback_log (F-RETRAIN), falling back
    to in-sample OHLCV training when no feedback model is available.
    Returns (score: float in [-100, 100], reason: str).
    score > 0 → bullish, score < 0 → bearish, score ≈ 0 → no edge.
    """
    try:
        import lightgbm as lgb
        if len(df) < 100 or 'rsi' not in df.columns:
            return 0.0, "LightGBM: insufficient data"

        # F-RETRAIN: Use feedback-trained model if available (out-of-sample, real outcomes)
        feedback_model = get_lgbm_feedback_model()
        if feedback_model is not None:
            try:
                close = df['close'].values
                bbu = df['bb_upper'].values
                bbl = df['bb_lower'].values
                rsi_v = df['rsi'].values
                hist_v = df['macd_hist'].values
                sk_v = df['stoch_k'].values
                bb_pos_last = (close[-1] - bbl[-1]) / (bbu[-1] - bbl[-1] + 1e-6)
                x_last = np.array([[
                    rsi_v[-1] / 100.0,
                    float(hist_v[-1]),
                    float(np.clip(bb_pos_last, 0.0, 1.0)),
                    float(df['adx'].iloc[-1]) if 'adx' in df.columns else 25.0,
                    sk_v[-1] / 100.0,
                ]], dtype=np.float32)
                prob_buy = float(feedback_model.predict_proba(x_last)[0][1])
                score = (prob_buy - 0.5) * 200
                return round(score, 1), f"LightGBM(feedback): P(win)={prob_buy:.2f}"
            except Exception:
                pass  # Fall through to in-sample training

        close = df['close'].values
        bbu = df['bb_upper'].values
        bbl = df['bb_lower'].values
        rsi_v = df['rsi'].values
        hist_v = df['macd_hist'].values
        sk_v = df['stoch_k'].values
        sd_v = df['stoch_d'].values

        X_rows, y_rows = [], []
        for i in range(60, len(df) - hold_bars):
            if np.isnan(rsi_v[i]) or np.isnan(hist_v[i]):
                continue
            bb_pos = (close[i] - bbl[i]) / (bbu[i] - bbl[i] + 1e-6)
            X_rows.append([
                rsi_v[i] / 100.0,
                np.clip(bb_pos, 0.0, 1.0),
                hist_v[i] / (abs(close[i]) + 1e-6),
                sk_v[i] / 100.0,
                sd_v[i] / 100.0,
            ])
            future_ret = (close[i + hold_bars] - close[i]) / (close[i] + 1e-6)
            y_rows.append(1 if future_ret > 0.001 else 0)

        if len(X_rows) < 30 or len(set(y_rows)) < 2:
            return 0.0, "LightGBM: insufficient training samples"

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_rows, dtype=np.int32)
        model = lgb.LGBMClassifier(
            n_estimators=30, learning_rate=0.1, max_depth=3,
            num_leaves=15, verbose=-1, random_state=42, n_jobs=1,
        )
        model.fit(X, y)

        # Predict on latest bar
        bb_pos_last = (close[-1] - bbl[-1]) / (bbu[-1] - bbl[-1] + 1e-6)
        x_last = np.array([[
            rsi_v[-1] / 100.0,
            np.clip(bb_pos_last, 0.0, 1.0),
            hist_v[-1] / (abs(close[-1]) + 1e-6),
            sk_v[-1] / 100.0,
            sd_v[-1] / 100.0,
        ]], dtype=np.float32)

        prob_buy = float(model.predict_proba(x_last)[0][1])
        # Map [0,1] probability → [-100, +100] vote
        score = (prob_buy - 0.5) * 200
        reason = f"LightGBM: P(up)={prob_buy:.2f}"
        return round(score, 1), reason

    except ImportError:
        return 0.0, "LightGBM: not installed (pip install lightgbm)"
    except Exception as e:
        logging.debug(f"LightGBM agent failed: {e}")
        return 0.0, "LightGBM: error"


# ──────────────────────────────────────────────
# LIGHTGBM FEEDBACK-RETRAINED MODEL (F-RETRAIN)
# ──────────────────────────────────────────────
# Module-level cache: {model: lgb.LGBMClassifier, trained_at: str, n_samples: int}
_lgbm_feedback_cache: dict = {"model": None, "trained_at": None, "n_samples": 0}
_lgbm_feedback_lock = threading.Lock()


def retrain_lgbm_from_feedback(min_samples: int = 50) -> dict:
    """Retrain LightGBM using RESOLVED feedback outcomes + stored indicator snapshots.

    This replaces pure OHLCV in-sample training with real trade outcomes (was_correct),
    converting the LightGBM agent from an in-sample price predictor to an out-of-sample
    signal quality predictor.

    Features used: snap_rsi, snap_macd_hist, snap_bb_pos, snap_adx, snap_stoch_k
    Label: was_correct (1=signal won, 0=signal lost)

    The trained model is cached in _lgbm_feedback_cache and used by agent_vote_lgbm()
    when the cache is fresh (trained within the last 24h).

    Args:
        min_samples: Minimum resolved rows required to retrain (default 50).

    Returns:
        dict: {success, n_samples, accuracy, trained_at, message}
    """
    try:
        import lightgbm as lgb
    except ImportError:
        return {"success": False, "message": "lightgbm not installed"}

    try:
        df_fb = _db.get_resolved_feedback_df(days=90)
        # Filter to rows with all required snapshot columns
        snap_cols = ['snap_rsi', 'snap_macd_hist', 'snap_bb_pos', 'snap_adx', 'snap_stoch_k']
        required = snap_cols + ['was_correct']
        for col in required:
            if col not in df_fb.columns:
                return {"success": False, "message": f"Missing column: {col} — run new scans to populate snapshots"}

        df_valid = df_fb[required].dropna()
        if len(df_valid) < min_samples:
            return {
                "success": False,
                "message": f"Only {len(df_valid)} rows with snapshots (need {min_samples}). Run more scans.",
                "n_samples": len(df_valid),
            }

        X = df_valid[snap_cols].values.astype(np.float32)
        y = df_valid['was_correct'].values.astype(np.int32)

        if len(set(y)) < 2:
            return {"success": False, "message": "Only one class in labels — need both wins and losses"}

        # 80/20 time-based split (no shuffling — preserves temporal order)
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        model = lgb.LGBMClassifier(
            n_estimators=100, learning_rate=0.05, max_depth=4,
            num_leaves=20, min_child_samples=10, subsample=0.8,
            colsample_bytree=0.8, verbose=-1, random_state=42, n_jobs=1,
            class_weight='balanced',
        )
        model.fit(X_train, y_train,
                  eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(15, verbose=False),
                              lgb.log_evaluation(-1)])

        val_acc = float((model.predict(X_val) == y_val).mean()) if len(X_val) > 0 else float('nan')
        trained_at = datetime.now(timezone.utc).isoformat()

        with _lgbm_feedback_lock:
            _lgbm_feedback_cache["model"] = model
            _lgbm_feedback_cache["trained_at"] = trained_at
            _lgbm_feedback_cache["n_samples"] = len(df_valid)

        logging.info(f"LightGBM feedback retrain: {len(df_valid)} samples, val_acc={val_acc:.3f}")
        return {
            "success": True,
            "n_samples": len(df_valid),
            "accuracy": round(val_acc, 4),
            "trained_at": trained_at,
            "message": f"Retrained on {len(df_valid)} resolved signals (val acc: {val_acc:.1%})",
        }

    except Exception as e:
        logging.warning(f"retrain_lgbm_from_feedback failed: {e}")
        return {"success": False, "message": str(e)}


def get_lgbm_feedback_model():
    """Return cached feedback-trained model if fresh (within 24h), else None."""
    with _lgbm_feedback_lock:
        m = _lgbm_feedback_cache.get("model")
        trained_at = _lgbm_feedback_cache.get("trained_at")
    if m is None or trained_at is None:
        return None
    try:
        age_hours = (datetime.now(timezone.utc) - datetime.fromisoformat(trained_at)).total_seconds() / 3600
        return m if age_hours < 24.0 else None
    except Exception:
        return None


def get_lgbm_feedback_cache_info() -> dict:
    """Return info about the current LightGBM feedback model cache for UI display."""
    with _lgbm_feedback_lock:
        return {
            "has_model":   _lgbm_feedback_cache.get("model") is not None,
            "trained_at":  _lgbm_feedback_cache.get("trained_at"),
            "n_samples":   _lgbm_feedback_cache.get("n_samples", 0),
        }


def multi_agent_vote(df, fng_value, fng_category, onchain_data, adx, atr_val, corr_value, position_pct):
    """Run all agent votes and return ensemble result.

    Returns:
        (final_vote, reasons, consensus, votes_dict)
        votes_dict: {'trend': v, 'momentum': v, 'meanrev': v, 'sentiment': v, 'risk': v, 'lgbm': v}
        Used by F4 to store per-agent votes in feedback_log for rolling accuracy tracking.
    """
    _empty = {'trend': 0.0, 'momentum': 0.0, 'meanrev': 0.0, 'sentiment': 0.0, 'risk': 0.0, 'lgbm': 0.0}
    if df is None or len(df) < 50:
        return 0.0, ["No data"], 0.0, _empty
    if onchain_data is None:
        onchain_data = fetch_onchain_metrics()
    try:
        rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else 50
        macd_line = df['macd'].iloc[-1] if 'macd' in df.columns else 0
        macd_sig = df['macd_signal'].iloc[-1] if 'macd_signal' in df.columns else 0
        hist = df['macd_hist'].iloc[-1] if 'macd_hist' in df.columns else 0
        prev_hist = df['macd_hist'].iloc[-2] if 'macd_hist' in df.columns and len(df) > 1 else hist
        stoch_k = df['stoch_k'].iloc[-1] if 'stoch_k' in df.columns else 50
        stoch_d = df['stoch_d'].iloc[-1] if 'stoch_d' in df.columns else 50
        bb_upper = df['bb_upper'].iloc[-1] if 'bb_upper' in df.columns else df['close'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1] if 'bb_lower' in df.columns else df['close'].iloc[-1]
        bb_pos = (df['close'].iloc[-1] - bb_lower) / (bb_upper - bb_lower + 1e-6)
        fib_closest, _ = compute_fib_levels(df)
        supertrend_up = compute_supertrend(df) == "Uptrend"
        regime = "Ranging" if adx < ADX_RANGE_THRESHOLD else "Trending" if adx > ADX_TREND_THRESHOLD else "Neutral"
        onchain_bias = get_onchain_bias(**onchain_data, adx=adx)

        # F4: Get 30-day rolling accuracy weights (cached once per scan — PERF-06)
        with _weights_lock:
            agent_accuracy = _agent_acc_cache["value"] if _agent_acc_cache["valid"] else None
        if agent_accuracy is None:
            agent_accuracy = _db.get_agent_accuracy_weights(days=30)

        named_agents = [
            ('trend',     agent_vote_trend,     (adx, supertrend_up, macd_line, macd_sig)),
            ('momentum',  agent_vote_momentum,  (rsi, stoch_k, stoch_d, hist, prev_hist)),
            ('meanrev',   agent_vote_meanrev,   (bb_pos, fib_closest, rsi, regime)),
            ('sentiment', agent_vote_sentiment, (fng_value, fng_category, onchain_bias)),
            ('risk',      agent_vote_risk,      (adx, atr_val, corr_value, position_pct)),
        ]

        votes = []
        reasons = []
        vote_weights = []
        votes_dict = {}
        for name, fn, args in named_agents:
            s, r = fn(*args)
            votes.append(s)
            reasons.append(r)
            # F4: use rolling accuracy as weight; default 0.5 = equal weight
            vote_weights.append(max(0.1, agent_accuracy.get(name, 0.5)))
            votes_dict[name] = round(float(s), 1)

        # T3-A: LightGBM 6th agent (omit if df not enriched or too small)
        lgbm_score, lgbm_reason = agent_vote_lgbm(df)
        votes_dict['lgbm'] = round(float(lgbm_score), 1)
        if lgbm_score != 0.0:
            votes.append(lgbm_score)
            reasons.append(lgbm_reason)
            vote_weights.append(max(0.1, agent_accuracy.get('lgbm', 0.5)))

        # F4: accuracy-weighted average — agents that have been more directionally accurate
        # over the last 30 days get more influence; falls back to equal weighting when
        # insufficient resolved data (all weights = 0.5, so np.average == np.mean)
        final_vote = round(float(np.average(votes, weights=vote_weights)), 1)
        consensus = len([v for v in votes if abs(v) > 70]) / len(votes) if votes else 0.0
        return final_vote, reasons, consensus, votes_dict
    except Exception as e:
        logging.warning(f"Multi-agent vote failed: {e}")
        return 0.0, [], 0.0, _empty

# ──────────────────────────────────────────────
# TECHNICAL INDICATORS
# ──────────────────────────────────────────────
def compute_rsi(series, period=14):
    if len(series) < period:
        return 50.0
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    prev_hist = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1]), float(prev_hist)

def compute_bollinger(series, window=20, std_mult=2):
    mid = series.rolling(window).mean()
    std = series.rolling(window).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return float(mid.iloc[-1]), float(upper.iloc[-1]), float(lower.iloc[-1])

def compute_stochastic(df, k_period=14, d_period=3):
    low_min = df['low'].rolling(k_period).min()
    high_max = df['high'].rolling(k_period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min + 1e-6)
    d = k.rolling(d_period).mean()
    return float(k.iloc[-1]), float(d.iloc[-1])

def compute_atr(df, period=14):
    tr = pd.concat([df['high'] - df['low'],
                    abs(df['high'] - df['close'].shift()),
                    abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    return tr.rolling(period).mean()  # Returns Series for SuperTrend; use .iloc[-1] for scalars

def compute_supertrend(df, period=10, multiplier=3.0):
    if len(df) < period:
        return "N/A"
    atr_series = compute_atr(df, period)
    hl2 = (df['high'] + df['low']) / 2
    upper_band = hl2 + multiplier * atr_series
    lower_band = hl2 - multiplier * atr_series
    in_uptrend = pd.array([True] * len(df), dtype=bool)
    ub = upper_band.values.copy()
    lb = lower_band.values.copy()
    close_vals = df['close'].values
    for i in range(1, len(df)):
        if close_vals[i - 1] > ub[i - 1]:
            in_uptrend[i] = True
        elif close_vals[i - 1] < lb[i - 1]:
            in_uptrend[i] = False
        else:
            in_uptrend[i] = in_uptrend[i - 1]
            if in_uptrend[i]:
                lb[i] = max(lb[i], lb[i - 1])
            else:
                ub[i] = min(ub[i], ub[i - 1])
    return "Uptrend" if in_uptrend[-1] else "Downtrend"

def compute_vwap(df):
    typical = (df['high'] + df['low'] + df['close']) / 3
    return (typical * df['volume']).cumsum() / df['volume'].cumsum().replace(0, np.nan)

def compute_ichimoku(df, tenkan=9, kijun=26, senkou=52):
    tenkan_sen = (df['high'].rolling(tenkan).max() + df['low'].rolling(tenkan).min()) / 2
    kijun_sen = (df['high'].rolling(kijun).max() + df['low'].rolling(kijun).min()) / 2
    senkou_a = (tenkan_sen + kijun_sen) / 2
    senkou_b = (df['high'].rolling(senkou).max() + df['low'].rolling(senkou).min()) / 2
    return tenkan_sen, kijun_sen, senkou_a, senkou_b

def compute_fib_levels(df):
    high = df['high'].max()
    low = df['low'].min()
    diff = high - low
    # Guard: flat price action — all fib levels collapse to the same value
    if diff == 0 or not (high > 0 and low > 0):
        mid = float(df['close'].iloc[-1])
        return '50.0%', mid
    levels = {
        '23.6%': high - 0.236 * diff, '38.2%': high - 0.382 * diff,
        '50.0%': high - 0.5 * diff,   '61.8%': high - 0.618 * diff,
        '78.6%': high - 0.786 * diff
    }
    price = df['close'].iloc[-1]
    closest = min(levels, key=lambda k: abs(levels[k] - price))
    return closest, levels[closest]

def compute_adx(df, period=14):
    tr = pd.concat([df['high'] - df['low'],
                    abs(df['high'] - df['close'].shift()),
                    abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    up = df['high'] - df['high'].shift()
    down = df['low'].shift() - df['low']
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-6)
    result = dx.rolling(period).mean()
    val = result.iloc[-1]
    return float(val) if not pd.isna(val) else 20.0

def compute_support_resistance(df, lookback=20):
    if len(df) < lookback:
        return None, None, "N/A", "N/A"
    recent = df.tail(lookback)
    pivot = (recent['high'] + recent['low'] + recent['close']) / 3
    resistance = pivot.mean() + (pivot.mean() - recent['low'].min())
    support = pivot.mean() - (recent['high'].max() - pivot.mean())
    price = df['close'].iloc[-1]
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    cur_vol = df['volume'].iloc[-1]
    breakout = "No Breakout"
    if price > resistance and cur_vol > VOLUME_BREAKOUT_MULTIPLIER * vol_avg:
        breakout = "Bullish Breakout"
    elif price < support and cur_vol > VOLUME_BREAKOUT_MULTIPLIER * vol_avg:
        breakout = "Bearish Breakout"
    sr_status = ("Near Resistance" if abs(price - resistance) < 0.01 * price else
                 "Near Support" if abs(price - support) < 0.01 * price else "Away from S/R")
    return float(support), float(resistance), breakout, sr_status

def detect_macd_divergence_improved(df):
    if 'macd' not in df.columns or len(df) < 10:
        return "None", "N/A"
    macd = df['macd'].iloc[-100:]
    price = df['close'].iloc[-100:]
    peaks_macd = (macd.shift(1) < macd) & (macd.shift(-1) < macd)
    troughs_macd = (macd.shift(1) > macd) & (macd.shift(-1) > macd)
    peaks_price = (price.shift(1) < price) & (price.shift(-1) < price)
    troughs_price = (price.shift(1) > price) & (price.shift(-1) > price)
    lpm = macd[peaks_macd].tail(3)
    ltm = macd[troughs_macd].tail(3)
    lpp = price[peaks_price].tail(3)
    ltp = price[troughs_price].tail(3)
    if len(lpm) >= 2 and len(lpp) >= 2:
        if lpp.iloc[-1] > lpp.iloc[-2] and lpm.iloc[-1] < lpm.iloc[-2]:
            return "Bearish (regular)", "Strong" if abs(lpm.iloc[-1] - lpm.iloc[-2]) > 0.5 * lpm.std() else "Mild"
        if lpp.iloc[-1] < lpp.iloc[-2] and lpm.iloc[-1] > lpm.iloc[-2]:
            return "Bearish (hidden)", "Strong" if abs(lpm.iloc[-1] - lpm.iloc[-2]) > 0.5 * lpm.std() else "Mild"
    if len(ltm) >= 2 and len(ltp) >= 2:
        if ltp.iloc[-1] < ltp.iloc[-2] and ltm.iloc[-1] > ltm.iloc[-2]:
            return "Bullish (regular)", "Strong" if abs(ltm.iloc[-1] - ltm.iloc[-2]) > 0.5 * ltm.std() else "Mild"
        if ltp.iloc[-1] > ltp.iloc[-2] and ltm.iloc[-1] < ltm.iloc[-2]:
            return "Bullish (hidden)", "Strong" if abs(ltm.iloc[-1] - ltm.iloc[-2]) > 0.5 * ltm.std() else "Mild"
    return "None", "N/A"

# ──────────────────────────────────────────────
# PHASE 4: STATISTICAL ARBITRAGE
# ──────────────────────────────────────────────
def compute_cointegration_zscore(df1, df2, lookback=STAT_ARB_LOOKBACK):
    if len(df1) < lookback or len(df2) < lookback:
        return 0.0, "NEUTRAL"
    try:
        p1 = df1['close'].tail(lookback)
        p2 = df2['close'].tail(lookback)
        _, pvalue, _ = coint(p1, p2)
        if pvalue > 0.05:
            return 0.0, "NEUTRAL"
        ratio = p1.values / p2.values
        mean_r = ratio.mean()
        std_r = ratio.std()
        z = (ratio[-1] - mean_r) / std_r if std_r != 0 else 0.0
        if z > STAT_ARB_Z_THRESHOLD: return z, "SHORT_SPREAD"
        elif z < -STAT_ARB_Z_THRESHOLD: return z, "LONG_SPREAD"
        elif abs(z) < STAT_ARB_Z_EXIT: return z, "EXIT_SPREAD"
        return z, "NEUTRAL"
    except Exception as e:
        logging.debug(f"Cointegration z-score failed: {e}")
        return 0.0, "NEUTRAL"

def get_stat_arb_bias(z_score, signal):
    if signal == "LONG_SPREAD": return 20.0
    if signal == "SHORT_SPREAD": return -20.0
    return 0.0

# ──────────────────────────────────────────────
# CANDLESTICK PATTERN DETECTION
# ──────────────────────────────────────────────
def detect_candlestick_patterns(df: pd.DataFrame) -> tuple:
    """
    Detect 10 key candlestick patterns on the last 3 candles.
    Returns (pattern_names: list[str], net_score: int)
    Positive score = bullish pressure, negative = bearish.
    """
    if len(df) < 5:
        return [], 0

    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values
    i = len(df) - 1

    body      = abs(c[i] - o[i])
    rng       = h[i] - l[i]
    if rng == 0:
        return [], 0

    upper_wick  = h[i] - max(c[i], o[i])
    lower_wick  = min(c[i], o[i]) - l[i]
    body_pct    = body / rng
    is_green    = c[i] > o[i]

    patterns = []
    score = 0

    # Doji (indecision)
    if body_pct < 0.1:
        patterns.append("Doji")

    # Hammer — small body top, long lower wick (bullish)
    if (is_green and lower_wick >= 2 * body and upper_wick <= 0.3 * body and body_pct < 0.4):
        patterns.append("Hammer"); score += 4

    # Inverted Hammer — small body bottom, long upper wick (bullish after down)
    if (is_green and upper_wick >= 2 * body and lower_wick <= 0.3 * body and body_pct < 0.4):
        patterns.append("Inv Hammer"); score += 3

    # Shooting Star — small body bottom, long upper wick (bearish after up)
    if (not is_green and upper_wick >= 2 * body and lower_wick <= 0.3 * body and body_pct < 0.4):
        patterns.append("Shooting Star"); score -= 4

    # Hanging Man — small body top, long lower wick (bearish after up)
    if (not is_green and lower_wick >= 2 * body and upper_wick <= 0.3 * body and body_pct < 0.4):
        patterns.append("Hanging Man"); score -= 3

    # Marubozu Bull — large green body, tiny wicks
    if (is_green and body_pct > 0.85 and upper_wick < 0.05 * body and lower_wick < 0.05 * body):
        patterns.append("Marubozu Bull"); score += 5

    # Marubozu Bear — large red body, tiny wicks
    if (not is_green and body_pct > 0.85 and upper_wick < 0.05 * body and lower_wick < 0.05 * body):
        patterns.append("Marubozu Bear"); score -= 5

    if i >= 1:
        pb = abs(c[i-1] - o[i-1])
        prev_green = c[i-1] > o[i-1]
        if pb > 0:
            # Bullish Engulfing
            if (not prev_green and is_green and
                    c[i] > o[i-1] and o[i] < c[i-1] and body > pb):
                patterns.append("Bull Engulfing"); score += 5

            # Bearish Engulfing
            if (prev_green and not is_green and
                    c[i] < o[i-1] and o[i] > c[i-1] and body > pb):
                patterns.append("Bear Engulfing"); score -= 5

            # Bullish Harami
            if (not prev_green and is_green and
                    c[i] < o[i-1] and o[i] > c[i-1]):
                patterns.append("Bull Harami"); score += 3

            # Bearish Harami
            if (prev_green and not is_green and
                    c[i] > o[i-1] and o[i] < c[i-1]):
                patterns.append("Bear Harami"); score -= 3

    if i >= 2:
        b1 = abs(c[i-2] - o[i-2])
        b2 = abs(c[i-1] - o[i-1])
        if b1 > 0:
            # Morning Star (3-candle bullish reversal)
            if (c[i-2] < o[i-2] and b2 < 0.3 * b1 and
                    is_green and c[i] > (o[i-2] + c[i-2]) / 2):
                patterns.append("Morning Star"); score += 6

            # Evening Star (3-candle bearish reversal)
            if (c[i-2] > o[i-2] and b2 < 0.3 * b1 and
                    not is_green and c[i] < (o[i-2] + c[i-2]) / 2):
                patterns.append("Evening Star"); score -= 6

            # Three White Soldiers (3 consecutive green closes)
            if (c[i-2] > o[i-2] and c[i-1] > o[i-1] and is_green and
                    c[i] > c[i-1] > c[i-2]):
                patterns.append("3 White Soldiers"); score += 6

            # Three Black Crows
            if (c[i-2] < o[i-2] and c[i-1] < o[i-1] and not is_green and
                    c[i] < c[i-1] < c[i-2]):
                patterns.append("3 Black Crows"); score -= 6

    return patterns, score


# ──────────────────────────────────────────────
# INDICATOR ENRICHMENT HELPER
# ──────────────────────────────────────────────
def _enrich_df(df):
    """Add all indicator columns to a df copy. Required before signal calculation."""
    df = df.copy()
    # MACD
    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss.replace(0, 1e-10)))
    df['rsi'] = df['rsi'].fillna(50)  # BUG-DC01: NaN during 14-bar warmup → neutral 50
    # Bollinger
    df['bb_mid'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    # Stochastic
    lmin = df['low'].rolling(14).min()
    hmax = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - lmin) / (hmax - lmin + 1e-6)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    # VWAP
    typical = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (typical * df['volume']).cumsum() / df['volume'].cumsum().replace(0, np.nan)
    # Ichimoku
    df['tenkan_sen'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun_sen'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    df['senkou_span_a'] = (df['tenkan_sen'] + df['kijun_sen']) / 2
    df['senkou_span_b'] = (df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2
    # ATR + ADX (PERF-07 / BUG-R26: compute TR once, derive both ATR and ADX from it so
    # calculate_signal_confidence reads df['atr'] and df['adx'] without re-computing)
    _tr = pd.concat([df['high'] - df['low'],
                     (df['high'] - df['close'].shift()).abs(),
                     (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
    _atr = _tr.rolling(14).mean()
    df['atr'] = _atr  # PERF-07: was missing — caused fallback compute_atr() on every signal calc
    _up   = df['high'] - df['high'].shift()
    _down = df['low'].shift() - df['low']
    _pdm  = pd.Series(np.where((_up > _down) & (_up > 0), _up, 0), index=df.index)
    _mdm  = pd.Series(np.where((_down > _up) & (_down > 0), _down, 0), index=df.index)
    _pdi  = 100 * _pdm.rolling(14).mean() / _atr
    _mdi  = 100 * _mdm.rolling(14).mean() / _atr
    _dx   = 100 * (_pdi - _mdi).abs() / (_pdi + _mdi + 1e-6)
    df['adx'] = _dx.rolling(14).mean().fillna(20.0)
    return df

# ──────────────────────────────────────────────
# SIGNAL CALCULATION
# ──────────────────────────────────────────────
def calculate_signal_confidence(df, tf, fng_value=50, fng_category="Neutral",
                                 onchain_data=None, pair='', corr_value=None, position_pct=0,
                                 iv_data=None, ob_data=None, btc_df=None, cvd_data=None):
    if df is None or len(df) < 50:
        return 0, False, "None", "N/A", "N/A", "N/A", "N/A", "Balanced", 0.0, 0.0, "NEUTRAL", {}
    if onchain_data is None:
        onchain_data = fetch_onchain_metrics()
    try:
        w = _get_weights()  # thread-safe snapshot — parallel workers each get their own copy
        # Skip re-enrichment if _scan_pair already enriched this df (PERF-01)
        if 'rsi' not in df.columns:
            df = _enrich_df(df)
        price = df['close'].iloc[-1]
        rsi = float(df['rsi'].iloc[-1]) if not pd.isna(df['rsi'].iloc[-1]) else 50.0
        macd_line = float(df['macd'].iloc[-1]) if not pd.isna(df['macd'].iloc[-1]) else 0.0
        macd_sig  = float(df['macd_signal'].iloc[-1]) if not pd.isna(df['macd_signal'].iloc[-1]) else 0.0
        hist      = float(df['macd_hist'].iloc[-1]) if not pd.isna(df['macd_hist'].iloc[-1]) else 0.0
        prev_hist = float(df['macd_hist'].iloc[-2]) if len(df) > 1 and not pd.isna(df['macd_hist'].iloc[-2]) else hist
        bb_upper  = float(df['bb_upper'].iloc[-1]) if not pd.isna(df['bb_upper'].iloc[-1]) else price
        bb_lower  = float(df['bb_lower'].iloc[-1]) if not pd.isna(df['bb_lower'].iloc[-1]) else price
        bb_pos = (price - bb_lower) / (bb_upper - bb_lower + 1e-6)
        stoch_k = float(df['stoch_k'].iloc[-1]) if not pd.isna(df['stoch_k'].iloc[-1]) else 50.0
        stoch_d = float(df['stoch_d'].iloc[-1]) if not pd.isna(df['stoch_d'].iloc[-1]) else 50.0
        adx = float(df['adx'].iloc[-1]) if 'adx' in df.columns else compute_adx(df)
        vwap = float(df['vwap'].iloc[-1]) if 'vwap' in df.columns and not pd.isna(df['vwap'].iloc[-1]) else price
        senkou_a = float(df['senkou_span_a'].iloc[-1]) if not pd.isna(df['senkou_span_a'].iloc[-1]) else price
        senkou_b = float(df['senkou_span_b'].iloc[-1]) if not pd.isna(df['senkou_span_b'].iloc[-1]) else price
        fib_closest, _ = compute_fib_levels(df)
        macd_div, div_strength = detect_macd_divergence_improved(df)

        volume_passed = True
        if tf == TIMEFRAMES[0]:
            vol_avg = df['volume'].rolling(20).mean().iloc[-1]
            if df['volume'].iloc[-1] <= VOLUME_MULTIPLIER * vol_avg:
                volume_passed = False

        supertrend_str = compute_supertrend(df)
        supertrend_up = supertrend_str == "Uptrend"
        support, resistance, breakout, sr_status = compute_support_resistance(df)
        sr_str = f"{sr_status} | {breakout}"
        # T2-B: HMM regime detection with ADX fallback
        hmm_regime = detect_hmm_regime(df)
        if hmm_regime:
            regime = hmm_regime
        else:
            regime = "Ranging" if adx < ADX_RANGE_THRESHOLD else "Trending" if adx > ADX_TREND_THRESHOLD else "Neutral"
        regime_str = f"Regime: {regime} (ADX {round(adx, 1)})"

        score = 0.0

        # Core
        core = 0
        if rsi < 30: core += 25
        elif rsi < 40: core += 15
        elif rsi > 70: core -= 20
        if macd_line > macd_sig: core += 20
        elif macd_line < macd_sig: core -= 15
        if bb_pos < 0.15: core += 18
        elif bb_pos > 0.85: core -= 15
        score += core * w.get('core', 0.25)

        # Momentum
        momentum = 0
        if hist > 0 and hist > prev_hist: momentum += 18
        if volume_passed: momentum += 15
        score += momentum * w.get('momentum', 0.15)

        # Stochastic
        stoch_score = 0
        if stoch_k < 20 and stoch_k > stoch_d: stoch_score += 20
        elif stoch_k > 80 and stoch_k < stoch_d: stoch_score -= 18
        score += stoch_score * w.get('stoch', 0.10)

        # ADX
        adx_score = 0
        if adx > 25:
            if macd_line > 0: adx_score += 12
            else: adx_score -= 10
        elif adx < 20:
            adx_score += 5
        score += adx_score * w.get('adx', 0.08)

        # VWAP / Ichimoku
        vwap_ich = 0
        if price > vwap: vwap_ich += 10
        if price > max(senkou_a, senkou_b): vwap_ich += 15
        elif price < min(senkou_a, senkou_b): vwap_ich -= 15
        score += vwap_ich * w.get('vwap_ich', 0.08)

        # Fibonacci
        fib_score = 0
        if fib_closest in ['61.8%', '78.6%'] and rsi < 40: fib_score += 8
        elif fib_closest in ['23.6%', '38.2%'] and rsi > 60: fib_score -= 8
        score += fib_score * w.get('fib', 0.08)

        # Candlestick patterns
        _, candle_score = detect_candlestick_patterns(df)
        score += candle_score

        # Divergence
        div_score = 0
        if "Bullish" in macd_div and rsi < 40:
            div_score += 15 if div_strength == "Strong" else 10
        if "Bearish" in macd_div and rsi > 60:
            div_score -= 15 if div_strength == "Strong" else 10
        score += div_score * w.get('div', 0.05)

        # SuperTrend (T1-A: normalized — raw ±15 multiplied by weight, same scale as continuous weights)
        super_raw = 0
        if supertrend_up and (macd_line > macd_sig or rsi < 40):
            super_raw = 15
        elif not supertrend_up and (macd_line < macd_sig or rsi > 60):
            super_raw = -15
        score += super_raw * w.get('supertrend', 0.667)

        # S/R Breakout (T1-A: normalized — raw ±15 multiplied by weight)
        sr_raw = 0
        if breakout == "Bullish Breakout" and volume_passed:
            sr_raw = 15
        elif breakout == "Bearish Breakout" and volume_passed:
            sr_raw = -15
        score += sr_raw * w.get('sr_breakout', 0.667)
        if "Near" in sr_status:
            score += 5  # small absolute bonus for proximity (not weight-scaled)

        # Regime (T1-A: normalized — raw ±12 multiplied by weight)
        regime_raw = 0
        if regime == "Trending" and supertrend_up == (macd_line > macd_sig):
            regime_raw = 12
        elif regime == "Ranging":
            regime_raw = -12
            if "Near" in sr_status:
                score += 10  # S/R anchor softens the ranging penalty
        score += regime_raw * w.get('regime', 0.667)

        # Bonus
        bonus = 0
        if rsi < 25: bonus += 20
        if rsi > 75: bonus -= 18
        if price < bb_lower * 1.01: bonus += 15
        if price > bb_upper * 0.99: bonus -= 12
        score += bonus * w.get('bonus', 0.5)

        # Strategy bias + regime bonus
        strategy_bias = "Balanced"
        regime_bonus = 0
        if regime == "Trending":
            strategy_bias = "Trend-Follow"
            if (supertrend_up and macd_line > macd_sig) or (not supertrend_up and macd_line < macd_sig):
                regime_bonus += 18
            if hist > 0 and hist > prev_hist and supertrend_up: regime_bonus += 12
            elif hist < 0 and hist < prev_hist and not supertrend_up: regime_bonus += 12
        elif regime == "Ranging":
            strategy_bias = "Mean-Reversion"
            near_sr = "Near" in sr_status
            if near_sr and (rsi < 25 or rsi > 75): regime_bonus += 20
            if near_sr and bb_pos < 0.2 and rsi < 35: regime_bonus += 15
            if near_sr and bb_pos > 0.8 and rsi > 65: regime_bonus += 15
        score += regime_bonus

        # Fear & Greed (T1-B: multiplier only — removed additive bias that caused +22.5pt inflation)
        fng_mult = 1.0
        if fng_value < 25:
            fng_mult = 1.15
        elif fng_value < 45:
            fng_mult = 1.08
        elif fng_value > 75:
            fng_mult = 0.85
            if adx < 30:
                score = min(score, 55)
        elif fng_value > 55:
            fng_mult = 0.92
        score = score * fng_mult

        # On-chain
        onchain_bias = get_onchain_bias(**onchain_data, adx=adx)
        score += onchain_bias * w.get('onchain', 0.12)

        # Deribit Options IV bias (BTC/ETH only — regime-aware)
        if iv_data and iv_data.get('source') == 'deribit':
            iv_signal = iv_data.get('signal', 'NORMAL')
            if iv_signal == 'EXTREME_FEAR':
                # Extreme vol + mean-reversion setup = strong contrarian opportunity
                if strategy_bias == 'Mean-Reversion': score += 12
                else: score -= 5  # Don't chase trends into panic
            elif iv_signal == 'FEAR':
                if strategy_bias == 'Mean-Reversion': score += 6
                else: score -= 3
            elif iv_signal == 'COMPLACENCY':
                # Low vol complacency favours trend breakouts, kills mean-reversion edge
                if strategy_bias == 'Trend-Follow': score += 6
                else: score -= 5

        # Order book imbalance bias (OKX SWAP depth)
        if ob_data and ob_data.get('signal') not in (None, 'N/A'):
            ob_signal = ob_data.get('signal')
            ob_imb = abs(ob_data.get('imbalance', 0.0))
            if ob_signal == 'BUY_PRESSURE':
                score += round(8 * ob_imb, 1)
            elif ob_signal == 'SELL_PRESSURE':
                score -= round(8 * ob_imb, 1)

        # CVD (Cumulative Volume Delta) bias — taker aggression confirms or contradicts direction
        # CVD is the strongest real-money signal: aggressive buyers/sellers reveal true intent
        # Max ±10 pts: stronger than OB depth (8 pts) since it measures actual executed trades
        if cvd_data and cvd_data.get('source') == 'okx_trades':
            cvd_signal = cvd_data.get('signal', 'BALANCED')
            cvd_imb = abs(cvd_data.get('imbalance', 0.0))
            cvd_momentum = cvd_data.get('cvd_change_pct', 0.0)  # positive = CVD accelerating
            # Base score from imbalance magnitude
            cvd_base = round(10 * cvd_imb, 1)
            # Momentum bonus: if CVD is accelerating in same direction, add up to +3
            _cvd_mom_bonus = min(3.0, abs(cvd_momentum) / 20.0)
            if cvd_signal == 'BUY_PRESSURE':
                score += cvd_base + (_cvd_mom_bonus if cvd_momentum > 0 else 0)
            elif cvd_signal == 'SELL_PRESSURE':
                score -= cvd_base + (_cvd_mom_bonus if cvd_momentum < 0 else 0)

        # Multi-agent (F4: unpack 4th value — per-agent votes dict)
        # df['atr'] already computed by _enrich_df — avoid double computation
        _atr_raw = float(df['atr'].iloc[-1]) if 'atr' in df.columns else float(compute_atr(df).iloc[-1])
        atr_val = _atr_raw if np.isfinite(_atr_raw) and _atr_raw > 0 else df['close'].iloc[-1] * 0.01
        agent_score, agent_reasons, consensus, agent_votes = multi_agent_vote(
            df, fng_value, fng_category, onchain_data, adx, atr_val, corr_value, position_pct
        )
        score += agent_score * w.get('agents', 0.25)

        # Statistical arbitrage — use pre-fetched btc_df if available (avoids N redundant API calls)
        stat_arb_signal = "NEUTRAL"
        if tf == '1d' and pair != 'BTC/USDT':
            try:
                _df_btc = btc_df  # use pre-fetched when provided
                if _df_btc is None:
                    ta_ex_arb = get_exchange_instance(TA_EXCHANGE)
                    if ta_ex_arb:
                        ohlcv_btc = ta_ex_arb.fetch_ohlcv('BTC/USDT', '1d', limit=STAT_ARB_LOOKBACK)
                        _df_btc = pd.DataFrame(ohlcv_btc, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                if _df_btc is not None:
                    z_score, stat_arb_signal = compute_cointegration_zscore(_df_btc, df)
                    score += get_stat_arb_bias(z_score, stat_arb_signal) * w.get('stat_arb', 0.15)
            except Exception as e:
                logging.warning(f"StatArb failed {pair} {tf}: {e}")

        score = max(0, min(100, score))
        # T2-A: Sigmoid calibration — converts raw score to a more decisive probability-like value.
        # Maps: 50→50, 65→72, 75→80, 45→28, 35→20. Scale=20 keeps changes moderate.
        score = round(100.0 / (1.0 + np.exp(-(score - 50.0) / 20.0)), 1)
        # F4: agent_votes is 12th return value — passed through to _scan_pair for feedback logging
        return (round(score, 1), volume_passed, macd_div, div_strength,
                supertrend_str, sr_str, regime_str, strategy_bias,
                agent_score, consensus, stat_arb_signal, agent_votes)
    except Exception as e:
        logging.warning(f"Signal calc failed {pair} {tf}: {e}")
        return 0, False, "None", "N/A", "N/A", "N/A", "N/A", "Balanced", 0.0, 0.0, "NEUTRAL", {}

def get_signal_direction(confidence):
    # CQ-09: symmetric thresholds around 50 to eliminate directional bias
    # STRONG BUY ≥ 75  |  BUY 55–74  |  NEUTRAL 45–54  |  SELL 25–44  |  STRONG SELL < 25
    if confidence is None:
        confidence = 0.0
    if confidence >= 75: return "STRONG BUY"
    if confidence >= 55: return "BUY"
    if confidence >= 45: return "NEUTRAL"   # BUG-R14: was > 45, excluded exactly 45.0 → SELL
    if confidence > 25:  return "SELL"
    return "STRONG SELL"

# ──────────────────────────────────────────────
# KELLY CRITERION POSITION SIZING
# ──────────────────────────────────────────────
def _compute_kelly_fraction() -> float | None:
    """
    Compute quarter-Kelly fraction from backtest history.
    Returns float in (0, 0.5] or None if insufficient data (<20 valid trades).
    Quarter-Kelly (25%) is used for safety — reduces variance while capturing most of the edge.
    """
    try:
        bt = _db.get_backtest_df()
        if bt.empty:
            return None
        bt = bt[~bt['direction'].str.contains('NEUTRAL|LOW VOL', na=False, regex=True)]
        buy_mask = bt['direction'].isin(['BUY', 'STRONG BUY']) & (bt['exit'] > bt['entry'])
        sell_mask = bt['direction'].isin(['SELL', 'STRONG SELL']) & (bt['exit'] < bt['entry'])
        bt = bt[buy_mask | sell_mask].copy()
        if len(bt) < 20:
            return None
        wins = bt[bt['pnl_pct'] > 0]
        losses = bt[bt['pnl_pct'] <= 0]
        if len(losses) == 0 or len(wins) == 0:
            return None
        p = len(wins) / len(bt)
        avg_win = wins['pnl_pct'].mean() / 100
        avg_loss = abs(losses['pnl_pct'].mean()) / 100
        if avg_loss == 0:
            return None
        b = avg_win / avg_loss
        kelly = (b * p - (1 - p)) / b
        # Quarter-Kelly, capped at 50% of portfolio
        return round(max(0.0, min(kelly * 0.25, 0.50)), 4)
    except Exception as e:
        logging.warning(f"Kelly computation failed: {e}")
        return None


# Per-scan Kelly cache — refreshed once at scan start via reset_kelly_cache()
_kelly_cache: dict = {"value": None, "valid": False}


def reset_kelly_cache():
    """Call once at the start of each scan to recompute Kelly for all pairs."""
    # BUG-R02: update dict in-place under lock instead of replacing the reference.
    # Replacing _kelly_cache globally is a TOCTOU: a worker thread reading
    # _kelly_cache["value"] under _weights_lock could hold the OLD reference
    # while this thread replaces the module-level name.
    val = _compute_kelly_fraction()
    with _weights_lock:
        _kelly_cache["value"] = val
        _kelly_cache["valid"] = True


# Per-scan agent accuracy cache — refreshed once at scan start (PERF-06)
# Avoids 24 redundant DB queries (one per pair×TF) for the same static data.
_agent_acc_cache: dict = {"value": None, "valid": False}


def reset_agent_acc_cache():
    """Call once at scan start to prefetch agent accuracy weights for all pairs."""
    # BUG-R02: update dict in-place under lock (same pattern as reset_kelly_cache)
    val = _db.get_agent_accuracy_weights(days=30)
    with _weights_lock:
        _agent_acc_cache["value"] = val
        _agent_acc_cache["valid"] = True


# ──────────────────────────────────────────────
# ENTRY / EXIT / POSITION SIZING
# ──────────────────────────────────────────────
def recommend_leverage(confidence: float, atr_pct: float) -> dict:
    """
    Recommend leverage range based on signal confidence and ATR % volatility.

    Tier logic (professional consensus):
      STRONG (≥85%) + high vol  → 4x–6x
      STRONG (≥85%) + low vol   → 8x–10x
      MEDIUM (65–84%) + high vol → 2x–4x
      MEDIUM (65–84%) + low vol  → 4x–8x
      LOW (<65%)                 → 1x–2x (risk-off)
    Hard cap: MAX_LEVERAGE_CAP (default 10x).
    Returns dict: {'min': int, 'max': int, 'basis': str}
    """
    high_vol = atr_pct > HIGH_VOL_ATR_THRESHOLD
    if confidence >= 85:
        lev_min, lev_max = (4, 6) if high_vol else (8, 10)
        tier = "Strong signal"
    elif confidence >= 65:
        lev_min, lev_max = (2, 4) if high_vol else (4, 8)
        tier = "Medium signal"
    else:
        lev_min, lev_max = 1, 2
        tier = "Low confidence"
    vol_label = "high vol" if high_vol else "low vol"
    lev_max = min(lev_max, MAX_LEVERAGE_CAP)
    lev_min = min(lev_min, lev_max)
    return {
        'min':   lev_min,
        'max':   lev_max,
        'label': f"{lev_min}x–{lev_max}x",
        'basis': f"{tier}, {vol_label}",
    }


def generate_entry_exit(df, regime_from_1h, pair, master_df, direction="NEUTRAL"):
    if df is None or len(df) < 50:
        return None, None, None
    price = df['close'].iloc[-1]
    fib_level, fib_price = compute_fib_levels(df)
    _atr_raw = float(compute_atr(df).iloc[-1])
    # BUG-H01: float(NaN) is truthy so `or` fallback never fires for NaN; use explicit guard
    atr = _atr_raw if np.isfinite(_atr_raw) and _atr_raw > 0 else 0.01 * price
    atr_mult = RISK_MODE_ATR.get(regime_from_1h, 2.0)
    pos_scale = RISK_MODE_POSITION.get(regime_from_1h, 1.0)

    if direction in ['STRONG BUY', 'BUY']:
        entry = fib_price if fib_level in ['61.8%', '78.6%'] else price
        stop = entry - atr_mult * atr
        risk_dist = abs(entry - stop)
        tp1   = entry + TP1_MULT * risk_dist
        tp2   = entry + TP2_MULT * risk_dist
        tp3   = entry + TP3_MULT * risk_dist
        exit_ = tp2   # backward-compat (backtest uses this field)
    elif direction in ['STRONG SELL', 'SELL']:
        entry = fib_price if fib_level in ['23.6%', '38.2%'] else price
        stop = entry + atr_mult * atr
        risk_dist = abs(entry - stop)
        tp1   = entry - TP1_MULT * risk_dist
        tp2   = entry - TP2_MULT * risk_dist
        tp3   = entry - TP3_MULT * risk_dist
        exit_ = tp2   # backward-compat
    else:
        entry = price
        stop = entry - atr_mult * atr
        risk_dist = abs(entry - stop)
        tp1   = entry + TP1_MULT * risk_dist
        tp2   = entry + TP2_MULT * risk_dist
        tp3   = entry + TP3_MULT * risk_dist
        exit_ = tp2

    # risk_dist already computed per-branch above
    base_usd = 0.0
    if risk_dist > 0 and entry > 0:
        base_usd = (PORTFOLIO_SIZE_USD * RISK_PER_TRADE_PCT / 100) / (risk_dist / entry)
    base_pct = (base_usd / PORTFOLIO_SIZE_USD) * 100

    corr_adjust = 1.0
    corr_val = None
    if pair != 'BTC/USDT' and master_df is not None and not master_df.empty:
        try:
            if 'pair' in master_df.columns and 'price_usd' in master_df.columns:
                sub = master_df[master_df['pair'].isin([pair, 'BTC/USDT'])].copy()
                if len(sub) >= CORR_LOOKBACK_DAYS:
                    pivot = sub.pivot_table(index='scan_timestamp', columns='pair', values='price_usd').tail(CORR_LOOKBACK_DAYS)
                    if pair in pivot.columns and 'BTC/USDT' in pivot.columns:
                        corr_val = float(pivot.corr().loc['BTC/USDT', pair])
                        if not np.isnan(corr_val) and corr_val > CORR_THRESHOLD:
                            corr_adjust = CORR_REDUCTION_FACTOR
        except Exception as e:
            logging.debug(f"Correlation adjustment failed: {e}")

    # Apply Kelly Criterion cap if backtest data is available (use per-scan cache — PERF-03)
    with _weights_lock:
        kelly_f = _kelly_cache["value"] if _kelly_cache["valid"] else None
    if kelly_f is None:
        kelly_f = _compute_kelly_fraction()
    # Guard: if kelly_f is None or zero/negative, use RISK-OFF size (5%), not MAX_POSITION_PCT_CAP.
    # BUG-14 fix: `if kelly_f` treats 0.0 as falsy — use explicit None/positive check.
    # BUG-KELLY01 fix: no edge (kelly_f <= 0) means we should be risk-off at 5%, NOT at 50%.
    # The old fallback to MAX_POSITION_PCT_CAP made positions BIGGER when the system had no edge.
    _KELLY_RISK_OFF_PCT = 5.0  # 5% of portfolio when kelly says no edge
    kelly_cap_usd = (
        PORTFOLIO_SIZE_USD * kelly_f
        if kelly_f is not None and kelly_f > 0
        else PORTFOLIO_SIZE_USD * _KELLY_RISK_OFF_PCT / 100
    )

    final_usd = min(
        base_usd * corr_adjust * pos_scale,
        PORTFOLIO_SIZE_USD * MAX_POSITION_PCT_CAP / 100,
        kelly_cap_usd,
    )
    final_pct = min((final_usd / PORTFOLIO_SIZE_USD) * 100, MAX_POSITION_PCT_CAP)

    # Leverage recommendation (uses ATR as % of price)
    atr_pct = atr / price if price > 0 else 0.0
    lev_rec = recommend_leverage(50.0, atr_pct)  # placeholder conf; overridden in _scan_pair

    return round(entry, 4), round(exit_, 4), {
        'stop_loss':             round(stop, 4),
        'tp1':                   round(tp1, 4),
        'tp2':                   round(tp2, 4),
        'tp3':                   round(tp3, 4),
        'rr_ratios':             {'tp1': f"{TP1_MULT}:1", 'tp2': f"{TP2_MULT}:1", 'tp3': f"{TP3_MULT}:1"},
        'risk_pct':              RISK_PER_TRADE_PCT,
        'position_size_usd':     round(final_usd, 2),
        'position_size_pct':     round(final_pct, 1),
        'risk_mode':             regime_from_1h,
        'corr_with_btc':         round(corr_val, 3) if corr_val is not None and not np.isnan(corr_val) else None,
        'corr_adjusted_size_pct': round(final_pct, 1),
        'leverage_rec':          lev_rec,   # updated with real conf in _scan_pair
    }

# ──────────────────────────────────────────────
# FEEDBACK / LOGGING
# ──────────────────────────────────────────────
def log_feedback(pair, direction, entry, exit_, confidence, agent_votes=None, indicator_snaps=None):
    _db.log_feedback(pair, direction, entry, exit_, confidence,
                     agent_votes=agent_votes, indicator_snaps=indicator_snaps)

MASTER_LOG_COLUMNS = [
    'scan_timestamp', 'pair', 'price_usd', 'confidence_avg_pct', 'direction',
    'strategy_bias', 'mtf_alignment', 'high_conf', 'fng_value', 'fng_category',
    'entry', 'exit', 'stop_loss', 'risk_pct', 'position_size_usd',
    'position_size_pct', 'risk_mode', 'corr_with_btc', 'corr_adjusted_size_pct',
    'regime', 'sr_status', 'circuit_breaker_triggered', 'circuit_breaker_drawdown_pct',
    'scan_sec',
]

def append_to_master(results):
    _db.append_to_master(results)

def update_dynamic_weights():
    """F2: Update all 15 indicator weights using actual resolved P&L from feedback_log.

    Replaces the old circular win_rate proxy (counting BUY signals with conf>50)
    with real trade outcomes resolved by resolve_feedback_outcomes().

    Algorithm:
    - Reads last 90 days of resolved feedback (actual_pnl_pct set by resolver)
    - Applies exponential recency weighting: lambda=0.98 per day (recent data counts more)
    - Computes weighted win-rate for each weight bucket:
        core/momentum/stoch/adx — general performance
        supertrend/regime/sr_breakout — trending-regime-conditional
        fib/div/vwap_ich/bonus — secondary signals
        fng/onchain/agents/stat_arb — macro/ensemble signals
    - Updates weight toward a target derived from win-rate deviation from 0.5:
        wr=0.7 → target=1.0 (strong edge, upweight)
        wr=0.5 → target=0.667 (neutral — keep at midpoint)
        wr=0.3 → target=0.333 (anti-edge, downweight)
    - Smoothing: weights['key'] = 0.7 * old + 0.3 * target (prevents overreaction)
    - Only updates if change > 0.05 (avoids write noise on tiny changes)

    If < 30 resolved rows exist, falls back to signal-distribution heuristics
    (same logic as before but using direction labels, not the circular BUY-conf proxy).
    """
    global weights

    resolved_df = _db.get_resolved_feedback_df(days=90)
    has_outcomes = len(resolved_df) >= 30

    if has_outcomes:
        # Exponential recency decay: weight_i = lambda ^ days_ago
        # lambda=0.98/day so 30d-ago row weighs 0.98^30 ≈ 0.55
        resolved_df = resolved_df.copy()
        resolved_df['timestamp'] = pd.to_datetime(resolved_df['timestamp'], errors='coerce')
        now = pd.Timestamp.utcnow().tz_localize(None)
        resolved_df['days_ago'] = (now - resolved_df['timestamp'].dt.tz_localize(None)).dt.days.clip(lower=0)
        resolved_df['recency_w'] = np.power(0.98, resolved_df['days_ago'].fillna(30))
        resolved_df['was_correct'] = pd.to_numeric(resolved_df['was_correct'], errors='coerce').fillna(0)

        total_w = resolved_df['recency_w'].sum()
        if total_w == 0:
            has_outcomes = False

    def _weighted_winrate(df_sub):
        """Compute recency-weighted win rate for a subset of resolved rows."""
        if df_sub.empty or 'recency_w' not in df_sub.columns:
            return 0.5
        n = len(df_sub)
        if n < 5:
            return 0.5
        w_wins = (df_sub['recency_w'] * df_sub['was_correct']).sum()
        w_total = df_sub['recency_w'].sum()
        return float(w_wins / w_total) if w_total > 0 else 0.5

    def _target_weight(wr, neutral=0.667, scale=0.833):
        """Convert win rate [0,1] → target weight [0.10, 1.50].
        wr=0.5 → neutral (0.667), wr=1.0 → 0.667+0.833*0.5=1.083, wr=0.0 → 0.667-0.833*0.5=0.250
        """
        return max(0.10, min(1.50, neutral + (wr - 0.5) * scale))

    def _update_w(key, wr, default=0.667, scale=0.833, threshold=0.05):
        """Smooth-update one weight. Returns True if weight changed."""
        target = _target_weight(wr, neutral=default, scale=scale)
        current = weights.get(key, default)
        new_val = round(current * 0.7 + target * 0.3, 4)
        if abs(new_val - current) > threshold:
            weights[key] = new_val
            return True
        return False

    updated = False

    with _weights_lock:
        if has_outcomes:
            # ── Regime-conditional weights ────────────────────────────────
            # Primary signal: overall directional accuracy
            wr_all = _weighted_winrate(resolved_df)
            if _update_w('supertrend', wr_all): updated = True
            if _update_w('regime',     wr_all, scale=0.667): updated = True
            if _update_w('sr_breakout', wr_all): updated = True

            # ── High-confidence subset — weights that fire when conf is high ──
            # BUG-H02: use column check then direct access (avoids misaligned boolean Series in pandas 2.x)
            high_conf = resolved_df[resolved_df['confidence'].fillna(0) > 65] \
                if 'confidence' in resolved_df.columns else resolved_df
            wr_hc = _weighted_winrate(high_conf)

            # Core technical weights (RSI, MACD, BB)
            if _update_w('core',       wr_hc, default=0.25, scale=0.5):  updated = True
            if _update_w('momentum',   wr_hc, default=0.15, scale=0.3):  updated = True
            if _update_w('stoch',      wr_hc, default=0.10, scale=0.2):  updated = True
            if _update_w('adx',        wr_hc, default=0.08, scale=0.16): updated = True
            if _update_w('vwap_ich',   wr_hc, default=0.08, scale=0.16): updated = True
            if _update_w('fib',        wr_hc, default=0.08, scale=0.16): updated = True
            if _update_w('div',        wr_hc, default=0.05, scale=0.10): updated = True
            if _update_w('bonus',      wr_hc, default=0.50, scale=0.5):  updated = True

            # Macro / ensemble weights
            if _update_w('fng',        wr_all, default=0.15, scale=0.3):  updated = True
            if _update_w('onchain',    wr_all, default=0.12, scale=0.24): updated = True
            if _update_w('agents',     wr_all, default=0.25, scale=0.5):  updated = True
            if _update_w('stat_arb',   wr_all, default=0.15, scale=0.3):  updated = True

        else:
            # ── Fallback: use signal-distribution heuristics ─────────────
            # Avoids the old circular proxy (BUY signals with conf>50).
            # Instead: use master_df SELL accuracy as a real heuristic.
            master_df = _db.get_signals_df()
            if len(master_df) < 20 or 'regime' not in master_df.columns:
                return

            # Measure how often the model generates BUY vs SELL (imbalance = signal quality proxy)
            direction_series = master_df['direction'].astype(str)
            buy_frac  = direction_series.str.contains("BUY",  na=False).mean()
            sell_frac = direction_series.str.contains("SELL", na=False).mean()
            # Balanced output (buy≈sell) implies model is responding to market, not biased
            balance_wr = 0.5 + min(0.15, 0.5 - abs(buy_frac - 0.5))  # near 0.5 → higher

            trending = master_df[master_df['regime'].str.contains("Trending", na=False)]
            if len(trending) >= 10:
                if _update_w('supertrend', balance_wr): updated = True
            if _update_w('regime', balance_wr, scale=0.667): updated = True

            breakouts = master_df[master_df.get('sr_status', pd.Series(dtype=str)).astype(str)
                                  .str.contains("Breakout", na=False)] \
                if 'sr_status' in master_df.columns else pd.DataFrame()
            if len(breakouts) >= 10:
                if _update_w('sr_breakout', balance_wr): updated = True

    if updated:
        save_weights()

def run_feedback_loop():
    """F1: Resolve pending signal outcomes and update weights from real P&L data.

    Pipeline:
    1. Resolve up to 50 unresolved feedback rows whose hold period elapsed
       (calls exchange to fetch actual exit price, writes outcome to DB).
    2. Log performance evaluation based on ALL resolved data (not just last 10).
    3. Call update_dynamic_weights() — now uses real P&L instead of circular proxy.
    """
    ta_ex = get_exchange_instance(TA_EXCHANGE)
    if not ta_ex:
        update_dynamic_weights()
        return

    # F1a: Quick resolve (72h) — cuts dead zone from 14 days to 3 days
    def _fetch_ohlcv_for_resolve(pair, since_ms, tf='1h'):
        try:
            return ta_ex.fetch_ohlcv(pair, tf, since=since_ms, limit=1)
        except Exception:
            return []

    try:
        quick_resolved = _db.quick_resolve_feedback(
            fetch_ohlcv_fn=_fetch_ohlcv_for_resolve,
            hold_hours=72,
            batch=100,
        )
        if quick_resolved > 0:
            logging.info(f"Feedback quick-resolve (72h): {quick_resolved} outcomes written")
    except Exception as e:
        logging.warning(f"run_feedback_loop quick_resolve failed: {e}")

    # F1b: Full resolve (14-day hold) — resolves older unresolved rows
    def _fetch_price(pair, since_ms):
        try:
            ohlcv = ta_ex.fetch_ohlcv(pair, '1h', since=since_ms, limit=1)
            return float(ohlcv[0][4]) if ohlcv else None
        except Exception:
            return None

    try:
        resolved_count = _db.resolve_feedback_outcomes(
            fetch_price_fn=_fetch_price,
            hold_days=BACKTEST_HOLD_DAYS,
            batch=50,
        )
        if resolved_count > 0:
            logging.info(f"Feedback resolver: {resolved_count} new outcomes written to feedback_log")
    except Exception as e:
        logging.warning(f"run_feedback_loop resolve failed: {e}")

    # Log evaluation metrics from ALL resolved data (was last-10-rows only — see Proof 9)
    resolved_df = _db.get_resolved_feedback_df(days=90)
    if not resolved_df.empty and 'actual_pnl_pct' in resolved_df.columns:
        pnl_vals = pd.to_numeric(resolved_df['actual_pnl_pct'], errors='coerce').dropna()
        if len(pnl_vals) >= 5:
            accuracy = round((pnl_vals > 0).mean() * 100, 1)
            _db.log_weights_eval(float(pnl_vals.mean()), accuracy)

    update_dynamic_weights()

    # F-RETRAIN: Auto-retrain LightGBM from resolved feedback every feedback cycle
    try:
        retrain_result = retrain_lgbm_from_feedback(min_samples=50)
        if retrain_result.get("success"):
            logging.info(f"LightGBM feedback retrain: {retrain_result['message']}")
        else:
            logging.debug(f"LightGBM feedback retrain skipped: {retrain_result.get('message')}")
    except Exception as lgbm_e:
        logging.warning(f"run_feedback_loop lgbm retrain failed: {lgbm_e}")

    # F6/F7: Run drift detection after weights update — store result for UI; auto-trigger Optuna if drift detected
    global _last_drift_result
    try:
        drift = check_concept_drift()
        with _weights_lock:
            _last_drift_result = drift  # BUG-C05: lock protects against torn reads in UI thread
        if drift.get('drift_detected'):
            logging.warning(
                f"CONCEPT DRIFT DETECTED: 30d win rate {drift['win_rate_30d']:.1%} vs "
                f"90d win rate {drift['win_rate_90d']:.1%} "
                f"(ratio={drift['ratio']:.2f} < threshold 0.75). "
                f"Triggering Optuna re-optimization on BTC/USDT 1h."
            )
            try:
                run_optuna_weight_optimization(n_trials=30, pair='BTC/USDT', tf='1h')
                logging.info("DRIFT: Optuna re-optimization complete.")
            except Exception as opt_e:
                logging.warning(f"DRIFT: Optuna re-optimization failed: {opt_e}")
    except Exception as drift_e:
        logging.warning(f"Drift detection failed: {drift_e}")


def check_concept_drift() -> dict:
    """F6/F7: ADWIN-style concept drift detector.

    Compares 30-day win rate against 90-day win rate from resolved feedback.
    If the ratio drops below 0.75, it means recent performance has decayed
    significantly relative to historical — a signal that market regime has shifted
    and the model's indicators are no longer as effective.

    Returns:
        dict with keys:
            drift_detected (bool)
            win_rate_30d   (float)
            win_rate_90d   (float)
            ratio          (float)  — win_rate_30d / win_rate_90d
            n_resolved_30d (int)
            n_resolved_90d (int)
            message        (str)

    Drift is only flagged when we have ≥30 resolved rows in the 90-day window
    (avoids false positives early in deployment).
    """
    resolved_90d = _db.get_resolved_feedback_df(days=90)
    resolved_30d = _db.get_resolved_feedback_df(days=30)

    n_90 = len(resolved_90d)
    n_30 = len(resolved_30d)

    if n_90 < 30:
        return {
            'drift_detected': False,
            'win_rate_30d':   0.0,
            'win_rate_90d':   0.0,
            'ratio':          1.0,
            'n_resolved_30d': n_30,
            'n_resolved_90d': n_90,
            'message':        f"Insufficient resolved data ({n_90} rows < 30 required)",
        }

    def _wr(df):
        col = pd.to_numeric(df.get('was_correct', pd.Series(dtype=float)), errors='coerce').dropna()
        return float(col.mean()) if len(col) >= 5 else 0.5

    wr_90 = _wr(resolved_90d)
    wr_30 = _wr(resolved_30d)
    ratio  = (wr_30 / wr_90) if wr_90 > 0 else 1.0

    drift = ratio < 0.75 and n_30 >= 10  # need ≥10 recent rows to trust the 30d rate
    message = (
        f"DRIFT ALERT: recent win rate {wr_30:.1%} is {ratio:.0%} of 90d rate {wr_90:.1%}"
        if drift else
        f"No drift: 30d={wr_30:.1%}, 90d={wr_90:.1%}, ratio={ratio:.2f}"
    )

    return {
        'drift_detected': drift,
        'win_rate_30d':   round(wr_30, 4),
        'win_rate_90d':   round(wr_90, 4),
        'ratio':          round(ratio, 4),
        'n_resolved_30d': n_30,
        'n_resolved_90d': n_90,
        'message':        message,
    }


def get_drift_status() -> dict:
    """Return the most recent concept drift result for display in the UI.

    Returns the last result from check_concept_drift() stored by run_feedback_loop().
    Returns empty dict if the feedback loop has not run yet this session.
    """
    with _weights_lock:
        return dict(_last_drift_result)


def show_trends():
    master_df = _db.get_signals_df()
    if len(master_df) < 2:
        return {}
    last_scan = master_df.sort_values('scan_timestamp').groupby('pair').tail(1)
    prev_scan = master_df.sort_values('scan_timestamp').groupby('pair').tail(2).groupby('pair').head(1)
    trends = {}
    for pair in PAIRS:
        curr = last_scan[last_scan['pair'] == pair]
        prev = prev_scan[prev_scan['pair'] == pair]
        if curr.empty or prev.empty:
            continue
        curr_conf = curr['confidence_avg_pct'].values[0]
        prev_conf = prev['confidence_avg_pct'].values[0]
        change = curr_conf - prev_conf
        curr_dir = curr['direction'].values[0]
        prev_dir = prev['direction'].values[0]
        trends[pair] = {
            'conf_change': round(change, 1),
            'curr_direction': curr_dir,
            'prev_direction': prev_dir,
            'flipped': curr_dir != prev_dir
        }
    return trends

# ──────────────────────────────────────────────
# BACKTEST
# ──────────────────────────────────────────────
def run_backtest():
    df_signals = _db.get_signals_df()
    if len(df_signals) < 10:
        return None

    # BUG-H03: strip both legacy 'MST' and current 'UTC' suffix so all timestamps parse as naive
    df_signals['scan_timestamp'] = pd.to_datetime(
        df_signals['scan_timestamp'].str.replace(r'\s*(MST|UTC)$', '', regex=True), errors='coerce'
    )
    df_signals = df_signals.dropna(subset=['scan_timestamp'])
    required = ['entry', 'exit', 'stop_loss', 'direction']
    for col in required:
        if col not in df_signals.columns:
            return None

    df_valid = df_signals.dropna(subset=required).copy()
    # Only backtest clear directional signals — skip NEUTRAL and LOW VOL (no clear edge)
    df_valid = df_valid[~df_valid['direction'].str.contains('NEUTRAL|LOW VOL', na=False)]
    if 'confidence_avg_pct' in df_valid.columns:
        df_valid = df_valid[df_valid['confidence_avg_pct'] > 30]
    if len(df_valid) == 0:
        return None

    ta_ex = get_exchange_instance(TA_EXCHANGE)
    if not ta_ex:
        return None

    trades = []
    equity = [PORTFOLIO_SIZE_USD]

    # PERF-05: Pre-fetch all OHLCV data in parallel (max_workers=4) before the serial trade loop.
    # Each signal row needs a unique (pair, since_ms) fetch; the serial loop then uses the cache.
    def _fetch_ohlcv_for_row(args):
        _pair, _since_ms = args
        try:
            result = ta_ex.fetch_ohlcv(_pair, '1h', since=_since_ms, limit=BACKTEST_HOLD_DAYS * 24 + 24)
            return (_pair, _since_ms), result
        except Exception:
            return (_pair, _since_ms), None

    def _to_naive_ts(ts):
        """Strip timezone from a pd.Timestamp so naive/aware subtraction never raises.

        BUG-R06: tz_localize(None) raises TypeError on an already-tz-aware Timestamp.
        Use tz_convert(None) which correctly converts to UTC-naive.
        """
        try:
            if isinstance(ts, pd.Timestamp) and ts.tzinfo is not None:
                return ts.tz_convert(None)
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                return ts.replace(tzinfo=None)
            return ts
        except Exception:
            return ts

    fetch_keys = [
        (row['pair'], int(_to_naive_ts(row['scan_timestamp']).timestamp() * 1000))
        for _, row in df_valid.iterrows()
    ]
    unique_fetch_keys = list(dict.fromkeys(fetch_keys))  # deduplicate while preserving order
    _ohlcv_cache = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _bt_executor:
        for key, data in _bt_executor.map(_fetch_ohlcv_for_row, unique_fetch_keys):
            _ohlcv_cache[key] = data

    for _, row in df_valid.iterrows():
        try:
            signal_time = _to_naive_ts(row['scan_timestamp'])
            pair = row['pair']
            direction = row['direction']
            entry = float(row['entry'])
            target = float(row['exit'])
            stop = float(row['stop_loss'])
            pos_pct = min(float(row.get('position_size_pct', 10)), MAX_POSITION_PCT_CAP) / 100

            # Skip signals with inverted targets (bad historical data — target on wrong side of entry)
            if direction in ['BUY', 'STRONG BUY'] and target <= entry:
                continue
            if direction in ['SELL', 'STRONG SELL'] and target >= entry:
                continue

            since_ms = int(signal_time.timestamp() * 1000)
            ohlcv = _ohlcv_cache.get((pair, since_ms))
            if not ohlcv or len(ohlcv) < 2:
                continue

            df_future = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_future['timestamp'] = pd.to_datetime(df_future['timestamp'], unit='ms')

            exit_price = None
            exit_reason = "Timeout"
            # Trailing stop: distance from entry to initial stop (as fraction of entry)
            trail_dist = abs(entry - stop) / entry if TRAILING_STOP_ENABLED and entry > 0 else None
            current_stop = stop
            for _, candle in df_future.iterrows():
                if direction in ['BUY', 'STRONG BUY']:
                    # Advance trailing stop upward with new highs
                    if trail_dist and candle['high'] > entry:
                        new_trail = candle['high'] * (1 - trail_dist)
                        if new_trail > current_stop:
                            current_stop = new_trail
                    if candle['high'] >= target: exit_price = target; exit_reason = "Target"; break
                    if candle['low'] <= current_stop: exit_price = current_stop; exit_reason = "TrailingStop" if current_stop > stop else "Stop"; break
                elif direction in ['SELL', 'STRONG SELL']:
                    # Advance trailing stop downward with new lows
                    if trail_dist and candle['low'] < entry:
                        new_trail = candle['low'] * (1 + trail_dist)
                        if new_trail < current_stop:
                            current_stop = new_trail
                    if candle['low'] <= target: exit_price = target; exit_reason = "Target"; break
                    if candle['high'] >= current_stop: exit_price = current_stop; exit_reason = "TrailingStop" if current_stop < stop else "Stop"; break
                if (candle['timestamp'] - signal_time).total_seconds() >= BACKTEST_HOLD_DAYS * 86400:
                    exit_price = candle['close']; exit_reason = "Timeout"; break

            if exit_price is None:
                continue

            # ── Fee & slippage model ───────────────────────────────
            # Entry always fills as a market order (taker + slippage)
            entry_cost_pct = TAKER_FEE_PCT + SLIPPAGE_PCT
            # Exit: limit at target → maker fee only; market at stop/timeout → taker + slippage
            if exit_reason == "Target":
                exit_cost_pct = MAKER_FEE_PCT
            else:
                exit_cost_pct = TAKER_FEE_PCT + SLIPPAGE_PCT
            round_trip_cost = entry_cost_pct + exit_cost_pct  # e.g. 0.0015 = 0.15%

            # Gross PnL (no fees)
            if direction in ['BUY', 'STRONG BUY']:
                gross_pnl = (exit_price - entry) / entry
            else:
                gross_pnl = (entry - exit_price) / entry

            # Net PnL after round-trip fees & slippage
            pnl_pct    = gross_pnl - round_trip_cost
            fee_usd      = round_trip_cost * (PORTFOLIO_SIZE_USD * pos_pct)
            # Slippage = entry impact + exit impact (limit target has zero exit slippage)
            slippage_sides = 1 if exit_reason == "Target" else 2
            slippage_usd   = (SLIPPAGE_PCT * slippage_sides) * (PORTFOLIO_SIZE_USD * pos_pct)

            pnl_usd = pnl_pct * (PORTFOLIO_SIZE_USD * pos_pct)
            trades.append({
                'timestamp': signal_time, 'pair': pair, 'direction': direction,
                'entry': entry, 'exit': exit_price, 'exit_reason': exit_reason,
                'gross_pnl_pct': round(gross_pnl * 100, 2),
                'pnl_pct': round(pnl_pct * 100, 2), 'pnl_usd': round(pnl_usd, 2),
                'fee_usd': round(fee_usd, 4), 'slippage_usd': round(slippage_usd, 4),
                'pos_pct': round(pos_pct * 100, 1)
            })
            equity.append(equity[-1] + pnl_usd)
        except Exception as e:
            logging.warning(f"Backtest trade error {row.get('pair', '?')}: {e}")
            continue

    if not trades:
        return None

    df_trades = pd.DataFrame(trades)
    _bt_run_id = datetime.now().strftime('bt_%Y%m%d_%H%M%S')
    _db.save_backtest_trades(trades, run_id=_bt_run_id)

    wins = df_trades[df_trades['pnl_pct'] > 0]
    losses = df_trades[df_trades['pnl_pct'] <= 0]
    win_rate = len(wins) / len(df_trades) * 100 if len(df_trades) > 0 else 0
    avg_pnl = df_trades['pnl_pct'].mean()
    _loss_sum = abs(losses['pnl_usd'].sum())
    profit_factor = min(wins['pnl_usd'].sum() / _loss_sum, 99.0) if len(losses) > 0 and _loss_sum > 1.0 else 99.0
    returns = pd.Series(equity).pct_change().dropna()
    n_returns = len(returns)
    sharpe = returns.mean() / returns.std() * np.sqrt(n_returns) if returns.std() != 0 else 0
    drawdowns = (pd.Series(equity) / pd.Series(equity).cummax() - 1) * 100
    max_dd = drawdowns.min()
    total_return = (equity[-1] / equity[0] - 1) * 100

    # Sortino — like Sharpe but only penalizes downside volatility
    downside = returns[returns < 0]
    sortino = (returns.mean() / downside.std() * np.sqrt(n_returns)
               if len(downside) > 1 and downside.std() != 0 else 0)

    # Calmar — annualized return / max drawdown (higher = better risk-adjusted return)
    calmar = abs(total_return / max_dd) if max_dd != 0 else 0.0

    # Max consecutive losses
    loss_flags = (df_trades['pnl_pct'] <= 0).astype(int).tolist()
    max_consec_losses = max(
        (sum(1 for _ in g) for k, g in itertools.groupby(loss_flags) if k == 1),
        default=0
    )

    # Expectancy per trade
    avg_win = wins['pnl_pct'].mean() if len(wins) > 0 else 0
    avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
    win_prob = len(wins) / len(df_trades)
    # avg_loss is already negative (losses have negative pnl_pct), so use it directly
    expectancy = (win_prob * avg_win) + ((1 - win_prob) * avg_loss)

    # Fee summary
    total_fees_usd     = round(df_trades['fee_usd'].sum(), 2)     if 'fee_usd'     in df_trades.columns else 0.0
    total_slippage_usd = round(df_trades['slippage_usd'].sum(), 2) if 'slippage_usd' in df_trades.columns else 0.0
    gross_return       = round(df_trades['gross_pnl_pct'].sum(), 2) if 'gross_pnl_pct' in df_trades.columns else round(total_return, 2)
    fee_drag_pct       = round(gross_return - total_return, 2)

    return {
        'trades': df_trades,
        'equity': equity,
        'metrics': {
            'total_trades': len(df_trades),
            'win_rate': round(win_rate, 1),
            'avg_pnl': round(avg_pnl, 2),
            'profit_factor': round(profit_factor, 2),
            'sharpe': round(sharpe, 2),
            'sortino': round(sortino, 2),
            'calmar': round(calmar, 2),
            'max_drawdown': round(max_dd, 2),
            'total_return': round(total_return, 2),
            'gross_return': gross_return,
            'fee_drag_pct': fee_drag_pct,
            'total_fees_usd': total_fees_usd,
            'total_slippage_usd': total_slippage_usd,
            'max_consec_losses': max_consec_losses,
            'expectancy': round(expectancy, 2),
            'var_95': round(float(np.percentile(df_trades['pnl_pct'].values, 5)), 2),
            'cvar_95': round(float(df_trades['pnl_pct'][df_trades['pnl_pct'] <= np.percentile(df_trades['pnl_pct'].values, 5)].mean()), 2) if len(df_trades) >= 5 else 0.0,
        }
    }

# ──────────────────────────────────────────────
# DEEP OHLCV-REPLAY BACKTEST
# ──────────────────────────────────────────────
def run_deep_backtest(pair: str = 'BTC/USDT', tf: str = '1h',
                      years: float = 3.0, hold_bars: int = 24,
                      pos_pct: float = 10.0) -> dict:
    """True OHLCV-replay backtest using paginated historical data.

    Unlike run_backtest() which replays stored scan signals (~282 rows),
    this fetches full historical OHLCV, runs the signal engine bar-by-bar,
    and simulates trades using actual future prices — no lookahead bias.

    Args:
        pair:      Trading pair (default 'BTC/USDT').
        tf:        Timeframe (default '1h').
        years:     Years of history to fetch (default 3.0).
        hold_bars: Bars to hold before checking target/stop (default 24 for 1h = 1 day).
        pos_pct:   Fixed position size % of portfolio (default 10%).

    Returns:
        dict with keys: trades (DataFrame), metrics (dict), pair, tf, n_bars, years
    """
    import time as _time

    tf_bar_hours = {'1h': 1, '4h': 4, '1d': 24, '1w': 168}
    bar_hours = tf_bar_hours.get(tf, 1)
    total_bars = int(years * 365 * 24 / bar_hours)
    # OKX/Kraken limit per request is 300 bars; paginate
    bars_per_req = 300
    _MAX_BARS = 2000  # cap to avoid very long runtimes

    ta_ex = get_exchange_instance(TA_EXCHANGE)
    if not ta_ex:
        return {"error": "Exchange unavailable", "trades": pd.DataFrame(), "metrics": {}}

    try:
        # Paginate backwards to collect full history
        all_candles = []
        since_ms = None
        pages = max(1, min(total_bars // bars_per_req + 1, _MAX_BARS // bars_per_req))
        end_ms = int(_time.time() * 1000)
        bar_ms = bar_hours * 3600 * 1000

        for page in range(pages):
            fetch_since = end_ms - (page + 1) * bars_per_req * bar_ms
            try:
                candles = ta_ex.fetch_ohlcv(pair, tf, since=fetch_since, limit=bars_per_req)
                if not candles:
                    break
                all_candles = candles + all_candles
                _time.sleep(0.2)  # respect rate limits
            except Exception as e:
                logging.warning(f"run_deep_backtest page {page} failed: {e}")
                break

        if len(all_candles) < 100:
            return {"error": f"Insufficient data: only {len(all_candles)} bars fetched",
                    "trades": pd.DataFrame(), "metrics": {}}

        # Deduplicate and sort
        seen_ts = set()
        unique_candles = []
        for c in all_candles:
            if c[0] not in seen_ts:
                seen_ts.add(c[0])
                unique_candles.append(c)
        unique_candles.sort(key=lambda x: x[0])

        df_full = pd.DataFrame(unique_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_full['timestamp'] = pd.to_datetime(df_full['timestamp'], unit='ms', utc=True)
        df_full = df_full.set_index('timestamp')
        n_bars = len(df_full)

        # Minimum warmup bars for indicators (Ichimoku = 52, BB = 20, etc.)
        warmup = 100
        if n_bars < warmup + hold_bars + 10:
            return {"error": f"Need >{warmup + hold_bars} bars, got {n_bars}",
                    "trades": pd.DataFrame(), "metrics": {}}

        # Bar-by-bar simulation
        trades = []
        equity = float(PORTFOLIO_SIZE_USD)
        peak_equity = equity
        max_dd = 0.0

        for i in range(warmup, n_bars - hold_bars):
            df_slice = df_full.iloc[max(0, i - OHLCV_LIMIT): i + 1].copy()
            if len(df_slice) < 60:
                continue

            try:
                df_enriched = _enrich_df(df_slice)
                conf, vol_ok, *_ = calculate_signal_confidence(df_enriched, tf, 50, 'N/A', {})
            except Exception:
                continue

            if not vol_ok:
                continue

            direction = get_signal_direction(conf)
            if direction in ('NEUTRAL', 'LOW VOL', 'NO DATA'):
                continue
            is_buy = 'BUY' in direction

            entry_price = float(df_full['close'].iloc[i])
            if entry_price <= 0:
                continue

            # Compute target/stop from ATR
            atr_raw = float(compute_atr(df_slice).iloc[-1])
            atr_val = atr_raw if np.isfinite(atr_raw) and atr_raw > 0 else entry_price * 0.02
            multiplier = RISK_MODE_ATR.get('Trending', 2.0)
            stop_dist = atr_val * multiplier
            target_dist = stop_dist * 2.0  # 2:1 R:R

            if is_buy:
                stop = entry_price - stop_dist
                target = entry_price + target_dist
            else:
                stop = entry_price + stop_dist
                target = entry_price - target_dist

            # Simulate forward hold_bars
            exit_price = None
            exit_reason = 'Hold'
            for j in range(1, hold_bars + 1):
                future = df_full.iloc[i + j]
                h, l = float(future['high']), float(future['low'])
                if is_buy:
                    if l <= stop:
                        exit_price = stop; exit_reason = 'Stop'; break
                    if h >= target:
                        exit_price = target; exit_reason = 'Target'; break
                else:
                    if h >= stop:
                        exit_price = stop; exit_reason = 'Stop'; break
                    if l <= target:
                        exit_price = target; exit_reason = 'Target'; break
            if exit_price is None:
                exit_price = float(df_full['close'].iloc[i + hold_bars])
                exit_reason = 'Timeout'

            size_usd = equity * pos_pct / 100.0
            if is_buy:
                pnl_pct = (exit_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100

            # Realistic fees: 0.1% round-trip taker
            fee_pct = 0.10
            pnl_pct -= fee_pct
            pnl_usd = size_usd * pnl_pct / 100
            equity += pnl_usd
            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity * 100
            max_dd = max(max_dd, dd)

            trades.append({
                'bar_idx':      i,
                'timestamp':    df_full.index[i].isoformat(),
                'pair':         pair,
                'direction':    direction,
                'confidence':   round(conf, 1),
                'entry':        round(entry_price, 6),
                'exit':         round(exit_price, 6),
                'exit_reason':  exit_reason,
                'pnl_pct':      round(pnl_pct, 4),
                'pnl_usd':      round(pnl_usd, 2),
                'equity':       round(equity, 2),
            })

        if not trades:
            return {"error": "No trades generated", "trades": pd.DataFrame(), "metrics": {}}

        df_trades = pd.DataFrame(trades)
        wins = df_trades[df_trades['pnl_pct'] > 0]
        losses = df_trades[df_trades['pnl_pct'] <= 0]
        pnl_arr = df_trades['pnl_pct'].values
        total_return = round((equity - PORTFOLIO_SIZE_USD) / PORTFOLIO_SIZE_USD * 100, 2)
        win_rate = round(len(wins) / len(df_trades) * 100, 1)
        avg_pnl = round(float(pnl_arr.mean()), 4)
        profit_factor = (
            round(float(wins['pnl_pct'].sum() / abs(losses['pnl_pct'].sum())), 3)
            if len(losses) > 0 and abs(losses['pnl_pct'].sum()) > 0 else float('inf')
        )
        n_ret = len(pnl_arr)
        sharpe = round(float(pnl_arr.mean() / (pnl_arr.std() + 1e-9) * np.sqrt(n_ret)), 3)

        metrics = {
            'total_trades':    len(df_trades),
            'win_rate':        win_rate,
            'avg_pnl':         avg_pnl,
            'total_return':    total_return,
            'profit_factor':   profit_factor,
            'sharpe':          sharpe,
            'max_drawdown':    round(max_dd, 2),
            'final_equity':    round(equity, 2),
            'n_bars':          n_bars,
            'years_tested':    round(n_bars * bar_hours / 8760, 2),
        }

        return {
            'trades':   df_trades,
            'metrics':  metrics,
            'pair':     pair,
            'tf':       tf,
            'n_bars':   n_bars,
            'years':    metrics['years_tested'],
        }

    except Exception as e:
        logging.warning(f"run_deep_backtest failed: {e}")
        return {"error": str(e), "trades": pd.DataFrame(), "metrics": {}}


# ──────────────────────────────────────────────
# MONTE CARLO SIMULATION
# ──────────────────────────────────────────────
def run_monte_carlo(trades_df: pd.DataFrame, n_sim: int = 1000,
                    initial_equity: float = None) -> dict:
    """
    Bootstrap Monte Carlo simulation on the backtest trade sequence.
    Resamples trade PnLs with replacement n_sim times to estimate the distribution
    of outcomes — answering: "What range of equity / drawdown should I expect?"

    Args:
        trades_df: DataFrame with 'pnl_pct' (%) and optionally 'pos_pct' (%) columns.
        n_sim: Number of bootstrap simulations (default 1000).
        initial_equity: Starting portfolio value (defaults to PORTFOLIO_SIZE_USD).

    Returns dict with percentile stats, or {'error': str} on failure.
    """
    if initial_equity is None:
        initial_equity = PORTFOLIO_SIZE_USD

    if trades_df is None or len(trades_df) < 5:
        return {'error': 'Need at least 5 trades for Monte Carlo'}

    pnl_fracs = trades_df['pnl_pct'].dropna().values / 100.0
    if 'pos_pct' in trades_df.columns:
        pos_fracs = trades_df['pos_pct'].dropna().values / 100.0
        # Align lengths (some rows might have NaN in pos_pct)
        min_len = min(len(pnl_fracs), len(pos_fracs))
        pnl_fracs = pnl_fracs[:min_len]
        pos_fracs = pos_fracs[:min_len]
    else:
        pos_fracs = np.full(len(pnl_fracs), 0.10)

    n_trades = len(pnl_fracs)
    rng = np.random.default_rng(seed=42)

    # Vectorized bootstrap: sample all simulations at once (n_sim × n_trades matrix)
    # Dollar gain per trade = pnl_frac × (initial_equity × pos_frac)
    dollar_gains = pnl_fracs * (initial_equity * pos_fracs)  # shape (n_trades,)
    idx_matrix = rng.integers(0, n_trades, size=(n_sim, n_trades))  # (n_sim, n_trades)
    sampled = dollar_gains[idx_matrix]                               # (n_sim, n_trades)

    # Cumulative equity path per simulation
    equity_paths = initial_equity + np.cumsum(sampled, axis=1)       # (n_sim, n_trades)

    final_equities = equity_paths[:, -1]                             # (n_sim,)

    # Vectorized max drawdown: running max then worst trough
    running_max = np.maximum.accumulate(equity_paths, axis=1)        # (n_sim, n_trades)
    drawdowns = (equity_paths - running_max) / running_max * 100.0   # (n_sim, n_trades)
    max_drawdowns = drawdowns.min(axis=1)                            # (n_sim,)

    pct_profitable = float((final_equities > initial_equity).mean() * 100)

    return {
        'n_sim': n_sim,
        'n_trades': n_trades,
        'initial_equity': initial_equity,
        'equity_p5':   round(float(np.percentile(final_equities, 5)),  0),
        'equity_p25':  round(float(np.percentile(final_equities, 25)), 0),
        'equity_p50':  round(float(np.percentile(final_equities, 50)), 0),
        'equity_p75':  round(float(np.percentile(final_equities, 75)), 0),
        'equity_p95':  round(float(np.percentile(final_equities, 95)), 0),
        'equity_mean': round(float(final_equities.mean()), 0),
        'mdd_p5':  round(float(np.percentile(max_drawdowns, 5)),  2),
        'mdd_p25': round(float(np.percentile(max_drawdowns, 25)), 2),
        'mdd_p50': round(float(np.percentile(max_drawdowns, 50)), 2),
        'mdd_p75': round(float(np.percentile(max_drawdowns, 75)), 2),
        'pct_profitable': round(pct_profitable, 1),
        'all_final_equities': final_equities.tolist(),
        'all_max_drawdowns':  max_drawdowns.tolist(),
    }


# ──────────────────────────────────────────────
# MAIN SCAN
# ──────────────────────────────────────────────
def _scan_pair(pair, ta_ex, fng_value, fng_category,
               funding_map, oi_map, iv_map, ob_map,
               master_df, circuit_breaker, start_time,
               trending_coins=None, global_mkt=None, btc_df=None, cvd_map=None):
    """Process one pair across all timeframes. Called from ThreadPoolExecutor workers."""
    if trending_coins is None:
        trending_coins = []
    if global_mkt is None:
        global_mkt = {}
    onchain_data = fetch_onchain_metrics(pair)
    # DefiLlama TVL — chain-level DeFi activity context
    try:
        import data_feeds as _df
        tvl_data = _df.get_defillama_tvl(pair)
    except Exception:
        tvl_data = {'tvl_usd': 0.0, 'change_7d': 0.0, 'signal': 'N/A', 'chain': None, 'error': 'failed'}

    tf_data = {}
    confidence_list = []
    regime_1h = "Neutral"
    bias_1h = "Balanced"
    last_df = None
    current_price = None
    signal_agent_votes = {}  # F4: per-agent votes from primary TF (1h preferred)

    for tf in TIMEFRAMES:
        df = robust_fetch_ohlcv(ta_ex, pair, tf)
        if df.empty:
            tf_data[tf] = {'confidence': 0, 'direction': 'NO DATA', 'volume_passed': False,
                           'rsi': 'N/A', 'stoch': 'N/A', 'adx': 'N/A', 'vwap': 'N/A',
                           'ichimoku': 'N/A', 'fib_closest': 'N/A', 'macd_div': 'N/A',
                           'supertrend': 'N/A', 'sr_status': 'N/A', 'regime': 'N/A',
                           'strategy_bias': 'N/A', 'agent_vote': 0, 'consensus': 0, 'stat_arb': 'NEUTRAL'}
            # Don't include NO DATA timeframes in the average
            continue

        # Enrich once here — calculate_signal_confidence will detect and skip re-enrichment (PERF-01)
        df = _enrich_df(df)

        (conf, vol_passed, macd_div, div_strength, supertrend_str,
         sr_str, regime_str, strategy_bias, agent_score, consensus, stat_arb,
         _tf_agent_votes) = calculate_signal_confidence(
            df, tf, fng_value, fng_category, onchain_data, pair,
            iv_data=iv_map.get(pair), ob_data=ob_map.get(pair),
            btc_df=btc_df, cvd_data=(cvd_map or {}).get(pair),
        )

        # Skip timeframes where calculation completely failed (returned 0 conf AND no volume)
        if conf == 0 and not vol_passed:
            tf_data[tf] = {'confidence': 0, 'direction': 'NO DATA', 'volume_passed': False,
                           'rsi': 'N/A', 'stoch': 'N/A', 'adx': 'N/A', 'vwap': 'N/A',
                           'ichimoku': 'N/A', 'fib_closest': 'N/A', 'macd_div': 'N/A',
                           'supertrend': 'N/A', 'sr_status': 'N/A', 'regime': 'N/A',
                           'strategy_bias': 'N/A', 'agent_vote': 0, 'consensus': 0, 'stat_arb': 'NEUTRAL'}
            continue

        direction = get_signal_direction(conf) if vol_passed else "LOW VOL"
        confidence_list.append(conf if vol_passed else round(conf * 0.6, 1))

        df_enriched = df  # already enriched above
        rsi_val = df_enriched['rsi'].iloc[-1] if 'rsi' in df_enriched.columns else 'N/A'
        stoch_k = df_enriched['stoch_k'].iloc[-1] if 'stoch_k' in df_enriched.columns else 'N/A'
        stoch_d = df_enriched['stoch_d'].iloc[-1] if 'stoch_d' in df_enriched.columns else 'N/A'
        adx_val = float(df_enriched['adx'].iloc[-1]) if 'adx' in df_enriched.columns else compute_adx(df)
        vwap_val = df_enriched['vwap'].iloc[-1] if 'vwap' in df_enriched.columns else 'N/A'
        sa = df_enriched['senkou_span_a'].iloc[-1] if 'senkou_span_a' in df_enriched.columns else 'N/A'
        sb = df_enriched['senkou_span_b'].iloc[-1] if 'senkou_span_b' in df_enriched.columns else 'N/A'
        close = df['close'].iloc[-1]
        ichimoku_pos = ("Above Cloud" if not pd.isna(sa) and not pd.isna(sb) and close > max(sa, sb)
                        else "Below Cloud" if not pd.isna(sa) and not pd.isna(sb) and close < min(sa, sb)
                        else "In Cloud")
        fib_cl, _ = compute_fib_levels(df)

        # Candlestick patterns for display (score already applied in calculate_signal_confidence)
        candle_patterns, _ = detect_candlestick_patterns(df_enriched)
        patterns_str = ", ".join(candle_patterns) if candle_patterns else "None"

        # Funding rate — only meaningful for short timeframes; N/A for spot-only exchanges
        fr = funding_map.get(pair, {})
        if fr.get('error') or not fr.get('funding_rate_pct'):
            funding_str = "N/A"
        else:
            funding_str = f"{fr['funding_rate_pct']:+.4f}% ({fr.get('signal', '?')})"

        # Open interest (Binance futures — N/A for spot-only exchanges)
        oi = oi_map.get(pair, {})
        if oi.get('error') or not oi.get('oi_usd'):
            oi_str = "N/A"
        else:
            oi_usd = oi['oi_usd']
            oi_fmt = f"${oi_usd/1e9:.2f}B" if oi_usd >= 1e9 else f"${oi_usd/1e6:.0f}M"
            oi_str = f"{oi_fmt} ({oi.get('signal', '?')})"

        # On-chain summary (only on first TF to avoid redundant API display)
        onchain_str = "N/A"
        if tf == TIMEFRAMES[0] and onchain_data.get('source') == 'coingecko':
            onchain_str = (
                f"SOPR {onchain_data['sopr']:.3f} | "
                f"MVRV-Z {onchain_data['mvrv_z']:.2f} | "
                f"Vol/MCap {onchain_data['vol_mcap_ratio']:.3f}"
            )

        # Deribit IV (BTC/ETH only; show on first TF only)
        iv_str = "N/A"
        iv = iv_map.get(pair, {})
        if tf == TIMEFRAMES[0] and iv.get('source') == 'deribit':
            iv_str = f"DVOL {iv['iv']:.1f} | {iv['iv_percentile']:.0f}th pct | {iv['signal']}"

        # Order book imbalance
        ob_str = "N/A"
        ob = (ob_map or {}).get(pair, {})
        if not ob.get('error') and ob.get('signal') not in (None, 'N/A'):
            ob_str = f"{ob['signal']} (imb: {ob['imbalance']:+.3f})"

        # CVD — Cumulative Volume Delta (show on first TF only; applies score bias)
        cvd_str = "N/A"
        cvd = (cvd_map or {}).get(pair, {})
        if tf == TIMEFRAMES[0] and not cvd.get('error') and cvd.get('source') == 'okx_trades':
            cvd_str = f"{cvd['signal']} (imb: {cvd['imbalance']:+.3f}, Δ{cvd['cvd_change_pct']:+.1f}%)"

        # DefiLlama TVL (show on first TF only)
        tvl_str = "N/A"
        if tf == TIMEFRAMES[0] and not tvl_data.get('error') and tvl_data.get('tvl_usd', 0) > 0:
            tvl_usd = tvl_data['tvl_usd']
            tvl_fmt = f"${tvl_usd/1e9:.2f}B" if tvl_usd >= 1e9 else f"${tvl_usd/1e6:.0f}M"
            tvl_str = f"{tvl_fmt} {tvl_data['signal']} ({tvl_data['change_7d']:+.1f}% 7d)"

        tf_data[tf] = {
            'confidence': conf,
            'direction': direction,
            'volume_passed': vol_passed,
            'rsi': round(float(rsi_val), 1) if not pd.isna(rsi_val) else 'N/A',
            'stoch': f"{round(float(stoch_k),1)}/{round(float(stoch_d),1)}" if not pd.isna(stoch_k) else 'N/A',
            'adx': round(adx_val, 1),
            'vwap': round(float(vwap_val), 2) if not pd.isna(vwap_val) else 'N/A',
            'ichimoku': ichimoku_pos,
            'fib_closest': fib_cl,
            'macd_div': f"{macd_div} ({div_strength})",
            'supertrend': supertrend_str,
            'sr_status': sr_str,
            'regime': regime_str,
            'strategy_bias': strategy_bias,
            'agent_vote': round(agent_score, 1),
            'consensus': round(consensus, 2),
            'stat_arb': stat_arb,
            'patterns': patterns_str,
            'funding': funding_str,
            'open_interest': oi_str,
            'onchain': onchain_str,
            'options_iv': iv_str,
            'ob_depth': ob_str,
            'cvd': cvd_str,
            'tvl': tvl_str,
        }

        if tf == '1h':
            regime_1h = regime_str.split(' (')[0].replace("Regime: ", "")
            bias_1h = strategy_bias
            last_df = df
            current_price = close
            signal_agent_votes = _tf_agent_votes  # F4: capture 1h TF agent votes for feedback

        if tf == TIMEFRAMES[0] and current_price is None:
            current_price = close
            last_df = df
            signal_agent_votes = _tf_agent_votes  # F4: fallback to first TF if no 1h

    # Dynamic MTF weights — heavier weight on higher timeframes; scales with actual TF count
    n = len(confidence_list)
    if n == 0:
        mtf_weights = []
    elif n == 1:
        mtf_weights = [1.0]
    elif n == 2:
        mtf_weights = [0.35, 0.65]
    elif n == 3:
        mtf_weights = [0.20, 0.35, 0.45]
    else:  # 4+
        base = [0.10, 0.15, 0.30, 0.45]
        if n > 4:
            # Equal weights normalised for more than 4 TFs
            mtf_weights = [1.0 / n] * n
        else:
            mtf_weights = base
    mtf_alignment = 0.0
    for j, c in enumerate(confidence_list[:len(mtf_weights)]):
        mtf_alignment += c * mtf_weights[j]
    mtf_alignment = round(mtf_alignment, 1)

    conf_avg = round(sum(confidence_list) / len(confidence_list), 1) if confidence_list else 0

    # ── Trending bonus: CoinGecko top-7 trending → +8 pts when already bullish/bearish ──
    _base_currency = pair.split("/")[0].upper() if "/" in pair else pair.upper()
    pair_is_trending = _base_currency in trending_coins
    if pair_is_trending and abs(conf_avg - 50) >= 5:  # only boost when signal has direction
        conf_avg = min(round(conf_avg + 8.0, 1), 99.9) if conf_avg > 50 else max(round(conf_avg - 8.0, 1), 0.1)

    # ── BTC Dominance macro adjustment (altcoins only) ──────────────────────────
    # BTC_DOMINANT (dom>55%) weakens altcoin momentum; ALTSEASON (<42%) amplifies it.
    if pair not in ('BTC/USDT', 'ETH/USDT') and conf_avg != 50:
        _btc_dom = global_mkt.get('btc_dominance', 50.0)
        _alt_label = global_mkt.get('altcoin_season_label', 'MIXED')
        if _btc_dom > 55.0:                                # macro headwind for alts
            _nudge = -5.0 if conf_avg > 50 else 5.0       # push toward neutral
            conf_avg = round(max(min(conf_avg + _nudge, 99.9), 0.1), 1)
        elif _alt_label == 'ALTSEASON':                    # macro tailwind for alts
            _nudge = 5.0 if conf_avg > 50 else -5.0       # push away from neutral
            conf_avg = round(max(min(conf_avg + _nudge, 99.9), 0.1), 1)

    direction_avg = get_signal_direction(conf_avg)

    # ── MTF confirmation gate ──────────────────────────────────────────────────
    # STRONG signals require the next higher TF to agree.
    # 1H STRONG BUY → check 4H/1D; if they say SELL, downgrade to BUY.
    mtf_confirmed   = True
    higher_tf_dir   = None
    if MTF_GATE_ENABLED and direction_avg in ('STRONG BUY', 'STRONG SELL'):
        for htf in ('4h', '1d'):
            htf_info = tf_data.get(htf, {})
            htf_dir  = htf_info.get('direction', '')
            if htf_dir and htf_dir not in ('NO DATA', 'N/A', 'LOW VOL', ''):
                higher_tf_dir = htf_dir
                if direction_avg == 'STRONG BUY' and 'SELL' in htf_dir:
                    direction_avg  = 'BUY'
                    mtf_confirmed  = False
                elif direction_avg == 'STRONG SELL' and 'BUY' in htf_dir:
                    direction_avg  = 'SELL'
                    mtf_confirmed  = False
                break   # use closest available higher TF only

    # Regime-aware HIGH_CONF threshold: trending markets allow a lower bar;
    # ranging / volatile markets require higher confidence to filter noise.
    _hc_threshold = _REGIME_HIGH_CONF_THRESHOLDS.get(regime_1h, HIGH_CONF_THRESHOLD)
    is_high_conf = conf_avg >= _hc_threshold and mtf_alignment >= HIGH_MTF_THRESHOLD

    entry, exit_, risk_info = (None, None, None)
    if last_df is not None:
        entry, exit_, risk_info = generate_entry_exit(last_df, regime_1h, pair, master_df, direction_avg)

    # Override leverage_rec with actual confidence now that we have it.
    # Re-derive ATR% from stop distance / entry (more accurate than the placeholder).
    if risk_info is not None and entry and entry > 0 and risk_info.get('stop_loss'):
        _atr_pct_real = abs(entry - risk_info['stop_loss']) / entry / max(RISK_MODE_ATR.get(regime_1h, 2.0), 1e-9)
        risk_info['leverage_rec'] = recommend_leverage(conf_avg, _atr_pct_real)

    if entry and exit_ and signal_agent_votes:
        # F-SNAP: build indicator snapshot from last_df for LightGBM retraining
        _snaps = {}
        if last_df is not None and len(last_df) > 0:
            try:
                _ldf = last_df
                if 'rsi' in _ldf.columns:
                    _snaps['rsi'] = float(_ldf['rsi'].iloc[-1])
                if 'macd_hist' in _ldf.columns:
                    _snaps['macd_hist'] = float(_ldf['macd_hist'].iloc[-1])
                if 'bb_upper' in _ldf.columns and 'bb_lower' in _ldf.columns:
                    _cl = float(_ldf['close'].iloc[-1])
                    _bbu = float(_ldf['bb_upper'].iloc[-1])
                    _bbl = float(_ldf['bb_lower'].iloc[-1])
                    _bb_rng = _bbu - _bbl
                    _snaps['bb_pos'] = (_cl - _bbl) / _bb_rng if _bb_rng > 0 else 0.5
                if 'adx' in _ldf.columns:
                    _snaps['adx'] = float(_ldf['adx'].iloc[-1])
                if 'stoch_k' in _ldf.columns:
                    _snaps['stoch_k'] = float(_ldf['stoch_k'].iloc[-1])
                _snaps['volume_ok'] = bool(
                    tf_data.get(TIMEFRAMES[0], {}).get('volume_passed', False)
                )
                _snaps['regime'] = regime_1h
            except Exception:
                pass  # snapshot is best-effort — never block signal logging
        log_feedback(pair, direction_avg, entry, exit_, conf_avg,
                     signal_agent_votes, indicator_snaps=_snaps)

    # Apply circuit breaker: if portfolio drawdown exceeds threshold, suppress new entries
    effective_direction = direction_avg
    _cb_triggered = circuit_breaker['triggered']
    if _cb_triggered and direction_avg not in ('NEUTRAL', 'LOW VOL', 'NO DATA'):
        effective_direction = 'NEUTRAL'  # Downgrade — no new entries during drawdown protection

    result = {
        'pair':               pair,
        'price_usd':          round(current_price, 4) if current_price else None,
        'confidence_avg_pct': conf_avg,
        'direction':          effective_direction,
        'strategy_bias':      bias_1h,
        'mtf_alignment':      mtf_alignment,
        'mtf_confirmed':      mtf_confirmed,
        'higher_tf_direction': higher_tf_dir,
        'high_conf':          is_high_conf and not _cb_triggered,
        'fng_value':          fng_value,
        'fng_category':       fng_category,
        'entry':              entry if not _cb_triggered else None,
        'exit':               exit_ if not _cb_triggered else None,
        'timeframes':         tf_data,
        'scan_sec':           round(time.time() - start_time, 1),
        'scan_timestamp':     datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'circuit_breaker':    circuit_breaker,
        # Social + macro context keys
        'trending':           pair_is_trending,
        'altcoin_season':     global_mkt.get('altcoin_season_label', 'N/A'),
        # Fallback keys always present so downstream consumers never get KeyError
        'regime':             f"Regime: {regime_1h}",
        'sr_status':          tf_data.get('1h', {}).get('sr_status', 'N/A'),
    }
    if risk_info:
        _sup = None if _cb_triggered else risk_info['stop_loss']
        result.update({
            'stop_loss':              _sup,
            'tp1':                    None if _cb_triggered else risk_info.get('tp1'),
            'tp2':                    None if _cb_triggered else risk_info.get('tp2'),
            'tp3':                    None if _cb_triggered else risk_info.get('tp3'),
            'rr_ratios':              risk_info.get('rr_ratios'),
            'leverage_rec':           risk_info.get('leverage_rec'),
            'risk_pct':               risk_info['risk_pct'],
            'position_size_usd':      risk_info['position_size_usd'],
            'position_size_pct':      risk_info['position_size_pct'],
            'risk_mode':              risk_info['risk_mode'],
            'corr_with_btc':          risk_info.get('corr_with_btc'),
            'corr_adjusted_size_pct': risk_info.get('corr_adjusted_size_pct'),
            'regime':                 f"Regime: {regime_1h}",
            'sr_status':              tf_data.get('1h', {}).get('sr_status', 'N/A'),
        })
    return result


def run_scan(progress_callback=None):
    """
    Run full multi-timeframe scan across all pairs in parallel using ThreadPoolExecutor.
    progress_callback(pair_index, total_pairs, pair_name) called after each pair completes.
    Returns list of result dicts in original PAIRS order.
    """
    start_time = time.time()
    reset_kelly_cache()      # Compute Kelly once per scan — reused by all pairs (PERF-03)
    reset_agent_acc_cache()  # Prefetch agent accuracy weights once — avoids 24+ DB queries (PERF-06)
    fng_value, fng_category = fetch_fear_greed()
    ta_ex = get_exchange_instance(TA_EXCHANGE)
    if not ta_ex:
        return []

    # Drawdown circuit breaker — checked once per scan run
    circuit_breaker = check_drawdown_circuit_breaker()

    # Fetch funding rates, open interest, and on-chain data once per scan
    import data_feeds as _data_feeds
    try:
        funding_map = _data_feeds.get_funding_rates_batch(PAIRS)
    except Exception as e:
        logging.warning(f"Funding rates batch fetch failed: {e}")
        funding_map = {}

    try:
        oi_map = _data_feeds.get_open_interest_batch(PAIRS)
    except Exception as e:
        logging.warning(f"Open interest batch fetch failed: {e}")
        oi_map = {}

    try:
        iv_map = _data_feeds.get_options_iv_batch(PAIRS)
    except Exception as e:
        logging.warning(f"Options IV batch fetch failed: {e}")
        iv_map = {}

    try:
        ob_map = _data_feeds.get_orderbook_batch(PAIRS)
    except Exception as e:
        logging.warning(f"Order book batch fetch failed: {e}")
        ob_map = {}

    try:
        cvd_map = _data_feeds.get_cvd_batch(PAIRS)
    except Exception as e:
        logging.warning(f"CVD batch fetch failed: {e}")
        cvd_map = {}

    try:
        trending_coins = _data_feeds.get_trending_coins()
    except Exception as e:
        logging.warning(f"Trending coins fetch failed: {e}")
        trending_coins = []

    try:
        global_mkt = _data_feeds.get_global_market()
    except Exception as e:
        logging.warning(f"Global market fetch failed: {e}")
        global_mkt = {}

    # PERF-02: limit to recent 200 rows — only used for BTC correlation; full table scan is wasteful
    master_df = _db.get_signals_df(limit=200)

    # PERF-StatArb: pre-fetch BTC/USDT 1d once — shared by all non-BTC pairs for cointegration
    btc_df_for_scan = None
    try:
        ohlcv_btc = ta_ex.fetch_ohlcv('BTC/USDT', '1d', limit=STAT_ARB_LOOKBACK)
        btc_df_for_scan = pd.DataFrame(ohlcv_btc, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    except Exception as _e:
        logging.warning(f"StatArb BTC/USDT pre-fetch failed: {_e}")

    # ── Parallel scan using thread pool ──────────────────────────────────────
    completed = [0]
    result_lock = threading.Lock()

    def _scan_with_progress(pair):
        result = _scan_pair(
            pair, ta_ex, fng_value, fng_category,
            funding_map, oi_map, iv_map, ob_map,
            master_df, circuit_breaker, start_time,
            trending_coins=trending_coins, global_mkt=global_mkt,
            btc_df=btc_df_for_scan, cvd_map=cvd_map,
        )
        with result_lock:
            completed[0] += 1
            if progress_callback:
                progress_callback(completed[0], len(PAIRS), pair)
        return result

    max_workers = min(len(PAIRS), 4)  # cap at 4 to respect exchange rate limits
    pair_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_scan_with_progress, pair): pair for pair in PAIRS}
        for future in concurrent.futures.as_completed(futures):
            pair = futures[future]
            try:
                result = future.result()
                if result:
                    pair_results[pair] = result
            except Exception as e:
                logging.warning(f"[scan] {pair} failed: {e}")

    # Restore original PAIRS order
    results = [pair_results[p] for p in PAIRS if p in pair_results]
    return results


# ──────────────────────────────────────────────
# SINGLE-PAIR SCAN (used by the autonomous agent)
# ──────────────────────────────────────────────
def scan_single_pair(pair: str) -> dict | None:
    """
    Lightweight single-pair scan wrapper for use by the autonomous agent
    (_node_enrich_signals in agent.py).

    Handles all context setup (ta_ex, F&G, one-pair data feeds) internally
    so callers only need to pass the pair symbol.  Uses the same _scan_pair()
    path as run_scan() — signals are identical to a full scan result.

    Returns the signal result dict, or None if the exchange is unreachable.
    """
    ta_ex = get_exchange_instance(TA_EXCHANGE)
    if not ta_ex:
        return None

    fng_value, fng_category = fetch_fear_greed()

    import data_feeds as _data_feeds

    def _safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return {}

    funding_map     = _safe(_data_feeds.get_funding_rates_batch,  [pair])
    oi_map          = _safe(_data_feeds.get_open_interest_batch,   [pair])
    iv_map          = _safe(_data_feeds.get_options_iv_batch,      [pair])
    ob_map          = _safe(_data_feeds.get_orderbook_batch,       [pair])
    cvd_map         = _safe(_data_feeds.get_cvd_batch,             [pair])
    trending_coins  = []
    try:
        trending_coins = _data_feeds.get_trending_coins()
    except Exception:
        pass
    global_mkt = {}
    try:
        global_mkt = _data_feeds.get_global_market()
    except Exception:
        pass

    master_df       = _db.get_signals_df(limit=200)
    circuit_breaker = check_drawdown_circuit_breaker()

    btc_df = None
    if pair != 'BTC/USDT':
        try:
            ohlcv_btc = ta_ex.fetch_ohlcv('BTC/USDT', '1d', limit=STAT_ARB_LOOKBACK)
            btc_df = pd.DataFrame(
                ohlcv_btc,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'],
            )
        except Exception:
            pass

    return _scan_pair(
        pair, ta_ex, fng_value, fng_category,
        funding_map, oi_map, iv_map, ob_map,
        master_df, circuit_breaker, time.time(),
        trending_coins=trending_coins, global_mkt=global_mkt,
        btc_df=btc_df, cvd_map=cvd_map,
    )


# ──────────────────────────────────────────────
# WALK-FORWARD OUT-OF-SAMPLE VALIDATION
# ──────────────────────────────────────────────
def run_walk_forward(n_splits: int = 4, pair: str = 'BTC/USDT',
                     tf: str = '1h', hold_bars: int = 5) -> dict:
    """
    Walk-forward out-of-sample validation.
    Fetches up to 800 bars, splits into n_splits non-overlapping windows.
    Each window: first 60% = warm-up (indicator stabilization), last 40% = test.
    Evaluates directional accuracy (confidence≥65 → BUY, ≤45 → SELL) vs next-hold_bars return.
    Reports per-window accuracy and aggregate mean ± std.
    Returns {'windows': [...], 'mean_accuracy': float, 'std_accuracy': float}
    or {'error': str} on failure.
    """
    try:
        exchange = get_exchange_instance(TA_EXCHANGE)
        if not exchange:
            return {'error': 'Exchange unavailable'}
        ohlcv = exchange.fetch_ohlcv(pair, tf, limit=800)
        df_all = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], unit='ms')
        df_all.set_index('timestamp', inplace=True)
    except Exception as e:
        return {'error': f'Data fetch failed: {e}'}

    n = len(df_all)
    if n < 150:
        return {'error': f'Insufficient data: {n} bars'}

    window_size = n // n_splits
    if window_size < 80:
        return {'error': f'Window too small ({window_size} bars). Reduce n_splits or use more data.'}

    # BUG-R04: include all keys returned by fetch_onchain_metrics() so that
    # _scan_pair onchain_str formatting (vol_mcap_ratio) doesn't KeyError.
    neutral_onchain = {'sopr': 1.0, 'mvrv_z': 0.0, 'net_flow': 0.0,
                       'whale_activity': False, 'vol_mcap_ratio': 0.0,
                       'price_24h_pct': 0.0, 'price_200d_pct': 0.0,
                       'source': 'neutral'}
    window_results = []

    for split_idx in range(n_splits):
        w_start = split_idx * window_size
        w_end = w_start + window_size if split_idx < n_splits - 1 else n
        df_window = df_all.iloc[w_start:w_end].copy()

        # Warm-up: first 60% (for indicator convergence); test: last 40%
        warmup_end = int(len(df_window) * 0.60)
        stride = 3

        correct = 0
        total = 0

        for bar_idx in range(warmup_end, len(df_window) - hold_bars, stride):
            # Slice up to this bar (minimum 50 bars needed)
            start_slice = max(0, bar_idx - 200)
            df_slice = df_window.iloc[start_slice:bar_idx + 1].copy()
            if len(df_slice) < 50:
                continue
            try:
                conf, vol_ok, *_ = calculate_signal_confidence(
                    df_slice, tf, fng_value=50, fng_category='Neutral',
                    onchain_data=neutral_onchain, pair=pair,
                )
                pred = 1 if conf >= 65 else (-1 if conf <= 45 else 0)
                if pred == 0:
                    continue
                abs_bar = w_start + bar_idx
                # BUG-L03: skip bar if future window extends past available data (no lookahead)
                if abs_bar + hold_bars >= n:
                    continue
                future_close = df_all['close'].iloc[abs_bar + hold_bars]
                current_close = df_all['close'].iloc[abs_bar]
                ret = (future_close - current_close) / current_close
                actual = 1 if ret > 0.001 else (-1 if ret < -0.001 else 0)
                if actual == 0:
                    continue
                if pred == actual:
                    correct += 1
                total += 1
            except Exception:
                continue

        accuracy = round(correct / total * 100, 1) if total > 0 else None
        period_start = df_window.index[warmup_end].strftime('%Y-%m-%d')
        period_end   = df_window.index[-1].strftime('%Y-%m-%d')
        window_results.append({
            'window': split_idx + 1,
            'period': f'{period_start} → {period_end}',
            'test_signals': total,
            'accuracy_pct': accuracy,
        })

    valid = [w['accuracy_pct'] for w in window_results if w['accuracy_pct'] is not None]
    mean_acc = round(float(np.mean(valid)), 1) if valid else None
    std_acc  = round(float(np.std(valid)), 1) if len(valid) > 1 else 0.0

    return {
        'windows': window_results,
        'mean_accuracy': mean_acc,
        'std_accuracy': std_acc,
        'n_splits': n_splits,
        'pair': pair,
        'tf': tf,
    }


# ──────────────────────────────────────────────
# OPTUNA ML WEIGHT OPTIMIZER
# ──────────────────────────────────────────────
def run_optuna_weight_optimization(n_trials: int = 50, pair: str = 'BTC/USDT',
                                    tf: str = '1h', hold_bars: int = 5) -> dict:
    """
    Bayesian weight optimization via Optuna TPE sampler.
    Pre-computes all indicators once on 300 bars of historical OHLCV, then evaluates
    n_trials weight configurations for directional accuracy (does signal ≥65 correctly
    predict price direction hold_bars bars later?).
    Optimizes: core, momentum, stoch, adx, vwap_ich, supertrend, regime, bonus.
    Saves best weights to dynamic_weights.json (non-optimized weights preserved).
    Returns {'best_weights', 'best_score', 'n_trials', 'train_bars', 'pair', 'tf'}
    or {'error': str} on failure.
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        return {'error': 'optuna not installed. Run: pip install optuna'}

    # ── Fetch OHLCV ──
    try:
        exchange = get_exchange_instance(TA_EXCHANGE)
        if not exchange:
            return {'error': 'Exchange unavailable'}
        ohlcv = exchange.fetch_ohlcv(pair, tf, limit=300)
        df_all = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], unit='ms')
        df_all.set_index('timestamp', inplace=True)
    except Exception as e:
        return {'error': f'Data fetch failed: {e}'}

    if len(df_all) < 100:
        return {'error': f'Insufficient data: {len(df_all)} bars'}

    # ── Pre-compute all indicators ONCE (fast numpy arrays) ──
    df_e = _enrich_df(df_all.copy())

    # ADX series (inline to get full series, not just last value)
    _tr = pd.concat([df_e['high'] - df_e['low'],
                     abs(df_e['high'] - df_e['close'].shift()),
                     abs(df_e['low'] - df_e['close'].shift())], axis=1).max(axis=1)
    _atr_r = _tr.rolling(14).mean()
    _up_m = df_e['high'] - df_e['high'].shift()
    _dn_m = df_e['low'].shift() - df_e['low']
    _pdi = 100 * pd.Series(np.where((_up_m > _dn_m) & (_up_m > 0), _up_m, 0),
                            index=df_e.index).rolling(14).mean() / _atr_r
    _mdi = 100 * pd.Series(np.where((_dn_m > _up_m) & (_dn_m > 0), _dn_m, 0),
                            index=df_e.index).rolling(14).mean() / _atr_r
    _dx = 100 * abs(_pdi - _mdi) / (_pdi + _mdi + 1e-6)
    adx_arr = _dx.rolling(14).mean().fillna(20.0).values

    # SuperTrend series (one Python loop over full df — O(n) once)
    _p, _m = SUPER_TREND_PERIOD, SUPER_TREND_MULTIPLIER
    _hl2 = (df_e['high'] + df_e['low']) / 2
    _atr_st = _tr.rolling(_p).mean()
    _ub = (_hl2 + _m * _atr_st).values.copy()
    _lb = (_hl2 - _m * _atr_st).values.copy()
    _close_a = df_e['close'].values
    st_up = np.ones(len(df_e), dtype=bool)
    for _i in range(1, len(df_e)):
        if _close_a[_i - 1] > _ub[_i - 1]:
            st_up[_i] = True
        elif _close_a[_i - 1] < _lb[_i - 1]:
            st_up[_i] = False
        else:
            st_up[_i] = st_up[_i - 1]
            if st_up[_i]:
                _lb[_i] = max(_lb[_i], _lb[_i - 1])
            else:
                _ub[_i] = min(_ub[_i], _ub[_i - 1])

    # Extract indicator arrays for zero-overhead access in objective
    rsi_a     = df_e['rsi'].fillna(50.0).values
    macd_a    = df_e['macd'].fillna(0.0).values
    msig_a    = df_e['macd_signal'].fillna(0.0).values
    mhist_a   = df_e['macd_hist'].fillna(0.0).values
    bbu_a     = df_e['bb_upper'].fillna(df_e['close']).values
    bbl_a     = df_e['bb_lower'].fillna(df_e['close']).values
    sk_a      = df_e['stoch_k'].fillna(50.0).values
    sd_a      = df_e['stoch_d'].fillna(50.0).values
    vwap_a    = df_e['vwap'].fillna(df_e['close']).values
    sa_a      = df_e['senkou_span_a'].values
    sb_a      = df_e['senkou_span_b'].values
    vol_a     = df_e['volume'].values
    vol_ma_a  = pd.Series(vol_a).rolling(20).mean().fillna(np.nanmean(vol_a)).values
    close_a   = df_e['close'].values

    n_bars = len(df_e)
    train_end = int(n_bars * 0.8)

    def objective(trial):
        tw = {
            'core':       trial.suggest_float('core',       0.05, 0.50),
            'momentum':   trial.suggest_float('momentum',   0.05, 0.40),
            'stoch':      trial.suggest_float('stoch',      0.03, 0.25),
            'adx':        trial.suggest_float('adx',        0.03, 0.20),
            'vwap_ich':   trial.suggest_float('vwap_ich',   0.03, 0.20),
            # T1-A: normalized to same scale as continuous weights (raw scores ±15/±12)
            'supertrend': trial.suggest_float('supertrend', 0.10, 1.50),
            'regime':     trial.suggest_float('regime',     0.10, 1.50),
            'bonus':      trial.suggest_float('bonus',      0.10, 1.0),
        }
        # T2-E: Collect per-trade returns for Sharpe ratio objective
        trade_returns = []
        stride = 5
        for idx in range(60, train_end - hold_bars, stride):
            p_now = close_a[idx]
            rsi   = rsi_a[idx]
            ml    = macd_a[idx];  ms = msig_a[idx]
            h     = mhist_a[idx]; ph = mhist_a[idx - 1] if idx > 0 else h
            bbu   = bbu_a[idx];   bbl = bbl_a[idx]
            bb_p  = (p_now - bbl) / (bbu - bbl + 1e-6)
            sk    = sk_a[idx];    sd = sd_a[idx]
            adx_v = adx_arr[idx]
            vwap_v = vwap_a[idx]
            _sa   = sa_a[idx] if not np.isnan(sa_a[idx]) else p_now
            _sb   = sb_a[idx] if not np.isnan(sb_a[idx]) else p_now
            vol_ok = vol_a[idx] > VOLUME_MULTIPLIER * vol_ma_a[idx]
            st    = st_up[idx]
            regime = ("Ranging" if adx_v < ADX_RANGE_THRESHOLD
                      else "Trending" if adx_v > ADX_TREND_THRESHOLD else "Neutral")

            # Core (RSI/MACD/BB)
            core = 0
            if rsi < 30:   core += 25
            elif rsi < 40: core += 15
            elif rsi > 70: core -= 20
            if ml > ms:    core += 20
            elif ml < ms:  core -= 15
            if bb_p < 0.15: core += 18
            elif bb_p > 0.85: core -= 15
            score = core * tw['core']

            # Momentum
            mom = 0
            if h > 0 and h > ph: mom += 18
            if vol_ok: mom += 15
            score += mom * tw['momentum']

            # Stochastic
            st_s = 0
            if sk < 20 and sk > sd:   st_s += 20
            elif sk > 80 and sk < sd: st_s -= 18
            score += st_s * tw['stoch']

            # ADX
            adx_s = 0
            if adx_v > 25:   adx_s += 12 if ml > 0 else -10
            elif adx_v < 20: adx_s += 5
            score += adx_s * tw['adx']

            # VWAP / Ichimoku
            vi = 0
            if p_now > vwap_v: vi += 10
            if p_now > max(_sa, _sb):   vi += 15
            elif p_now < min(_sa, _sb): vi -= 15
            score += vi * tw['vwap_ich']

            # SuperTrend (T1-A: normalized raw ±15 × weight)
            sup_raw = 0
            if st and (ml > ms or rsi < 40):       sup_raw = 15
            elif not st and (ml < ms or rsi > 60): sup_raw = -15
            score += sup_raw * tw['supertrend']

            # Regime (T1-A: normalized raw ±12 × weight)
            reg_raw = 0
            if regime == "Trending" and (st == (ml > ms)): reg_raw = 12
            elif regime == "Ranging":                        reg_raw = -12
            score += reg_raw * tw['regime']

            # Bonus
            bon = 0
            if rsi < 25: bon += 20
            if rsi > 75: bon -= 18
            if p_now < bbl * 1.01: bon += 15
            if p_now > bbu * 0.99: bon -= 12
            score += bon * tw['bonus']

            score = max(0.0, min(100.0, score))
            # T2-A: Apply sigmoid calibration to match calculate_signal_confidence behavior
            score = 100.0 / (1.0 + np.exp(-(score - 50.0) / 20.0))
            pred = 1 if score >= 55 else (-1 if score <= 45 else 0)
            if pred == 0:
                continue

            future_p = close_a[min(idx + hold_bars, n_bars - 1)]
            ret = (future_p - p_now) / p_now
            # T2-E: collect directional return (positive if prediction was correct direction)
            if pred == 1:
                trade_returns.append(ret)
            else:
                trade_returns.append(-ret)

        # T2-E: Sharpe ratio objective (maximizes risk-adjusted return, not just accuracy)
        if len(trade_returns) < 5:
            return -1.0
        r = np.array(trade_returns, dtype=np.float64)
        std = r.std()
        if std < 1e-8:
            return 0.0
        return float(r.mean() / std)

    study = optuna.create_study(
        direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    # BUG-M03: best_value is the Sharpe ratio (dimensionless), not a percentage.
    # Multiply by 100 only for display scaling; label it as "score" not "%".
    best_score = round(study.best_value, 4)  # raw Sharpe ratio

    # Merge optimized weights into live weights dict and persist (lock protects parallel scan workers)
    with _weights_lock:
        weights.update(best)
    save_weights()

    return {
        'best_weights': {k: round(v, 4) for k, v in best.items()},
        'best_score': best_score,
        'n_trials': n_trials,
        'train_bars': train_end,
        'pair': pair,
        'tf': tf,
    }


# ──────────────────────────────────────────────
# MAIN (for standalone execution)
# ──────────────────────────────────────────────
def compute_correlation_matrix(pairs=None, lookback_days=30, tf='1d'):
    """
    Fetch OHLCV close prices for each pair and return a pairwise Pearson
    correlation DataFrame of daily returns.
    Returns: (corr_df, error_str) — error_str is None on success.
    """
    if pairs is None:
        pairs = PAIRS
    exchange = get_exchange_instance(TA_EXCHANGE)
    if not exchange:
        return None, "Exchange unavailable"

    closes = {}
    limit = lookback_days + 10  # small buffer
    for pair in pairs:
        try:
            ohlcv = exchange.fetch_ohlcv(pair, tf, limit=limit)
            if not ohlcv:
                continue
            label = pair.replace('/USDT', '').replace('/USD', '')
            closes[label] = [o[4] for o in ohlcv[-lookback_days:]]
        except Exception as e:
            logging.warning(f"compute_correlation_matrix: fetch failed for {pair}: {e}")

    if len(closes) < 2:
        return None, f"Not enough pairs returned data (got {len(closes)})"

    min_len = min(len(v) for v in closes.values())
    df_closes = pd.DataFrame({k: v[-min_len:] for k, v in closes.items()})
    df_returns = df_closes.pct_change().dropna()
    if df_returns.empty or len(df_returns) < 2:
        return None, "Insufficient return data for correlation"

    corr_matrix = df_returns.corr()
    return corr_matrix, None


def run_cointegration_scan(pairs=None, tf='1d', lookback=100):
    """
    Scan ALL pair combinations for statistical cointegration (Engle-Granger test).

    Returns:
        (results, error_msg): tuple where results is a list of dicts sorted by
        |z_score| descending (only pairs with p-value < 0.05), and error_msg is
        None on success or a string describing the failure.

    Each result dict contains:
        pair_a, pair_b, pvalue, zscore, hedge_ratio, signal,
        signal_plain, mean_ratio, std_ratio
    """
    if pairs is None:
        pairs = PAIRS
    exchange = get_exchange_instance(TA_EXCHANGE)
    if not exchange:
        return [], "Exchange unavailable"

    # Fetch close prices for all pairs
    closes = {}
    for pair in pairs:
        try:
            ohlcv = exchange.fetch_ohlcv(pair, tf, limit=lookback + 10)
            if len(ohlcv) < lookback:
                continue
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            closes[pair] = df['close'].values[-lookback:]
        except Exception as e:
            logging.warning(f"run_cointegration_scan: fetch failed {pair}: {e}")

    valid_pairs = list(closes.keys())
    if len(valid_pairs) < 2:
        return [], f"Need ≥2 pairs with data (got {len(valid_pairs)})"

    results = []
    tested = set()
    for i, a in enumerate(valid_pairs):
        for b in valid_pairs[i + 1:]:
            key = (a, b)
            if key in tested:
                continue
            tested.add(key)
            try:
                p1 = closes[a]
                p2 = closes[b]
                _, pvalue, _ = coint(p1, p2)
                if pvalue > 0.05:
                    continue

                # Hedge ratio via OLS: p1 = hedge_ratio * p2 + const
                x = np.column_stack([p2, np.ones(len(p2))])
                coeffs, _, _, _ = np.linalg.lstsq(x, p1, rcond=None)
                hedge_ratio = float(coeffs[0])

                # Spread and z-score
                spread     = p1 - hedge_ratio * p2
                mean_spr   = float(spread.mean())
                std_spr    = float(spread.std())
                z          = float((spread[-1] - mean_spr) / std_spr) if std_spr != 0 else 0.0

                # Signal
                if z > STAT_ARB_Z_THRESHOLD:
                    signal = "SHORT_SPREAD"
                    signal_plain = f"Sell {a.split('/')[0]} / Buy {b.split('/')[0]} — spread unusually wide"
                elif z < -STAT_ARB_Z_THRESHOLD:
                    signal = "LONG_SPREAD"
                    signal_plain = f"Buy {a.split('/')[0]} / Sell {b.split('/')[0]} — spread unusually narrow"
                elif abs(z) < STAT_ARB_Z_EXIT:
                    signal = "EXIT_SPREAD"
                    signal_plain = "Spread near mean — close any open pair trade"
                else:
                    signal = "NEUTRAL"
                    signal_plain = "No actionable spread signal right now"

                results.append({
                    "pair_a":       a,
                    "pair_b":       b,
                    "pvalue":       round(float(pvalue), 4),
                    "zscore":       round(z, 3),
                    "hedge_ratio":  round(hedge_ratio, 4),
                    "signal":       signal,
                    "signal_plain": signal_plain,
                    "mean_ratio":   round(mean_spr, 6),
                    "std_ratio":    round(std_spr, 6),
                })
            except Exception as e:
                logging.debug(f"run_cointegration_scan: pair ({a},{b}) failed: {e}")

    results.sort(key=lambda r: abs(r["zscore"]), reverse=True)
    return results, None


def main():
    print(f"\nCrypto Model {VERSION}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    results = run_scan()
    run_feedback_loop()
    append_to_master(results)
    show_trends()
    run_backtest()
    print("\nAll done.")
    input("\nPress Enter to close...")

if __name__ == "__main__":
    main()
