# Claude Code — Master Agreement
# CRYPTO SIGNAL APP (aka SuperGrok Mathematically Model)
# Last updated: 2026-04-23
# Inherits from: ../master-template/CLAUDE_master_template.md

> This file overrides or extends the master template where noted.

---

## SECTION 1 — PERMISSION & AUTONOMY

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 2 — PROJECT SCOPE

```
  Name:          Crypto Signal App
  Path:          C:\Users\david\OneDrive\Desktop\Cowork\crypto-signal-app
  Repo:          github.com/davidduraesdd1-blip/crypto-signal-app
  Deploy:        https://cryptosignal-ddb1.streamlit.app/
  User role:     builder / designer / reviewer
  Collaborators: 1 (user)

  Purpose: Crypto signal engine. Coin-level technical indicators,
  composite signal scoring, Buy/Hold/Sell decision logic, regime
  detection, multi-timeframe analysis, backtesting. This codebase
  holds the reference signal logic that sibling projects adapt for
  their asset classes.

  Foundation repos this project references (READ ONLY):
    - rwa-infinity-model → portfolio construction patterns
    - flare-defi-model   → architectural template
```

---

## SECTION 3 — COMMIT & PUSH RULES

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 4 — UNIFIED AUDIT & TEST PROTOCOL

[VERBATIM FROM MASTER TEMPLATE.]

Project-specific emphasis:
- `composite_signal.py` is the gold reference for signal aggregation.
  Any change must include a backtest diff against the prior signal
  output on the 2023-2026 universe, committed to `docs/signal-regression/`.
- `cycle_indicators.py`, `top_bottom_detector.py` — math-heavy; each
  function has a fixture with a known-correct output.
- Backtest outputs live in `crypto_scan_*.csv` and
  `crypto_dashboard_*.xlsx` in the project root. Historical outputs are
  kept for regression comparison. Archive older than 90 days to
  `data/archive/`.

---

## SECTION 5 — RESEARCH STANDARDS

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 6 — BRANDING & IDENTITY

[MASTER TEMPLATE with project defaults:]

`BRAND_NAME = "Crypto Signal App"` (placeholder).

Tone: crypto-native and energetic. This is the most "retail-feeling" app
in the portfolio. Colors used more expressively than RWA or ETF advisor.

---

## SECTION 7 — USER LEVEL SYSTEM

[MASTER TEMPLATE with project-specific tier definitions:]

  Beginner:     Crypto-curious retail. Plain English. "This coin is
                showing strong upward momentum" not "RSI=73, divergence
                confirmed."
  Intermediate: Active traders. Condensed signal interpretations with
                key metric values visible.
  Advanced:     Quant-oriented. Raw RSI/MACD/ADX values, regime state,
                composite breakdown, Optuna hyperparameter outputs.

---

## SECTION 8 — DESIGN STANDARDS

[VERBATIM FROM MASTER TEMPLATE.]

Project tone note: more expressive color usage is allowed. Heatmaps,
regime-state banners, trend-strength gradients. Still no color-only
encoding (pair with shape/icon).

---

## SECTION 9 — MATH MODEL ARCHITECTURE

LAYER 1 — TECHNICAL: coin-level indicators. Momentum (RSI, MACD, ADX),
  trend (SMA/EMA crosses, Supertrend), volume (OBV, volume regimes),
  volatility (ATR, Bollinger width).

LAYER 2 — MACRO / FUNDAMENTAL: BTC dominance, total crypto market cap,
  DXY, risk-on/risk-off regime flags, equity index correlation.

LAYER 3 — SENTIMENT: Crypto Fear & Greed, funding rates, long/short
  ratios, Google Trends retail sentiment (via pytrends, graceful
  fallback if rate-limited), social volume from free sources.

LAYER 4 — ON-CHAIN: MVRV, SOPR, active addresses, exchange in/out flows,
  NVT, exchange reserve deltas.

COMPOSITE SIGNAL: weighted combination of all four layers in
`composite_signal.py`. Weights are config-driven and backtested.

REGIME DETECTION: HMM (hmmlearn) across macro + on-chain features —
identifies bull/bear/sideways/transition states. Composite weights
adjust per regime.

BACKTESTER: vectorized via pandas. Tests every signal change against
the historical universe; outputs saved to CSV + XLSX dashboard.

ML ENHANCEMENTS (optional, feature-flagged):
  - LightGBM / XGBoost classifier on composite + regime → signal
    confirmation
  - LangGraph for multi-step agent workflows on complex decisions

OUTPUT RULE: BUY / HOLD / SELL with confidence level. Always paired
with regime state and 3-5 bullet "why."

---

## SECTION 10 — DATA SOURCES & FALLBACK CHAINS

Crypto OHLCV:
  Primary:   ccxt library → OKX (highest quality free)
  Secondary: ccxt → Kraken
  Tertiary:  CoinGecko (daily-only fallback)
  Upgrade path: Kaiko, Cryptocompare paid

Fear & Greed:
  Primary:   alternative.me API (free, unlimited)

Funding rates:
  Primary:   OKX public API (free, unlimited)
  Secondary: Bybit public API (datacenter-IP quirks — test against
             Streamlit Cloud before relying on)

