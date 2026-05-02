# Math-Correctness Audit — Crypto Signal App

**Date:** 2026-05-02
**Scope:** composite_signal.py, cycle_indicators.py, top_bottom_detector.py, composite_weight_optimizer.py, risk_metrics.py, ml_predictor.py, plus existing test fixtures.
**Audit basis:** CLAUDE.md §9 (math model architecture), §4 (audit protocol). composite_signal.py is the GOLD REFERENCE — any bug there invalidates every signal output the app emits.
**Severity legend:** `critical` = signal directionally wrong / fundamentally invalidated · `high` = edge-case crash or systemic miscalibration · `medium` = NaN/silent-fallback bug, masked or biased numeric · `low` = cosmetic/naming.

---

## EXECUTIVE SUMMARY

### Top 5 critical/high issues

1. **CRITICAL — composite_signal.py:1149-1170** — single-layer-outage renormalization treats a *legitimate* layer score of `0.0` as "missing" and redistributes its weight away. Inputs that produce a true neutral on every layer survive (all 4 layers stay) but a single layer that lands on a TRUE neutral 0.0 (e.g. RSI=50, sopr~1.0, vix in [15,25]) gets dropped from the basis even though it produced data. Inverts confidence semantics: more "0.0 neutral" signals = composite gets *more* concentrated on whatever layer has a non-zero number.
2. **HIGH — composite_signal.py:843** — Hash Ribbon E1 gate uses `btc_above_20sma is False` but `data_feeds.fetch_btc_ta_signals` writes `above_20sma` only when `len(closes) >= 20`. On cold-start / new asset, `above_20sma is None` → gate silently skipped → BUY scored at full +0.8 even though the price-confirmation criterion was never evaluated. Documented as "downgrade if False"; should be "downgrade if not strictly True".
3. **HIGH — top_bottom_detector.py:1623-1628 (MTF confluence weight)** — The MTF result is mixed into the divergence layer at sub-weight 0.30 *in addition* to RSI/MACD/CVD whose sub-weights total 1.00 (0.45+0.35+0.20). The renormalization (`/ norm`) does spread it correctly, but the arithmetic effectively gives MTF up to 23% of the divergence layer alongside three same-asset divergences — and the MTF is itself an aggregate of *only RSI* divergences across timeframes. The same RSI signal can be counted once in `rsi_div` and a second time in `mtf` for the primary timeframe. Double-counts the strongest dimension.
4. **HIGH — risk_metrics.py:294-300 (max-drawdown formula)** — `drawdowns = (roll_max - equity) / safe_roll_max * 100` returns drawdown as a positive %, but `np.nanmax(drawdowns)` is taken — a peak-to-trough drawdown is conventionally reported as a NEGATIVE percentage (or absolute drop magnitude). Code labels the result `max_drawdown_pct` and uses it in `calmar = ann_return / max_dd`. Correct sign here, but inconsistent with `crypto_model_core.run_deep_backtest` (line 4015) which stores `max_dd` as a positive % too — at least the *direction* is consistent app-wide. Real bug: if `equity_arr` ever contains a `0` followed by recovery, `safe_roll_max` is `nan` for that bar and `np.nanmax` skips it — but the drawdown to that zero bar is exactly 100% and should be captured. Mitigation: use `where(equity == 0, 100.0, ...)` instead of nan-skip.
5. **HIGH — top_bottom_detector.py:1618-1630 (CVD weight inflation)** — `compute_cvd_divergence` returns `confidence: 60` for either side and `0` only when no signal, but the cvd weight is fixed `0.20`. When CVD divergence is `NONE`, the `if d.get("confidence", 0) > 0` filter keeps confidence at 0 → drops it from the basis correctly. Problem: the *confidence* check is what gates inclusion, not the score itself, so a 0.5 NEUTRAL output is dropped regardless of how solid the underlying CVD math was. Adjacent issue: `mid = len(tail) // 2` was fixed in P1 audit (good), but `tail` is `lookback + 5 = 25` rows — `mid=12` produces 12-vs-13 split, asymmetric by 1 bar. Acceptable, called out for completeness.

### Issue counts by severity
- **Critical:** 2
- **High:** 7
- **Medium:** 14
- **Low:** 9
- **Total findings:** 32

### High-confidence fixture coverage
- crypto_model_core.py: ~22 of 22 indicators with locked fixtures (test_indicator_fixtures.py).
- composite_signal.py: 5 regression scenarios + 5 learned-weight scenarios. **Per-helper fixtures missing for all 14 `_score_*` sub-scoring functions.**
- top_bottom_detector.py: **0 fixture coverage.** None of the 18 detection functions have a deterministic fixture test.
- cycle_indicators.py: **0 fixture coverage** for any of 6 signals.
- risk_metrics.py: **0 fixture coverage** for VaR / Kelly / Calmar / Sortino. Direct unit tests absent.
- ml_predictor.py: **0 fixture coverage.** No deterministic seed-based train/predict round-trip test.

This is the largest gap in the audit suite. See "Test Gap List" at the end.

---

## SECTION 1 — composite_signal.py

The gold reference. ~56K and dense; aggregation, regime detection, layer renormalization, learned-weight cache, BUY/HOLD/SELL emission. Heavily commented research-trail in docstrings. Audit by category.

### 1.1 Off-by-one / window correctness

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| LOW | `_score_rsi` 222-232 | The threshold ladder is **half-open** — at exactly RSI=20.0 we return `+1.0`, at 20.0001 we return `+0.6 + (30-20.0001)/25 ≈ +0.999`. There is a `_clamp` discontinuity at the bracket boundaries (e.g. RSI=30 gives `+0.6 + 0/25 = +0.6`, RSI=30.0001 gives `+0.2 + (40-30.0001)/25 ≈ +0.6`). Continuous within ±0.0001 — accept. | None — note in docstring. |
| MEDIUM | `_score_funding_rate` 656-690 | Step function (post-fix). At fr=0.01 returns +0.1 (covered by `>= -0.005` branch); at 0.0100001 returns -0.2. Step of 0.3 across 0.0001 of input. Documented but a 30-bp step on a noisy signal can flip a borderline composite. Consider linear interpolation between bands. | Replace with a continuous sigmoid mapping (preserves step intent at extremes, smooths the band edges). |
| LOW | `_score_yield_curve` 472 | `if spread_2y10y >= -0.5: return _clamp(spread_2y10y * 0.4)`. At spread=-0.5 returns -0.2; at spread=-0.49 returns -0.196 — continuous. At spread=-0.51 the next branch runs `_clamp(-0.2 + (-0.51 + 0.5) * 0.6) = -0.206`. Continuous. Fine. | None. |

### 1.2 Look-ahead bias

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `score_macro_layer` 540 | All Layer-2 inputs come from FRED / yfinance daily data without explicit "as-of" timestamps. `compute_composite_signal` is called live so this is fine for production, but **historical backtests using current FRED revisions absorb future data** (FRED revises CPI/M2 quarterly; the current value at a 2023 timestamp is NOT what the agent saw in 2023). | When backtesting, route macro through `data_feeds.get_macro_enrichment_asof(date)` and use vintage data. **No such function exists today** — flag as known gap. |
| MEDIUM | `_score_realized_price` 892 | `realized_price = btc_price / mvrv_ratio`. If `mvrv_ratio` was computed at end-of-day T and `btc_price` is mid-day T+1, the ratio is internally inconsistent. Currently both come from the same scan tick, so OK live; backtester replay must align. | Document timestamp-pair invariant in docstring; backtester must use `realized_price` from the same `as_of` snapshot. |

