# Master Game Plan — Legacy-Look Audit + Full Codebase Deep Dive
**Date:** 2026-05-02
**Status:** PROPOSAL — awaiting David's approval per CLAUDE.md §1
**Inputs:** 8 user screenshots (Images 1–8) + 6 parallel deep-audit reports

---

## 0. Source documents (read before approving)

1. `docs/audits/2026-05-02_legacy-look-audit-in-progress.md` — image-by-image inventory
2. `docs/audits/2026-05-02_ui_css_audit.md` — bright-green saturation, ds-card gaps, sidebar Legal wrap, topbar wrap
3. `docs/audits/2026-05-02_onchain_data_audit.md` — On-chain page blank-cards root cause (Image 8 headline)
4. `docs/audits/2026-05-02_math_audit.md` — composite signal + indicator math
5. `docs/audits/2026-05-02_data_feeds_audit.md` — cascade, geo-block, Hyperliquid parser, status pills
6. `docs/audits/2026-05-02_empty_states_audit.md` — truthful empty-state inventory
7. `docs/audits/2026-05-02_test_coverage_audit.md` — coverage gaps + new tests needed

---

## 1. Executive summary — what's actually wrong

The "legacy-look" complaint and the deeper functional issues share **four root causes** that show up in every screenshot and every audit:

### Root cause A — Status pills are hardcoded string literals
Four page headers (`app.py:2247, 7556, 8219, 8617`) hardcode `"Glassnode · live"`, `"OKX · live"`, etc. with **zero plumbing** from any health check. The pill cannot be anything other than what the literal says. This is why Image 8's On-chain page claims "Glassnode · live" while every metric card is blank — the page **never actually calls Glassnode**, and even if it did, the pill couldn't tell you it failed.

### Root cause B — Bright-green saturation = one CSS rule + one Streamlit token
- `ui_components.py:178-200` defines `section.main button[kind="primary"]` with `linear-gradient(...) !important`. This wins the cascade and paints every primary button bright `#00d4aa`.
- `.streamlit/config.toml:3 primaryColor = "#00D4AA"` paints multiselect tag chips at the Streamlit-native level — and `#00D4AA` doesn't even match the design system's `#22d36f`. Token drift.

Deleting the legacy block + flipping `primaryColor` to `--accent-soft` fixes Images 4, 6, 7, 8 cosmetic complaints app-wide.

### Root cause C — Empty-state copy is non-truthful
135 bare `"—"` sites and 19 `except: return None` sites mean any of: loading / no-scan-yet / geo-blocked / rate-limited / no-api-key / not-tracked / genuinely zero. The user can't tell which. `data_feeds.py` already produces structured failure metadata (`_empty_result`, `_no_key_result`) — the UI just throws it away.

### Root cause D — Two critical math bugs in `composite_signal.py` affecting every BUY/HOLD/SELL output
1. `composite_signal.py:1149-1170` — survivor renormalization treats a layer with `components` dict full of `None` values as "alive" because `dict` is truthy. Pollutes composite with fake-neutral 0.0 on partial-data outage.
2. `composite_signal.py:843` — Hash Ribbon E1 gate uses `btc_above_20sma is False` as downgrade trigger. When `data_feeds` returns `None` (cold-start, <20 bars), gate **silently skips** and BUY scores at full +0.8 unconfirmed.

These two bugs mean every signal the app outputs right now may be wrong.

---

## 2. Critical-bug inventory (must-fix before any sprint)

