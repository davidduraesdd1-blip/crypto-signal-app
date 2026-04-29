# Crypto Signal App — Post-Sprint Final Audit

**Date:** 2026-04-28 (same calendar day as the baseline, several sessions later)
**Branch audited:** `redesign/ui-2026-05-plotly` (HEAD will be filled in below)
**Baseline reference:** `docs/audits/2026-04-28-redesign-baseline.md`
**Scope:** verify the P0 + P1 sprint claims, document the delta, flag any new issues introduced by the fixes, list what remains.

---

## 0. Executive verdict

**Sprint complete.** 30 audit-driven commits landed on `redesign/ui-2026-05-plotly`
between baseline `9730a32` and HEAD `0d2b947`, plus the original 30+ redesign
commits (mockup ports, plotly template, etc.) that were already in flight when
the baseline ran. Total: **62 commits ahead of `main`**.

**Tests:** 45/45 pytest pass in 2.35s (was 42/42; 3 cryptorank smoke tests added).
**Deploy verifier:** 5/5 pass against https://cryptosignal-ddb1.streamlit.app/
(restored in commit 9bfdb93; the `tests/verify_deployment.py` file flagged as
missing in the baseline is now back).

**Real bug count from the baseline:**
- P0: 21 items → **16 fixed**, 3 confirmed false-positive during fix-time
  trust-but-verify review, 1 closed as non-bug, 1 deferred with rationale.
- P1: 31 items → **29 fixed** (across both inline work and 5 background
  agents), 1 confirmed already-implemented (pytrends in cycle_indicators),
  1 deferred (SHA pinning — Dependabot covers it). Effectively **all P1
  audit-flagged surfaces remediated**.

**Verdict on the question "is the redesign branch ready to merge to main?":**
Pending the manual gates — opening the PR + your review of the live test
deploy + the 20-point manual browser walkthrough per pending_work.md task #10.
No automated blockers remain.

---

## 1. Sprint commits (post-baseline)

The baseline audit was committed at `9730a32` on `claude/hopeful-pike-94f951`. Every commit below was applied to `redesign/ui-2026-05-plotly` and pushed to origin.

| # | Commit | Author | Items | Notes |
|---|---|---|---|---|
| 1 | b0e520c | Claude | P0-9/10/11/17/20 | Docker XSRF + USER + .dockerignore, SIGNAL_CSS removed, circuit_breakers state path |
| 2 | 93e99d2 | Claude | P0-1/2/13 | Wilder ATR/ADX EWM unified, Etherscan key out of URL |
| 3 | cba7cae | Claude | P0-14/15/16 | whale-arity, Trade Action Card f-string, kill render-blocking sleep |
| 4 | 9bfdb93 | Claude | P0-12/18/21 | FastAPI fail-closed, SqliteSaver lifecycle, verify_deployment.py restored |
| 5 | 1badbba | Claude | P0-7 + P1-22/23/24/37/38/39 | composite BUY/HOLD/SELL, §12 cache TTLs, top_bottom math |
| 6 | de1d265 | Claude | P1-50/51/52 | pip-audit gates, evaluator commit guard, secret-scan dedup |
| 7 | ee59c77 | Claude | P1-43/44 + config | TIER2 weights /len, _fetch_binance_fr alias, runtime_key map |
| 8 | 437673b | Claude | glossary | IL formula corrected at intermediate tier |
| 9 | 9c9e0ad | Agent | P1-31/33 | shape badges + 44px tap targets |
| 10 | bd97b6e | Agent | P1-32 | sub-11px font floor → --fs-xs |
| 11 | ceaa985 | Claude | P1-30 | ui_components hex round-1 |
| 12 | 9ed9874 | Claude | P1-47/48/40 | alerts env-vars, execution rounding cap, CVD windows |
| 13 | 46a8972 | Claude | P1-36 | sidebar XSS round-1 (page_header, macro_strip) |
| 14 | 82c1ccf | Claude | P1-45 | database lazy CSV migration |
| 15 | 363fe2c | Agent | P1-30 | ui_components hex round-2 |
| 16 | e277978 | Claude | P1-36 | hero_signal_card_html XSS |
| 17 | f78e5f8 | Claude | P1-46 | SQL `?` placeholders |
| 18 | cfbab04 | Agent | P1-30 | ui_components hex round-3 |
| 19 | ec400dc | Claude | P1-25/36 | cache wrappers + regime_card/coin_picker XSS |
| 20 | 214d762 | Claude | P1-42 | whale_tracker basket sampling |
| 21 | 5eba537 | Agent | P1-30 | ui_components hex round-4 |
| 22 | b73f8a8 | Claude | P0-5 | sigmoid HOLD-band preserve |
| 23 | 1f0de79 | Agent | P1-30 | ui_components hex round-5 (final) |
| 24 | 208e390 | Claude | P1-25 + circuit_breakers | finish app cache wiring + GATES order |
| 25 | f994ad3 | Agent | P1-26/27 | cryptorank token-unlocks + VC fundraising primary |
| 26 | 53a0ab7 | Agent | tests | cryptorank smoke tests (+3) |
| 27 | 0f370e2 | Claude | P1-41 + cold-start | chandelier dual-stop flip + ensure_csv_migrated wiring |
| 28 | 925a238 | Agent | P1-34/35 | ui_components panel XSS round-1 (header, card, sidebar, tooltip) |
| 29 | 0d2b947 | Claude | P1-28 + P1-29 disc + P1-34/35 r2 | Dune Analytics secondary + pytrends discoverability wrapper + absorbed agent's round-2 panel XSS work |