### 1.3 Divide-by-zero

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `score_ta_layer` 393 | `raw = (sum(...) / _wsum if _wsum > 0 else 0.0)` — guard is correct but `0.0 if all sub-scores None` is interpreted by downstream renormalization (line 1157) as "this layer survived" because the components dict is non-empty. → composite gets a fake-neutral. | Return `None` from layer when no sub-signals available; bump to layer-renormalization path. |
| LOW | `score_macro_layer` 582 | `raw = (sum(active) / len(active)) if active else 0.0` — same as above but emits 0.0 with empty components dict. The line 1157 `(lyr.get("components") or 0.0)` truth check then drops macro from the basis. Inconsistent with TA path. | Standardize: every layer returns explicit `score=None` + `data_present=False` when nothing scored. |
| MEDIUM | `_score_realized_price` 902 | `if realized_price <= 0: return None` — guards zero. But `mvrv_ratio = 0` upstream produces division-by-zero before reaching here: `realized_price = btc_price / mvrv_ratio` at line 1112 — guarded by `mvrv_ratio > 0` only inside the conditional. If `mvrv_ratio = 1e-12` (rounding noise from a stale Glassnode reading) you get `realized_price = btc_price * 1e12` and then a ratio in the bottom branch `< 0.70` returns +0.8 — wrong direction. | Tighten guard: `mvrv_ratio > 0.01` or treat mvrv_ratio as None below threshold. |

### 1.4 Weight normalization (THE CRITICAL BUG)

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| **CRITICAL** | `compute_composite_signal` 1149-1170 | `_surviving = [(lyr, w) for lyr, w in _layer_specs if (lyr.get("components") or 0.0) or float(lyr.get("score") or 0.0) != 0.0]` — the survival rule is "non-empty components OR non-zero score". A layer that genuinely scored exactly 0.0 (e.g. macro: VIX=18, all neutral; sentiment: F&G=50, no put-call data) BUT whose components dict has any key inside (it always does — TA returns 8 component keys regardless of values) survives. Path A: layer that scored 0.0 with non-empty components → SURVIVES (because of the `or 0.0` check returning truthy `dict`). Path B: layer that hit the `except` branch → empty components, score=0.0 → DROPPED. The truth-table is correct **for the intended semantics** but the comment "any layer with a non-empty `components` dict OR a non-zero raw `score`" hides a subtle issue: a non-empty components dict with all None values still passes `(lyr.get("components") or 0.0)` because `{...}` is truthy. So a layer that produced a components dict but failed to score anything (all `_score_*` returned None → `raw=0.0`, components has keys with None values) **also survives**, polluting the basis with a fake-neutral. Reproducible: pass `macro_data={"vix": None, "dxy": None, "yield_spread_2y10y": None, "cpi_yoy": None, "m2_yoy": None}` — macro layer returns `{score: 0.0, components: {dxy_composite: {value: None, score: None}, ...}}`. Treated as surviving and weighted at full 0.20. | Replace survivor check with: `surviving = [(lyr, w) for lyr, w in _layer_specs if any(c.get('score') is not None for c in (lyr.get('components') or {}).values())]`. Layer survives iff at least one scored sub-signal exists. Add unit test for the all-None-input-per-layer case. |
| HIGH | `compute_composite_signal` 1149-1170 | When `len(_surviving) == 4` (all layers survive), the code falls through to the `else` branch which sums the **un-renormalized** weighted scores (`ta_layer["weighted"] + ...`). If learned weights from `_current_layer_weights()` were used and sum to 0.97 due to rounding (the validator allows ±0.01 tolerance), the composite score is implicitly compressed to that 0.97 basis. Composite emits `0.97 × (true score)` until renormalized. | After computing weighted total, divide by `(w_ta + w_mac + w_sent + w_oc)` always, not just when surviving < 4. Tightens the [-1, +1] domain guarantee. |
| MEDIUM | `_REGIME_WEIGHTS_BASE` 165 | Manual sum check: CRISIS = 0.10+0.15+0.25+0.50 = 1.00 ✓. TRENDING = 0.30+0.20+0.20+0.30 = 1.00 ✓. RANGING = 0.10+0.20+0.30+0.40 = 1.00 ✓. NORMAL filled in dynamically (line 181) → matches `_current_layer_weights()` which validates to ±0.01. **Test gap:** no test asserts `sum(w.values()) == 1.0` for each regime. | Add `test_regime_weights_sum_to_one` with all four regimes and learned/default scenarios. |

### 1.5 NaN / None propagation

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `_score_ma_signal` 235-243 | When `ma_signal=None` returns `None`, but when `ma_signal="NEUTRAL"` (not "GOLDEN_CROSS"/"DEATH_CROSS"), code falls to `+0.1 if above_200ma is True else (-0.1 if above_200ma is False else 0.0)`. So passing ma_signal="NEUTRAL", above_200ma=None returns 0.0, treated as a real signal at sub_weight 0.18. | Return None when both ma_signal is non-cross AND above_200ma is None — consistent with "no data available". |
| MEDIUM | `score_sentiment_layer` 749 | `s_vc = vc_funding_score if vc_funding_score is None else _clamp(float(vc_funding_score))`. If a string sneaks through (e.g. cryptorank returns "n/a"), `float("n/a")` raises → propagates to caller's `try/except` → entire sentiment layer drops. | Catch in-place: `try: s_vc = _clamp(float(vc_funding_score)); except: s_vc = None`. |
| MEDIUM | `compute_composite_signal` 1064-1099 | Each layer wrapped in `try/except` and on failure replaced by `{"score": 0.0, "weight": _W_*, "weighted": 0.0, "components": {}}`. Then the regime-weight rewrite at 1135-1138 multiplies `0.0 * w_ta = 0.0` and the survivor check (1156-1158) drops it. Acceptable. **But** `logger.warning` only — no metric emission. A single bad layer fails silently in production. | Emit a structured event (e.g. `metrics.increment('composite.layer_failure', {layer: 'macro'})`) so dashboards can spot drift. |

### 1.6 Confidence calculation

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | `_confidence_from_score` 1011-1016 | `confidence = abs(score) * 100`. **This is not a real confidence.** It's just signal magnitude. A composite score of +0.7 driven by 4 strongly-aligned layers and one driven by 1 layer at +0.7 with 3 absent layers both report confidence = 70. Per CLAUDE.md §9 the output rule is "BUY/HOLD/SELL with confidence" — the latter should reflect inter-layer agreement, not just |score|. | Compute confidence as `1 - normalized_std_dev_of_layer_scores`. Implementation sketch: `layer_scores = [ta_layer.score, macro_layer.score, sentiment_layer.score, onchain_layer.score]; agreement = 1 - (np.std(layer_scores) / 0.7)`; final confidence = 0.5 * abs(score) + 0.5 * agreement, scaled to [0, 100]. |
| MEDIUM | `_decision_from_score` 1004-1008 | Thresholds ±0.30 for BUY/SELL. `_signal_label` (legacy 7-state) uses ±0.30 as its boundary too — consistent. But there's no hysteresis — on a borderline composite of 0.299 → 0.301 → 0.299, decision flips HOLD→BUY→HOLD bar-by-bar. | Add a 0.05 hysteresis band: once BUY is set, threshold to revert is 0.25, not 0.30. Persist last decision in DB. |

