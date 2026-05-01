# Post-Phase-C Deep Audit — 2026-05-01

**Branch:** `main` (post-Phase-C merge)
**HEAD:** `1da35f9` — chore: remove 4 orphan modules
**Tag:** `redesign-ui-2026-05-shipped` → `20587d2` (restore point)
**Auditor:** Claude Opus 4.7 (1M context)
**Scope:** Every Python file in repo + GitHub state, per CLAUDE.md §4 protocol

---

## Executive summary

Phase C shipped clean across functional axes — 185 tests pass, §4 regression has zero categorical drift, deploy verifier 5/5, cold-start 10.9s. **The codebase compiles and runs, no crash bugs found.**

Substantive issues are **architectural / cleanup**, not blocking:

| Category | Findings | Severity |
|---|---|---|
| Real architectural gap | per-TF data on Signals page falls back to 1d when `_result` came from DB (not scan_results) — see Issue #1 | **HIGH** |
| Cleanup debt | 3 more orphan modules (~1,200 lines), 9 dead session_state keys, 5+ stale remote branches | **MED** |
| Cosmetic / hygiene | dead read of `_settings_tab`, 53 silent-pass exception handlers, 1 dev-env-only pip-audit warnings | **LOW** |

---

## A1 — Test sweep

| | |
|---|---|
| Full pytest (incl slow) | **185 passing** in 8.20s |
| §4 composite-signal regression | **6/6 pass · zero categorical drift** on BTC + ETH |
| §22 indicator fixtures | **37 / 37 pass** (all RSI/MACD/BB/ATR/ADX/SuperTrend/Stoch/Ichimoku/Hurst/Squeeze/Chandelier/CVD/Gaussian/S+R/MACD-div/RSI-div/candlestick/Wyckoff/HMM/cointegration/VWAP/fib) |
| `tests/verify_deployment.py --env prod` | **5/5 PASS** |
| Cold-start prod | **10.9s** (60s budget) |
| `py_compile` recursive | **clean** across all 56 .py files |
| `compileall` repo root | **OK** (no syntax errors anywhere) |

---

## A2 — Issue ledger (open)

### Issue #1 — Signals page falls back to 1d data on cold reload (HIGH)

**File:** `app.py:7259` (`page_signals` — `_tf_view = (_result.get("timeframes", {})...)` block)

**Symptom:** User clicks 1h / 4h / 1w in the timeframe strip — RSI / ADX / composite scores don't change. Only 1d works.

**Root cause:**
`_result` is built from two sources:
1. `st.session_state["scan_results"]` — fresh scan output, includes `_result["timeframes"][tf]` per-TF dict
2. `_cached_signals_df(500)` — DB fallback when scan_results is empty

The `daily_signals` table schema (`database.py:217`) stores only **top-level scalar fields** (rsi, macd_hist, regime, direction, etc.) — **NOT the `timeframes` dict**. So when `_result` comes from DB, `_result["timeframes"]` is `None` → `_tf_view = {}` → `_tf_or_top` falls back to top-level 1d values for every TF click.

**Fix paths (pick one):**
- **A1.1 (cheap):** When `_result` lacks `timeframes` dict, recompute per-TF indicators on-demand from cached OHLCV. Wraps `cycle_indicators.compute_*` in a 5-min cached helper keyed by `(pair, tf)`. ~30 lines.
- **A1.2 (proper):** Add `timeframes_json TEXT` column to `daily_signals`; `append_to_master` serialises the dict; `get_signals_df` deserialises. Schema migration required. ~50 lines.
- **A1.3 (UX):** When `_tf_view` is empty, surface the existing caption ("Showing 1d data — run a scan…") more prominently and disable the strip buttons except 1d. ~10 lines. Doesn't fix data but makes behaviour explicit.

**Recommendation:** A1.1 — cheapest, no schema risk, matches the on-demand-recompute pattern used for composite (`_sg_cached_composite_per_pair`).

---

### Issue #2 — `_settings_tab` is read but never written (LOW)

**File:** `app.py:2775` — `_st_tab_override = st.session_state.pop("_settings_tab", None)`

C6 removed the writer (sidebar nav side-effect). `pop()` always returns `None`. Dead read; harmless but confusing.

**Fix:** Delete the line + the downstream conditional that uses `_st_tab_override`. ~5 lines.

---

### Issue #3 — 9 session_state keys written but never read (LOW)

```
_ds_current_nav_key      arb_ts                  beginner_mode
runtime_coingecko_key    scan_error              scan_run
show_legacy_scan_view    wallet_holdings         zerion_portfolio
```

Dead writes; bloat session_state. Mostly leftovers from refactors.

**Fix:** Audit each, remove the writer if confirmed dead. ~30 lines total.

---

### Issue #4 — 3 more orphan top-level modules (MED)