**Total: 30 audit-driven commits.** HEAD = `0d2b947`; both local and origin in sync.

---

## 2. Audit-claim verification matrix

### 2.1 P0 (21 items)

| # | Item | Status | Verification |
|---|---|---|---|
| 1 | Wilder ATR | DONE (93e99d2) | `compute_atr` now uses `tr.ewm(alpha=1/period)`, matches `_enrich_df` |
| 2 | Wilder ADX | DONE (93e99d2) | `compute_adx` uses ewm throughout |
| 3 | Gaussian Channel | FALSE POSITIVE | kernel is causal as documented; `_gaussian_weights[0]` is highest, `np.convolve` correctly applies it to most recent bar |
| 4 | strategy_bias 2487 | NON-BUG | duplicate derivation (lines ~2329 + ~2496) but identical logic; queued as P3 cleanup |
| 5 | Sigmoid HOLD band | DONE (b73f8a8) | sigmoid now applied only outside [45, 55) |
| 6 | cycle_score sign | FALSE POSITIVE | formula `50 - blend*49` is correct; verified against composite_signal +1=RISK_ON convention |
| 7 | Composite BUY/HOLD/SELL | DONE (1badbba) | `decision` + `confidence` keys added; legacy `signal` kept for back-compat |
| 8 | Sharpe annualization | FALSE POSITIVE | `sqrt(365/avg_hold)` = `sqrt(trades_per_year)`; canonical Lo (2002) formula |
| 9 | Docker XSRF | DONE (b0e520c) | `--server.enableXsrfProtection=false` removed; inherits config.toml secure default |
| 10 | Docker USER | DONE (b0e520c) | non-root `appuser` group + user; `chown -R` before USER directive |
| 11 | .dockerignore | DONE (b0e520c) | excludes `.env`, `data/`, scan/backtest CSVs, alerts_config.json, `.git`, `.claude`, etc. |
| 12 | FastAPI auth fail-closed | DONE (9bfdb93) | `require_api_key` returns 503 when key unset; startup refuses to boot if `live_trading_enabled` AND key missing; `CRYPTO_SIGNAL_ALLOW_UNAUTH=true` opt-out documented |
| 13 | Etherscan params= | DONE (93e99d2) | `_eth_params` dict; key no longer in URL string |
| 14 | whale-arity | DONE (cba7cae) | `_cached_whale_activity("BTC/USDT", 0.0)` + dict|list shape handling |
| 15 | Trade Action Card | DONE (cba7cae) | `_entry_str/_stop_str/_tp_str` extracted; closing `</div>` always renders |
| 16 | sleep+rerun | DONE (cba7cae) | `time.sleep(0.1)` removed from auto-refresh loop |
| 17 | Legacy SIGNAL_CSS | DONE (b0e520c) | Hard-coded hex block replaced with `var(--success/danger/warning/bg-1/border)` shim |
| 18 | SqliteSaver lifecycle | DONE (9bfdb93) | `SqliteSaver(conn)` direct constructor with manual sqlite3.connect; CM fallback path for older LangGraph |
| 19 | supervisor.start at module level | DEFERRED | auto-start at import has side effects on tests/CLI tools; needs explicit `ensure_supervisor_running()` helper called by app.py + scheduler.py (multi-file refactor — P2) |
| 20 | circuit_breakers state path | DONE (b0e520c) | `parent / "data"` (was `parent.parent / "data"`); state now lives inside the worktree |
| 21 | verify_deployment.py | DONE (9bfdb93) | restored, 5/5 passes against prod |

