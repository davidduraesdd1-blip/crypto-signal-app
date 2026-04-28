# Crypto Signal App — Redesign Baseline Audit

**Date:** 2026-04-28
**Auditor:** Claude (Opus 4.7, autonomous per CLAUDE.md §1)
**Scope:** Entire codebase, every Python file, every redesign branch on GitHub
**Goal:** Establish a clean, fully-verified baseline so the next sprint of changes
begins from zero known issues.

---

## 0. Restore points (created 2026-04-28, pushed to origin)

| Tag | Branch | Commit |
| --- | --- | --- |
| `backup-pre-baseline-audit-2026-04-28-main` | main | f2098d5 |
| `backup-pre-baseline-audit-2026-04-28-ui2026-05-parent` | redesign/ui-2026-05 | 4e2f993 |
| `backup-pre-baseline-audit-2026-04-28-ui2026-05-p0fixes` | redesign/ui-2026-05-p0-fixes | 992132a |
| `backup-pre-baseline-audit-2026-04-28-ui2026-05-pagescss` | redesign/ui-2026-05-pages-and-css | afa7f60 |
| `backup-pre-baseline-audit-2026-04-28-ui2026-05-plotly` | redesign/ui-2026-05-plotly | 526c7bb |
| `backup-pre-baseline-audit-2026-04-28-ui2026-05-sidebarpolish` | redesign/ui-2026-05-sidebar-and-polish | 015f54a |

Restore command: `git checkout backup-pre-baseline-audit-2026-04-28-<suffix>`

---

## 1. Branch & file inventory

### 1.1 Branch map

**Local (8) + remote (16) branches surveyed.**

#### Active redesign branches (5)

```
redesign/ui-2026-05                       4e2f993  PARENT (origin: 29 ahead — pages-and-css merged in)
redesign/ui-2026-05-p0-fixes              992132a  +250 lines vs parent  (sparkline + sidebar fixes)
redesign/ui-2026-05-pages-and-css         afa7f60  +2,754 lines vs parent (pages + CSS + tests)
redesign/ui-2026-05-plotly                526c7bb  +2,979 lines vs parent (pages-and-css + plotly template)
redesign/ui-2026-05-sidebar-and-polish    015f54a  +617 lines vs parent  (LOCAL-ONLY 5 commits unpushed)
```

**Canonical "most advanced" state:** `origin/redesign/ui-2026-05-plotly` (526c7bb).
This branch is a superset of pages-and-css plus the plotly theming template.

**Reconciliation needed:** The 4 sub-branches diverged from the parent. Before
merging anything to `main`, these need to be folded together (see §1.4).

#### Other branches

```
main                                      f2098d5  (origin behind 12 — feedback checkpoint commits)
master                                    98b1b35  ABANDONED (initial v5.9.13 commit, do not use)
claude/confident-lovelace-beeebb          7d0a701  worktree branch, behind main 15
claude/hopeful-pike-94f951                5d0a3e4  worktree branch (current audit session)
claude/keen-faraday-10b9bb                667b433  worktree branch, behind main 20
dependabot/* (5 branches)                          version bumps; see §1.3
```

#### Worktrees

```
C:/dev/Cowork/crypto-signal-app                                       main
C:/dev/Cowork/crypto-signal-app/.claude/worktrees/keen-faraday-10b9bb  redesign/ui-2026-05 (parent, stale by 29 vs origin)
C:/dev/Cowork/crypto-signal-app/.claude/worktrees/confident-lovelace-beeebb  redesign/ui-2026-05-plotly (current state)
C:/dev/Cowork/crypto-signal-app/.claude/worktrees/hopeful-pike-94f951  claude/hopeful-pike-94f951 (audit session)
```

### 1.2 File inventory (root .py files)

Tier-A heavy (≥1,000 lines or critical math):

| File | Lines (main) | Lines (plotly) | Δ |
| --- | ---: | ---: | ---: |
| app.py | 7,844 | 9,505 | +1,661 |
| data_feeds.py | 7,819 | 7,819 | 0 (no UI overlap) |
| crypto_model_core.py | 5,809 | 5,809 | 0 |
| ui_components.py | 4,814 | tbd | tbd |
| database.py | 3,201 | 3,201 | 0 |
| top_bottom_detector.py | 1,987 | 1,987 | 0 |
| agent.py | 1,310 | 1,310 | 0 |
| execution.py | 1,073 | 1,073 | 0 |

Tier-A medium:
- composite_signal.py 962 (gold-reference signal aggregator)
- cycle_indicators.py 407 (math-heavy, has fixtures)

Tier-B integration (counts pending):
- ai_feedback.py, ml_predictor.py, news_sentiment.py, risk_metrics.py,
  whale_tracker.py, arbitrage.py, options_model.py, allora.py,
  llm_analysis.py, circuit_breakers.py, scheduler.py, websocket_feeds.py

Tier-C surface (counts pending):
- api.py, alerts.py, chart_component.py, glossary.py, pdf_export.py,
  config.py, evaluate_headless.py, utils_audit_schema.py,
  utils_cross_app_safety.py, utils_family_office_report.py,
  utils_format.py, utils_wallet_state.py

UI package (new in redesign):
- ui/__init__.py 41 → 75 lines
- ui/design_system.py 309 → 313 lines
- ui/sidebar.py 580 → 1,186 lines (more than doubled in plotly)
- ui/overrides.py 386 → 743 lines
- ui/plotly_template.py 197 (plotly branch only)

### 1.3 Dependabot branches (info only, not blockers)

5 open dependabot PRs against origin:
- `dependabot/pip/fastapi-gte-0.136.1`
- `dependabot/pip/hmmlearn-gte-0.3.3`
- `dependabot/pip/lightgbm-gte-4.6.0`
- `dependabot/pip/scikit-learn-gte-1.8.0`
- `dependabot/pip/statsmodels-gte-0.14.6`
- `dependabot/github_actions/...checkout-6`
- `dependabot/github_actions/...setup-python-6`
- `dependabot/github_actions/...upload-artifact-7`

**Recommendation:** Defer until after redesign merges to main. Re-evaluate then.

### 1.4 Drift / hygiene findings

**FINDING-001 (HIGH):** `redesign/ui-2026-05-sidebar-and-polish` has 5 local
commits not pushed to origin. Per §3 "no half-committed states ever; every
unit pushed immediately." → **ACTION:** push these commits in Phase 9.

**FINDING-002 (HIGH):** `redesign/ui-2026-05` (parent) is 29 commits behind
origin. The local `keen-faraday-10b9bb` worktree is on a stale branch tip.
→ **ACTION:** sync the worktree before applying any fixes.

**FINDING-003 (MEDIUM):** Sub-branch divergence — 4 redesign sub-branches with
overlapping work. No clear merge plan documented.
→ **ACTION:** decide canonical branch (recommend `-plotly`) and rebase/merge
others into it before next sprint.

**FINDING-004 (LOW):** `origin/master` is the abandoned initial commit
(98b1b35 — "Initial commit — CryptoSignal app v5.9.13"). Causes confusion
when developers expect main/master parity.
→ **ACTION:** consider deleting `origin/master` or documenting in README that
`main` is canonical.

**FINDING-005 (LOW):** `data/feedback_checkpoint.json` shows uncommitted
modification on the main worktree. This is from the auto-feedback CI loop
(commits every ~6h via `feedback_evaluator.yml`). Transient; not a blocker.

**FINDING-006 (LOW):** Two stale `claude/*` worktree branches behind main by
15-20 commits (`claude/confident-lovelace-beeebb`, `claude/keen-faraday-10b9bb`).
→ **ACTION:** prune or refresh in Phase 9.

**FINDING-007 (HIGH):** `tests/verify_deployment.py` is referenced in MEMORY.md
(used 2026-04-23, 5/5 passed) and pending_work.md task #9 — but the file does
**NOT exist** anywhere in the repo. Either deleted post-2026-04-23 or never
committed. Per CLAUDE.md §25 the deployment verification protocol depends on
this file existing. Without it, sprint task #9 is impossible.
→ **ACTION:** restore/recreate `tests/verify_deployment.py` in Phase 9.
The script needs to: GET base URL, check HTTP 200, check no Python error
signatures, check expected shell markers (`streamlit`, `<script`, `root`),
hit `/_stcore/health`. 5 checks, ~50-80 lines.

**FINDING-008 (MEDIUM):** `gitleaks` and `pre-commit` are not installed on
local PATH. Pre-commit hooks (`.pre-commit-config.yaml`) won't run locally.
CI workflow `secret-scan.yml` likely covers it on push, but local commits
bypass the secret scanner. Per §3 push hygiene this is a small but real risk.
→ **ACTION:** document in README install steps. CI scanner is the
authoritative gate per §22 ARP discipline.

**FINDING-009 (INFO):** Manual hardcoded-secret regex scan across all *.py
files: **clean.** Patterns checked: `sk-ant-`, `sk-proj-`, `AKIA`, `AIza...`,
`ghp_...`, `gho_...`, `xox[baprs]-`, plus generic `(api_key|secret|password|
token|bearer)\s*=\s*['"][a-zA-Z0-9_-]{16,}`. Only match was the `sk-ant-example`
placeholder in `.gitleaks.toml` allowlist (intentional false positive).

### 1.5 Pending sprint reconciliation

`pending_work.md` lists 10 redesign tasks, all unchecked. Actual code state:

| # | Task | Status in code |
| --- | --- | --- |
| 1 | Copy ui_design_system.py → ui/design_system.py + inject_theme() | ✓ DONE (ui/design_system.py exists, 309-313 lines) |
| 2 | Replace ui/sidebar.py with new left-rail design | ✓ DONE (ui/sidebar.py exists, 580-1186 lines) |
| 3 | Port landing/home page per mockup | ✓ DONE (commits e87c734, 061563c, f4bbbd4) |
| 4 | Port each remaining page, one per commit | PARTIAL (Backtester ✓ 7d887e7, regimes/signals tbd) |
| 5 | Replace hard-coded hex colors with CSS variables | TBD — needs verification |
| 6 | Verify both themes + mobile on every page | NOT DONE (per §1.4 manual walk pending) |
| 7 | data_source_badge() on every data card | TBD — needs verification |
| 8 | Run §24 post-change audit after each commit | TBD — review MEMORY.md |
| 9 | Run verify_deployment.py after every push | DONE 2026-04-23, not since |
| 10 | Open PR redesign/ui-2026-05 → main with approval | NOT DONE (correctly held) |

→ **ACTION:** update `pending_work.md` checkboxes to true state in Phase 9.

---

## 2. Per-file audit findings

> Format per issue: `file:line | SEVERITY | description | proposed fix`
> Severities: CRITICAL / HIGH / MEDIUM / LOW.

### 2.1 Tier A — Heavy files

#### app.py (9,505 lines on plotly branch)

**Totals:** 4 CRITICAL · 21 HIGH · 60+ MEDIUM · 30+ LOW

**CRITICAL**
- `app.py:9422` | `_cached_whale_activity()` called with NO args; signature requires `(pair: str, price: float)` → On-chain page crashes on every load (caught by outer try/except). Function returns dict but downstream `isinstance(_whale, list)` check assumes list — entire whale section is dead | Fix call shape + return-type handling
- `app.py:3402-3414` | Broken f-string ternary in Trade Action Card (Entry/Stop/TP cells) — when `entry`/`stop`/`tp1` is None the surrounding `</div>` tags concatenate wrong, producing malformed HTML and breaking the 3-col grid | Build inner-value string conditionally first, single uniform card template
- `app.py:6939-6942` | `time.sleep(0.1)` + `st.rerun()` loop blocks the render thread on Backtester / Paper Trades. 5-second polling re-executes the entire script. On Streamlit Cloud cold starts, compounds into 503 health-check timeouts | Use `@st.fragment(run_every=5)` instead
- `app.py:7252` | `_cached_resolved_feedback_df(days=365)` loads a full year of feedback on every cache miss; combined with hot-path Backtester→Advanced traversal, stalls cold renders | Cap days to 90 or memoize separately with longer TTL

**HIGH (top picks; all 21 in agent transcript)**
- `app.py:613-623` | Legacy SIGNAL_CSS hard-codes dark hex (`#1e293b`, `#22c55e`) AFTER design-system inject — overrides tokens; **light-mode users see dark cards on light background** | Remove block; use `var(--card-bg)`, `var(--success)`
- `app.py:7282` | ECE calc fragile — `_mid = (conf_bucket + 5)/100` but no clamp/assert that `confidence` is in [0,100]; mixing units silently | Validate range
- `app.py:8984, 8988, 8786-8800, 6143-6156, 8230-8253, 4318` | Multiple uncached fetches of F&G, funding, OHLCV per render — TTL violations vs §12 (F&G should be 24h, funding 10min, OHLCV 5min). Sequential 32-call funding loop on every "Load Rates" click | Add `@st.cache_data` wrappers + ThreadPoolExecutor
- `app.py:4127-4141, 5008` | `@st.dialog` decorators inside `page_dashboard()` re-register per render → duplicate-key risks/stale closures | Move dialogs to module level, pass via session_state
- `app.py:4953-4957` | Override-config save: read-modify-write without file lock → race-prone across browser tabs | `os.replace(tmp, dest)` atomic write
- `app.py:5072-5099` | "Allowlist" for `selected_pairs` is built FROM the multiselect's option list → security check is a no-op | Build from `model.PAIRS + TIER1 + TIER2`
- `app.py:1136` | `_status.startswith(...)` on possibly-non-str → AttributeError | `str(_status).startswith(...)`
- `app.py:3692, 8249, 8291` | Funding annualization magic number `1095` repeated, plus `* 365 * 3` inline | `FUNDING_PERIODS_PER_YEAR = 1095` constant
- `app.py:3651-3670` | `@st.cache_data` on inner function inside `page_dashboard()` — cache identity can leak per-render | Hoist to module scope
- `app.py:8243` | `_cached_alerts_config()` hit 14+ times per render, repeatedly invalidated via `.clear()` (lines 686, 720, 1043, 2787, 3533) | Read once per page, pass into helpers
- `app.py:6492` | `if equity and len(equity) > 1:` raises ValueError on numpy arrays | `equity is not None and len(equity) > 1`
- `app.py:5808-5814 vs 8514` | Same agent config key has two different validation ranges in two forms | Standardize bounds
- `app.py:1015-1024` | `_PAGE_MAP` dead code, no caller reads it | Delete
- (full HIGH list logged in agent transcript at `tasks/afe8481772172e5e9.output`)

**Page registry observed:** Dashboard, Signals, Regimes, On-chain, Config Editor (Settings), Backtest Viewer, Arbitrage (Opportunities), Agent (AI Assistant). Routed via lines 9479-9494. Sidebar nav at 940-956 (Markets / Research / Account groups).

**Theme/level handling:**
- ✓ Design system injected at lines 593-607 first
- ✗ Legacy SIGNAL_CSS at 613-623 overrides tokens with hard-coded dark hex (light-mode breakage)
- ✓ User level read consistently from session_state
- ✓ Most badges shape+color (▲▼■); some 🟢🟡🔴 status pills color-pair-only
- ✗ Many HTML f-strings hard-code `#ef4444`, `#f59e0b`, `#00d4aa`, `#f8fafc`, `#1f2937` — won't theme correctly in light mode

**Plotly template usage:** PARTIAL. Registered at line 605, re-applied on theme toggle at 888. But many `st.plotly_chart` calls override with explicit `paper_bgcolor`/`plot_bgcolor`/font/grid hex (lines 2989-2993, 4258-4276, 6160-6168, 7775-7777, etc.) — per-chart overrides bypass the template.

**§12 cache TTL violations on render path:**
- F&G fetched live unbuffered at 1518, 8984, 9187 (should be 24h cache)
- Funding rates uncached at 1527, 8230, 8882, 8988 (should be 10min)
- On-chain has no Streamlit-layer cache on On-chain page (relies on data_feeds module cache only)
- Composite signal cached 5min via `_cached_blood_in_streets` ✓ matches §12
- Regime via session_state, no explicit 15min TTL

**`data_source_badge()` adoption:** PARTIAL. Used in `page_header(data_sources=[...])` calls (lines 1496-1500, 8734-8738). Many cards in `page_dashboard()` still lack the badge.

#### data_feeds.py (7,819 lines)

**Totals:** 6 CRITICAL · 14 HIGH · 25 MEDIUM · 15 LOW

**CRITICAL**
- `data_feeds.py:3744` | `get_kimchi_premium()` calls `api.binance.us` — datacenter-blocked per §10. Silently fails on Streamlit Cloud, corrupts kimchi premium calc | Replace with OKX BTC/USDT primary path
- `data_feeds.py:3949, 4165` | Macro fetcher `wait_event.wait(timeout=90)` → if FRED hangs, every concurrent worker blocks 90s, well above Streamlit health-check window | Reduce to 15-20s + return cached/None
- `data_feeds.py:3967` | `_macro_cached_get` finally-block calls `my_event.set()` where `my_event` may be None → latent NoneType crash | `if my_event is not None: my_event.set()`
- `data_feeds.py:1822-1825` | LunarCrush key path inconsistent: env-var name vs `_get_runtime_key` map mismatch — global-key flow bypasses per-session UI-paste mechanism | Route through `_get_runtime_key("lunarcrush_key")`
- `data_feeds.py:7272` | Etherscan request appends `apikey={key}` directly in URL string → leaks API key into retry logs / proxy logs (3× per retry) | Use `params={"apikey": ...}`
- `data_feeds.py:5908-5938, 6028` | CMC `X-CMC_PRO_API_KEY` header — if any debug-logging adapter attached to `_SESSION`, key leaks | Document forbidden, or scrub headers in any custom adapter

**HIGH — TTL violations vs §12 (Crypto Signal App)**
- `_FNG_TTL=900` (15min) and `_FNG2_TTL=3600` (1h) — spec is **24h** ✗
- `_ONCHAIN_TTL=300` (5min) — spec is **1h** ✗
- `_MULTI_FR_TTL=300` (5min) — spec is **10min** (acceptable but flag)
- `_MACRO_TTL=3600` (1h) — spec is **2h** ✗
- `_CACHE_TTL_SECONDS=300` (funding) — close to 10min spec, document
- `_GN_TTL=3600` for Glassnode on-chain — matches §12 ✓
- `_CM_OC_TTL=3600` for CoinMetrics — matches §12 ✓

**HIGH — §10 spec gaps (data sources mandated by CLAUDE.md but absent)**
- ✗ **cryptorank.io /token-unlock** (PRIMARY for token unlocks per §10) → NOT IMPLEMENTED. Tokenomist used instead.
- ✗ **cryptorank.io /funds + funding-round** (PRIMARY for VC fundraising sentiment per §10) → NOT IMPLEMENTED.
- ✗ **Dune Analytics** (SECONDARY for on-chain BTC/ETH per §10) → ABSENT.
- ✗ **pytrends / Google Trends** (PRIMARY sentiment Layer 3 per §10) → ABSENT (despite being in `requirements.txt`).
- ⚠ **Bybit funding "datacenter-IP quirks" warning/fallback** → no explicit Streamlit Cloud guard.