Google Trends:
  Primary:   pytrends (free, rate-limited, graceful fallback)

On-chain (BTC, ETH):
  Primary:   Glassnode free tier (rate-limited; cache aggressively)
  Secondary: Dune Analytics free queries
  Tertiary:  native RPC reads for exchange addresses (slow)

Token unlocks / vesting (Layer 4 — known forward sell-pressure events):
  Primary:   cryptorank.io /token-unlock endpoints (calendar + per-token vesting)
  Secondary: TokenUnlocks.app / token.unlocks.app (free, web scrape)
  Tertiary:  issuer documentation (manual, for new tokens cryptorank misses)

Fundraising / VC-sentiment data (Layer 3 sentiment — where smart money goes):
  Primary:   cryptorank.io /funds + funding-round endpoints (10,000+ rounds tracked)
  Secondary: CryptoFundraising (RootData mirror, free)
  Tertiary:  DropsTab public dashboards

CRITICAL: Binance US has datacenter-IP blocks; test on Streamlit Cloud
before committing. CoinMetrics community is slow but reliable.

---

## SECTION 11 — DEPLOYMENT ENVIRONMENTS

[MASTER TEMPLATE. Project-specific:]

Streamlit Cloud URL: https://cryptosignal-ddb1.streamlit.app/

Cold-start on Streamlit Cloud can be 30-60s due to model loading.
Lazy-load LightGBM / XGBoost — import only when the ML page is
opened.

---

## SECTION 12 — DATA REFRESH RATES

[MASTER TEMPLATE. Project-specific windows:]

- OHLCV intraday:      5 min cache during market hours (24/7 for crypto)
- Fear & Greed:        24 hour cache
- Funding rates:       10 min cache
- On-chain metrics:    1 hour cache
- Regime detection:    15 min recompute cycle
- Composite signal:    5 min recompute cycle

---

## SECTION 13 — DATA UNIVERSE

TOP-100 BY MARKET CAP — refreshed daily via scanner. Filters:
  - Min daily volume: $5M (live on at least 2 exchanges)
  - Min market cap: $50M
  - Exclude wrapped / synthetic duplicates
  - Exclude flagged scam-list coins

RISK TIERS (5-tier, crypto-calibrated):
  Tier 1: BTC-only
  Tier 2: BTC + ETH
  Tier 3: BTC + ETH + top-10 alts
  Tier 4: top-25 alts + stablecoin hedge
  Tier 5: top-100 breadth, higher-vol names

---

## SECTION 14 — BACKUP & RESTORE PROTOCOL

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 15 — SPRINT TASK LIST

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 16 — SESSION CONTINUITY & RESUME PROTOCOL

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 17 — PARALLEL AGENT MONITORING & TAKEOVER

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 18 — STREAMLIT-SPECIFIC PATTERNS

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 19 — CROSS-APP MODULE DISCIPLINE

[MASTER TEMPLATE. This project is the signal-engine reference:]

Other projects that adapt signal logic copy the relevant module into
their own repo (e.g., `composite_signal.py` → `signals/composite.py`
in the target). They do NOT import from this repo at runtime.

---

## SECTION 20 — GIT HYGIENE ON SHARED DEV MACHINES

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 21 — TONE & STYLE DURING COLLABORATION

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 22 — PROJECT-SPECIFIC CONSTRAINTS

- Historical CSV outputs (crypto_scan_v*.csv, crypto_dashboard_v*.xlsx)
  are VERSIONED in filenames. Do not delete without user approval — they
  are regression baselines.
- `optuna` hyperparameter tuning runs are long; log to
  `optuna_studies.sqlite` and never delete automatically.
- `backtest_equity*.png` charts are regenerated each run; safe to
  overwrite.
- `fastapi` / `uvicorn` are included for a future headless API mode
  (not yet wired).

---

## SECTION 23 — TOKEN EFFICIENCY (PROGRESS-PRESERVING)

[VERBATIM FROM MASTER TEMPLATE.]

---

## SECTION 24 — POST-CHANGE FULL REVIEW PROTOCOL (WHEN)

[VERBATIM FROM MASTER TEMPLATE.]

Project-specific notes:
- Fast-test suite target: under 30s locally (ML model loading is slow,
  so ML tests go in `@pytest.mark.slow`).
- Hot paths for perf check: scanner results, backtester, regime
  detector, composite signal page.
- `composite_signal.py` is the gold reference for signal aggregation —
  any change includes a backtest diff against the prior output on the
  2023-2026 universe, committed to `docs/signal-regression/`.
- ML model cold-start: if models change, verify Streamlit Cloud
  cold-start still loads under 60s (lazy-load LightGBM/XGBoost).

---

## SECTION 25 — DEPLOYMENT VERIFICATION PROTOCOL

[VERBATIM FROM MASTER TEMPLATE.]

Project-specific:
- Deploy URL: https://cryptosignal-ddb1.streamlit.app/
- Checklist: `shared-docs/deployment-checklists/crypto-signal-app.md`
- Post-deploy signal-consistency check: run the composite signal on
  BTC and ETH; compare output to yesterday's saved signal; expect
  small drift, flag if categorical (BUY→SELL) without regime change.
- Fallback-chain test: swap CCXT primary exchange to unreachable;
  confirm secondary exchange takes over.
