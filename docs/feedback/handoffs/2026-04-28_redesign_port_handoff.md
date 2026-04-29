# Crypto Signal App — Redesign Port Handoff

**Date:** 2026-04-28
**Branch:** `claude/funny-jennings-1a4193`
**Deploy:** https://cryptosignal-ddb1.streamlit.app/
**Reviewer:** David Duraes
**Status:** Visual redesign shipped. Data-to-component wiring broken on most deep pages. Triage doc for Cowork.

---

## TL;DR

The redesign port (PR #11, merged) replaced page chrome successfully on the
**Market Home** page — hero cards, macro strip, and watchlist all populate from
live data and work as expected.

Every page deeper than Market Home received the new visual chrome but **lost
its data-to-component wiring** during the port. The data-fetch functions
themselves are healthy (proven by the §22 fixture mandate — 22/22 indicators
have known-correct fixtures — and the §4 composite-signal regression baseline
locked into `docs/signal-regression/`). The fix is plumbing: reconnect the
existing fetch layer to the new card containers.

A separate UX defect was introduced in the sidebar: nav buttons require **two
clicks** before they show their highlighted/selected state.

The Config Editor (Trading / Signal & Risk / Alerts tabs) appears to have lost
its panel wiring entirely — historical screenshots show fully-functional
controls (pair pills, sliders, API key inputs); current state is unclear and
may need a from-scratch rewire.

The Settings / AI Agent page survived the port intact (STOPPED-state badge,
agent-config sliders, dry-run toggle all rendering and live).

---

## What's Done (P0/P1 sprint + follow-ups, last ~30 commits)

### Math & signal layer
- §22 fixture mandate **COMPLETE** — 22/22 indicators have known-correct fixtures
  (RSI, MACD, BB, ATR, ADX, SuperTrend, Stochastic, Ichimoku, Hurst, Squeeze,
  Chandelier, CVD, Gaussian, S/R, MACD/RSI divergence, candlestick, Wyckoff,
  HMM regime, cointegration, VWAP, fib levels).
- `composite_signal.py` — regression baseline locked + 5-scenario diff (§4).
- Layer 3 (sentiment) wired: VC funding via cryptorank `/funds` feeding composite.
- Layer 4 (on-chain) wired: Dune custom queries feeding composite.
- CryptoRank token-unlock data surfaced on Signals page.

### Security
- XSS-hardened header / card / sidebar / tooltip helpers (P1-34, P1-35).
- Round-2 ui_components panel hardening.

### Data sources
- Dune Analytics promoted to **SECONDARY** on-chain source.
- pytrends discoverability wrapper added (graceful rate-limit fallback).

### Build / CI / deps
- pip-audit flag fix (`--format`), bogus `--strict` dropped.
- Dependabot consolidated: fastapi, hmmlearn, lightgbm, scikit-learn, statsmodels,
  actions/checkout v6, setup-python v6, upload-artifact v7.
- Redesign sprint closed; PR #11 merged.

### MEDIUM follow-ups landed
- Grade boundaries.
- ML cache thrash (cache-key fix).
- Slippage RNG seeded.
- Alerts module dead import removed.
- `bp` → `bps` plural correctness.
- Atomic checkpoint write (no torn files on crash).
- Glossary fallback for older Streamlit versions.
- PDF version sourced from `VERSION` constant.
- `ensure_supervisor_running` helper (closes deferred P0-19).

---

## Open Issues — Triage List

### CRITICAL — block release / make page unusable

| # | Page | Issue | Likely root cause |
|---|---|---|---|
| C1 | All pages | Beginner / Intermediate / Advanced toggle has no visible effect on content. | Level state not being read by post-port renderers. |
| C2 | Backtester | "Re-run backtest →" and "▶ Run Backtest" buttons do nothing on click. | Click handlers not bound to new buttons; backtest function not invoked. |
| C3 | Regimes / BTC detail | All 4 composite layers, technical indicators, and on-chain values empty. | Data-fetch results not piped into new card containers. |
| C4 | On-chain page | MVRV-Z, SOPR, Exchange Reserve, Active Addresses empty for BTC, ETH, XRP — page is data-less. | Same plumbing failure as C3, on-chain detail surface. |
| C5 | Config Editor | Old build had fully-functional Trading + Signal & Risk + Alerts tabs (pair pills, sliders, API key inputs). Current redesign state appears wiring-stripped — may need full rewire. | Config-editor panels never reattached during port. |

### HIGH — visible defect, page partially usable

| # | Page | Issue | Likely root cause |
|---|---|---|---|
| H1 | Top bar (narrow viewport) | Beginner/Intermediate/Advanced/Refresh/Theme pill labels wrap inside their pills. | Pill min-width / no-wrap missing; needs `white-space: nowrap` + responsive sizing. |
| H2 | Top bar | "Refresh All Data" button shows no visible feedback (no spinner / no toast / no state change). | Click handler missing UI feedback step. |
| H3 | Regimes / BTC detail | "Price · last 90d" panel shows "Price history unavailable". | OHLCV fetch result not reaching panel; same plumbing class as C3. |
| H4 | Sentiment cards (detail pages) | Google Trends and News Sentiment show "—" placeholders. | Sentiment fetchers not piped to new cards; verify pytrends wrapper still firing. |
| H5 | Sidebar | Nav buttons require **two clicks** before highlighted/selected state appears. First click navigates but doesn't update the highlight; second click then highlights. | Likely `st.session_state` selection write happening *after* the rerun, so first paint reads old value. Move state update to *before* `st.rerun()`. |

---

## Failure Pattern (one-paragraph summary)

> The redesign delivered new visual chrome cleanly on the Market Home and
> Settings / AI Agent pages, but on every other deep page the new card
> containers were stamped in without re-binding their data sources. Fetch
> functions are intact (regression baselines + fixtures prove this); the
> integration layer between data and view was the casualty. Recommended fix
> is a single plumbing sprint: page-by-page, re-attach the existing data-fetch
> outputs to the new card components, then verify against the locked
> §4 regression diff.

---

## Recommended Fix Order

1. **C1 — User-level toggle.** Cross-cuts every page; fixing first means every
   subsequent page can be verified at all 3 user levels in one pass.
2. **H5 — Sidebar double-click highlight.** Cheap fix (state-write ordering),
   eliminates a constant friction point during the rest of the testing.
3. **C3 + C4 + H3 + H4 — On-chain / Regimes / Sentiment plumbing.** Same root
   cause class; fix the wiring pattern once, apply to all four surfaces.
4. **C2 — Backtester buttons.** Isolated handler rebind.
5. **C5 — Config Editor.** Largest scope; may require rebuild of the three
   tabs against the new card system. Schedule last so smaller fixes ship first.
6. **H1 + H2 — Top bar polish.** Cosmetic / feedback-affordance fixes.

---

## Image Workflow Going Forward (avoid the 2000px limit)

The chat hit `An image in the conversation exceeds the dimension limit for
many-image requests (2000px)` mid-review. To prevent this from blocking
future sessions, switching to a text-first workflow:

**Preferred — text template per issue:**
```
PAGE:        e.g. "Composite Signal" or "Signals → BTC"
USER LEVEL:  Beginner / Intermediate / Advanced
THEME:       Dark / Light
WHAT I SAW:  one sentence — what's wrong, where on the page
EXPECTED:    one sentence — what it should look/do
```

**When the issue is purely visual** (color, layout, overflow):
> "VISUAL ONLY — open the deploy URL and repro live."
> Claude will hit https://cryptosignal-ddb1.streamlit.app/ directly with a
> browser tool, take its own screenshot at safe dimensions, and fix from there.

**When an image is genuinely required:**
1. Resize to **≤ 1600px on the longest edge** before pasting.
2. Or drop the file into `docs/feedback/inbox/<filename>.png` in the repo and
   reference it by filename in chat — local file paths are not subject to
   the chat-image dimension limit.

---

## Verification Plan (after fixes land)

- All 3 user levels × dark + light mode = 6 visual passes per page.
- Composite-signal regression diff against the locked §4 baseline; expect
  zero categorical drift (BUY ↔ SELL) on BTC + ETH without a regime change.
- Streamlit Cloud cold-start under 60s (lazy-loaded ML imports).
- Fallback-chain test: force CCXT primary unreachable, confirm secondary
  takes over.
- Sidebar: every nav button highlights on first click.
- Top bar: refresh button shows clear in-flight + completion feedback.