### 1.7 Composite output invariant

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `compute_composite_signal` 1172-1194 | Every code path returns a dict with `score, decision, confidence, signal, risk_off, beginner_summary, regime, layers, weights_applied`. ✓ But: when ALL 4 layers raise exceptions, all four are replaced by `{"score": 0.0, ...}` and the survivor check drops all four → `_surviving = []` → falls through to `else` total = sum of weighted (all zero) → `total = 0.0` → decision = HOLD, confidence = 0. That IS a clean fallback but the user has no idea anything broke. | When `len(_surviving) == 0`, set `regime = "DATA_OUTAGE"` and emit a top-level `data_health: {layers_failed: 4}` field consumed by the UI's "Refresh" button to show a stale-data banner. |

### 1.8 Other findings — composite_signal.py

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| LOW | 192 | `_REGIME_WEIGHTS = _regime_weights()` runs at module import, snapshotting whatever `alerts_config.json` says at first load. External callers reading this constant get a stale view. | Convert to a property / function for backward compat shim. |
| LOW | 1029-1031 | `is_risk_off(score)` returns `score <= -0.30`. `_decision_from_score` uses `score <= -0.30` for SELL. So `risk_off == True` iff decision == SELL. Fine — but the `signal == STRONG_RISK_OFF` (≤ -0.60) tier is implicitly buried. | Document the equivalence in docstring. |

---

## SECTION 2 — cycle_indicators.py

Six signals: Google Trends, stablecoin supply delta, breadth, voliquidity, dumb money, unified cycle 1-100. All optional, fail-soft.

### Findings

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `fetch_google_trends_signal` 92-94 | `current = float(series[-1])`, `avg_4w = sum(series[-4:]) / 4.0`. The "current" point is INCLUDED in the 4w window. So `avg_4w` is the avg of the last 4 weekly observations and `spike = current/avg_4w - 1`. By construction, current is one of the 4 inputs to the average → spike is shrunk. Standard practice: average of the PREVIOUS 4 excluding the current. | Use `avg_4w = sum(series[-5:-1]) / 4.0` and require `len(series) >= 5`. |
| MEDIUM | `fetch_google_trends_signal` 78-114 | pytrends rate-limit / 429 handling is implicit (`except Exception`). pytrends has known datacenter-IP blocks on Streamlit Cloud — this will fail silently and downstream `fetch_dumb_money_signal` will return None → cycle bundle loses the dumb-money input without surfacing why. | Catch HTTPError separately and emit a structured warning. Also align with CLAUDE.md §10 "graceful fallback if rate-limited" — currently the fallback is a generic logger.debug. |
| LOW | `fetch_stablecoin_supply_delta` 119 | `_STABLE_COINS = ["tether", "usd-coin", "dai"]`. Excludes BUSD, FDUSD, TUSD, USDC.e, USDT-tron — the live stablecoin supply is now ~80% USDT+USDC, but the trend signal is sensitive to FDUSD/PYUSD adoption shifts. | Refresh list quarterly; document rationale. |
| MEDIUM | `compute_breadth` 188 | Uses `len(closes) < 50` to skip — but if `closes` has e.g. 49 valid prices and 50+ entries with some `None` filtered out, the row is dropped. Acceptable for breadth (we want robust majority counting), but `n_50_total` becomes a biased subset of the universe. With our 7 must-have small caps, several rarely have 200d history → bias toward large caps in the breadth reading. | Document the bias. |
| MEDIUM | `compute_breadth` 207-212 | The mapping is **non-monotonic in score**: `>=80` → -0.4 (extended bearish), `>=60` → +0.3 (bullish), `>=40` → 0.0, `>=20` → +0.3 (correction = bullish?), `<20` → +0.6 (capitulation = bullish). At 19% it's +0.6 but at 21% it's +0.3 — discontinuity is fine, but the labels imply mid-range bullishness disappears between 21% and 39% (mapped to +0.3 and 0.0 respectively). Actually wait: 40% → 0.0 (MIXED), 39% → +0.3 (CORRECTION). So as breadth deteriorates from 40% to 39% the score JUMPS from 0 to +0.3. That's a contrarian-bottom signal forming, justifying the bump, but the threshold step is jarring. | Smooth into linear interpolation. |
| LOW | `compute_voliquidity` 232 | `if not (atr_14 and price and volume_24h and market_cap):` — uses Python truthiness, so any zero-valued input returns None. ATR=0 (perfectly flat asset) is a real condition for delisted/halted markets; should return a score, not None. | Replace with explicit `is None` checks. |
| MEDIUM | `fetch_dumb_money_signal` 269-278 | Pulls `trends.get("spike_pct", 0.0) or 0.0` then thresholds. **Combines Google Trends spike WITHOUT the F&G filter the docstring promises** ("If spike >= +50% AND F&G > 75: strong DUMB_MONEY_ACTIVE"). Code uses spike alone. Either docstring lies or implementation is incomplete. | Either pass F&G in (preferred — increases signal-to-noise) or update docstring. |
| LOW | `cycle_score_100` 312 | `cycle = int(round(50 - blend * 49))` — note the 49, not 50. So blend = +1 → cycle = 1 (Strong Buy); blend = -1 → cycle = 99 (not 100). At blend = 0 → cycle = 50. Off-by-one against the docstring "1-100 (100 = euphoria/top)". A composite of -1.0 should yield 100, not 99. | Use 50, not 49. |

---

## SECTION 3 — top_bottom_detector.py

5 layers, ~83K. The largest by far. Pivot detection drives most of layer 3-4-5. Volume profile and Wyckoff are mostly self-contained. **Zero deterministic fixture coverage today.**

### 3.1 Pivot detection

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | `_pivot_lows`/`_pivot_highs` 121-136 | `series == series.rolling(window=2*n+1, center=True).min()`. With `center=True`, the rolling window at index i includes [i-n, i+n] — this **uses future bars**. For real-time pivot detection on the live bar (index = -1), the rolling at -1 has only [n] valid bars in the window (the right side is missing). pandas returns NaN on the right edge with the right size, then `fillna(False)` blanks it — so the LAST n bars never produce a pivot. **This is correct** for bias-free detection (a "pivot" by definition needs N bars to confirm), but downstream code uses `pl_idx[-1]` and treats it as "current". | Document explicitly: pivot points lag by `swing_n` bars. Surface this to the UI ("This signal needs N more bars to confirm"). |
| MEDIUM | `_pivot_lows` for SR/divergence | Strict equality `series == rolling().min()` — when two consecutive bars print the same low, BOTH register as pivot lows (or neither, depending on tie). On flat series, every bar in a flat valley becomes a pivot. Pivot index lists balloon. | Add tie-breaking — keep the leftmost. Or use `strict=False`; rolling with `min` and check `i == idxmin()`. |