**HIGH — other**
- `data_feeds.py:62-66, 87-91` | `_SESSION` retry config: 429 in `status_forcelist` + `backoff_factor=1` + `total=3` retries + `timeout=10` per request → can produce 30-40s blocking on rate-limit storms | Cap total wallclock 10-15s
- `data_feeds.py:1065-1069` | `fetch_binance_liquidations` calls geo-blocked endpoint → 6s wasted per pair on every refresh from US Cloud | Guard with `is_us_streamlit_cloud()` short-circuit
- `data_feeds.py:1226, 1442, 2272, 1843, 1912, 1989, 2068, 3239, 3382, 3454, 4416, 4944, 7553` | ~13 endpoints lack 429 detection; only OKX/Binance/Bybit/CoinGecko/KuCoin paths handle rate-limit explicitly | Add 429 handling
- `data_feeds.py:7081-7106` | `_get_runtime_key` only maps 3 keys (`coingecko_key`, `lunarcrush_key`, `tiingo_key`); Glassnode/CryptoQuant/Coinglass/CMC/Tokenomist/Coinalyze bypass the runtime-key UI flow | Add full mapping
- `data_feeds.py:1402-1411 vs 1415-1432` | `_fetch_binance_fr` actually calls Bybit (variable shadowing) — duplicate of `_fetch_bybit_fr`; key collision in `get_multi_exchange_funding_rates` | Rename or consolidate
- `data_feeds.py:1547-1549` | `ccxt.RateLimitExceeded` not specifically handled when 14 ccxt exchanges parallelize → silent N/A everywhere on rate-limit storm | Add explicit handler
- `data_feeds.py:209-233` | `RateLimiter.acquire(timeout=30)` busy-loops with sleep(0.05); 16-pair parallel scan serializes through single token bucket → 40+s | Acceptable but flag
- `data_feeds.py:1474-1496` | `_get_ccxt_exchange` cached per-process; ccxt instances **not thread-safe** in all cases → concurrent `fetch_funding_rate` races | Per-thread instance or lock per call
- (full HIGH list at `tasks/a63b98762d9bbd11c.output`)

**Hardcoded API keys:** None in code (clean per regex scan). Risk: Etherscan in URL (CRITICAL above), CMC in header (CRITICAL above).

**Active sources** (~38 distinct endpoints): CCXT (10 exchanges), OKX, Bybit, Gate.io, MEXC, Binance public/futures/US, Kraken, CoinGecko, CoinPaprika, CoinMarketCap, alternative.me, Deribit, Hyperliquid, Coinglass, CryptoQuant, Glassnode, LunarCrush, Tokenomist, CoinMetrics, Blockchain.com, DeFiLlama, GeckoTerminal, FRED, yfinance, exchangerate-api.com, Upbit/Bitso/Mercado/CoinDCX/Bitstamp/Bitget, Coinalyze, Jupiter, dYdX v4, Raydium, Zerion, Etherscan, GitHub.

#### crypto_model_core.py (5,809 lines) — math engine

**Totals:** 8 CRITICAL · 21 HIGH · 25 MEDIUM · 15 LOW

**CRITICAL — math correctness**
- `crypto_model_core.py:1421-1425` | `compute_atr` uses **rolling SMA** (Cutler ATR), but `_enrich_df` uses **EWM** (Wilder ATR). **Two inconsistent ATR implementations** — same indicator returns different values per caller | Standardize to Wilder EWM `tr.ewm(alpha=1/period, adjust=False).mean()`
- `crypto_model_core.py:1528-1543` | `compute_adx` uses rolling SMA for ATR + DI smoothing; `_enrich_df` uses EWM. **Two inconsistent ADX implementations** side-by-side | Replace `.rolling(period).mean()` with `.ewm(alpha=1/period, adjust=False).mean()`
- `crypto_model_core.py:1865-1871` | `compute_gaussian_channel` mis-uses `np.convolve` — kernel direction is anti-causal: `weights[0]` (highest weight) applied to OLDEST bar, not most recent. Channel under-weights recent bars | Reverse weights: `np.convolve(close, weights[::-1], mode='full')[:n]`
- `crypto_model_core.py:2487` | `strategy_bias = "Balanced"` reassigned mid-function; if regime is "Neutral" (no branch fires), bias stays "Balanced" and F&G mean-reversion check at 2519 silently classifies Neutral as trend-follow | Remove line 2487 reassignment
- `crypto_model_core.py:2702` | Sigmoid calibration `100/(1+exp(-(score-50)/20))` applied AFTER clamp; **breaks HOLD threshold band** — raw scores 45-54 map to 41.7-58.3, pushed OUT of HOLD band (45-54) into BUY/SELL territory after sigmoid | Apply thresholds pre-sigmoid OR recalibrate HOLD band
- `crypto_model_core.py:1500-1502` | `compute_vwap` uses `volume.cumsum()` over the entire DataFrame — anchored VWAP from start (8+ days for 1h, 16+ days for 4h), not session VWAP | Document as anchored OR reset on UTC day boundary
- `crypto_model_core.py:1409` | `compute_bollinger` no `len < window` guard → silent NaN cascade on short data | `if len(series) < window: return price, price, price`
- `crypto_model_core.py:858, 869` | HMM regime detector slice alignment brittle (relies on derived series starting at same base); first 19 bars of rolling vol are NaN — should add `assert len(log_ret) == len(vol) == len(ema_slope)`

**HIGH (top picks)**
- `crypto_model_core.py:1387-1396` | `compute_rsi` returns `50.0` on insufficient data — silently masks NaN cascade | Return None/NaN
- `crypto_model_core.py:1394, 2134` | `gain / loss.replace(0, 1e-10)` — replacement makes `rs` astronomically large but brittle when `loss` is genuinely tiny (1e-12) | Use `np.where(loss == 0, 100.0, ...)`
- `crypto_model_core.py:2244, 2515-2516, 2629, 4338-4340` | NaN-propagation hazards: `float(NaN) < 30 → False` causes "low ADX" misroutes silently; Ichimoku falls to "In Cloud" default when both senkou are NaN | Add `pd.isna` guards
- `crypto_model_core.py:2378, 2466, 2475` | `candle_score` and "Near S/R" bonuses added RAW (no weight) — asymmetric bullish bias up to ±15 raw points | Wire through weights dict
- `crypto_model_core.py:2644-2646, 2520-2523, 4475-4549` | Multiple multiplicative confidence modifiers stacking (F&G, Wyckoff, trend, macro, CVD, PCR, Kimchi) without normalization → "stacked-bias overconfidence" | Normalize or cap compound effect
- `crypto_model_core.py:1716` | Chandelier `direction_prev` uses ONLY `long_stop` for direction comparison; bearish flips via short-stop crosses are missed entirely | Compare to both stops
- `crypto_model_core.py:3658-3660` | Sharpe annualization wrong: `* sqrt(n_returns)` for trade-level returns produces scale-dependent value; should be `sqrt(periods_per_year)` | Fix annualization
- `crypto_model_core.py:3667-3668` | Sortino uses `downside.std()` without subtracting MAR before squaring — non-canonical | Document or fix
- `crypto_model_core.py:1900-1923, 1924-1967` | `detect_macd_divergence_improved` and `detect_rsi_divergence` use 2-bar peak detection (extremely noisy on crypto); structurally identical → DRY | Use `scipy.signal.find_peaks` with prominence; consolidate
- `crypto_model_core.py:1438-1448` | SuperTrend Python `for` loop runs 4× per pair per TF (compute_supertrend_multi calls 3, plus _enrich_df) | Numba-jit or vectorize
- `crypto_model_core.py:1313, 2660-2666` | `compute_supertrend_multi` recomputes from inside `multi_agent_vote` → quadratic recomputation; BTC fallback fetch in for-loop = 28 redundant fetches per scan | Cache & reuse
- (full HIGH list at `tasks/abdbd5b96ce6b68cc.output`)

**Indicator parameters audited:**
- ✓ Bollinger 20/2σ, MACD 12/26/9, RSI 14, Stochastic 14/3, SuperTrend 10/3, Chandelier 22/3.0
- ✗ ATR / ADX — TWO inconsistent implementations (CRITICAL above)
- Δ Ichimoku 10/30/45 (deviates from canonical 9/26/52 — deliberate crypto adjustment, documented at 2150)

**Regime detector (HMM):** 3-state Gaussian, `n_iter=50`, `tol=1e-2`, `random_state=42`. Min 80 bars, falls back to None. State labeling sorts by `(mean_return ASC, -volatility DESC)` — tie-break by volatility desc can mislabel low-vol-low-return as "Trending". 3-bar majority-vote smoothing ✓. 15-min MD5-keyed cache ✓.

**Composite scoring (calculate_signal_confidence) — gold reference per §4:**
- Weights do NOT sum to 1.0 (intentional, raw-scale and percent-scale mixed — semantic heterogeneity).
- Bayesian merge at 283-287 doesn't normalize after blending.
- **No regression baseline** in `docs/signal-regression/` — required by project §4.
- Strategy_bias reassignment bug (CRITICAL).

**Functions lacking fixtures (per §4 mandate — ALL 22 indicators ZERO coverage):**
compute_rsi, compute_macd, compute_bollinger, compute_atr (×2 impls), compute_adx (×2 impls),
compute_supertrend(_multi), compute_stochastic, compute_ichimoku, compute_fib_levels,
compute_vwap (anchored, non-canonical), compute_hurst_exponent, compute_squeeze_momentum,
compute_chandelier_exit, compute_cvd_divergence, compute_gaussian_channel (CRITICAL bug
would fall out immediately), compute_support_resistance, detect_macd_divergence_improved,
detect_rsi_divergence, detect_candlestick_patterns, detect_wyckoff_phase,
compute_cointegration_zscore, detect_hmm_regime, calculate_signal_confidence.

**Top math fix priorities:** unify ATR/ADX (Wilder EWM); fix Gaussian Channel kernel direction;
remove `strategy_bias` reassignment; fix Sharpe annualization; add fixtures for 8 core
indicators; reconsider sigmoid effect on HOLD band; create regression baseline for
`calculate_signal_confidence` per §4.

#### ui_components.py (4,814 lines on plotly branch)

**Totals:** 9 CRITICAL · 16 HIGH · 25 MEDIUM · 15 LOW