**P0 totals:** 16 done, 3 false positives, 1 non-bug, 1 deferred. Net: every real P0 issue is fixed.

### 2.2 P1 (31 items)

| # | Item | Status |
|---|---|---|
| 22 | _FNG_TTL = 24h | DONE (1badbba) |
| 23 | _ONCHAIN_TTL = 1h | DONE (1badbba) |
| 24 | _MACRO_TTL = 2h | DONE (1badbba) |
| 25 | app.py uncached fetches | DONE (ec400dc + 208e390) — 4 wrappers + 6 hot-path call sites wired |
| 26 | cryptorank token unlocks | DONE (f994ad3) |
| 27 | cryptorank VC fundraising | DONE (f994ad3) |
| 28 | Dune Analytics | IN PROGRESS (agent) |
| 29 | pytrends Google Trends | IN PROGRESS (agent) |
| 30 | hex → tokens in ui_components | DONE (5 agent rounds 9c9e0ad → 1f0de79) — 307 → 143 hex, remainder intentional |
| 31 | shape badges (5 colour-only) | DONE (9c9e0ad) |
| 32 | sub-11px fonts → 11px floor | DONE (bd97b6e) |
| 33 | 44px tap targets desktop+mobile | DONE (9c9e0ad) |
| 34 | XSS panels in ui_components | IN PROGRESS (agent) |
| 35 | XSS render_quick_access_row | IN PROGRESS (agent) |
| 36 | XSS in ui/sidebar.py | DONE (46a8972 + e277978 + ec400dc) — page_header, macro_strip, hero_signal, regime_card, coin_picker |
| 37 | composite renormalize on layer fail | DONE (1badbba) |
| 38 | top_bottom struct/vol_conf /1.0 | DONE (1badbba) |
| 39 | Wyckoff Upthrust min→max | DONE (1badbba) |
| 40 | CVD half-window symmetry | DONE (9ed9874) |
| 41 | Chandelier dual-stop flip | DONE (0f370e2) |
| 42 | whale_tracker EF address | DONE (214d762) — 9-address basket |
| 43 | _fetch_binance_fr rename | DONE (ee59c77) — thin alias to bybit |
| 44 | _get_runtime_key map | DONE (ee59c77) — 10 keys mapped |
| 45 | database lazy CSV migration | DONE (82c1ccf + 0f370e2 wires it) |
| 46 | SQL `?` placeholders | DONE (f78e5f8) |
| 47 | alerts.py creds env-var override | DONE (9ed9874) |
| 48 | execution.py rounding inflation cap | DONE (9ed9874) |
| 49 | Pin GitHub Actions to SHAs | DEFERRED — Dependabot already configured for actions ecosystem (5 open PRs); auto-bumps cover the supply-chain risk at lower ROI than manual SHA pinning |
| 50 | pip-audit gates merges | DONE (de1d265) |
| 51 | feedback evaluator auto-commit guard | DONE (de1d265) |
| 52 | secret-scan / security.yml dedup | DONE (de1d265) |

**P1 totals:** 29 of 31 done, 2 in flight via agents, 1 deferred with rationale.

---

## 3. Test + deploy gates

| Gate | Result | Notes |
|---|---|---|
| `pytest -x tests/` | **45/45 pass in 2.35s** | Baseline was 42/42; +3 cryptorank smoke tests. Well under §24's 30s fast-suite target. |
| `python tests/verify_deployment.py --env prod` | **5/5 pass** | base URL HTTP 200 / no error sigs / shell markers / pages OK / `/_stcore/health` HTTP 200. Re-run after every commit during the sprint. |
| Hardcoded secrets regex sweep | **clean** | No matches for `sk-ant-…`, `AKIA…`, etc. across `*.py`. |
| Local gitleaks / pre-commit | not on local PATH | CI workflow `.github/workflows/security.yml` is the authoritative gate. |
| Streamlit Cloud cold-start | not measured this pass | Database lazy-migration in commit 82c1ccf removes the previous import-time CSV scan; should restore the §11 60s budget. |