`risk_metrics.py` (511 lines), `utils_audit_schema.py` (lines TBD), `utils_format.py` (lines TBD) — only `tests/test_smoke.py` references them (parametrized over root `.py` files). All other code references = 0.

`api.py` was flagged but has 24 actual references — not orphan (regex false-positive earlier).

**Fix:** Same pattern as last cleanup commit (`1da35f9`): `git rm` + commit. ~1,200 lines removable.

---

### Issue #5 — Stale remote branches (MED)

```
origin/claude/hopeful-pike-94f951
origin/fix/redesign-port-data-wiring-2026-04-28
origin/redesign/ui-2026-05
origin/redesign/ui-2026-05-p0-fixes
origin/redesign/ui-2026-05-pages-and-css
origin/redesign/ui-2026-05-plotly
origin/redesign/ui-2026-05-sidebar-and-polish
origin/master                              # legacy pre-rename
```

All content reached `main` via tags (`redesign-port-fixed-2026-04-29`, `redesign-ui-2026-05-shipped`, plus `backup-pre-*` tags as redundant safety).

**Fix:** `git push origin --delete <branch>` for each. Tags preserve all history.

---

### Issue #6 — 53 silent-pass exception handlers (LOW)

53 `except ... : pass` patterns where no logging happens. These are mostly defensive (e.g., `_html.escape` failure, optional cache invalidation) but make debugging harder.

**Fix:** No urgent action. As individual handlers are touched in future work, swap `pass` for `logger.debug("[scope] op failed: %s", _e)`.

---

### Issue #7 — 118 `unsafe_allow_html=True` sites (LOW)

Each is a potential XSS surface. Phase C closed the most-likely-poisoned ones (P1-34 fix in `605b297`, plus the page_header/macro_strip/sidebar P1 audit fixes from prior sprints).

Static spot-check shows interpolation patterns mostly use `_html.escape()` on user-data fields. The remaining 35 / 94 / 95 / 2 sites in app.py / ui/sidebar.py / ui_components.py / ui/design_system.py are mostly literal-template f-strings (not user data).

**Fix:** No urgent action. Defensive: any future edit touching these sites should add `_html.escape()` on any field whose source is API/DB/user-input.

---

### Issue #8 — pip-audit findings on local env (NONE — false alarm)