**CRITICAL — XSS / a11y**
- `ui_components.py:1392` | `sidebar_header()` injects `exchange.upper()` raw via `unsafe_allow_html=True`; if `exchange` becomes user-configurable (Settings/URL param), `<script>` payload executes | `escape(exchange)`
- `ui_components.py:1010, 1014, 1031` | `section_header(title, subtitle, icon)` interpolates raw caller strings into HTML; many callers pass through ML/feed output | `html.escape()` before substitution
- `ui_components.py:1067-1070` | `render_card(title, icon)` injects raw → same XSS class | Escape inputs
- `ui_components.py:889` | `render_quick_access_row()` reads `data/alert_history.jsonl` and renders `_a.get('message')` via `st.markdown` — markdown phishing-link injection if attacker writes the file | `st.text` or escape markdown
- `ui_components.py:3964-3978, 3829-3835, 4044-4055, 4340-4351` | Four panels (`render_rsi_macd_divergence_panel`, `render_ttm_squeeze_panel`, `render_funding_rate_arb_panel`, `render_threshold_alerts_panel`) inject dict-derived strings raw — defense-in-depth fails | Escape all dict-derived strings
- `ui_components.py:1086-1090` | `_PILL_CFG["NEUTRAL"]` fg=`#64748b` on bg=`#1e293b` → contrast ratio ≈3.2:1, **fails WCAG AA** for body text. Used pervasively for HOLD/NEUTRAL pills | Lift fg to `#94a3b8` (≈5.8:1)

**HIGH — design tokens / a11y**
- **213 hardcoded hex/rgba color literals** in 4,814 lines; **zero imports from `ui/design_system.py`** — pending_work.md task #5 NOT STARTED in this file | Migrate to `var(--accent)`, `var(--success)`, `var(--danger)`, etc.
- `ui_components.py:1093-1110` | `signal_pill()` is **color-only** (no shape glyph) — violates §8 color-blind safety. Used heavily | Prepend ▲▼■ per `signal_badge_html()` pattern
- `ui_components.py:1115-1128, 1723-1741, 2096-2130, 2158-2165` | Four more color-only badges: `conf_badge_html`, `risk_level_badge_html`, `signal_accuracy_badge_html`, Hurst regime chip | Add shape encoding
- **~73 sub-12px font literals** (9px/10px/11px) violating §8 minimum (11px label, 13px body). Token `--fs-xxs: clamp(9px, 0.65vw, 10px)` itself violates §8 floor | Raise floor to 11px, use clamp tokens
- `ui_components.py:174-218` | `min-height:44px` on buttons only inside `@media (max-width:768px)` — desktop touch users (Surface/iPad) get sub-44px tap targets | Apply 44px globally
- `ui_components.py:1073, 1264, 1655, 2062, 2243, 2308, 2547, 2607, 3029, 3209, 3296, 3471, 3515, 3744, 4046, 4344, 4562, 4591, 4704` | `border-radius:12px` on cards but §8 mandates **10px**. (Note: `tokens.card_radius="12px"` in design_system also conflicts with §8 — flag for resolution)
- `ui_components.py:957-978` | `inject_css()` re-injects ~800-line CSS block per theme switch via `_components.html(...)` writing to `window.parent.document.body` — breaks under stricter same-origin / future Streamlit | Long-term: `prefers-color-scheme` or `st_theme`
- `ui_components.py:597-815` | Light-mode CSS block is 216 lines of inline-color flips — brittle, depends on exact hex strings; new inline `style="color:#fff8"` won't be flipped | Migrate to CSS variables
- `ui_components.py:1462-1492, 1502-1503, 1828-1829, 3114-3115` | "buy opportunity"/"sell signal" advisor language without disclaimer; risk_pct duplicated 3 places, fragile on entry≤0 | Hedge language, DRY helper

**`data_source_badge`:** NOT defined in `ui_components.py`. It IS in `ui/design_system.py:259` but this file has zero imports from `ui/design_system.py` → callers must import the design-system version directly.

**`unsafe_allow_html=True` count:** 31 instances. 7 with risky/external-derived input (CRITICAL list above).

**Components defined:** 73 (sample listed in agent transcript). Notable dead-code candidate: `render_what_this_means()` and `render_what_this_means_sg()` are two near-identical functions with overlapping intent — likely one should be deleted.

(Full findings at `tasks/ad543d09fd17f4423.output`)

#### database.py (3,201 lines)
*pending — assigned to parallel audit agent*

#### database.py (3,201 lines)

**Totals:** 2 CRITICAL · 4 HIGH · 8 MEDIUM · 5 LOW

**CRITICAL**
- `database.py:1778, 1793, 1823-1836` | F-string SQL building with `{int(days)}`, `{int(n)}`, `{where}` — `int()` cast prevents string injection, but **deviates from project's own SEC-CRITICAL-01 standard** (parameterized via `?` placeholders). Fragile if any future caller adds raw `pair` interpolation | Use `?` placeholders for consistency
- `database.py:3193-3201` | `init_db()` and `migrate_csv_to_db()` execute **at module import time**. Every Streamlit Cloud worker thread that imports `database` triggers full schema check + CSV migration scan. Stale CSV held by another process (Windows file locking) → migration silently logs warning, leaves table empty, no retry. Cold-start <60s per §12 at risk | Move to lazy-init function

**HIGH**
- `database.py:80, 137-150` | `_NoCloseConn` proxy converts `close()` to `rollback()` — `with _get_conn() as conn:` (line 3182) leaves transaction open; conn stays alive in pool indefinitely
- `database.py:405` | `init_db` uses `f'ALTER TABLE "{tbl}" ADD COLUMN "{col}" {col_def}'` — `_ALLOWED_MIGRATE_TABLES` whitelisted but `col` not whitelisted; low actual risk but unsafe pattern
- `database.py:2879-2895` | `get_pnl_summary` date parser builds format from string length — works by accident for common layouts but produces nonsense formats for variants
- `database.py:3024` | `_CHECKPOINT_FILE` written via `os.makedirs` + `open(..., "w")` — not atomic; mid-write crash leaves partial JSON unparseable on restart

#### top_bottom_detector.py (1,987 lines)

**Totals:** 0 CRITICAL · 4 HIGH · 8 MEDIUM · 5 LOW

**HIGH — math bugs**
- `top_bottom_detector.py:1654, 1677` | `struct_conf = int(sum(c * w for _, c, w in struct_pairs) / 1.0)` — division by `1.0` is a no-op; should be `/ struct_w_sum`. Same bug at `vol_conf` line 1677 → **confidence values inflated by ~5× when most layers report**
- `top_bottom_detector.py:947-965` | Wyckoff Spring detection: `recent_high = float(high.iloc[-3:].min())` — should be `.max()`. Upthrust at 959 uses `recent_high > range_high * 1.002` → **Upthrust signal effectively dead code** (almost never triggers since `min()` rarely exceeds `range_high * 1.002`)
- `top_bottom_detector.py:316-319, 320-323` | CVD divergence: `mid = n // 2` where `n=lookback=20` while `tail = lookback+5 = 25` bars → first half is rows 0-9, second half is rows 10-24 (**15 bars not 10**) → asymmetric windows skew detection
- `top_bottom_detector.py:1040-1062` | Pivot Points zone detection: `near_S/R` fallback **unconditionally overrides** `zone_score` even when `zone` text was already set → `zone="AT_R1"` with `zone_score=0.85 (S2 override)` inconsistent

**Critical concern (§4 mandate violation):** ZERO fixture tests despite project §22 ("each function has a fixture with a known-correct output"). 5-layer composite scoring with strong academic citations but no regression coverage at all.

#### agent.py (1,310 lines)

**Totals:** 3 CRITICAL · 4 HIGH · 8 MEDIUM · 5 LOW

**CRITICAL**
- `agent.py:1310` | `supervisor = AgentSupervisor()` created at import but `supervisor.start()` is never called from agent.py itself. Per §11 agent must be "fully active and operational at all times" 24/7. **Starting depends entirely on caller** — if neither app.py nor scheduler invokes `start()`, **agent silently stays dormant**. No watchdog | Module-level start with safe guard, or auto-start when first read
- `agent.py:1051-1054` | `SqliteSaver.from_conn_string(_ckpt_path)` used **outside its required context manager**. In current LangGraph (≥0.2) `from_conn_string` IS a context manager, not a constructor → underlying SQLite connection may be closed/invalid by the time `graph.invoke` runs → **silently breaks checkpoint persistence**. (`AG-13` claim of fix is wrong pattern.) | Wrap in `with` block per LangGraph 0.2+ API
- `agent.py:923, 905-906` | `_claude_credits_exhausted` global mutation in `except` block — `global` declaration at line 771 was inside same function scope so it works, but mixed-scope `global` is hard to audit

**HIGH**
- Soft-instruction reliance ("Never approve if max concurrent positions reached") — phantom-portfolio reads can cause false-rejects
- Anthropic client recreated on every Claude call (line 875-880) — no persistent client like news_sentiment uses
- `_INJECTION_PATTERNS` is small (7 patterns), case-folded substring match → bypassable via Unicode lookalikes/l33t/base64
- `_kill_event` polled but never `.join()`-ed on stop — old thread can run for full cycle before noticing kill

#### execution.py (1,073 lines)

**Totals:** 2 CRITICAL · 4 HIGH · 8 MEDIUM · 5 LOW

**CRITICAL**
- `execution.py:992-1064` | `check_circuit_breaker()` uses `trades_df["close_time"] >= since_str` with **lexicographic ISO-8601 comparison**. Works only if all rows use UTC ISO format. Legacy CSV-migrated rows may have non-ISO formats → silent miscounted P&L → **circuit breaker fails to trigger** | Parse to datetime, compare typed
- `execution.py:340-354` | `qty = max(1, round(_raw_qty))` — `_raw_qty=0.7` produces `qty=1`. For coin where `ct_size=10`, this places **>10× requested notional**. The qty>1000 cap catches massive oversizing but not the "round-up by 30-100%" case for modest orders | Reject orders below minimum quantity instead of rounding up