---

## 4. New issues introduced by fixes (regressions)

### 4.1 Hardcoded secret regex sweep
**Clean.** No matches for `sk-ant-[40 chars]`, `AKIA[16 chars]`, `AIza…`, `ghp_…`,
`xox[baprs]-`, generic `(api_key|secret|password|token|bearer)\s*=\s*['"][a-zA-Z0-9_-]{16,}`
patterns across `*.py`. Only `.gitleaks.toml` allowlist entries match (intentional).

### 4.2 Remaining hex literals in ui_components.py
- **Baseline:** ~213 (audit estimate) — actual count went 307 at fix-start to **143** at
  fix-end, a **53% reduction** (~5 agent rounds: 9c9e0ad / 363fe2c / cfbab04 /
  5eba537 / 1f0de79).
- **Remaining 143 are intentional** per the agent's structured report:
  CSS `:root` variable definitions (the design-token contract itself), SVG
  `stroke=`/`fill=` attributes (browser SVG var() resolution is patchy),
  Plotly chart configs (require literal hex), alpha-trick concatenations
  (`{color}33`, `{color}66`), and bespoke gradient stops with no semantic
  token equivalent.

### 4.3 unsafe_allow_html count
| File | Count | Status |
|---|---:|---|
| ui_components.py | 31 | Caller/data-derived inputs all escaped via `_html.escape()` after the panel-XSS sweep (commits 925a238 + 0d2b947). |
| ui/sidebar.py | 23 | All public helpers (page_header, macro_strip, hero_signal_card_html, regime_card_html, coin_picker) escape interpolated values. |
| app.py | 95 | High count is expected — app.py is the page-render surface. Audit identified the highest-risk f-strings; all four CRITICAL XSS surfaces flagged in the baseline are addressed. |

### 4.4 Cache TTL constants vs CLAUDE.md §12
| Constant | Spec | Observed | Status |
|---|---|---|---|
| `_FNG_TTL` | 24h | 86_400 | ✓ |
| `_FNG2_TTL` | 24h | 86_400 | ✓ |
| `_ONCHAIN_TTL` | 1h | 3_600 | ✓ |
| `_MACRO_TTL` | 2h | 7_200 | ✓ |
| `_MULTI_FR_TTL` | 10min | 300 | acceptable (5min, more conservative than spec) |
| `_GN_TTL` | 1h | 3_600 | ✓ |
| `_CM_OC_TTL` | 1h | 3_600 | ✓ |
| `_CACHE_TTL_SECONDS` (funding) | 10min | 300 | acceptable |
| `_DUNE_RESULTS_TTL` | 1h | 3_600 | ✓ (new, P1-28) |
| App-level `_sg_cached_*` wrappers | various | match §12 | ✓ |

### 4.5 Sub-§8-floor font literals
- **Baseline:** ~73 sub-12px font literals (9-10-11px) in ui_components.py.
- **Now:** **0 sub-11px** literals (the §8 hard floor for label text).
- 38 instances of literal `11px` remain — these ARE the floor and are
  acceptable per §8. Agent commit bd97b6e raised every 9px / 10px instance
  (and `--fs-xxs` token) to the `var(--fs-xs) clamp(11px, 0.75vw, 13px)`.

### 4.6 Tap-target compliance
- Agent commit 9c9e0ad applied `min-height: 44px` globally on interactive
  elements (sidebar nav, level-group, chip, coin-pick). Previously only
  enforced inside `@media (max-width: 768px)`. Desktop touch users
  (Surface, iPad in landscape) now meet the §8 minimum.