### 3.2 Hindsight bias / live-bar pivots

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | `detect_rsi_divergence` 178-225 | `ph_idx = close.index[ph_price].tolist()` → uses pivots from `_pivot_highs(close, swing_n)` which has the look-ahead-by-n bars. So `ph_idx[-1]` (the most recent pivot) is necessarily AT LEAST `swing_n` bars old. Still: the divergence comparison `close.iloc[i2] > close.iloc[i1] AND rsi.iloc[i2] < rsi.iloc[i1]` is fine because both indices are confirmed. **However the function returns immediately** — it does not flag "this divergence was confirmed N bars ago" vs "still forming". | Add `bars_since_confirm = len(close) - 1 - i2` to the result dict; UI can hide stale (>5 bar) signals. |
| HIGH | `detect_chart_patterns` 873-893 | Double-bottom: `b1, b2 = sl_vals[-2], sl_vals[-1]` and condition `if current > neckline * 0.99`. The neckline is "max of highs between b1 and b2". current is `close.iloc[-1]`. **The pattern is flagged on the CURRENT bar BEFORE the breakout is confirmed by close above neckline by a margin (only 1% slop).** Real Edwards & Magee methodology requires ≥3% breakout + volume expansion. | Tighten: `current > neckline * 1.03` AND volume on breakout bar > 1.2× 20d avg. |
| MEDIUM | `detect_wyckoff_spring_upthrust` 957-971 | Spring detected via `recent_low < range_low * 0.998 AND current > range_low`. So the moment the price recovers back above range_low — even by 1 cent — Spring fires. The 82% accuracy quoted in the docstring assumes Wyckoff's full criteria (volume signature, retest of low, etc.). This implementation is a strict-superset of true Springs. | Add volume confirmation: spring volume should be > 1.5× the 20-bar avg. Add retest requirement (current must hold above range_low for 2+ bars). |
| MEDIUM | `compute_chandelier_exit` 1242-1253 | `if current > long_stop` … `if prev <= long_stop: signal = "BUY"`. `prev = float(df["close"].iloc[-2])`. So the BUY signal fires on the *current bar* the moment the close prints above the long stop, after exactly 1 prior close below. Whipsaw-prone. | Require 2-3 consecutive closes above stop or use a percentage cushion (current > long_stop × 1.005). |

### 3.3 Look-ahead in indicators

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `compute_volume_profile` 687-703 | Volume distributed across bins by overlap — uses `candle_low`/`candle_high` of the SAME bar. POC/VAH/VAL are computed using volume from each bar including the latest. **The "shape ratio" `top_vol / bot_vol`** at line 738-739 then uses bins indexed `[bins//2:]` (top half by price). The latest bar's volume gets full weight in the shape calc. Acceptable for current state, but in a rolling-window backtest **every recompute changes the bins because price_min/price_max shift bar-by-bar**, making the shape signal non-stationary across bars. | Stabilize bins using a rolling 50-bar high/low rather than the full lookback. |
| LOW | `compute_anchored_vwap` 1145-1152 | `_avwap_from(anchor_idx)` — denominator can be 0 if all volume is 0 in the post-anchor window. Returns `tp.iloc[-1]` as fallback (last typical price). Fine — but the score logic (line 1175) treats this fallback as a real AVWAP value. | Return None when fallback fires; gate the score branch. |