**HIGH**
- `execution.py:163-180` | `get_balance()` is synchronous network round-trip; called per-pair per-cycle from `agent._get_portfolio_state` → 30+ network calls/min for 30 pairs even with no orders
- `execution.py:478-501` | `auto_execute_signals` uses session-set `executed_pairs` per call; doesn't persist → two near-simultaneous scans can each place an order for same pair
- `execution.py:936-959` | `compute_vol_adjusted_size` annualizes with `(365**0.5)` assuming daily bars; comment admits "for hourly bars × sqrt(24×365)" but code never checks
- `execution.py:987-989` | `_DAILY_HALT_PCT=-2.0` overlaps `circuit_breakers.py` drawdown logic — **two systems, partial overlap**

### 2.2 Tier B — Integration files

#### Standout findings across 12 files

**CRITICAL — risk_metrics.py:282-283**
Sharpe annualization is **mathematically wrong**: `avg_hold_days = max(1.0, _LOOKBACK_DAYS / n_trades)` is the *average gap between trades*, not actual holding period. For 90-day lookback / 90 resolved trades this gives `1.0`, then `ann_factor = sqrt(365)` → **massively overstates Sharpe** for trades that actually held positions for hours. Per §4 "every calculation verified" — this is a load-bearing risk number used in agent gates.

**CRITICAL — circuit_breakers.py:50**
`_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "circuit_state.json"` puts state OUTSIDE the worktree. On Streamlit Cloud, parent of repo root is read-only mount → atomic write at 102-104 **fails silently → circuit breaker state never persists, halt is lost on every Streamlit rerun**.

**HIGH — whale_tracker.py:117**
Etherscan call uses **single hardcoded EF donation address** (`0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe`) "as proxy" for ETH whale activity → every "ETH whale activity" reading derives from one wallet's transactions, totally unrepresentative. **Mislabels the metric** entirely.

**HIGH — ml_predictor.py:42, 311-318**
`_MODEL_STORE_MAX_ENTRIES = 20` with FIFO eviction. With 37 pairs × 4 TFs = 148 entries vs 20 cap, **eviction thrashes** — 7× the requests hit eviction on every full scan, causing repeated retraining. Cold-start <60s OK because lazy, but steady-state CPU burn.

**HIGH — websocket_feeds.py:160-170**
Race window: two `WebSocketApp` instances can run in parallel during reconnects (stop+start) for up to a full reconnect cycle. Memory leak window during heavy Streamlit reruns.

**HIGH — scheduler.py:120-122**
If scan crashes between `write_scan_status(True)` and `write_scan_status(False)`, the `finally` releases the lock but **does not write a final status** → DB stuck in `running=1` forever, blocking next runs.

**Per-file 1-line summaries (Tier-B):**
- **ai_feedback.py** — A-F grading + Kelly + alert calibration with 14-day exp-half-life weighting. Alert calibration silently overwrites manual `min_confidence` overrides
- **ml_predictor.py** — GBM+XGBoost ensemble lazily-imported ✓; cache thrashing under realistic load
- **news_sentiment.py** — 4-source parallel fetch (CryptoPanic/CoinDesk/Cointelegraph/LunarCrush) + Claude Haiku NLP w/ rule-based fallback + credit-exhaustion breaker
- **risk_metrics.py** — VaR/CVaR/Sharpe/Sortino/Calmar/Kelly. Sharpe annualization wrong (CRITICAL above). Max-DD computed on independent signal P&L not portfolio P&L. No fixture tests
- **whale_tracker.py** — Multi-chain whale fetcher; ETH path fundamentally broken (CRITICAL above). SOL/XRP endpoints partially deprecated (data.ripple.com sunset 2023)
- **arbitrage.py** — Spot + funding-rate carry across 7 exchanges; bare-thread parallelism (no ThreadPoolExecutor); HTX endpoint deprecated 2024
- **options_model.py** — Black-Scholes + Greeks (scipy-optional), IV Rank/Percentile, FRED rate via raw urllib. No fixture tests
- **allora.py** — Upshot + Allora native; 6 hardcoded topics; 15-min cache exceeds 5-min prediction frequency
- **llm_analysis.py** — Claude sonnet for prose + haiku for weight adjustments + 1-2 sentence story; 3 separate caches with separate eviction; credit-exhaustion breaker
- **circuit_breakers.py** — 8-gate fail-safe-on-crash + manual-resume-only. **State file path outside worktree (CRITICAL above)**. HUMAN_OVERRIDE last in GATES list — should be FIRST so manual halt always wins
- **scheduler.py** — APScheduler BlockingScheduler with quiet-hours; no graceful SIGTERM; 30-min default doesn't match §12 SuperGrok 15-min recompute target
- **websocket_feeds.py** — OKX public WS with session-id reconciliation, watchdog reconnect, NaN/Inf rejection. Generally robust; race window on stop+start (HIGH above)

(Full findings at `tasks/a32dd41fedb8e924c.output`)

#### composite_signal.py (962 lines) — GOLD REFERENCE

**Totals:** 1 CRITICAL · 4 HIGH · 9 MEDIUM · 5 LOW

**CRITICAL**
- **No BUY/HOLD/SELL output rule.** Module emits a 7-state risk_on/off label (`STRONG_RISK_ON ... STRONG_RISK_OFF`). **CLAUDE.md §9 explicit:** "BUY / HOLD / SELL with confidence." A separate map exists in `ui/sidebar.py:399-405` for badge rendering, but the gold-reference signal aggregator does not emit the canonical decision. | Add `decision: BUY|HOLD|SELL` + `confidence: 0-100` keyed off score thresholds + regime.

**HIGH**
- `composite_signal.py:879-919` | Each layer try/except silently sets layer score to 0 on failure — swallows critical bugs (e.g. dict shape change). Need `data_quality` field surfaced to UI (e.g. "macro: cached/down")
- `composite_signal.py:937-942` | When a layer fails it contributes 0 with FULL weight → composite diluted incorrectly | Renormalize over surviving layers (redistribute failed weights)
- `composite_signal.py:847-962` | Module-level `_W_*` constants exposed publicly but regime weights override them at runtime → callers reading `_W_*` see different values than the actual composite | Document or remove module-level constants from public surface
- `composite_signal.py:840-844` | `is_risk_off` threshold -0.30 maps to MILD_RISK_OFF in label scale; docstring says "RISK_OFF or worse" — doc/code drift

**Layer 1-4 wiring verification:**
- ✓ TA via `ta_data` dict
- ✓ Macro via `macro_data` dict (FRED, DXY, yield curve)
- ✓ Sentiment via `fg`/put-call/funding
- ✓ On-chain via mvrv/hash/puell/sopr/realized/nvt
- ✓ Regime weight switching at lines 921-936

**Weight sum verdict (verified):**
- ✓ NORMAL regime: 0.20 + 0.20 + 0.25 + 0.35 = 1.00
- ✓ CRISIS, TRENDING, RANGING regimes — all sum to 1.00
- ✓ TA sub-weights: 0.32+0.18+0.10+0.13+0.09+0.08+0.10 = 1.00
- ✓ Macro sub-weights: 5×0.20 = 1.00
- ✓ Sentiment sub-weights: 0.45+0.10+0.30+0.15 = 1.00
- ✓ On-chain sub-weights: 0.35+0.25+0.20+0.08+0.07+0.05 = 1.00
- ✗ Bayesian merge at 283-287 doesn't normalize after blending

**Confidence calc:** NOT EMITTED. Add `confidence = abs(score) * 100` or similar.

**No regression baseline** in `docs/signal-regression/` — required by project §4.

#### cycle_indicators.py (407 lines)

**Totals:** 0 CRITICAL · 3 HIGH · 9 MEDIUM · 4 LOW

**HIGH**
- `cycle_indicators.py:312` | **`cycle_score_100` SIGN-INVERTED.** `cycle = int(round(50 - blend * 49))` — blend=+1 ("euphoria/top" per docstring) maps to `50-49=1` (Strong Buy). Should map to 100 (top/euphoria). | Fix: `cycle = int(round(50 + blend * 49))`
- `cycle_indicators.py:155-160` | Stablecoin delta thresholds asymmetric: `-0.5 → STABLE`, `+0.5 → ACCUMULATING` (band split asymmetric across zero) | Symmetric thresholds
- `cycle_indicators.py:137-145` | `_fetch` no exponential backoff; CoinGecko free tier ~10-30 req/min → three sequential calls hit rate-limit fast on cold cache; 429 not specifically handled

**Notable bug:** Beneath HIGH-1 is a substantial UX/signal-quality bug — anyone reading the cycle gauge sees inverted recommendations. Fix is one line.

### 2.3 Tier C — Surface files

*pending*

### 2.3 Tier C — Surface files

**Totals across 12 surface files + 4 CI workflows + 3 deploy configs:** 5 CRITICAL · 11 HIGH · MEDIUM/LOW per file in agent transcript

**CRITICAL — Deploy / API security**
- `Dockerfile:34` | `--server.enableXsrfProtection=false` overrides `.streamlit/config.toml` secure default (XSRF=true) → production loses XSRF protection | Set `true` or omit flag (inherit config)
- `Dockerfile` no `USER` directive + `docker-compose.yml` no `user:` → all 3 services run as **container root**. Combined with `crypto_data` volume at `/app`, code-exec → root takeover
- `docker-compose.yml:18, 34, 47` | `env_file: .env` mounts host `.env` into all 3 containers → real OKX secret/passphrase, ANTHROPIC key etc. baked into runtime, readable via `docker exec`. **No `.dockerignore` visible** → `.env` may also get COPY'd into the image
- `Dockerfile:18` | `COPY *.py ./` includes any stray `.env`, `alerts_config.json`, etc. at repo root | Add `.dockerignore` listing all sensitive paths
- `api.py:117 + 618` | When `api_key` config is empty, `require_api_key()` short-circuits to no-op → anyone reaching port 8000 can `POST /execute/order` (live trade) and `POST /scan/trigger` and `tradingview_webhook` **without auth**. CLAUDE.md says FastAPI is "scaffold per §22 — not yet wired" but `docker-compose.yml` exposes it on :8000 → contradiction. | Refuse-to-start when `api_key` unset and live_trading_enabled is true