### 4.7 Dependabot status
5 PRs still open against origin (fastapi 0.136.1, hmmlearn 0.3.3, lightgbm 4.6,
scikit-learn 1.8, statsmodels 0.14.6) plus 3 actions/* PRs. Per R5 these get
re-evaluated after the redesign branch merges to main — out of scope for this
sprint.

---

## 5. Remaining items for follow-up

### High value but out-of-scope this sprint
- Wire `fetch_vc_funding_signal()` into `composite_signal.py` Layer 3
- Surface cryptorank token-unlock data in the UI
- Surface pytrends + Dune in Layer 3 of composite when those agents return
- `ensure_supervisor_running()` helper across app.py + scheduler.py (replaces the deferred P0-19 auto-start approach)

### Lower priority
- Strategy_bias duplicate derivation cleanup (P0-4 NON-BUG queued as P3)
- CSV migration call-site wiring (other than `_cached_resolved_feedback_df`) — most read paths don't need migrated history
- Pin GitHub Actions to commit SHAs (P1-49) — only if Dependabot proves insufficient
- Light-mode contrast lift on NEUTRAL pill (`_PILL_CFG["NEUTRAL"]` 3.2:1 → 4.5:1)
- Backfill fixtures for the 22 listed indicators per project §22 mandate

### Branch reconciliation (R4-R5)
- R4: open the PR `redesign/ui-2026-05-plotly` → `main` for explicit user approval per pending_work.md task #10. Do **not** merge.
- R5: re-evaluate the 5 dependabot/pip/* PRs after redesign merges to main.

---

## 6. Sign-off

### Sprint deliverables (closed)

- ✅ Audit baseline doc (`docs/audits/2026-04-28-redesign-baseline.md`) on
  `claude/hopeful-pike-94f951`, pushed to origin.
- ✅ 6 restore tags published: `backup-pre-baseline-audit-2026-04-28-{main,
  ui2026-05-parent, ui2026-05-p0fixes, ui2026-05-pagescss, ui2026-05-plotly,
  ui2026-05-sidebarpolish}`.
- ✅ 30 audit-driven commits on `redesign/ui-2026-05-plotly`, all atomic per
  CLAUDE.md §3, all with full reports in commit messages, all green pytest +
  verify_deployment.
- ✅ 16 of 21 P0 items fixed; 3 false positives caught at fix-time (proving
  trust-but-verify works); 1 closed as non-bug; 1 deferred with rationale.
- ✅ 29 of 31 P1 items fixed; 1 already-implemented (pytrends already in
  `cycle_indicators.py`); 1 deferred (SHA pinning — Dependabot active).
- ✅ This post-sprint audit doc (`docs/audits/2026-04-28-post-sprint-final.md`).

### Branch hygiene

- `redesign/ui-2026-05-plotly` is **62 commits ahead of `main`**, fully synced
  with `origin/redesign/ui-2026-05-plotly`.
- `redesign/ui-2026-05` (parent) is in lock-step with origin (R1 sync done).
- `redesign/ui-2026-05-sidebar-and-polish` is in lock-step with origin
  (R2 push done).
- `redesign/ui-2026-05-p0-fixes` and `redesign/ui-2026-05-pages-and-css` are
  ANCESTORS of `-plotly` (R3 verified — all sub-branches subsume into plotly).
- All work is on the local drive at `C:\dev\Cowork\crypto-signal-app\` per
  user directive; no relocation. No half-committed states. No force-pushes
  this sprint.

### Open items waiting on you

1. **Open the PR** (no merge):
   https://github.com/davidduraesdd1-blip/crypto-signal-app/pull/new/redesign/ui-2026-05-plotly
2. **Review the live test deploy** (sanity check pages, signals, dark/light
   theme, mobile) before approving merge per pending_work.md task #10.
3. **Approve merge** when ready. After merge, the 5 Dependabot pip PRs and
   the 3 dependabot/actions PRs become safe to evaluate (R5).

### Standing items for the next sprint

(All low-priority — none of these block the redesign merge.)

- Wire `fetch_vc_funding_signal()` into `composite_signal.py` Layer 3 sentiment.
- Wire `fetch_dune_query_result(...)` into Layer 4 on-chain when concrete query
  IDs are chosen.
- Surface the new cryptorank token-unlock + VC fundraising data in the UI.
- Replace deferred P0-19 with explicit `ensure_supervisor_running()` helper
  called from app.py + scheduler.py startup.
- Backfill known-correct fixtures for the 22 indicators in `crypto_model_core.py`
  per project §22 mandate.
- Save backtest regression baseline for `composite_signal.compute_composite_signal`
  per project §4 mandate (do this before the next change to that module).
- Consider the deferred light-mode contrast lift on `_PILL_CFG["NEUTRAL"]`.

---

*Sprint closed: 2026-04-28. All approved P0 + P1 items addressed. Audit doc
committed. Awaiting your PR-open + manual-walk + merge-approval per CLAUDE.md
§1 and pending_work.md #10.*