| # | File:line | Severity | Issue | Fix size |
|---|---|---|---|---|
| C1 | `composite_signal.py:1149-1170` | CRITICAL | Survivor renorm treats None-only dict as alive — composite poisoned during partial outage | ~10 lines |
| C2 | `composite_signal.py:843` | CRITICAL | Hash Ribbon E1 gate skips on `None` instead of treating as unknown — over-confident BUY | ~5 lines |
| C3 | `app.py:8617-8621` | CRITICAL | On-chain status pills hardcoded "live" — Image 8 lying | ~30 lines (real health helper) |
| C4 | `app.py:8718-8749` | CRITICAL | On-chain card render: `0.0 or None == None` truthiness bugs — collapses real fallback values to "—" | ~6 lines |
| C5 | `app.py:8691` | CRITICAL | `active_addresses_24h: None` hardcoded — fourth card slot guaranteed blank while pill says "live" | ~3 lines |
| C6 | `data_feeds.py:4413-4479` | HIGH | Hyperliquid funding annualization `× 3 × 365` is **8× too low** (API returns hourly, not 8h). Plus 10× duplicate POSTs in batch mode | ~15 lines |
| C7 | `app.py:6852` | HIGH | `row[exch.upper()] = None if rd.get("error") else rate` → literal "None" rendered in funding table (Image 7) | ~4 lines |
| C8 | `arbitrage.py:325-336` | HIGH | Spot arb returns empty buy/sell exchange when `signal == "NO_ARB"` even though prices are populated (Image 5) | ~12 lines |
| C9 | `ui_components.py:178-200` | HIGH | Legacy `linear-gradient !important` block wins cascade → bright-green primary buttons everywhere (Images 4, 6, 7, 8) | DELETE 22 lines |
| C10 | `.streamlit/config.toml:3` | HIGH | `primaryColor = "#00D4AA"` paints multiselect chips bright + drifts from design system | 1-line change |
| C11 | `app.py:2463-2475` `_ds_build_hero` | HIGH | Hero cards bypass cascade for non-OKX-SWAP pairs (XDC/SHX/ZBCN) — Image 1 root cause | ~15 lines |
| C12 | `whale_tracker.py:411` | HIGH | `_synthesize_signal` discards per-transfer `moves` list — Image 8 ambiguous "no transfers OR offline" never resolves | 1-line + render fix |
| C13 | `risk_metrics.py:79-89` | HIGH | VaR-99 with 20 samples is statistically meaningless (0.2 expected tail events) | ~10 lines |
| C14 | `ml_predictor.py:380-401` | HIGH | "Out-of-sample" holdout is bars BEFORE training, not after — accuracy reported on stale regime | ~20 lines |
| C15 | `top_bottom_detector.py:1623-1637` | HIGH | RSI divergence double-counted in MTF confluence layer | ~8 lines |
| C16 | `tests/test_data_wiring.py:169` | MEDIUM | Hidden no-op skip — `return` with no skip marker → appears green but asserts nothing | ~3 lines |
| C17 | `data_feeds.py:8328-8330` | MEDIUM | Variable misnamed: `above_200ma` set using `ma50` in fallback branch | 2-line fix |
| C18 | `cycle_indicators.py:312` | MEDIUM | `cycle_score_100 = 49 + …` off-by-one (blend=−1 yields 99 not 100) | 1-line fix |
| C19 | `cycle_indicators.py:92-94` | MEDIUM | Google Trends spike includes current week in 4-week average → muted spike | ~4 lines |
| C20 | `composite_signal.py:1011` | MEDIUM | `_confidence_from_score = abs(score) * 100` — confidence is signal magnitude, not inter-layer agreement | ~30 lines (real metric) |

---

## 3. Proposed fix sprint — phased & numbered

> **Per CLAUDE.md §1: I will not implement any item until you reply with explicit "approved, go" or equivalent. Once approved, I execute the entire list autonomously without further check-ins.**

### PHASE 1 — Math correctness hotfix (~2–3 hours)
Fixes that change BUY/HOLD/SELL output. Backtest diff committed to `docs/signal-regression/` before merge per project §22.

1. **C1** — Fix survivor renormalization to require non-None component values not just truthy dict
2. **C2** — Hash Ribbon E1 gate treats `None` as unknown, downgrades confidence rather than skipping
3. **C13** — VaR-99 minimum sample threshold tiered by confidence level (≥250 for VaR-99, ≥100 for VaR-95, ≥40 for VaR-90)
4. **C14** — ML holdout = trailing 40 bars *after* train window; document as "near-term out-of-sample"
5. **C15** — Drop MTF confluence from divergence-layer aggregation (already counted in MTF layer)
6. **C17** — Variable rename in `data_feeds.py:8328` `above_200ma` → use `ma200` source
7. **C18** — `cycle_indicators.py:312` change `49` → `50` constant
8. **C19** — Google Trends spike: exclude current week from baseline
9. **C20** — Replace `abs(score) * 100` confidence with inter-layer agreement metric (stddev across surviving layers, normalized)

**Backtest regression diff** generated for items 1, 2, 9 → committed to `docs/signal-regression/2026-05-02_phase1_math.csv`.

### PHASE 2 — On-chain page (Image 8 headline bug, ~3 hours)
Fix the page that shows "live · live · live" with blank cards.