**HIGH**
- `api.py:55` | `ws_feeds.start(model.PAIRS)` runs at module **import** → tests/CLI tools that import `api` silently spawn background WS threads | Move to FastAPI lifespan startup hook
- `alerts.py:67-86, 126` | `email_pass`, `okx_secret`, `okx_passphrase`, `okx_api_key` persisted in `alerts_config.json` plaintext. `chmod 0o600` no-op on Windows (per code comment) | Encrypt-at-rest or move to keyring
- `chart_component.py:16` | `_CDN = "https://unpkg.com/lightweight-charts@4.1.3/..."` runtime CDN dependency → app breaks for offline users; not pinned by integrity hash either | Bundle locally with SRI
- `chart_component.py` | TradingView Lightweight Charts uses hardcoded dark-only colors (`#0d0e14`, `#00d4aa`, etc.) instead of `ui/design_system.py` tokens → light mode unreadable
- `glossary.py:38` | IL formula at intermediate level: `IL = 2√P − 1 − P` is **mathematically wrong**. Standard form: `IL = 2*sqrt(p)/(1+p) − 1` | Fix user-facing math
- `glossary.py:201` | `st.popover` requires Streamlit ≥1.31; older versions raise AttributeError | Add try/except or version guard
- `config.py:182` | BRAND_NAME default `"Family Office · Signal Intelligence"` conflicts with project CLAUDE.md §6 placeholder `"Crypto Signal App"` | Reconcile with §6
- `config.py:107` | TIER2_DEFAULT_WEIGHTS uses `1.0/20` but TIER2_PAIRS now has 21 entries (CC added at L80) → **weights sum to 1.05** | Recompute as `1.0/len(TIER2_PAIRS)`
- `utils_family_office_report.py:79` | `_current_app_key()` substring matches "supergrok|crypto-signal|crypto_signal|grok" — **"grok" matches unrelated repos** → mis-identification leads to wrong app's data being aggregated
- `utils_wallet_state.py:144` | `_res_id` uses `hash(note) & 0xFFFFFF` for collision-resistance entropy — non-cryptographic, deterministic per process → same-second same-note reservations collide | Use `uuid.uuid4()`

**CI workflows audit**
- `secret-scan.yml`, `security.yml` — gitleaks active ✓ but **all actions floating major tags** (`@v4`, `@v5`, `@v2`) — supply-chain risk per security best practice | Pin to commit SHAs + add Dependabot for actions
- `feedback_evaluator.yml:36-37, 43, 59` | `pip install ... || true` swallows failures, `continue-on-error: true`, then `git push` to main with `permissions: contents: write` → **poisoned checkpoint can auto-commit** without halting CI
- `deps-audit.yml:20`, `security.yml:29` | pip-audit results ` || true` → vulnerabilities never gate merges, only published as artifacts | Fail on CRITICAL CVEs
- `secret-scan.yml` and `security.yml` partially redundant (both run gitleaks, both run pip-audit) | Consolidate into one

**Per-file 1-line summaries**
- **api.py** — Functional FastAPI app with HMAC auth, but auth no-op when api_key unset; auto-starts WS feeds at import; "not wired" claim contradicted by docker-compose
- **alerts.py** — Email-only, 4h dedup, atomic config save; plaintext credentials in JSON (chmod no-op on Windows); dedup not persistent across restarts
- **chart_component.py** — TradingView Lightweight Charts via CDN; dark-only colors; not Plotly so plotly_template doesn't apply but theme integration missing
- **glossary.py** — 30 terms × 3 depths ✓ (matches §7); IL math typo at intermediate level; popover requires Streamlit ≥1.31
- **pdf_export.py** — reportlab PDFs; hardcoded version string; fixed 4-decimal price rounds sub-cent tokens to "$0.0000"; no Inter/JetBrains Mono fonts (§8)
- **config.py** — Clean feature-flag pattern; BRAND_NAME conflict (§6); TIER2 weights sum to 1.05 after CC added
- **evaluate_headless.py** — Headless feedback evaluator; sequential ticker fetches with no per-call timeout → can hang
- **utils_audit_schema.py** — Solid event schema; unknown event_types only debug-logged
- **utils_cross_app_safety.py** — Multi-sig + position-overlap ledger; `parent.parent / "data"` path assumes utils/ subfolder layout the SuperGrok repo doesn't have
- **utils_family_office_report.py** — Cross-app aggregator; "grok" substring overly permissive; uses fpdf2 ✓
- **utils_format.py** — Em-dash + k/M/B formatters; fraction-vs-percent heuristic (`abs<=1.5`) ambiguous near boundary
- **utils_wallet_state.py** — Reservation ledger; `_res_id` collision-prone; same parent.parent path issue
- **`.streamlit/config.toml`** — Dark theme matches §8; XSRF=true correct; no `maxUploadSize` set (default 200MB); no light-theme overrides

(Full findings at `tasks/afe13138625eb5f66.output`)

### 2.4 UI package (new in redesign)

#### ui/__init__.py (75 lines)
**Verdict:** Clean barrel exports of design_system / sidebar / overrides / plotly_template. No issues found.

#### ui/design_system.py (313 lines)
**Verdict:** Well-documented, mockup-aligned. ✓ shape+color in `signal_badge()` (▲▼■). ✓ `data_source_badge()` defined. ✓ accent token per app via `ACCENTS` dict. **Concern:** uses CSS `color-mix()` (Chrome 111+/Safari 16.2+) — older browsers fall back to transparent. **Concern:** `tokens.card_radius="12px"` — CLAUDE.md §8 says 10px. Reconcile.

#### ui/plotly_template.py (197 lines, plotly branch only)
**Verdict:** Clean. Lazy-import of plotly with graceful fallback ✓. Theme dark/light ✓. `_TOKENS` dict duplicates design_system tokens — minor DRY concern but justified per docstring (self-contained surface for charts).

#### ui/sidebar.py (1,186 lines)
**Totals:** 1 CRITICAL · 4 HIGH · 15 MEDIUM · 8 LOW

**CRITICAL**
- `ui/sidebar.py:743` | `inject_streamlit_overrides` and many helpers (`page_header`, `macro_strip`, `regime_card_html`, etc.) interpolate `title`/`subtitle`/`ticker`/`note`/`params`/`regime_label`/`state` raw via `unsafe_allow_html` — XSS if any field is API/DB-derived | `html.escape()` every interpolated string OR document strict trusted-callers boundary

**HIGH**
- `ui/sidebar.py:497, 1043-1052` | Hardcoded hex `#22c55e`/`#ef4444` for spark stroke + regime segments — won't theme | Use `var(--success)` / `var(--danger)` (modern browsers support CSS vars in SVG)
- `ui/sidebar.py:417, 421` | `int(regime_confidence)` — float NaN crashes int(); also accepts 0-1 floats which display as "0% conf" | Add `math.isfinite` guard + range normalization
- `ui/sidebar.py:740-746` | Bar fill threshold logic confused: `if v < 60 cls += " mid"` then `if v < 40 cls = "low"` — works but rewrite as if/elif
- `ui/sidebar.py:905-908` | Color-encoding heuristic on substring matching of arbitrary text ("vs btc +", "tightening", "tailwind") — silently breaks if subtitle copy changes | Pass explicit `tone` parameter

#### ui/overrides.py (743 lines)
**Totals:** 1 CRITICAL · 5 HIGH · 10 MEDIUM · 5 LOW

**CRITICAL**
- `ui/overrides.py:701-708` | Legacy h1 suppression via `display:none !important` matching `font-size:26px` and `clamp(24px, 2.2vw, 32px)` — brittle attribute-selector chain breaks silently if legacy header style changes by 1px | Document as transitional + add sunset date

**HIGH — sub-floor fonts and tap targets**
- `ui/overrides.py:122, 171-174, 317-325` | Topbar/level-group/sidebar-popover button font-size **12.5px** — under §8 13px body floor
- `ui/overrides.py:739` | `.ds-status-pill { font-size: 10px }` mobile — under §8 11px label floor
- `ui/overrides.py:65-78, 172, 179-186, 447-454` | Sidebar nav buttons `min-height: 30px`, level-group buttons ~24-28px, chip buttons ~28px, coin-pick ~28px → ALL violate §8 44×44 tap target minimum
- `ui/overrides.py:304-310, 397-399` | `:has()` and `color-mix()` modern CSS features — Chrome 105+/Safari 15.4+/Firefox 121+. Older browsers no-op silently → invisible badges/missing styles

#### ui/__init__.py exports verification
✓ All symbols imported by `app.py` exist in their source modules.

---

## 3. Math & signal correctness — VERDICT

**Overall:** numerous correctness defects, fully detailed in §2.1 entries for `crypto_model_core.py`, `composite_signal.py`, `cycle_indicators.py`, `top_bottom_detector.py`, `risk_metrics.py`, `options_model.py`.

**Top 8 math defects (priority-ranked):**

1. `crypto_model_core.py:1421-1425, 1528-1543` — TWO inconsistent ATR + ADX implementations (SMA vs EWM) — same indicator returns different values per caller
2. `crypto_model_core.py:1865-1871` — Gaussian Channel `np.convolve` is anti-causal (under-weights recent bars) — needs `weights[::-1]`
3. `crypto_model_core.py:2702` — Sigmoid calibration applied AFTER threshold check breaks HOLD band (raw 45-54 → mapped 41.7-58.3 → pushed out of HOLD)
4. `crypto_model_core.py:2487` — `strategy_bias = "Balanced"` reassignment makes Neutral regimes silently fall to trend-follow scoring
5. `cycle_indicators.py:312` — `cycle_score_100` SIGN-INVERTED (euphoria/top renders as Strong Buy)
6. `composite_signal.py` (whole module) — emits 7-state risk_on/off, NOT BUY/HOLD/SELL — §9 violation
7. `risk_metrics.py:282-283` — Sharpe annualization conflates trade frequency with hold duration → massively overstates Sharpe
8. `top_bottom_detector.py:1654, 1677, 947-948` — `/1.0` no-op divisor inflates confidence ~5×; Wyckoff Upthrust dead via min/max swap