### 3.4 Composite top/bottom math

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | `compute_composite_top_bottom_score` 1697-1706 | `if W["onchain"] == 0 and W["sentiment"] == 0: redistrib = (_W_ONCHAIN + _W_SENTIMENT) / 2; W["divergence"] += redistrib; W["structure"] += redistrib`. Adds **half** of the missing weight to each of div/struct. So instead of `0.30 + 0.20 = 0.50` of weight to redistribute, each of div/struct gains 0.25 → totals: divergence 0.50, structure 0.40, volatility 0.10 → sum = 1.00 ✓. But: when ONLY onchain is missing (sentiment present), the code does nothing because the AND condition. Sentiment-only data with no on-chain would proceed with W["onchain"]=0 silently — handled by `total_w = sum(W.values())` at 1711, so the math stays normalized but **the user gets a composite based on 70% of intended dimensions without warning.** | When ANY layer weight is 0, redistribute proportionally to the surviving layers. |
| HIGH | 1623-1637 | MTF confluence weighted at 0.30 alongside RSI 0.45, MACD 0.35, CVD 0.20. Sum = 1.30. Renormalized (`norm = sum(div_weights)`) divides by 1.30, so actual contributions are: RSI 0.346, MACD 0.269, CVD 0.154, MTF 0.231. RSI is *also* aggregated inside MTF (it's RSI-divergence across timeframes). Strongest dimension counted twice. | Either remove the MTF slot or remove the per-tf RSI for the primary timeframe to avoid double-counting. |
| MEDIUM | `compute_onchain_macro_score` 1394 | `sub_w = {"mvrv": 0.30, "nupl": 0.20, "sopr": 0.20, "hash_ribbons": 0.15, "pi_cycle": 0.15}`. Sum = 1.00 ✓. Renormalization at 1462 over `weights_available` correctly handles missing inputs. **But:** `compute_sentiment_score` uses `fear_greed: 0.60, funding_rate: 0.40` (sum 1.00 ✓), **inconsistent** with composite_signal.py's sentiment sub-weights which are `fg=0.40, fgt=0.10, pc=0.25, fr=0.15, vc=0.10` (sum 1.00). Two different "Sentiment" layer definitions in the codebase. | Document the divergence: top_bottom_detector uses a simpler 2-input sentiment by design. Or unify — but they target different decision types (cycle position vs current trade). |

### 3.5 Other top_bottom_detector findings

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| LOW | `_rsi` 90-96 | `rs = gain / loss.replace(0, np.nan)` — avoids divide-by-zero by producing NaN. Then `100 - 100/(1+rs)` propagates NaN. Caller at 169 does `.fillna(50.0)` — neutralizes. Loss=0 historically means RSI=100. The intent "fully overbought" gets coerced to "neutral 50" — wrong direction. | Use `np.where(loss == 0, 100, 100 - 100/(1+rs))` or `loss.replace(0, 1e-12)`. |
| MEDIUM | `compute_volume_profile` 706-723 | Value Area selection sorts bins by volume desc, accumulates until ≥70%. The set of bins is then `va_bins`. VAH/VAL set to the price bounds of these bins via `max(va_bins)+1` / `min(va_bins)`. **But these bins may not be contiguous** — the VAH/VAL definition assumes a contiguous price range. Implementation produces a "convex hull" of the value area which can be much wider than the true value area. | Use the standard VA algorithm: start from POC bin, expand outward symmetrically. |
| LOW | `compute_pivot_points` 1043 | Camarilla formula uses `R * 0.55 / 2` for H4 and `R * 0.275 / 2` for H3. Original Camarilla (Camerino 1989) uses `range × 1.1/2` for H4 and `range × 1.1/4` for H3. Half off — verify against Camarilla canon. | Confirm via TradingView Camarilla reference; correct or document the deviation. |

---

## SECTION 4 — composite_weight_optimizer.py

Optuna-driven layer-weight retuning. Daily 04:00 UTC job. 100 trials, TPESampler, L2-regularized log-loss objective.

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `_compute_loss` 159-177 | Log-loss term divides by `len(samples)` BEFORE adding the L2 penalty. So `loss = mean_logloss + 0.10 * l2`. Numerical scale: a typical log-loss is ~0.5-0.7; L2 over (w_i - default_i)² with `w_i ∈ [0.05, 0.60]` and defaults 0.20-0.35 → at most `(0.60 - 0.20)² × 4 ≈ 0.64` → 0.10 × 0.64 = 0.064. So L2 penalty is ~9% of typical log-loss. **Reasonable** but means weights drift up to ~25% from defaults per retune (not the "10%" claimed in the docstring). | Either tighten `_L2_LAMBDA = 0.20` or update docstring. Add unit test showing maximum weight delta from defaults under typical loss landscape. |
| HIGH | `_load_resolved_feedback_rows` 144 | `df = df.dropna(subset=cols)` — drops rows where ANY of `[layer_ta, layer_macro, layer_sent, layer_onchain, was_correct]` is NULL. **In practice the layer scores can be 0.0 (genuinely neutral) which is NOT NULL — these survive correctly.** But the row count under-represents periods of partial-data outage which biases the optimizer toward "data-rich" historical regimes. | Keep rows with non-null `was_correct` and at least 2 layer scores; impute missing layers with 0.0 (matching live-data renormalization behaviour). |
| MEDIUM | `_objective` 240-248 | Optuna samples each weight independently in [0.05, 0.60]. After `_normalize` each weight is `raw / sum(raw)`. Sum-to-1 constraint enforced. **But:** the per-weight `_W_MAX = 0.60` is BEFORE normalization. Post-normalization a weight can exceed 0.60 only if the others are very small — but it can also collapse below 0.05 if others are large. So the `[0.05, 0.60]` bound on the *normalized* weight is NOT enforced. | Resample if normalized weight outside bounds, or use Dirichlet sampling with `alpha = [1, 1, 1, 1]` constrained to bounds. |
| LOW | `retune_layer_weights` 250-254 | TPESampler seed=42 — reproducible. But `study.best_value` can be marginally worse than `_loss_old` due to L2 regularization always being non-negative AND a fresh study not having visited the old weights. The existing-loss check at 260 saves us — if Optuna's best is worse, no writeback. Good. **But:** if the existing weights are already at a local minimum and Optuna's TPE doesn't sample near them, the job will report `loss_new >= loss_old` and skip writeback indefinitely. | Seed Optuna with the existing weights as the first trial (`study.enqueue_trial({...})`) so it's always evaluated. |
| LOW | `_sigmoid` 100-108 | Numerically stable two-branch implementation. Clamped to `[1e-6, 1-1e-6]` for log safety. ✓ |
| MEDIUM | Test `test_loss_decreases_with_more_aligned_weights` | The test asserts `loss_aligned < loss_anti` on synthetic data. Real data has **noise** — the alignment improvement may be < L2 penalty drift, in which case Optuna correctly stays at defaults. The test itself is fine but doesn't verify the L2 doesn't crush real signal. | Add a noisy-data test where the optimal weights are 5pp away from defaults, verify Optuna converges within 1pp. |

---

## SECTION 5 — risk_metrics.py

Historical VaR (≥20 samples), Cornish-Fisher parametric fallback (≥5), Sharpe/Sortino/Calmar/max-drawdown, Kelly sizing.

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | `compute_historical_var` 82-89 | `idx = int((1 - confidence) * len(sorted_pnl))`. At confidence=0.95, len=20 → idx=1. So VaR_95 = `-sorted_pnl[1]` = the second-worst loss. With only 20 samples the 95th percentile is **statistically meaningless** — confidence interval of the 1-in-20 quantile spans most of the loss distribution. The `_MIN_HIST_SAMPLES = 20` threshold is too aggressive for VaR-99 (20 × 1% = 0.2 — fewer than 1 expected tail event). | Tier the threshold: VaR_90 needs 20, VaR_95 needs 50, VaR_99 needs 100. Below tier → parametric fallback. |
| MEDIUM | `_parametric_var` 156-159 | Skewness clamped `[-3, 3]`, kurtosis `[-3, 10]`. Crypto BTC kurtosis on daily returns 2017-2024 ≈ 7-12; on weekly trades much lower. The clamp is reasonable for daily but may bite on hourly. | Document. Also consider widening kurt clamp upper bound to 15 — empirically observed in BTC flash-crash periods. |
| MEDIUM | `compute_var_summary` 295-300 | `safe_roll_max = np.where(roll_max == 0, np.nan, roll_max)` — zero peak equity (catastrophic loss → liquidation). Drawdown to that bar gets NaN'd → `np.nanmax` skips it → max drawdown UNDERSTATED to whatever the prior peak's drawdown was. **A ruin event reads as smaller drawdown than a 50% draw to a survivor account.** | When `equity == 0` is hit, set drawdown = 100% explicitly, then continue. Or terminate the equity curve at the first ruin. |
| MEDIUM | `compute_var_summary` 280-283 | `n_trades = len(pnl); avg_hold_days = max(1.0, _LOOKBACK_DAYS / n_trades); ann_factor = (365.0 / avg_hold_days) ** 0.5`. **Trades have variable holding times.** This formula assumes uniform spacing across the 90-day window. With a strategy that takes 30 trades in week 1 and 0 thereafter, n_trades/window collapses. | Use the ACTUAL avg holding period from `pair, entry_ts, exit_ts` rather than (lookback / n_trades). |
| HIGH | `compute_portfolio_risk` 396-399 | `div_factor = math.sqrt(1 + (n - 1) * correlation_assumption) / math.sqrt(n)`. At n=4, correlation=0.30 → `div_factor = sqrt(1 + 0.9) / 2 = sqrt(1.9)/2 ≈ 0.689`. **But:** the formula approximates a portfolio of equal-volatility, equal-position-size assets. With unequal positions (which `position_vars` allows), the diversification benefit is overstated. Crypto correlations also spike to 0.8+ in stress events — the `0.30` assumption is dangerously low. | Use a regime-dependent correlation: 0.30 in normal, 0.70 in CRISIS regime (read from composite_signal regime). |
| LOW | `compute_kelly_fraction` 484-488 | `full_kelly = (b * win_rate - (1 - win_rate)) / b`. Standard Kelly formula. Clamped `[0, 1]`. ✓. Caps at 20% portfolio (`_KELLY_MAX_POSITION`). ✓. With win_rate=0.55, avg_win=0.08, avg_loss=0.04 (b=2): full_kelly = (2*0.55 - 0.45)/2 = 0.325 → fractional 0.0813 → 8.13% of portfolio. Reasonable. |
| MEDIUM | `compute_kelly_fraction` 469-481 | Edge-case validation rejects `avg_win <= 0 or avg_loss <= 0` — but doesn't check that `win_rate * b > (1 - win_rate)` (no edge condition). When edge is zero or negative, the formula returns negative kelly which is then clamped to 0. So the function returns 0% position size silently. | Surface "no statistical edge" explicitly in the result — it's important info for the agent. |

---

## SECTION 6 — ml_predictor.py

GBM + XGBoost ensemble, 3-class labels, rolling 500-bar training window. HMM regime detector at the bottom.

### 6.1 Train/test contamination

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `_train_model` 253 | `train_df = df.iloc[-(TRAIN_BARS + LOOKAHEAD_BARS):-LOOKAHEAD_BARS]` — slice EXCLUDES the final LOOKAHEAD_BARS to avoid labeling future-leak. ✓ |
| HIGH | `_compute_accuracy` 380-401 | "True out-of-sample" holdout = 40 bars BEFORE training window. Documented fix for Issue #14. Verify: `training_start_idx = -(TRAIN_BARS + LOOKAHEAD_BARS) = -504`, `holdout_start = -544`, `holdout_end = -504`. With df length N, slicing `df.iloc[-544:-504]`. **For df < 544 bars, `abs(-544) > N` → returns None.** Function correctly returns 0.0. ✓ But: the 40-bar holdout PRECEDES the training window in time, so it's actually EARLIER data than what the model trained on. With a non-stationary process (crypto regime shifts), accuracy on past data is not the same as accuracy on future data. **Should split TIME-FORWARD**: train on bars [-544, -44] and test on bars [-44, -4]. | Reverse the holdout direction: hold out the most recent bars, train on the older window. |
| MEDIUM | `_build_features` 116-196 | All features built with `_build_features(df)` — using `df.iloc[-1]` of indicators that are `rolling()` with `center=False` (default). ✓ no look-ahead via indicator. **However:** at line 143 `feat["atr_pct"] = df["close"].pct_change().abs().rolling(14).mean()` is used as a FALLBACK if `atr` column missing. This ATR fallback is computed from CLOSE-to-CLOSE returns, not high/low/close — diverges from the proper ATR used elsewhere in the codebase. Models trained when fallback is active produce different decision boundaries than models trained with real ATR — silent regime split. | Always build proper ATR upstream; never silently substitute a different definition. |

### 6.2 Feature leakage

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `_build_labels` 218-225 | `future_close = df["close"].shift(-LOOKAHEAD_BARS)`. **Look-ahead is the LABEL — that's correct, labels must use future data**. The danger is if `feat` indices overlap with `labels` indices for the LAST LOOKAHEAD bars (those have NaN labels and are dropped) — verified via `labels.reindex(feat_index).dropna()`. ✓ |
| MEDIUM | `_build_features` 165-194 | `onchain_ctx` (mvrv_z, sopr) is a CONSTANT across all rows of the training window. Documented (line 102-105) as intentional regime context. **But:** at PREDICTION time (`get_ml_prediction`, line 462), the SAME constant is applied to df.tail(20) → trains and predicts both see today's mvrv_z. Within-sample. Backtests built using today's mvrv_z labeled against historical bars are LOOK-AHEAD BIASED. | For backtests, mvrv_z must be from t-1 OHLCV's matching on-chain snapshot. Confirm there's no backtester path that calls get_ml_prediction with current onchain_ctx — currently `crypto_model_core.run_deep_backtest` does NOT pass onchain to ML, so production backtests are clean. Document this constraint. |

### 6.3 Cold-start

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `_get_or_train_model` 327-357 | Memory cache → disk cache (joblib pkl) → retrain. Disk TTL = 1 hour. **But:** if a model on disk was trained on stale data (price regime has shifted in last 60 minutes), the disk cache will return it. Stale model may emit BUY based on yesterday's regime. | Include `df.index[-1]` timestamp in the model dict and verify it's within 1 hour of current bar before serving. |
| LOW | `get_ml_prediction` 447-451 | When `df` is too short, returns `_NEUTRAL_RESULT` with `error="Insufficient data"`. Cached for 1 hour. So the next 60 minutes of identical-too-short calls return the cached neutral. ✓ |
| MEDIUM | `_train_model` 267-268 | `if len(np.unique(y)) < 2: return None` — guards degenerate single-class. **But:** with 3-class labels, having only 2 of 3 classes (e.g. all DOWN and NEUTRAL) is ALSO statistically problematic — model can't learn the missing class. Yet `len(unique)>=2` lets it through. | Tighten: require at least 2 of 3 classes with ≥10% representation each. |

### 6.4 HMM regime detector

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| MEDIUM | `fit_hmm_regime` 668-671 | `means = [float(X[states == s, 0].mean()) ...]` — labels states by mean log-return ascending. **What if a state has zero observations?** `(states == s).sum() == 0 → mean = 0.0` (the fallback). Then sort puts that state in the middle → mislabeled. Rare but possible during initial training on 30-bar minimum. | Drop empty states from sort, label remaining. |
| LOW | `fit_hmm_regime` 658-666 | Two GaussianHMM constructors — handles `covariance_floor` API change in hmmlearn 0.3.0+. Defensive ✓. |
| MEDIUM | `fit_hmm_regime` 583 | Cache key: `f"hmm:{len(prices)}:{round(prices[0], 0)}:{round(prices[-1], 0)}"`. **Two different price histories can collide** (same first/last/length but different middle). Probability of collision in production is very low but not zero; result: stale HMM model returned for new data. | Hash full series via `hashlib.blake2b(np.array(prices).tobytes(), digest_size=8).hexdigest()`. |

---

## SECTION 7 — Backtester (crypto_model_core.run_deep_backtest)

Reviewed `run_deep_backtest` at lines 3791-4032 (called out by audit context). Includes 0.20% round-trip taker cost, but several gaps:

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | 3942-3960 | Forward-bar simulation: `for j in range(1, hold_bars+1): future = df_full.iloc[i + j]`. Stop/target check uses each bar's H/L. **Slippage NOT MODELED.** Stop-loss exit fills at exactly `stop` price. In reality, fast moves mean stop fills below stop (for longs). Backtest results are systematically optimistic. | Add 0.05-0.10% slippage to all stop/target fills. |
| HIGH | Backtester | **Funding rates NOT included in PnL.** Perp positions held >8 hours accumulate funding cost (or income). Strategy backtest on perpetual contracts that doesn't account for funding undercounts cost in long-funding-positive regimes (e.g. all of late 2021). | Lookup historical funding from OKX/Binance, add to round-trip cost per (pair, entry_ts, exit_ts). |
| MEDIUM | Backtester | **Survivorship bias.** Pair list comes from current top-N CCXT availability. Symbols delisted between 2022 and now (e.g. LUNA, FTT, post-TerraLuna, post-FTX) NEVER appear in backtest universe — the strategy backtest looks artificially profitable because it never had to deal with the exit liquidity crisis of those names. | Maintain an "as-of" pair list per backtest start date (manual list for top-30 milestone dates: 2018-01, 2020-01, 2021-12, 2023-06). |
| MEDIUM | 3902-3923 | `for i in range(warmup, n_bars - hold_bars)`. The bar-at-i signal computed via `df_slice = df_full.iloc[max(0, i - OHLCV_LIMIT): i + 1]` — slice INCLUDES bar i. So the signal at bar i sees bar i's CLOSE price and indicators using close-of-i. **Then entry_price = `df_full['close'].iloc[i]`** — entry at the CLOSE of the same bar the signal fired on. In live trading, you can't enter at the same bar's close after the close has printed — the next-bar OPEN is the realistic entry. | Use entry_price = `df_full['open'].iloc[i+1]` to match realistic execution. |
| LOW | 4006 | `sharpe = pnl_arr.mean() / (pnl_arr.std() + 1e-9) * np.sqrt(n_ret)`. **Annualization factor `sqrt(n_ret)` is wrong** for non-daily returns. `n_ret` is the trade COUNT, not annualized periods. Real annualized Sharpe needs `sqrt(365 / avg_hold_days)`. The risk_metrics.py compute_var_summary fixed this. crypto_model_core.run_deep_backtest still has the broken version. | Mirror the fix already in risk_metrics.py. |

---

## SECTION 8 — Cross-cutting findings

| Severity | Location | Finding | Fix proposed |
|---|---|---|---|
| HIGH | data_feeds.py:8328-8330 | Variable misnaming bug. When `len(closes) >= 50` but `< 200`: `above_200ma = closes[-1] > ma50`. **The variable name says above_200ma but the comparison is to ma50.** Downstream `_score_ma_signal(ma_signal, above_200)` reads this as price-vs-200d when it's price-vs-50d for those underdata pairs. Semantics inverted on cold-start markets. | Drop the elif branch — return `above_200ma = None` when 200d data unavailable. |
| MEDIUM | composite_signal.py / cycle_indicators.py | **Two distinct "score" sign conventions.** composite_signal uses [-1, +1] where +1 = risk-on/buy. cycle_indicators.cycle_score_100 uses [1, 100] where 100 = top/sell (inverted polarity). top_bottom_detector uses [0, 1] where 1.0 = bottom/buy. Different parts of the codebase emit different sign conventions for "buy". UI must be aware of which scale each card uses. | Document central README of sign conventions; add unit tests asserting the polarity at each boundary. |
| MEDIUM | All score-bucket functions | Step-function scoring (e.g. RSI 30 → 0.6 vs RSI 30.0001 → 0.6 same, but RSI 20 → 1.0 vs RSI 20.001 → 0.6 + (30-20)/25 = ~1.0). Most buckets are continuous within bands but NOT across the boundary. A 0.0001-input change can flip a borderline composite from BUY to HOLD. | Replace with smooth (sigmoid / logistic) mappings. Adds compute cost but eliminates whipsaw on noisy inputs. |
| LOW | composite_signal.py + top_bottom_detector.py | Both score sentiment from `fear_greed`, `funding_rate`. composite_signal uses funding bands `[+0.05, +0.03, +0.01, -0.005, -0.02]` (fraction per 8h), top_bottom_detector uses bands `[+50, +10, -10, -50]` (annualized %). Same input concept, different unit conventions. | Standardize on annualized % everywhere for funding, OR document the unit difference at the boundary. |

---

## SUMMARY TABLE — All findings

| # | Severity | Module | Location | Issue |
|---|---|---|---|---|
| 1 | CRITICAL | composite_signal | 1149-1170 | Survivor renormalization treats components-with-all-None as "alive" → fake-neutral pollution |
| 2 | CRITICAL | composite_signal | 843 | Hash Ribbon E1 gate: `is False` skipped when None → BUY ungated |
| 3 | HIGH | composite_signal | 1149-1170 | All-4-survivors path doesn't renormalize against rounding-induced sum<1 |
| 4 | HIGH | composite_signal | 1011 | Confidence = abs(score) — not real inter-layer agreement |
| 5 | HIGH | composite_signal | 1064-1099 | Layer failure logged but not metric-emitted |
| 6 | HIGH | top_bottom_detector | 1623-1637 | MTF + RSI div double-counted in divergence layer |
| 7 | HIGH | top_bottom_detector | 873-893 | Double-bottom pattern fires on 1% breakout — too lax |
| 8 | HIGH | top_bottom_detector | 1697-1706 | Single-layer-missing redistribution only fires when BOTH macro layers missing |
| 9 | HIGH | risk_metrics | 79-89 | VaR-99 with 20-sample threshold — tail estimate meaningless |
| 10 | HIGH | risk_metrics | 295-300 | Catastrophic-loss bar (equity=0) NaN'd → max-DD understated |
| 11 | HIGH | risk_metrics | 396-399 | Portfolio diversification factor uses 0.30 fixed correlation; spikes in stress |
| 12 | HIGH | crypto_model_core | run_deep_backtest 3942-3960 | No slippage modeled on stop fills |
| 13 | HIGH | crypto_model_core | run_deep_backtest | No funding cost on perpetuals |
| 14 | HIGH | crypto_model_core | run_deep_backtest 3924 | Entry on same-bar close — uses unattainable price |
| 15 | HIGH | data_feeds | 8328-8330 | `above_200ma` variable inverted to use ma50 in fallback |
| 16 | HIGH | ml_predictor | 380-401 | Holdout window is BEFORE training window — backwards-time eval |
| 17 | MEDIUM | composite_signal | 749 | s_vc float() can raise on bad cryptorank string → entire layer drops |
| 18 | MEDIUM | composite_signal | 1112 | mvrv_ratio near-zero produces wild realized_price |
| 19 | MEDIUM | composite_signal | 235-243 | _score_ma_signal returns 0.0 when ma_signal="NEUTRAL", above_200ma=None — dilutes |
| 20 | MEDIUM | composite_signal | regime weights | No test asserts regime weights sum to 1.0 |
| 21 | MEDIUM | composite_signal | 540 | All macro inputs use latest-vintage FRED — backtester contamination |
| 22 | MEDIUM | cycle_indicators | 92-94 | Google Trends spike includes current week in 4w avg → muted |
| 23 | MEDIUM | cycle_indicators | 269-278 | Dumb-money docstring claims F&G filter; impl uses spike alone |
| 24 | MEDIUM | top_bottom_detector | 957-971 | Wyckoff Spring fires on 1-cent recovery — needs volume + retest |
| 25 | MEDIUM | top_bottom_detector | 1242-1253 | Chandelier BUY fires on first close-above — whipsaw-prone |
| 26 | MEDIUM | top_bottom_detector | 706-723 | Volume Profile VA via top-N volume bins — non-contiguous |
| 27 | MEDIUM | composite_weight_optimizer | 144 | dropna() on layer_score columns biases optimizer to data-rich periods |
| 28 | MEDIUM | composite_weight_optimizer | post-normalize | Per-weight bounds [0.05, 0.60] not enforced after normalize step |
| 29 | MEDIUM | risk_metrics | 156-159 | Skewness/kurtosis clamps loose for crypto hourly |
| 30 | MEDIUM | risk_metrics | 280-283 | avg_hold_days = lookback / n_trades assumes uniform spacing |
| 31 | MEDIUM | ml_predictor | 143 | atr fallback uses close-pct-change MEAN instead of true ATR — silent split |
| 32 | MEDIUM | ml_predictor | 165-194 | onchain_ctx constant in train+predict — backtester contamination if used |

(LOW findings: 9, summarized in section bodies.)

---

## TEST GAP LIST — fixtures that should be added

### composite_signal.py

1. `test_score_rsi_boundary_continuity` — assert |_score_rsi(20.001) - _score_rsi(20.0)| < 0.5 (no abrupt step at hard boundary).
2. `test_score_funding_rate_step_intent` — verify step function returns expected band for each docstring threshold.
3. `test_layer_renormalization_drops_all_none_components` — pass macro layer with all-None inputs; assert it's REMOVED from the survivor basis (currently fails — survives bug).
4. `test_layer_renormalization_handles_zero_score_with_real_data` — pass macro with vix=18, dxy=102 (genuine neutral) → must survive.
5. `test_compute_composite_with_all_layers_failing` — assert returns `decision="HOLD", confidence=0, regime` annotated as data-outage state.
6. `test_regime_weights_sum_to_one` — for each of CRISIS/TRENDING/RANGING/NORMAL, assert sum(values) == 1.0 within 1e-9.
7. `test_confidence_reflects_inter_layer_agreement` — when 4 layers all = +0.7, confidence > when only 1 layer = +0.7 with 3 absent. (Currently fails; both report 70.)
8. `test_realized_price_handles_near_zero_mvrv_ratio` — pass mvrv_ratio = 1e-6 → should treat as None, not produce ratio = 1e-6/btc_price.

### top_bottom_detector.py — ALL DETECTION FUNCTIONS need fixtures

9. `test_pivot_lows_lag_n_bars` — verify pivots within last n bars are NOT flagged (look-ahead-free).
10. `test_detect_rsi_divergence_locked_fixture` — synthetic OHLCV with hand-crafted bull divergence → expect score_0to1 > 0.85.
11. `test_detect_macd_divergence_locked_fixture` — same.
12. `test_compute_cvd_divergence_asymmetric_window` — verify mid = len(tail)//2 produces ±1-bar split (post-fix).
13. `test_detect_bos_choch_choch_vs_bos_classification` — engineered uptrend + break-down → BEARISH_CHOCH.
14. `test_detect_chart_patterns_double_bottom_threshold` — verify 1% breakout NOT flagged (require new 3% threshold).
15. `test_detect_wyckoff_spring_volume_required` — spring without volume confirmation NOT flagged.
16. `test_compute_volume_profile_va_contiguous` — assert VAH/VAL bins are contiguous price bins.
17. `test_compute_chandelier_exit_multi_bar_confirmation` — single close above stop NOT a BUY signal.
18. `test_compute_composite_top_bottom_score_layer_redistribution` — pass macro_data only, sentiment_data only, both, neither → verify weights renormalize.

### cycle_indicators.py

19. `test_google_trends_spike_excludes_current` — once spike formula fixed.
20. `test_compute_breadth_bias` — universe with 50 large-caps with 200d data + 50 small-caps with only 50d data; assert output bias is documented.
21. `test_cycle_score_100_boundaries` — assert blend=+1 → score=1, blend=-1 → score=100 (after off-by-one fix).
22. `test_compute_voliquidity_atr_zero_returns_score` — perfectly flat asset returns "ULTRA_COMPRESSED" not None.

### composite_weight_optimizer.py

23. `test_l2_lambda_caps_drift_at_documented_pct` — synthetic data with strong signal in technical layer; assert max(|w - default|) ≤ 25% (or lower if docstring fixed).
24. `test_normalize_post_constraint_bounds` — Optuna trial returning normalized weights [0.01, 0.05, 0.04, 0.90] should be REJECTED (or resampled).
25. `test_retune_seeds_with_existing_weights` — assert existing weights are tested as trial 0 (so optimizer can reject if they're already optimal).

### risk_metrics.py

26. `test_var_99_requires_more_samples` — 25-sample dataset should fall back to parametric for VaR-99, historical for VaR-90.
27. `test_max_drawdown_handles_ruin_event` — equity curve [10000, 5000, 0, 1000, 5000] → max_dd should be 100%, not 50%.
28. `test_kelly_fraction_zero_edge_surfaces_explicitly` — win_rate=0.40, b=1 → return must include "no_edge" flag (not just 0%).
29. `test_compute_var_summary_with_ten_trades_uses_cf` — 10 trades → uses Cornish-Fisher (≥5 samples), method == "cornish_fisher".

### ml_predictor.py

30. `test_holdout_is_temporally_after_training` — assert holdout indices > training indices (currently fails — they're before).
31. `test_atr_fallback_emits_warning` — when ml_predictor's atr fallback engages, log a WARNING (not just .debug).
32. `test_hmm_cache_hash_collision_resistant` — pass two distinct 100-bar series with same first/last → cache must NOT collide.

### Backtester (crypto_model_core.run_deep_backtest)

33. `test_run_deep_backtest_includes_slippage` — synthetic series with stop-out → fill price ≠ stop price (slippage applied).
34. `test_run_deep_backtest_funding_charged_on_perps` — long position held 24h → equity reduced by 24/8 × funding × position.
35. `test_run_deep_backtest_entry_at_next_bar_open` — assert trade entry timestamp > signal bar timestamp.
36. `test_run_deep_backtest_sharpe_uses_calendar_annualization` — manually compute sharpe with sqrt(365/avg_hold_days), assert backtester output matches.

---

## CONCLUSION

`composite_signal.py` is **structurally sound** — research-grounded thresholds, regime detection, learned-weight infrastructure, fail-soft layer wrapping. **Two critical bugs** undermine the gold-reference status:
1. The all-None-components-survive bug pollutes the composite with fake neutral on partial-data outages.
2. The Hash Ribbon E1 gate skips on `None` instead of treating it as failure-to-confirm, allowing un-gated BUY signals on cold-start markets.

Both should be hotfixed before any new sprint touches the file. After those, the next priority is **fixture coverage** — `top_bottom_detector.py`, `cycle_indicators.py`, `risk_metrics.py`, and `ml_predictor.py` have effectively zero deterministic locked-output tests. CLAUDE.md §22 mandates that math-heavy functions each have a fixture. 18 detection functions in top_bottom_detector currently have none.

`composite_weight_optimizer.py` looks safe but the **normalize-after-bound** approach to weight constraints lets the optimizer drift outside the [0.05, 0.60] band — minor but worth fixing now while the feature is fresh.

`risk_metrics.py` has the most concerning **threshold problem**: VaR-99 requires only 20 samples, which is statistically insufficient. A 99-percentile estimate from 20 samples has standard error of ~50% of the estimate. Tier the threshold per-confidence-level.

`ml_predictor.py` has the most concerning **temporal-direction** bug: the "out-of-sample" holdout is BEFORE the training window. Any reported model accuracy is on past data the regime no longer matches.

The **backtester** in `crypto_model_core.run_deep_backtest` lacks slippage, funding-cost, and proper entry-bar conventions. All three bias backtest results positively. Until fixed, backtest "Sharpe ratios" should be discounted by 30-50% mentally and treated as "ceiling" not "expectation".