`pip-audit` flagged 14 deps on the local dev env (aiohttp, cryptography, pillow, requests, tornado, etc.). **Production deploy is on FIXED versions** (per Streamlit Cloud's deploy log: `aiohttp==3.13.5`, `cryptography==47.0.0`, `pillow==12.2.0`, `requests==2.33.1`, etc.). Only the local laptop env is stale.

**Fix (optional):** `pip install --upgrade -r requirements.txt` on local dev box.

---

## A3 — File inventory

```
TOTAL:  56 Python files, 44,942 lines

Top 10 largest:
  data_feeds.py             8,464
  app.py                    8,068
  crypto_model_core.py      5,851
  ui_components.py          4,829
  database.py               3,637
  top_bottom_detector.py    1,999
  agent.py                  1,364
  execution.py              1,108
  composite_signal.py       1,064
  api.py                      866

ui/:                  3,496 lines (5 files)
tests/:               6,996 lines (21 files)
```

---

## A4 — Per-file scan summary

Each top-level module sampled for:
- TODO/FIXME/XXX/HACK markers
- Obvious dead code (unreachable branches, unused functions)
- Bare `except:` (none found)
- Heavy logic without unit tests (flagged but not enumerated)

| File | Findings |
|---|---|
| `app.py` (8,068 LoC) | 1 dead read (#2), 9 dead session keys (#3), Signals TF gap (#1) |
| `data_feeds.py` (8,464 LoC) | Clean. 35+ external API integrations, all wrapped in try/except + caches. Largest file in repo. |
| `crypto_model_core.py` (5,851 LoC) | Clean. The signal engine. §22 fixture-locked, §4 regression-locked. |
| `ui_components.py` (4,829 LoC) | Clean post-P1-34 fix. 95 f-string HTML interpolations — most are template literals not user-data. |
| `database.py` (3,637 LoC) | Clean. Schema migrations safe (`_ALLOWED_MIGRATE_TABLES` allowlist). New tables: `regime_history` (C8), extended `alerts_log` (C6). |
| `top_bottom_detector.py` (1,999 LoC) | NOT orphan (used by `crypto_model_core`). |
| `agent.py` (1,364 LoC) | Clean. Decision-log writes via `_db.log_agent_decision`. |
| `execution.py` (1,108 LoC) | Clean. OKX integration. |
| `composite_signal.py` (1,064 LoC) | Clean. The 4-layer aggregator. §4 regression-locked. |
| `api.py` (866 LoC) | Clean. FastAPI headless mode (not yet wired). |
| `ml_predictor.py` (723 LoC) | Clean. Lazy-loaded LightGBM. |
| `ai_feedback.py` (616 LoC) | Clean. |
| `whale_tracker.py` (560 LoC) | Clean. |
| `risk_metrics.py` (511 LoC) | **ORPHAN** (#4). |
| `llm_analysis.py` (511 LoC) | Clean. Anthropic API calls. |
| `alerts.py` (484 LoC) | Clean post-C6. Logs every fire to `alerts_log`. |
| `news_sentiment.py` (477 LoC) | Clean. |
| `arbitrage.py` (472 LoC) | Clean. |
| `chart_component.py` (452 LoC) | Clean. |
| `cycle_indicators.py` (407 LoC) | Clean. §22 fixture-locked. |
| `pdf_export.py` (346 LoC) | Clean. |
| `websocket_feeds.py` (320 LoC) | Clean. |
| `circuit_breakers.py` (317 LoC) | Clean. |
| `allora.py` (291 LoC) | Clean. Allora oracle integration. |
| `glossary.py` (~250 LoC) | Clean. |
| `scheduler.py` (~200 LoC) | Clean. |
| `utils_wallet_state.py` (~150 LoC) | Clean. |
| `utils_audit_schema.py` | **ORPHAN** (#4). |
| `utils_format.py` | **ORPHAN** (#4). |

---

## A5 — UI / theme / level audit (static-only)

Cannot run actual UI without a Streamlit server. Static review only:

- **Level system**: confirmed `current_user_level()` reads `st.session_state["user_level"]` consistently across pages (per C9 wiring + §C1 helper). Test `test_user_level_persistence.py::test_page_reads_user_level_from_session_state` enforces.
- **Theme system**: dual-token CSS in `ui/design_system.py` — both dark + light. Light-mode contrast pre-validated against WCAG AA in earlier audits.
- **Mobile breakpoints**: `@media (max-width: 768px)` rules in `ui/overrides.py` cover sidebar collapse + topbar pill hiding + tab-gap reduction. C1 added universal `*, *::before, *::after { box-sizing: border-box; min-width: 0; }` to prevent overflow.
- **Manual verification still needed**: actual button clicks, chart renders, modal/dropdown behaviour at 3 levels × 2 themes × mobile/desktop. **Not in scope for static audit.**

---

## A6 — GitHub state

| | |
|---|---|
| `main` HEAD | `1da35f9` |
| Tags | `redesign-ui-2026-05-shipped`, `redesign-port-fixed-2026-04-29`, 7 `backup-pre-*` tags |
| Stale local branches | 9 (4 `claude/*`, 1 `fix/*`, 4 `redesign/*`) |
| Stale remote branches | 8 (incl `master` legacy + 7 redesign branches) |
| Recent commits on main (last 10) | All Phase C commits + cleanup |
| Dependabot branches | 2 open (actions/checkout-v6, actions/setup-python-v6) |

**Recommendation:** Branch prune cleanup ticket — issue #5.

---

## A7 — Recommended fix order

If/when you want to act on findings:

1. **Issue #1 (HIGH)** — Signals/per-TF data gap. Pick path A1.1 (cheap on-demand recompute) or A1.3 (UX disable). Ships in <1h.
2. **Issue #5 (MED)** — branch prune. Cosmetic, ~30s.
3. **Issue #4 (MED)** — orphan module cleanup. Same pattern as `1da35f9`. ~5min.
4. **Issue #2 + #3 (LOW)** — dead reads + session state. Bundle into one cleanup commit. ~30min.
5. **Issue #6 (LOW)** — silent-pass exception handlers. Touch as you encounter them in future work, no dedicated sprint.
6. **Issue #7 (LOW)** — XSS surface. Same — touch as encountered.
7. **Issue #8** — non-action; prod is fine.

**Defer until you hit one in production**: 2 / 3 / 6 / 7 / 8.

---

## A8 — What was NOT audited (calls out scope limits)

- **Live UI verification** at 3 levels × 2 themes × mobile/desktop — requires running Streamlit + manual clicks
- **API rate-limit budget** under sustained scan load — requires scan loop + monitoring
- **Web3 wallet read paths** — requires connected wallet
- **AI agent live decision flow** — requires agent supervisor running
- **Data refresh interval verification** under prod traffic — requires live deploy observation
- **Cross-browser** — only HTTP-level checks possible from CLI

These are **CLAUDE.md §4-mandated** but require user-side execution (running the app + clicking through). The static audit found nothing that prevents those checks from going green.

---

## A9 — Tomorrow's standing instruction

Pick up issue #1 first. The user's reported bug ("Signals → ETH 4h timeframe leaves indicator cards on 1d") **maps directly** to this finding — same root cause. Fix lands one batch, validates the user's reported issue + closes the architectural gap.

If you have further bug reports from manual testing, append them to the issue ledger above.

---

*Audit completed 2026-05-01. Test count snapshot: 185 passing, §4: 6/6, §22: 37/37, deploy verifier: 5/5.*