**Indicator parameter compliance:** ✓ canonical for Bollinger, MACD, RSI, Stochastic, SuperTrend, Chandelier. Δ Ichimoku 10/30/45 (deliberate crypto-tuned). ✗ ATR/ADX double-implementation.

**Composite `calculate_signal_confidence` — gold reference per §4:**
- ✓ Layer 1-4 inputs all wired
- ✓ Regime weight switching at 921-936
- ✓ All regime weight dicts sum to 1.00
- ✗ No regression baseline in `docs/signal-regression/` (project §4 mandate)
- ✗ No fixture for any of the 22 indicators (project §22 mandate)

---

## 4. Data pipeline & API discipline — VERDICT

**Fallback chains** (per §10):

| Stream | Spec | Status |
|---|---|---|
| Crypto OHLCV | CCXT → OKX → Kraken → CoinGecko | ⚠ Partial — OKX/Gate.io/Bybit/MEXC tier-2 wired; **Kraken not on OHLCV path** |
| Funding | OKX → Bybit | ✓ |
| F&G | alternative.me | ✓ |
| Google Trends | pytrends | ✗ NOT IMPLEMENTED (despite being in requirements.txt) |
| On-chain BTC/ETH | Glassnode → Dune → RPC | ⚠ Partial — Glassnode primary; **Dune absent** |
| Token unlocks | cryptorank /token-unlock (PRIMARY) | ✗ NOT IMPLEMENTED — Tokenomist used instead |
| VC fundraising | cryptorank /funds (PRIMARY) | ✗ NOT IMPLEMENTED |

**§12 cache TTL compliance** (Crypto Signal App spec):

| Data | Spec | Observed | Status |
|---|---|---|---|
| OHLCV intraday | 5min | 5min | ✓ |
| F&G | **24h** | 15min / 1h | ✗ |
| Funding | 10min | 5min | ⚠ over-cached |
| On-chain | **1h** | 5min | ✗ |
| Macro/rates | **2h** | 1h | ✗ |
| Glassnode (on-chain) | 1h | 1h | ✓ |
| CoinMetrics | 1h | 1h | ✓ |

**Secret hygiene:**
- ✓ No hardcoded API keys in code (manual regex scan + `.gitleaks.toml` allowlist clean)
- ✗ Etherscan key in URL string (data_feeds.py:7272) — leaks via retry/proxy logs
- ✗ alerts_config.json stores OKX secret/passphrase in plaintext (alerts.py:67-86)
- ✗ Local `gitleaks`/`pre-commit` not installed → CI scanner is sole gate

**Datacenter-IP hazards:**
- ✗ `get_kimchi_premium()` uses `api.binance.us` (CRITICAL data_feeds.py:3744)
- ⚠ `fetch_binance_liquidations` 6s timeout per pair on every refresh (geo-blocked)
- ⚠ Bybit funding "datacenter-IP quirks" — no explicit Streamlit Cloud guard

---

## 5. UI / UX feature walkthrough — VERDICT (static analysis)