10. **C3** — Add `_data_source_health()` helper that probes each source (Glassnode key + last response timestamp + last error). Returns one of `live | cached(Nm) | rate-limited | no-api-key | geo-blocked | fetching | error(reason)`.
11. **C4** — On-chain card render: replace `or` truthiness chains with explicit `_v(value if value is not None else fallback, ...)`.
12. **C5** — Wire real `active_addresses_24h` from `fetch_coinmetrics_onchain` (free, no key, BTC works) — replace hardcoded `None`.
13. **Wire CoinMetrics free tier** as primary on-chain source for BTC (MVRV-Z, SOPR, active addresses), Glassnode as overlay when key is present, Dune for chain-specific queries (deferred — needs query IDs configured).
14. **Drop "Native RPC" pill** until a real reader exists. (No `web3.py` import in repo today — pill is fictional.)
15. **C12** — `whale_tracker._synthesize_signal` adds `result["events"] = moves[:25]`. Page render uses 3-state copy: offline / live-quiet / live-with-events.

### PHASE 3 — Bright-green saturation (cosmetic, ~1 hour)
Single CSS pass fixes Images 4, 6, 7, 8 cosmetic complaints app-wide.

16. **C9** — Delete `ui_components.py:178-200` legacy `linear-gradient !important` block.
17. **C10** — `.streamlit/config.toml:3 primaryColor` → `#1a3a32` (matches `--accent-soft`).
18. `ui/overrides.py:580-583` — flip `var(--accent)` to `var(--accent-soft)` on active states.
19. **Multiselect tag chip styling** — add CSS pass for `[data-testid="stMultiSelect"] [data-baseweb="tag"]` with muted background + smaller padding.
20. **Sidebar Legal item** — add `[data-testid="stExpander"] summary { white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }` scoped to sidebar.
21. **Topbar narrow viewport** — add `@media (min-width: 769px) and (max-width: 1023px)` block to collapse update/theme buttons to icon-only or shorten labels.

### PHASE 4 — Truthful empty-states + status pills (~2 hours)
22. Create `truthful_empty_state(reason, level, detail)` in `utils_format.py` with 9 reason codes × 3 user-level tiers.
23. Create `data_source_health()` shared helper used by all 4 page headers (Dashboard, Signals, Regimes, On-chain).
24. **C7** — Funding rate table: convert literal `None` to truthful `"geo-blocked"` / `"rate-limited"` / `"timeout"` based on `rd.get("error")` reason code.
25. Add health probe at app startup that detects geo-block on Binance/Bybit/KuCoin from current datacenter IP. Cache result 15 min. Drives both the routing logic AND the status pill.
26. Replace 7 copies of generic "page failed to load — check logs" with page-specific truthful messages.
27. `app.py:3956` `st.error(f"Retune failed: {_e_rt}")` — wrap with `truthful_empty_state("error", level, ...)` so raw exceptions never leak to user (CLAUDE.md §8 violation today).

### PHASE 5 — Functional fixes from Images 1, 5, 7 (~2 hours)
28. **C11** — Hero card cascade (Image 1): mirror watchlist's `_sg_cached_live_prices_cascade` call into `_ds_build_hero` for non-OKX-SWAP pairs (XDC, SHX, ZBCN, FLR, etc.).
29. **C8** — Spot arb table (Image 5): when `signal == "NO_ARB"` populate buy-on with `min(asks)` exchange and sell-on with `max(bids)` exchange so the table reveals where price differences live.
30. **C6** — Hyperliquid funding parser (Image 7):
   - Rename field `funding_rate_8h` → `funding_rate_1h` (matches API contract)
   - Annualize as `rate * 24 * 365 * 100` (was `× 3 × 365 × 100`)
   - Fix batch-mode caching to populate all pairs in one POST (currently caches only `pairs[0]`)
31. **Funding Rate Monitor display** (Image 7): expand the 4 displayed columns to 9 (matching the 9 queried exchanges) OR add a "Best Rate" tooltip that lists the broader exchange universe.