**Live browser walkthrough deferred** to a separate session. Static findings from app.py + ui_components.py + ui/* agents:

**Pages observed via app.py registry:** Dashboard, Signals, Regimes, On-chain, Config Editor, Backtest Viewer, Arbitrage, Agent (8 pages).

**Theme handling:**
- ✓ Design system injected first (app.py:593-607)
- ✗ Legacy SIGNAL_CSS at 613-623 overrides tokens with hard-coded dark hex → **light-mode users see dark cards on light background**
- ✗ Many HTML f-strings in app.py + ui_components.py hard-code hex `#ef4444`/`#22c55e`/`#00d4aa`/`#f8fafc`/`#1f2937` — won't theme correctly
- ✗ ui_components.py has **213 hardcoded color literals + zero `ui/design_system` imports** — pending_work.md task #5 not started

**User-level scaling:** ✓ session_state read consistently; ✗ "buy opportunity"/"sell signal" advisor language without disclaimer in beginner output (ui_components.py:1462-1492)

**§8 accessibility:**
- ✗ 5 color-only signal badges (no shape) in ui_components.py: `signal_pill`, `conf_badge_html`, `risk_level_badge_html`, `signal_accuracy_badge_html`, Hurst regime chip
- ✗ ~73 sub-12px font literals violating §8 11px label / 13px body floor
- ✗ Tap targets <44×44 desktop on multiple components (sidebar nav 30px, level-group ~28px, chip ~28px, coin-pick ~28px)
- ✗ NEUTRAL pill contrast (fg `#64748b` on bg `#1e293b`) ≈3.2:1 — fails WCAG AA
- ✗ Card border-radius 12px conflicts with §8 mandated 10px
- ✓ Mobile breakpoint 768px matches §8

**Plotly theme propagation:** PARTIAL. Template registered (app.py:605, re-applied at 888) but per-chart `update_layout` overrides at 2989-2993, 4258-4276, 6160-6168, 7775-7777 etc. bypass it.

**`data_source_badge()`:**
- ✓ Defined in `ui/design_system.py:259`
- ✗ Not in ui_components.py; ui_components.py has zero `ui/design_system` imports
- ⚠ Partial adoption via `page_header(data_sources=[...])`; many cards in page_dashboard still lack it

**XSS surface (HTML interpolation without escape):**
- 7 high-risk surfaces in ui_components.py (sidebar_header, section_header, render_card, render_quick_access_row reading alert_history.jsonl, 4 panel renderers — see §2.1 ui_components CRITICAL)
- Multiple unsafe interpolations in ui/sidebar.py (`page_header`, `macro_strip`, `regime_card_html`, etc.)

---

## 6. AI agents, feedback loops, scheduler — VERDICT

- ✗ **agent.py:1310** — `supervisor` instance created at import but `start()` is never called by the module → 24/7 §11 operation contingent on caller; no module-level guarantee
- ✗ **agent.py:1054** — `SqliteSaver.from_conn_string` used outside its required context manager → checkpoint persistence may silently break
- ⚠ **scheduler.py:120-122** — No final scan-status write on crash → DB stuck `running=1`
- ⚠ **circuit_breakers.py:50** — State file path outside worktree → halt state lost on every Streamlit Cloud rerun
- ⚠ **circuit_breakers.py GATES order** — HUMAN_OVERRIDE last; should be first so manual halt always wins
- ⚠ **ai_feedback.py** — Alert calibration silently overwrites manual min_confidence overrides
- ⚠ Anthropic client recreated per Claude call (agent.py:875-880) — no reuse like news_sentiment
- CI feedback evaluator running every ~6h ✓ (commits visible in `git log`)

---

## 7. Web3 / wallet integration — VERDICT

- ✓ Level A (read-only) wallet state in `utils_wallet_state.py` operational; no accidental tx broadcast paths in execution.py
- ✗ Level B/C scaffolding — execution.py is **NOT scaffold-only**; it's fully wired with `place_order`, `close_position`, TWAP, Iceberg paths. Live trade gated only by `live_trading_enabled` config flag
- ✗ FastAPI `/execute/order` exposed on `:8000` in docker-compose with no auth when api_key empty — see §2.3 CRITICAL
- ⚠ `utils_wallet_state.py:144` — `_res_id` collision-prone (non-cryptographic `hash()`)
- ⚠ `utils_wallet_state.py` + `utils_cross_app_safety.py` + `utils_family_office_report.py` all use `Path(__file__).parent.parent / "data"` — assumes `utils/` subfolder layout this repo doesn't have

---

## 8. Tests, deploy, cold-start — VERDICT

- ✓ **pytest 42/42 pass in 5.20s** on `redesign/ui-2026-05-plotly` (well under 30s §24 target)
- ✗ **`tests/verify_deployment.py` does not exist** — referenced in MEMORY.md (used 2026-04-23, 5/5 passed) and pending_work.md task #9. Either deleted post-2026-04-23 or never committed. **§25 deployment verification protocol depends on this file.**
- ✗ **Zero test coverage** for the gold-reference modules: `composite_signal.py`, `cycle_indicators.py`, `top_bottom_detector.py`, `risk_metrics.py`, `options_model.py` — required per project §22
- ⚠ Test glob in `tests/test_smoke.py:40-43` only checks top-level .py — misses `ui/`, `agents/`, etc.
- ⚠ No autouse fixture blocking accidental network in tests (cycle_indicators imports could trigger fetch on import)
- ⚠ No regression-baseline fixture for `composite_signal.compute_composite_signal` (project §4 explicit)
- ⚠ Cold-start on Streamlit Cloud at risk: `database.init_db() + migrate_csv_to_db()` run at import time → schema check + CSV migration scan per worker
- ✓ LightGBM/XGBoost lazy-loaded ✓ (verified by `_ml_mod` import gate at app.py:144 + ml_predictor.py imports inside `_train_model`)

**Local dev environment:**
- ✗ `gitleaks`, `pre-commit` not installed on PATH → CI scanners are sole gate
- ⚠ Python 3.14.3 in use locally; `runtime.txt` should be checked for prod parity

---

## 9. Aggregate fix log — PRIORITIZED

> **Per CLAUDE.md §1 — fixes will NOT be applied without an explicit "approve and go" from David on this fix list.**
> The audit established the baseline. The fix list below is the proposal for the next sprint. Each item is independently committable per §3.

### P0 — CRITICAL fixes (block any merge to main)

**Math correctness (8 fixes):**
1. `crypto_model_core.py:1421-1425` — Standardize ATR to Wilder EWM (`tr.ewm(alpha=1/period).mean()`)
2. `crypto_model_core.py:1528-1543` — Standardize ADX to Wilder EWM (RMA across DM/DI/ATR)
3. `crypto_model_core.py:1865-1871` — Fix Gaussian Channel kernel direction (`weights[::-1]`)
4. `crypto_model_core.py:2487` — Remove `strategy_bias = "Balanced"` reassignment
5. `crypto_model_core.py:2702` — Move sigmoid before threshold OR recalibrate HOLD band
6. `cycle_indicators.py:312` — Fix sign inversion (`50 + blend * 49`)
7. `composite_signal.py` — Add BUY/HOLD/SELL output rule + confidence per §9
8. `risk_metrics.py:282-283` — Fix Sharpe annualization (use actual hold duration, not trade gap)

**Security / deploy (5 fixes):**
9. `Dockerfile:34` — Remove `--server.enableXsrfProtection=false`
10. `Dockerfile` — Add `USER appuser` non-root directive
11. `Dockerfile` + `docker-compose.yml` — Add `.dockerignore` excluding `.env`, `data/`, `alerts_config.json`, `*.csv`, `*.xlsx`
12. `api.py:117, 618` — Refuse to start if `api_key` unset and live_trading_enabled true
13. `data_feeds.py:7272` — Move Etherscan key from URL to `params={"apikey": ...}`

**App correctness (4 fixes):**
14. `app.py:9422` — Fix `_cached_whale_activity()` arity + return-type handling
15. `app.py:3402-3414` — Rebuild Trade Action Card with conditional inner-value strings
16. `app.py:6939-6942` — Replace `sleep+rerun` loop with `@st.fragment(run_every=5)`
17. `app.py:613-623` — Remove legacy SIGNAL_CSS that overrides design tokens

**Operations (3 fixes):**
18. `agent.py:1054` — Wrap `SqliteSaver.from_conn_string` in `with` per LangGraph 0.2+ API
19. `agent.py:1310` — Module-level supervisor `.start()` with safe guard
20. `circuit_breakers.py:50` — Move `_STATE_FILE` inside the worktree (`Path(__file__).parent / "data"`)

**Tests (1 fix):**
21. Restore/recreate `tests/verify_deployment.py` (5-check script per MEMORY.md 2026-04-23 history)

### P1 — HIGH fixes (block redesign sprint sign-off)

**§12 cache TTL fixes (4):**
22. `data_feeds.py` — Raise `_FNG_TTL`/`_FNG2_TTL` to 86400 (24h)
23. `data_feeds.py:_ONCHAIN_TTL` → 3600 (1h)
24. `data_feeds.py:_MACRO_TTL` → 7200 (2h)
25. `app.py` — Wrap F&G/funding/OHLCV fetches at lines 8984/8988/8786-8800/6143-6156/8230-8253/4318 with `@st.cache_data` matching §12 windows

**§10 spec gaps (3 — major surface additions):**
26. Add cryptorank.io `/token-unlock` PRIMARY for token unlocks (data_feeds.py)
27. Add cryptorank.io `/funds` PRIMARY for VC fundraising (data_feeds.py)
28. Add Dune Analytics SECONDARY for on-chain BTC/ETH (data_feeds.py)
29. Add pytrends Google Trends PRIMARY for Layer 3 sentiment (data_feeds.py — already in requirements.txt)

**Design system migration (4):**
30. `ui_components.py` — Migrate 213 hardcoded hex colors to `var(--*)` tokens; add `from ui.design_system import ACCENTS, SEMANTIC`
31. `ui_components.py:1093-1110, 1115-1128, 1723-1741, 2096-2130, 2158-2165` — Add shape encoding (▲▼■) to all 5 color-only badges
32. `ui_components.py` + `ui/overrides.py` — Raise all sub-11px font literals (~73 of them) to use `clamp(11px, 0.75vw, 13px)` or higher; remove `--fs-xxs` token
33. `ui/overrides.py` — Apply `min-height:44px` globally on interactive elements (not just `@media (max-width:768px)`)

**XSS hardening (3):**
34. `ui_components.py:1010, 1067, 1392, 3829-3835, 3964-3978, 4044-4055, 4340-4351` — Add `html.escape()` on all user/data-derived strings before HTML interpolation
35. `ui_components.py:889` — Replace `st.markdown` with `st.text` for `alert_history.jsonl` content
36. `ui/sidebar.py:209-210, 327-336, 425-435` — Same escape treatment in `page_header`/`macro_strip`/`regime_card_html`

**Math correctness P1 (5):**
37. `composite_signal.py:937-942` — Renormalize composite over surviving layers when one fails
38. `top_bottom_detector.py:1654, 1677` — Fix confidence aggregation (`/struct_w_sum` not `/1.0`)
39. `top_bottom_detector.py:947-948` — Fix `recent_high = .max()` (Wyckoff Upthrust)
40. `top_bottom_detector.py:316-319, 320-323` — Fix CVD half-window symmetry
41. `crypto_model_core.py:1716` — Chandelier compare to BOTH long AND short stops

**Data hygiene P1 (3):**
42. `whale_tracker.py:117` — Replace single EF address with proper top-N ETH whale wallet list
43. `data_feeds.py:1402-1411` — Rename or consolidate `_fetch_binance_fr` (actually calls Bybit)
44. `data_feeds.py:_get_runtime_key` — Add full key mapping (Glassnode, CryptoQuant, Coinglass, CMC, Tokenomist, Coinalyze)

**Operations P1 (4):**
45. `database.py` — Lazy-init pattern; remove module-level init_db/migrate_csv_to_db calls
46. `database.py:1778, 1793, 1823-1836` — Convert f-string SQL to `?` placeholders
47. `alerts.py:67-86` — Move OKX secret/passphrase out of plaintext JSON (keyring or env-only)
48. `execution.py:340-354` — Reject orders below minimum quantity instead of rounding up

**CI hardening (4):**
49. Pin all GitHub Actions to commit SHAs (currently floating `@v4`/`@v5`)
50. Remove ` || true` from `deps-audit.yml:20` and `security.yml:29` so CRITICAL CVEs gate merges
51. `feedback_evaluator.yml:43, 59` — Remove `continue-on-error: true` OR gate `git push` on `outcome == 'success'`
52. Consolidate `secret-scan.yml` and `security.yml` (currently both run gitleaks + pip-audit)

### P2 — MEDIUM fixes (next sprint after merge to main)

53–110. The 180+ MEDIUM findings in §2 — track in a separate `pending_work.md` sprint after the redesign merges. Includes: most cache-bound, dead-code removal, magic-number constants, docstring drift, and similar quality items.

### P3 — LOW fixes (background)

111–220+. The 110+ LOW findings — mostly style, minor inefficiency, comment hygiene. Address opportunistically.

### Branch reconciliation tasks (Phase 9 prerequisites)

R1. Sync local `redesign/ui-2026-05` (in keen-faraday-10b9bb worktree) to origin (29 commits behind)
R2. Push 5 unpushed commits on `redesign/ui-2026-05-sidebar-and-polish`
R3. Decide canonical branch (recommend `redesign/ui-2026-05-plotly`); merge `-p0-fixes`, `-pages-and-css`, `-sidebar-and-polish` into it (or rebase onto plotly tip)
R4. After P0+P1 fixes complete: open PR `redesign/ui-2026-05-plotly` → `main` for explicit user approval per pending_work.md task #10
R5. Once redesign merged: re-evaluate the 5 dependabot PRs against new HEAD

---

## 10. Sign-off

### Audit completion summary (2026-04-28)

**Coverage:** 100% of root .py files (35 modules), all `ui/` package files (5 modules), all CI workflows (4), all deploy configs (Dockerfile + docker-compose + `.streamlit/config.toml`), all 5 redesign branches + main, full GitHub remote (16 branches surveyed). Audit doc: ~1,400 lines / ~50KB.

**Static analysis:** ✓ COMPLETE
**Live browser walkthrough (every page × 3 levels × 2 themes × mobile):** DEFERRED — requires Streamlit dev server + browser automation, separate session.

**Findings totals (deduplicated):**
- **CRITICAL: ~44** (math correctness 12, security/deploy 8, app correctness 6, data 6, ops 7, tests 5)
- **HIGH: ~124**
- **MEDIUM: ~180**
- **LOW: ~110**

**Test status:** 42/42 pytest pass in 5.20s ✓
**Verify deployment:** SCRIPT MISSING (FINDING-007)
**Secret scan:** No hardcoded keys in code ✓; gitleaks/pre-commit not on local PATH (FINDING-008)
**Cold start risk:** `database` module-level init at import — can exceed §11 60s on Streamlit Cloud worker spawn

**Restore points (6 tags pushed to origin 2026-04-28):** see §0.

**Verdict for the question "can we merge `redesign/ui-2026-05` → `main`?":**
**NO — not until P0 + P1 fixes ship.** The static design-system port is well-executed but P0 issues (composite signal not emitting BUY/HOLD/SELL, math double-impls, anti-causal Gaussian, sign-inverted cycle gauge, XSRF disabled in container, no-auth FastAPI on :8000, plaintext OKX secrets, Sharpe overstatement, agent supervisor never started) are blockers.

**Recommendation for next sprint:**
1. Approve P0 list (items 1-21) — execute in single sprint per §1, §3 atomic commits
2. Approve P1 list (items 22-52) — fold in immediately after P0
3. After P0+P1 complete, re-run this audit script (this doc) and confirm zero P0 + zero P1 remains
4. Then approve PR `redesign/ui-2026-05-plotly` → `main`
5. Defer P2/P3 to follow-up sprints

**Awaiting:** explicit "approve and go" on the P0 + P1 fix lists from David before applying any code changes.

---

*Audit complete: 2026-04-28. All 10 phases finished. Restore tags published. Fix list awaiting approval.*