### PHASE 6 — Data-feed resilience polish (~1.5 hours)
32. Add `_SESSION.cache.clear()` to `_refresh_all_data` (`app.py:1650-1711`) — `requests-cache` HTTP cache currently survives the Refresh All Data button.
33. Add `_FNG_CACHE` to the cache-clear list (Fear & Greed sticks at last reading after refresh until 24h TTL).
34. Funding cache TTL: 300s → 600s (CLAUDE.md §12 spec).
35. CryptoPanic auth header: pass key from `config.CRYPTOPANIC_API_KEY` (currently sends `public=true` + ignores key → 50 req/24h instead of 50k/month).
36. Glassnode 429 handling: stop retrying 3× (daily cap won't recover within request window), cache the rate-limited state for 30 min, surface "rate-limited" in pill.
37. Add `BingX` to data-feeds (in CLAUDE.md §10 but absent from code). Remove Coinbase/Gemini from UI dropdown OR wire fetchers (currently dropdown lists with no fetcher).
38. `.env.example` add: `CRYPTOPANIC_API_KEY`, `CRYPTORANK_API_KEY`, explicit `GLASSNODE_API_KEY`, `LUNARCRUSH_API_KEY` documentation.

### PHASE 7 — Test coverage backfill (~3 hours)
Per CLAUDE.md §22 + the test-coverage audit. New test files in priority order:

39. `tests/test_hero_card_cascade.py` (Image 1)
40. `tests/test_arbitrage_buy_sell_on.py` (Image 5)
41. `tests/test_funding_rate_parser.py` (Image 7 — Hyperliquid annualization, geo-block label)
42. `tests/test_onchain_page_binding.py` (Image 8 — pills truthful, cards populate)
43. `tests/test_status_pill_truthfulness.py` (cross-cutting)
44. `tests/test_empty_state_helper.py` (the new truthful_empty_state helper)
45. `tests/test_composite_signal_critical_fixes.py` (regression for C1, C2)
46. `tests/test_indicator_fixtures_extended.py` (close §22 fixture mandate gap on `cycle_indicators`, `risk_metrics`, `top_bottom_detector`)
47. `tests/test_ml_predictor_holdout.py` (regression for C14)
48. `tests/test_whale_tracker_states.py` (3-state disambiguation)
49. `tests/test_streamlit_cloud_geo_probe.py` (datacenter-IP detection caching)

Fix the existing hidden-skip at `tests/test_data_wiring.py:169` (C16) — replace bare `return` with `pytest.skip("reason")`.

### PHASE 8 — Backtester integrity (~1.5 hours)
Per math audit:

50. Add slippage model on stop-loss fills in `crypto_model_core.run_deep_backtest`.
51. Include funding cost on perpetual positions in PnL (currently price-delta only).
52. Fix entry-at-same-bar-close → use next-bar open (current entry is unattainable in live execution).
53. Add survivorship-bias note to backtest report — universe should be historical top-100, not current.

---

## 4. Effort & sequencing

Estimated total: **14–17 hours of focused work**, parallelizable into 2 sessions:

| Session | Phases | Hours | Risk |
|---|---|---|---|
| Session 1 | 1, 2, 3, 4 (math + on-chain + UI + empty states) | 8–9 | Touches signal logic — needs backtest diff & full audit |
| Session 2 | 5, 6, 7, 8 (functional + data-feed polish + tests + backtester) | 6–8 | Lower risk — mostly additive |

Per CLAUDE.md §3: every phase committed atomically with the full written report in the message. Per §4: full audit pass on each phase before committing.

---

## 5. What this game plan does NOT do

Out of scope for this sprint (worth flagging for future):
- New mockups for Settings → Trading / Settings → Dev Tools / AI Assistant (these are bucket (b) — no design exists yet; current "legacy" appearance is the only spec). Recommend mockup work as a separate sprint.
- Token-unlock + fundraising data wiring per CLAUDE.md §10 (cryptorank.io). Architecturally specced but not surfaced in any UI page yet — this is a feature add, not a bug fix.
- Web3 Level B activation (transaction execution from app per global CLAUDE.md §11). Requires explicit go-signal.
- ML predictor full retrain + validation suite. Phase 1 fixes the holdout direction; full re-training is its own sprint.

---

## 6. What you need to do

Reply with one of:
- **"Approved, go"** → I execute Phases 1–8 in order, commit + push each phase atomically with full report, run audit per CLAUDE.md §4 after each.
- **"Approved through Phase N"** → I execute up to that phase only, then stop for re-approval.
- **"Skip phase N"** / **"Reorder X before Y"** / **"Drop item C20"** → tell me the modifications and I'll re-confirm scope before executing.
- **"Hold — questions first"** → I'll answer before any work begins.

Per CLAUDE.md §16: once approved, the authorization persists across sessions. No re-approval needed if context limits force a session break.

---

**End of game plan.** All 7 audit reports listed in §0 are ready for your review. Recommended reading order: this doc first, then `_onchain_data_audit.md` (highest-impact bug), then `_math_audit.md` (highest-correctness risk), then the cosmetic ones.
