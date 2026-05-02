# Crypto Signal App — Comprehensive UI / CSS Audit

**Date:** 2026-05-02
**Auditor:** Claude (deep-dive pass following the in-progress legacy-look
audit doc `2026-05-02_legacy-look-audit-in-progress.md`)
**Scope:** All redesigned + partially-ported pages — Home, Signals,
Regimes, Backtester, Arbitrage sub-view, On-chain, Alerts, AI Assistant,
Settings.
**Files inspected:**
- `ui/design_system.py` — CSS tokens + helpers (360 lines)
- `ui/sidebar.py` — sidebar, topbar, page header, all DS helpers (1860 lines)
- `ui/overrides.py` — Streamlit widget overrides (1146 lines)
- `ui_components.py` — legacy stylesheet (4829 lines, large segments still load-bearing)
- `app.py` — page renderers (8865 lines)
- `.streamlit/config.toml`

This audit augments the in-progress doc; the in-progress doc is
screenshot-driven (per-image observations), this one is code-driven
(every file inspected for token consistency).

---

## TL;DR — Headline numbers

- **Estimated redesign-port completion:** ~62% of surfaces are fully
  ported, ~28% are hybrid (DS chrome + legacy widget body), ~10%
  unchanged legacy. Token + state-styling consistency is **the single
  biggest gap** — primary buttons and chips render bright-green on
  every "deeper" page because two competing stylesheets fight over
  `[kind="primary"]` and the legacy stylesheet (with `!important`
  gradient) wins.
- **Single most impactful fix:** delete `ui_components.py` lines 178-200
  (the `section.main button[kind="primary"]` gradient block) and
  the matching tab-pill block at lines 244-271. This single change
  resolves bright-green saturation on **every** main-area primary
  button across every page (Update, Load Rates, Save Settings,
  Run Backtest, Activate Emergency Stop, etc.) in one stroke.
- **Second most impactful fix:** add a sidebar-scoped `[data-testid=
  "stExpander"] summary` rule with `white-space: nowrap; text-overflow:
  ellipsis` plus a `title=` attribute fallback, so "📜 Legal (Internal
  Beta)" stops stacking vertically inside the 150px rail.

---

## 1. Bright-green saturation offenders (the recurring complaint)

The user-confirmed preference — see `docs/audits/2026-05-02_legacy-look-
audit-in-progress.md` §"Open user preferences" + memory file
`feedback_design_accent.md` — is: active states + primary CTAs should
use `--accent-soft` (rgba 12% teal) with `--text-primary` text, NOT
the full saturated `--accent` (#22d36f) on a coloured fill. `--accent`
remains the right token for thin accent strokes (border-left stripes,
1px focus rings, the regime dot, layer-bar fill) but **not** for any
button surface a user is going to click.

### 1.1 The structural cause — TWO stylesheets fighting

| Layer | Selector | Specificity | Background | Verdict |
|---|---|---|---|---|
| `ui/overrides.py:580-583` | `section.main [data-testid="stButton"] > button[kind="primary"]` | `(0,2,2)` | `var(--accent)` solid | **Already wrong** — should be `--accent-soft` |
| `ui_components.py:178-181` | `section.main .stButton > button[kind="primary"], section.main button[kind="primary"]` | `(0,2,2)` + `!important` | `linear-gradient(135deg, #00d4aa 0%, #10b981 60%, #a78bfa 100%)` | **Wins** — overrides the design-system rule because of `!important` |

The legacy `linear-gradient` + 700 weight + glow shadow is what users
are seeing on **every** main-area primary button in screenshots 4, 6,
7, 8 — it has nothing to do with token drift in `--accent` itself. The
fix is to delete the legacy block, then change the surviving DS rule
to `--accent-soft` to match the sidebar's active-state treatment.

### 1.2 Specific offenders (file · line · element)

| # | File | Line | Element / surface | Current code | Severity | Bucket |
|---|---|---|---|---|---|---|
| BG-1 | `ui_components.py` | 178-200 | All `section.main button[kind="primary"]` (Update / Load Rates / Save Settings / Run Backtest / Run WFO / Run Stress / Activate Emergency Stop / etc.) | `background: linear-gradient(135deg, #00d4aa 0%, #10b981 60%, #a78bfa 100%) !important; color: #0d0e14 !important; font-weight: 700 !important; box-shadow: 0 2px 14px rgba(0,212,170,0.25)` | **Critical** | (c) hybrid token drift |
| BG-2 | `ui/overrides.py` | 580-583 | Same surface, design-system version | `background: var(--accent); color: var(--accent-ink); border-color: var(--accent);` — solid bright fill | **High** | (c) — switch to `--accent-soft` |
| BG-3 | `ui_components.py` | 261-267 | `[data-testid="stTabs"] [aria-selected="true"]` — settings tabs, backtester sub-tabs | `background: linear-gradient(135deg, rgba(0,212,170,0.18) 0%, rgba(99,102,241,0.12) 100%) !important; box-shadow: 0 0 0 1px rgba(0,212,170,0.25)` | **High** | (c) competing with `ui/overrides.py:708-712` underline pattern |
| BG-4 | `.streamlit/config.toml` | 3 | `primaryColor = "#00D4AA"` — sets baseweb / multiselect tag chip color | This token paints **all** Streamlit native chips (multiselect tag pills, focus rings, slider thumb) bright teal | **High** | (c) — should be `#22d36f` to match `--accent`, but ideally even softer |
| BG-5 | `ui/overrides.py` | 944-950 | `.ds-bt-runbtn` decorative HTML button (Backtester) | `background: var(--accent); color: var(--accent-ink); padding: 8px 16px;` | Low (decorative-only since C2 fix; rendered hidden by default but token still wrong if a caller opts in) | (c) |
| BG-6 | `ui/overrides.py` | 736-737 | Beginner panel input focus ring — uses `var(--accent)` border + 1px box-shadow | The 1px focus halo is fine (thin accent stroke = right use of `--accent`); flag here only because users on beginner mode see solid teal line on every focus event | Low | leave as-is, it's correct |
| BG-7 | `ui_components.py` | 312-316 | `[data-baseweb="slider"] [role="slider"]` — slider thumb solid teal | `background: var(--primary) !important; border-color: var(--primary) !important;` | Medium | (c) sliders in Settings + Beginner panel |
| BG-8 | `ui_components.py` | 314-316 + 425-429 | scrollbar gradient + slider glow + various `--primary-glow` shadows | `background: linear-gradient(180deg, rgba(0,212,170,0.35), rgba(99,102,241,0.25))` | Low | cosmetic — keep on a wishlist |
| BG-9 | `ui_components.py` | 461-470 | `.live-dot` pulsing teal dot | `background: var(--primary); animation: pulse-dot 2.2s` | Low — actually correct usage (a dot/indicator, not a CTA) | leave |

### 1.3 Why `--accent-soft` is the right answer (per user)

The sidebar nav (`ui/overrides.py:123-128`) already uses
`background: var(--accent-soft); color: var(--text-primary);` for the
active nav item, and the topbar level pills + segmented control + tf
strip all use the same treatment (`overrides.py:646-649`,
`overrides.py:249-253`, `overrides.py:287-291`). The Update button +
multiselect tag chips + main-area primary buttons + tab-active state
are the four surfaces that **don't** follow this — exactly the four
surfaces the user has flagged.

### 1.4 Recommended fix — single CSS pass

Replace `section.main button[kind="primary"]` rules in **both**
`ui_components.py` and `ui/overrides.py` with a single rule in
`ui/overrides.py`:

```css
section.main [data-testid="stButton"] > button[kind="primary"] {
  background: var(--accent-soft) !important;
  color: var(--text-primary) !important;
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent) !important;
  font-weight: 600 !important;
  box-shadow: none !important;
}
section.main [data-testid="stButton"] > button[kind="primary"]:hover {
  background: color-mix(in srgb, var(--accent) 18%, transparent) !important;
  border-color: var(--accent) !important;
}
```

Plus delete `ui_components.py:178-200` (legacy gradient) and `ui_
components.py:244-271` (legacy tab-active gradient — the underline
pattern in `overrides.py:708-712` is the right successor).

---

## 2. Plain Streamlit widget surfaces missing `ds-card` wrap

Pages without dedicated mockups (On-chain deeper sections, Backtester
arbitrage internals, Funding Rate Monitor expander, Hyperliquid DEX
expander, Alerts history, Settings deeper tabs) drop directly into raw
Streamlit widgets with no `<div class="ds-card">` shell. Result: the
content reads as "from a different app" because the redesigned pages
above have card-shells with `var(--bg-1)` + 12px radius + 1px border.

### 2.1 Specific offenders

| # | Page | File · line | What's missing | Severity | Bucket |
|---|---|---|---|---|---|
| WW-1 | Backtester → Arbitrage → Funding Rate Monitor | `app.py:6809-6909` | The `with st.expander("📡 Funding Rate Monitor", expanded=False):` body has `st.dataframe`, multiselect, button, two captions — none wrapped in `ds-card`. Mockup-style would be: section header → ds-card containing the controls row → ds-card containing the table. | High | (b) no mockup yet |
| WW-2 | Backtester → Arbitrage → Hyperliquid DEX | `app.py:6955-7005` | Same shape — bare `st.expander` + `st.dataframe`. | High | (b) |
| WW-3 | Alerts → History view | `app.py:7053-7123` | 4 selectboxes + `st.dataframe(_hist_rows, …)` — bare row of selectboxes (no card-shell), bare dataframe (no card frame). The existing redesigned `signal_history_table()` helper in `ui/sidebar.py:1467` is the model to follow. | High | (b) — could be ported using existing helpers with low effort |
| WW-4 | Alerts → Configure form | `_render_alerts_configure` referenced from `app.py:7050` | Email config form rendered raw inside `st.expander`. | Medium | (b) |
| WW-5 | On-chain → Whale Activity table | `app.py:8772-8807` | The custom HTML row builder is wrapped in a `ds-card`, BUT the `st.markdown('</div>', unsafe_allow_html=True)` close tag at 8796 is emitted as a separate markdown element, leaving the card open in the DOM if anything between them throws. Defensive fix: build the whole block as one f-string. | Low | (d) DOM bug |
| WW-6 | Settings → Trading tab | `app.py:3303-3470` (multiselect, custom pair text input, sliders, expanders) | None of the row-groups are card-wrapped. Mockup parity would shell each subsection as a `ds-card`. | Medium | (b) no mockup yet for Settings interior |
| WW-7 | Settings → Signal & Risk / Dev Tools / Execution tabs | `app.py:~3700-4400` | Same — bare st.\* widgets, no shell. | Medium | (b) |
| WW-8 | AI Assistant → Active Limits / Decision log | `app.py:7372-7497` | Active Limits expander uses bare `st.metric` (correctly styled by `overrides.py:551-565` so individual cards look right) but the Recent Decisions `st.dataframe` is not card-shelled. | Medium | (b) |
| WW-9 | AI Assistant → Pipeline Architecture `st.code(...)` | `app.py:7406-7409` | Renders as a plain code block; no card. | Low | (b) |
| WW-10 | Backtester → Trade History sub-tabs (Master Log, Paper Trades, Feedback, Execution, Slippage) | `app.py:~5169-5800` | Multiple bare multiselects + bare dataframes per sub-tab, no `ds-card` wrap. | Medium | (b) |
| WW-11 | Backtester → Advanced (Walk-Forward, OHLCV-Replay, Signal Calibration, IC & WFE) | `app.py:~5800-6500` | Same — extensive bare-widget surface area. | Medium | (b) |

### 2.2 Recommended primitive — add a generic `ds-section` shell helper

Add to `ui/sidebar.py` (or a new `ui/shells.py`):

```python
@contextmanager
def ds_section(title: str, subtitle: str = "", *,
               help_text: str = "", actions_html: str = ""):
    """Wrap an arbitrary block of Streamlit widgets in a ds-card with a
    section header. Usage:
        with ds_section("Funding Rate Monitor",
                        "Compare perpetual funding rates across …"):
            st.multiselect(...)
            st.button(...)
            st.dataframe(...)
    """
```

With this primitive in place, every "deeper" page can wrap its bare
widget surface in 2 lines without per-page custom HTML.

---

## 3. Multiselect / select / expander styling gaps

### 3.1 Multiselect tag chips — bright-green pills

**Cause:** No CSS rule targets `[data-testid="stMultiSelect"]
[data-baseweb="tag"]`. The chips fall back to Streamlit/baseweb defaults
which read the theme's `primaryColor` token (`.streamlit/config.toml:3
= "#00D4AA"`). That hex is the legacy bright accent — both *too bright*
relative to the design-system `#22d36f` and *too saturated* relative to
the desired `--accent-soft` muted treatment.

| # | File · line | Issue | Severity | Bucket |
|---|---|---|---|---|
| MS-1 | `.streamlit/config.toml:3` | `primaryColor = "#00D4AA"` paints every baseweb tag chip + select highlight + slider thumb bright teal. Should be `#22d36f` to match DS, or even softer (`color-mix` not available in TOML — use the DS soft hex equivalent). | High | (c) token drift |
| MS-2 | `ui/overrides.py:670-675` | Only restyles the **outer container** (`stMultiSelect [data-baseweb="select"] > div`) — does not reach the per-tag `[data-baseweb="tag"]` chip. | High | (c) incomplete port |
| MS-3 | `ui_components.py:305-309` | Legacy rule on `[data-testid="stMultiSelect"] > div` (background + border) — same gap. | Medium | (c) |

**Fix:** add to `ui/overrides.py` after the existing multiselect block:

```css
[data-testid="stMultiSelect"] [data-baseweb="tag"] {
  background: var(--accent-soft) !important;
  color: var(--text-primary) !important;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent) !important;
  border-radius: 6px !important;
  font-size: 12px !important;
  padding: 2px 8px !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] [role="presentation"] {
  /* the × close button — keep it muted */
  color: var(--text-secondary) !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"]:hover {
  background: color-mix(in srgb, var(--accent) 18%, transparent) !important;
}
```

### 3.2 Selectbox + textinput dropdown popovers

| # | File · line | Issue | Severity | Bucket |
|---|---|---|---|---|
| SB-1 | `ui/overrides.py:670-675` | Selectbox closed state restyled, but the **opened dropdown `[data-baseweb="popover"]`** menu is unstyled — falls to legacy `ui_components.py:728-736` light-mode rule (no dark equivalent). The opened dropdown reads on a near-black baseweb default fill that doesn't match `--bg-1`. | Medium | (c) |
| SB-2 | `ui_components.py:298-309` | Legacy rule competes with new override. The legacy uses `rgba(14,18,30,0.9)` (close to but not `var(--bg-1)`). Functional fine, but causes the Settings page selects to look slightly different from Backtester selects. | Low | (c) |

### 3.3 Expander shell

| # | File · line | Issue | Severity | Bucket |
|---|---|---|---|---|
| EX-1 | `ui/overrides.py:678-682` | Generic `[data-testid="stExpander"]` rule — applies to **every** expander including the sidebar Legal one, which is exactly the wrong scope (see §6 below). | High | (c) needs scoping |
| EX-2 | `ui_components.py:160-161` | `(b) DELETED` per the audit comment — but the comment explicitly says "Sidebar [data-testid="stExpander"] override — Legal expander now inherits its style from the main expander rules in overrides.py". The inheritance assumption is correct in the dark theme but **the inherited rule has no `white-space: nowrap` on the summary**, which is the root cause of Image-8's vertical-word-stacking. | High | (a) incomplete port |
| EX-3 | `ui_components.py:679-690` | Light-mode expander has glassmorphic gradient border that doesn't match the dark-mode flat-card look. Result: light-mode users see a gradient border on every expander; dark-mode users see a flat card. | Medium | (c) |

---

## 4. Empty-state copy: every place that shows bare `—` or `None`

The user preference (memory file `feedback_empty_states.md`) is:
"truthful labels — say 'geo-blocked', 'rate limited', 'run a scan to
populate' instead of silent 'None' / '—'."

### 4.1 Specific offenders

| # | Page | File · line | Current | Should say | Severity | Bucket |
|---|---|---|---|---|---|---|
| ES-1 | Funding Rate Monitor table | `app.py:6852` (`row[exch.upper()] = None if rd.get("error") else rate`) | Renders Pandas `None` → "None" string for every Binance/Bybit/KuCoin row from US Streamlit Cloud (geo-blocked) | Replace `None` with the literal string `"geo-blocked"` (or `"unreachable"` if `rd.get("error_kind")` distinguishes). The colour-mapper at `_color_fr` line 6879 already returns text-muted for non-numeric values, so the replacement is safe. | **High** | (e) empty-state polish |
| ES-2 | Funding Rate Monitor "Best Rate" col | `app.py:6864-6868` | Logic only emits `"—"` when `valid` is empty; doesn't surface why (could be: all 4 displayed exchanges geo-blocked + only the hidden 9-exchange queries returned). Per Image-7, the system queries 9 exchanges internally but only displays 4. | Either expand columns to all 9 OR add a "Source pool" tooltip explaining "Best Rate references the 9-exchange query universe (OKX, Binance, Bybit, KuCoin, COINEX, HTX, PHEMEX, BingX, BitMEX); displayed columns show the 4 most-quoted. " | High | (d) functional clarity |
| ES-3 | Hyperliquid funding all 0.0000% | `app.py:6973` (`d.get('funding_rate_pct', 0)`) | Default 0 → `+0.0000%` even when the parser returned None | Use `f"{rate:+.4f}%" if rate is not None else "rate-limited / unparsed"`. The Open Interest column already uses an `if/else "—"` pattern at line 6982 — apply the same shape to the funding column. | High | (d) — funding rate parser is also broken upstream per the in-progress doc |
| ES-4 | On-chain metric cards | `app.py:8714-8750` | All four cells per slot show "—" because no scan has populated `_result_for(ticker)` AND the `data_feeds.get_onchain_metrics` fallback returns `{}` when Glassnode is rate-limited. Status pills at the page header still claim "Glassnode · live" + "Native RPC · live" — the pills lie. | Two fixes, BOTH needed: (a) inspect `data_feeds.get_onchain_metrics` return + status; if rate-limited or geo-blocked, change the page-header `data_sources` arg in `app.py:8617-8621` to reflect reality (`("Glassnode", "rate-limited")` etc.); (b) replace the cell "—" with a discoverable empty-state copy: `"rate-limited — try again in N min"`, `"free-tier exhausted"`, or `"no data yet — run a scan"` depending on which path was hit. The `_v(x)` helper at line 8698 is the central place to add a "what reason should we show?" branch. | **Critical** | (d) headline bug per user note in in-progress doc Image-8 + (e) empty-state polish |
| ES-5 | Whale Activity ambiguous empty state | `app.py:8798-8805` | "No large transfers in the last 24h, or whale tracker is offline." | Resolve to one definite state. Inspect `_whale_raw` — if it's a dict with `error` / `unavailable` keys, surface those; else say "Whale tracker active — no transfers above threshold in last 24h." | Medium | (e) |
| ES-6 | Spot Arbitrage table — Buy On / Sell On / Buy Price / Sell Price | `app.py:6679-6696` (and upstream `arbitrage.py:325-336`) | When `signal == "NO_ARB"` the helper returns an `_empty` dict with `buy_exchange=None / sell_exchange=None / buy_price=None / sell_price=None`, so the display row shows `—` everywhere even though the per-exchange `prices` dict is fully populated. | Even when no profitable arb exists, populate `buy_exchange = min-by-ask`, `sell_exchange = max-by-bid` so the table reveals **where** the price differences live. The "Net Spread %" column already conveys "no profit" via the negative value + colour map. | High | (d) data-display gap |
| ES-7 | Signals page ATR shows "$0" | `app.py:7940` | `("$" + f"{float(_atr):,.0f}") if _atr is not None else "—"` — but the ATR fallback when no ohlcv data is loaded is `0.0`, not `None`, so the `is not None` check passes and it renders "$0". | Replace with: `("$" + f"{float(_atr):,.0f}") if (_atr is not None and float(_atr) > 0) else "—"`. Same pattern likely affects Beta, Funding (8h) — audit lines 7941-7942. | Low | (e) — Image 3 minor nit |
| ES-8 | Signals page Funding (8h) "0.000%" | `app.py:7942` (`_fmt_pct` returns the value or "—") | If funding fetch returns `0.0` or fallback default, the formatter at line 7928-7936 emits "0.000%" — semantically ambiguous (real zero funding vs. no data). | Tighten `_fmt_pct` to return "—" if `abs(fv) < 1e-6`. | Low | (e) |
| ES-9 | Hyperliquid DEX Mark Price / OI | `app.py:6980-6982` | Uses `if d.get("mark_price")` truthy-check — `0` and `None` collapse to "—". | Functionally OK for prices (no crypto trades at literally $0) but flag for audit completeness. | Low | (e) |
| ES-10 | Spot Arbitrage "All Prices" | `app.py:6681-6683` | When `r["prices"]` is empty (single-exchange listing), shows "—". This is the right copy here (no cross-exchange data is the genuine state). | leave | (correct) |
| ES-11 | Backtester KPI strip | `app.py:4662-4670` (`f"{float(_bt_sharpe):.2f}" if _bt_sharpe is not None else "—"`) | Bare `—` when no backtest has run. | Replace with `"no backtest yet — click Run Backtest"` or split: KPI cells show `—` (right) but a single-line empty-state banner above the strip says "No backtest results yet — click ▶ Run Backtest to populate." This pattern is already used by `recent_trades_card` (line 1685: "No trades recorded yet — run a backtest to populate.") so adopt it consistently. | Medium | (e) |
| ES-12 | Hyperliquid funding label | `app.py:6981` | Funding parser bug means even valid coins show `+0.0000%`. | Per ES-3 above plus an upstream fix to `data_feeds.get_hyperliquid_batch` parser. | High | (d) |
| ES-13 | Generic `or "—"` patterns | `app.py:5441, 5490, 5499` etc. | Many bare-`—` placeholders inside tables/metrics that belong to dataframes (rendering in `st.dataframe` cells). For dataframe-level empties, leaving "—" is fine because the whole table is muted; flag only the ones a user can act on (run a scan / load rates / etc.). | leave for now | (e) |
| ES-14 | Topbar status pill — Agent stopped | `app.py:1643` (`{"tone": "info", "icon": "○", "label": "Agent · stopped"}`) | When `agent.py` failed to import, the helper returns `[]` (empty pill row) — silent failure. | Add a 4th branch: when `_agent is None`, return `[{"tone": "warning", "icon": "⚠", "label": "Agent · unavailable (import failed)"}]`. | Low | (e) |

---

## 5. Topbar layout / wrapping at narrow viewports

Image 8 showed: "er" / "te" / "ed" / "Updat e" / "Them e" labels
clipping mid-word. Root cause is a flex/grid issue where the level
pills (which have variable-width labels — Beginner is 8 chars but
Intermediate is 12) compete with the fixed-width Update + Theme
buttons inside the same `[3, 1.4, 1.7, 1.4, 1.2, 1.2]` columns split.

### 5.1 The columns ratio

`ui/sidebar.py:295` uses `cols = _topbar_ctx.columns([3, 1.4, 1.7, 1.4,
1.2, 1.2])` — 10.9 total units. At a 1024px viewport with a 150px
sidebar that leaves 874px main column → 1 unit ≈ 80px. "Intermediate"
needs ~100px at the existing 12.5px font. The 1.7-unit cell for
Intermediate gives it 136px nominally — **but** the topbar buttons
have an internal padding of `4px 10px` (line 623) plus the column
gap, so the usable text width is closer to 110-115px. Cuts close to
the wrap point.

At narrower viewports (Image 8 looks like ~768-900px), the maths
collapse. The mobile breakpoint at `overrides.py:1134-1140` correctly
hides the level pill columns (`display: none`) on `<768px`, but the
**769-900px range** is unguarded and the breaking continues until the
breakpoint kicks in.

### 5.2 Specific issues

| # | File · line | Issue | Severity | Bucket |
|---|---|---|---|---|
| TB-1 | `ui/overrides.py:1106-1111` | The `@media (max-width: 1200px)` rule already drops font-size to 11.5px and padding to 3px 6px — reasonable. But Image 8 is at the 768-900px range where this rule applies, and even at 11.5px "Intermediate" is ~92px which is right at the limit. | High | (c) topbar overflow |
| TB-2 | `ui/overrides.py:1113-1118` | `@media (max-width: 1024px)` further drops font to 11px / padding 3px 4px — total label width ~85px for Intermediate. Still wraps in some browsers. | High | (c) |
| TB-3 | `ui/sidebar.py:295` | The columns ratio assumes a 1024px+ viewport. Should add an explicit fallback: at <1024px, drop to 4-col `[breadcrumb, refresh, theme, _padding]` and hide level pills. The mobile breakpoint already does this at <768px — extend to <1024px. | High | (c) |
| TB-4 | `ui/overrides.py:1134-1140` | Mobile breakpoint hides cols 2,3,4 (Beg/Int/Adv) — fine. Should be raised to <1024px so the 769-1023px window also collapses. | High | (c) |
| TB-5 | `ui/overrides.py:621-660` | The topbar button rule has `white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;` — correct in principle but combined with `min-width: 0 !important;` allows the pill to shrink below the label's intrinsic width. The descendant rule at line 655-660 propagates nowrap/ellipsis to the inner `<p>` — also correct. **The browser is honoring it, the column is just too narrow.** | medium | (c) |
| TB-6 | `ui/sidebar.py:399-414` | The "✓ refreshed Xs ago" caption under the Update button is only present when there's a recent refresh. When absent, the column has just the button. Fine. | low | leave |

### 5.3 Recommended fix

Two changes:

(a) `ui/overrides.py:1134-1140` — change `@media (max-width: 768px)` to
`@media (max-width: 1024px)` for the level-pill hide. This collapses
the topbar to `[breadcrumb] [refresh] [theme]` at any viewport <1024px.

(b) `ui/sidebar.py:295` — keep the 6-col `columns([3, 1.4, 1.7, 1.4,
1.2, 1.2])` for desktop ≥1024px (where it works), but introduce a
`min-width` guard via `st.session_state.get("_viewport_w")` if the
existing ResizeObserver is wired. Alternative: stop trying to fit
all 5 controls + breadcrumb on one row; lift level pills into the
sidebar permanently (they're already in the page_header `data_sources`
pill row anyway as the "View · Beginner" pill via `page_header(show_
level=True)` at `sidebar.py:466-483`).

---

## 6. Sidebar Legal item — vertical word stacking

### 6.1 Diagnosis

`app.py:2228` renders:
```python
with st.expander("📜 Legal (Internal Beta)", expanded=False):
```

inside `with st.sidebar:` (line 2223). The expander DOM has a `<summary>`
with the literal text "📜 Legal (Internal Beta)" which measures
~155px at 13px Inter — **wider** than the 150px `--rail-w`. There is
no `white-space: nowrap` rule scoped to `[data-testid="stSidebar"]
[data-testid="stExpander"] summary`, so the words wrap.

The C-fix-07 fix at `ui/overrides.py:157-171` (the Glossary popover
nowrap fix) targets `[data-testid="stSidebar"] [data-testid="stPopover"]
button` but **not** `stExpander summary`. So the Glossary popover
correctly truncates to "Glossary…" but the Legal expander still
wraps.

### 6.2 Specific issues

| # | File · line | Issue | Severity | Bucket |
|---|---|---|---|---|
| SL-1 | `ui/overrides.py` (no rule exists) | Missing sidebar-scoped expander summary nowrap rule | **High** | (a) incomplete port — same pattern as the C-fix-07 Glossary nowrap |
| SL-2 | `app.py:2228` | Label text "📜 Legal (Internal Beta)" is too long for 150px rail at any reasonable font size. Either shorten the label or use an icon-only collapsed state. | High | (b) UX choice — recommend shorten to "📜 Legal" (3 chars + emoji = ~50px, fits with breathing room) and put "(Internal Beta)" inside the expanded body as a sub-line. | (e) copy polish |

### 6.3 Recommended fix

Two-line CSS in `ui/overrides.py` after the existing sidebar popover
rule at line 175:

```css
/* Sidebar Legal/Glossary expander — same nowrap treatment as the
   popover trigger so long labels don't stack vertically inside the
   150px rail. */
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  max-width: 100% !important;
  font-size: 12.5px !important;
  padding: 6px 10px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary > * {
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
  border: none !important;
  background: transparent !important;
  margin-top: 8px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"][open] {
  background: var(--bg-2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
}
```

Plus shorten the Streamlit label in `app.py:2228` from
`"📜 Legal (Internal Beta)"` to `"📜 Legal"` and add a `caption` line
inside the expanded body: `st.caption("Internal Beta — see ToS + Privacy below.")`.

---

## 7. Other inconsistencies surfaced by the deep dive

### 7.1 Token drift — three competing `:root` blocks

| File · line | What it sets | Problem |
|---|---|---|
| `ui/design_system.py:163-189` | `--accent`, `--accent-soft`, `--bg-0..3`, `--text-primary..muted`, `--border`, `--card-radius`, etc. — the canonical token block | Owned by `inject_theme()`, called once at page top |
| `ui_components.py:68-139` | `--bg-base`, `--bg-0..3`, `--bg-glass`, `--primary`, `--primary-dim`, `--bull`, `--bear`, `--text-1..4`, `--border`, `--r-xs..xl`, `--shadow-*` — the legacy token block | Sets `--bg-0` to `#0d0e14` whereas DS sets it to `#0a0a0f`. Both load. The one defined last wins via cascade. **Result:** background color flickers depending on which CSS block paints last. |
| `.streamlit/config.toml:2-6` | `primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor` — Streamlit's native theme | Only affects Streamlit-internal widgets that read these tokens (multiselect tags, baseweb popovers, slider thumb). Set to `#00D4AA / #080B12 / #111520 / #F8FAFC` — none of these match either DS or legacy. |

| # | Severity | Bucket |
|---|---|---|
| TD-1 — `ui_components.py:71` `--bg-0: #0d0e14` collides with `design_system.py:168` `--bg-0: #0a0a0f` | High | (c) |
| TD-2 — `.streamlit/config.toml:3-6` colours don't match either | High | (c) |
| TD-3 — `ui_components.py` defines `--accent: #8b5cf6` (indigo), DS defines `--accent: #22d36f` (green). Used differently — legacy `--accent` is in shadow effects (e.g. `--accent-glow`), DS `--accent` is the main brand color. **They share a name and they don't share a value.** | **Critical** for any inline `style="color:var(--accent)"` written by legacy code | (c) |

### 7.2 Typography drift

| # | File · line | Issue | Severity |
|---|---|---|---|
| TY-1 | `ui_components.py:54` imports Inter weights `300;400;500;600;700;800` | Loads weight 800 (used by old gradient h1 at line 657-662). DS imports only `400;500;600;700` (line 162). Two duplicate font requests on cold load → ~250ms extra. | Medium |
| TY-2 | `ui_components.py:108-119` clamp-based font-sizes (`--fs-base = clamp(13px, 0.9vw, 14px)` etc.) live alongside DS's fixed 13/13.5/22px sizes | Both load. Inline-style HTML still uses `var(--fs-sm)` etc. The DS approach (fixed sizes per-component) won't match the legacy fluid approach on edge viewports. | Low — cosmetic |
| TY-3 | `ui_components.py:657-662` light-mode h1 has `linear-gradient` text fill | Light-mode page headers get a gradient that looks 2017-era. DS expects flat `--text-primary`. | Medium |

### 7.3 Tabs — dual styling

`ui/overrides.py:689-712` defines an underline-pattern tab style
(matches the Settings mockup line 44-48). `ui_components.py:244-267`
defines a pill-with-gradient-background tab style. Both load. The
legacy pill rule at line 261-267 has higher specificity (`[aria-selected
="true"]` vs the DS `button[role="tab"][aria-selected="true"]`) and
also has `!important`, so **the legacy pill wins**. Visual result: tabs
on Settings + Backtester show the gradient pill (legacy) not the clean
underline (mockup-correct).

| # | File · line | Severity | Bucket |
|---|---|---|---|
| TX-1 — delete `ui_components.py:244-271` (tabs gradient) | High | (c) |

### 7.4 Light mode breakages

The `body.light-mode` block in `ui_components.py:610-810` does extensive
light-mode mapping but **doesn't override the new `--accent: #22d36f`
token** — it only overrides legacy `--bg-*`, `--text-*`, `--border-*`.
Result: in light mode, `--accent-soft` (rgba 12% green) on a white
`--bg-1` looks fine, but pages that use raw `var(--accent)` (like the
composite-score `font-color` at `sidebar.py:1424`) render as pure
`#22d36f` against `#ffffff` — passes WCAG AA contrast at 14px+ but
reads as a "neon highlight" in an otherwise calm light-mode interface.

| # | File · line | Severity | Bucket |
|---|---|---|---|
| LM-1 — `ui_components.py:633-640` light-mode `.stApp` background overrides DS `--bg-0` directly with `#f1f5f9` and a radial gradient | Medium — radial gradient adds noise that DS light-mode doesn't have | (c) |
| LM-2 — `ui_components.py:679-689` light-mode expander has glassmorphic gradient border | Doesn't match the dark-mode flat-card look — light-mode users see decorations dark-mode users don't. | Medium |
| LM-3 — `ui_components.py:657-662` light-mode h1 gradient text-fill | Doesn't match DS `.ds-page-title` flat-color rule (which has higher specificity at line 495-505 and should win — verify in browser). | Low |
| LM-4 — `ui_components.py:768-771` light-mode alert styling uses different rgba mixes than dark | Inconsistent transparency. | Low |

### 7.5 Dark/light theme switching mechanism

`render_top_bar` accepts `on_theme=_toggle_theme` callback. The
`_toggle_theme` function (referenced but not in the snippets I read)
should swap `st.session_state["theme"]` between "dark" and "light",
then on next render `inject_theme(app, theme=...)` reinjects the
correct token block. **Confirm:** the legacy `body.light-mode` class
is added/removed independently. If both mechanisms run, order matters
— the legacy class should be the source of truth for now (since DS
light-mode token block is incomplete per LM-1..4 above).

### 7.6 Specificity audit — who's winning each fight

For the four core "active state" surfaces, here's who wins in the
cascade:

| Surface | DS rule | Legacy rule | Winner |
|---|---|---|---|
| Sidebar nav primary | `overrides.py:123-128` `--accent-soft` | none (legacy sidebar deleted) | **DS** ✓ |
| Topbar level pill | `overrides.py:645-650` `--accent-soft !important` | none (scoped via `data-stkey`) | **DS** ✓ |
| Topbar Update btn | `overrides.py:645-650` `--accent-soft !important` | `ui_components.py:178` legacy gradient `!important` | **fight** — the `[data-stkey="ds_topbar_row"]` selector has equal `!important` and is more specific than `section.main`, so DS should win — **but only if `[data-stkey="ds_topbar_row"]` actually applies** to the Update button container. **Confirmed in production via Image 8: Update button is bright green → DS rule is NOT taking effect.** Possible cause: Streamlit's `st.container(key=...)` wrapper doesn't always emit `data-stkey` when nested inside `st.columns`. | **Legacy** (per Image 8) |
| Main-area primary buttons | `overrides.py:580-583` `var(--accent)` solid | `ui_components.py:178` gradient `!important` | **Legacy** |
| Tab active | `overrides.py:708-712` underline | `ui_components.py:261-267` pill gradient `!important` | **Legacy** |
| Multiselect tag | none | none (baseweb default reading `primaryColor`) | **baseweb default** |

### 7.7 Spacing drift

| # | File · line | Issue |
|---|---|---|
| SP-1 | `ui_components.py:188-189` legacy primary button `padding: 8px 18px` | DS overrides at `overrides.py:574` use `padding: 6px 14px`. Inconsistency on legacy primaries. |
| SP-2 | `ui_components.py:404-410` legacy `[data-testid="stForm"]` rule has `padding: 18px` + `backdrop-filter: blur(12px)` | DS doesn't set form padding. Forms inside Settings (Email Alerts, API Config) get the glassmorphic backdrop blur — looks dated next to flat ds-cards. |
| SP-3 | `ui_components.py:339` legacy progress-bar shimmer | Decorative, fine to keep. |

---

## 8. Per-page redesign-port completeness

| Page | Status | What's done | What's left | % complete |
|---|---|---|---|---|
| **Home (page_dashboard)** | Mostly ported | Topbar, page_header, hero cards, watchlist, regime mini-grid, KPI strip, recent_trades_card | Hero card prices "—" for non-OKX-SWAP coins (Image 1, ~10 line fix). Overall layout matches mockup. | **90%** |
| **Signals (page_signals)** | Fully ported (the gold reference) | Topbar, page_header, pair_dropdown, multi_timeframe_strip, signal_hero_detail_card, composite_score_card, indicator_card×3, signal_history_table | ATR `$0` formatter nit (Image 3) | **98%** |
| **Regimes (page_regimes)** | Mostly ported | Topbar, page_header, pair_dropdown, regime_cards_grid, regime_state_bar, macro_regime_overlay_card, regime_weights_grid | Regime state bar rendering only short truncated "Regim" labels (Image 4) — regime_state_bar segment label uses `name.title()[:5]` at `sidebar.py:1730`, truncates to 5 chars. Increase to full word + style as needed. Bright-green pair pills (per ES below — same root cause as §1). | **80%** |
| **Backtester (page_backtest)** | Top half ported | Topbar, page_header, segmented_control (Backtest/Arbitrage), backtest_controls_row, backtest_kpi_strip, optuna_top_card, recent_trades_card | Trade History sub-tabs (Master Log, Paper Trades, Feedback, Execution, Slippage) + Advanced sub-tabs (Walk-Forward, OHLCV-Replay, Signal Calibration, IC & WFE) all bare st.* widgets | **55%** |
| **Backtester → Arbitrage** | Hybrid | Topbar/header inherited; segmented control work fine | Funding Rate Monitor + Hyperliquid DEX expanders + table styling + Buy/Sell-On data gap (§4 ES-6) | **40%** |
| **On-chain (page_onchain)** | Hybrid (thin pass acknowledged in code comments) | Topbar, page_header, ticker_pill_button×3, indicator_card×3 | Whale activity table styling (DOM open-tag bug §2 WW-5), all metric cells blank (§4 ES-4), advanced view ticker selectors look right | **45%** (functional bug dominant — cards show nothing) |
| **Alerts (page_alerts)** | Hybrid | Topbar, page_header, segmented_control (Configure/History) | Configure form bare; History view bare 4-selectbox row + bare dataframe | **45%** |
| **AI Assistant (page_agent)** | Mostly ported | Topbar, page_header, status row card, 4-card metric strip, 2-card engine row, in-progress banner | Config form bare; Active Limits expander bare; Decision log bare dataframe | **70%** |
| **Settings (page_config)** | Hybrid | Topbar, page_header, Beginner panel ds-card-styled inputs (`ds_beg_panel`), tab strip (legacy underline-pill fight) | All deeper tabs (Trading, Signal & Risk, Dev Tools, Execution) bare st.* widgets | **35%** |

**Weighted average across all pages: ~62% redesigned, ~28% hybrid, ~10% legacy.**

The "legacy look" complaint is therefore not about token drift in the
20% of cases where DS is fully applied — it's about the **38% of
surfaces where it's incomplete** (hybrid + legacy combined). Most of
those surfaces are accessible only via Settings deeper tabs and
Backtester sub-views, which is why the user has been screenshotting
exactly those.

---

## 9. Fix sprint plan — ordered list

Ordered for **maximum perceived improvement per line of code changed**.
Each item is self-contained (no inter-dependencies) so they can ship as
a single 1-day sprint or fan out across PRs.

### Sprint A — Token consolidation (the bright-green sweep)

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| A-1 | `ui_components.py` | Delete lines 178-200 (legacy primary button gradient) | All main-area primary buttons (Update, Load Rates, Save, Run, Activate) flip from gradient teal → muted accent-soft in one pass |
| A-2 | `ui_components.py` | Delete lines 204-222 (legacy secondary/ghost button) — let `ui/overrides.py:570-579` win | Secondary buttons get the DS flat-card look uniformly |
| A-3 | `ui_components.py` | Delete lines 244-271 (legacy tab pill gradient) | Settings + Backtester tabs flip to underline pattern matching mockup |
| A-4 | `ui/overrides.py` | Lines 580-583: change `var(--accent)` → `var(--accent-soft)` + `color: var(--text-primary)` + add a soft border | Topbar and main-area primaries match sidebar's active treatment |
| A-5 | `.streamlit/config.toml` | Line 3: `primaryColor = "#00D4AA"` → `"#22d36f"` (or even softer like `#16a85a`) | Multiselect tag chips, slider thumb, baseweb popover focus rings all get the muted DS color |
| A-6 | `ui/overrides.py` | After line 675, add 25-line block for `[data-testid="stMultiSelect"] [data-baseweb="tag"]` | Multiselect tag chips flip from default-baseweb-bright to muted accent-soft pills (§3.1 fix) |

**Sprint A line-count: ~70 deletions + ~30 additions = ~100 lines.**
**Visual surfaces fixed: Update button, Load Rates, Save Settings, Run
Backtest, multiselect chips, all settings tabs, all backtester
sub-tabs, slider thumbs, and all `[kind="primary"]` buttons app-wide.**

### Sprint B — Sidebar Legal + topbar wrapping

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| B-1 | `ui/overrides.py` | After line 175, add 30-line block for sidebar `stExpander summary` nowrap + ellipsis (§6.3) | "📜 Legal (Internal Beta)" stops stacking vertically |
| B-2 | `app.py:2228` | Shorten label to `"📜 Legal"`; add `st.caption("Internal Beta — ToS + Privacy below.")` inside expanded body | Even tighter fit + clearer in-context label |
| B-3 | `ui/overrides.py:1134` | Change `@media (max-width: 768px)` → `@media (max-width: 1024px)` for the level-pill column hide | Topbar collapses cleanly at 768-1023px instead of wrapping mid-word |
| B-4 | `ui/overrides.py` | Lines 1106-1118 — collapse the two media queries (1200px / 1024px) into one stronger `<1024px` rule that also caps `font-size: 11px` and uses `flex-shrink: 0` on the breadcrumb cell so it can't push the buttons | Cleaner breakpoint behavior |

**Sprint B line-count: ~50 lines changed.**

### Sprint C — Empty-state truthful copy

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| C-1 | `app.py:6852` | Funding Rate Monitor: `None` → `"geo-blocked"` for error rows | Per-cell honesty for Binance/Bybit/KuCoin from US Streamlit Cloud |
| C-2 | `app.py:6864-6868` | Funding Rate "Best Rate" column: add tooltip explaining the 9-exchange query universe | Resolves "Best Rate references exchange not in row" confusion |
| C-3 | `app.py:6973` (data_feeds.get_hyperliquid_batch upstream too) | Hyperliquid funding rate parser fix; surface `None` → `"rate-limited"` when fetch fails | Stops misleading `+0.0000%` display |
| C-4 | `app.py:8617-8621` (page_onchain `data_sources` arg) | Inspect actual Glassnode/Dune/RPC call status; pass `("Glassnode", status)` where status reflects reality (`live`/`cached`/`down`/`rate-limited`) | Status pills stop lying — Image 8 headline issue |
| C-5 | `app.py:8698-8704` (the `_v` helper in page_onchain) | Add a "reason" parameter — when input is None, show "rate-limited" / "free-tier exhausted" / "no data yet — run a scan" depending on what failed | Cards stop being silently blank |
| C-6 | `app.py:8798-8805` | Whale Activity ambiguous empty state — split into two distinct branches (offline vs zero events) | One definite state per render |
| C-7 | `arbitrage.py:325-336` + `app.py:6679-6696` | Even when `signal == "NO_ARB"`, populate `buy_exchange = min-by-ask`, `sell_exchange = max-by-bid` so the table reveals where price differences live | Image 5 fix |
| C-8 | `app.py:7940` | Tighten ATR truthy-check: `if (_atr is not None and float(_atr) > 0)` | Image 3 nit fix |
| C-9 | `app.py:7942` (`_fmt_pct` helper) | Tighten zero-handling: return "—" if `abs(fv) < 1e-6` | Funding (8h) "0.000%" → "—" when no data |
| C-10 | `app.py:1643` | Add 4th status-pill branch when `_agent is None` (import failed) | Surfaces silent agent-import failure |

**Sprint C line-count: ~80 lines changed across 5 files.**

### Sprint D — Hero card price cascade (Image 1 fix)

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| D-1 | `app.py:2369` (`_live_prices = _ws.get_all_prices()`) | After this line, layer the cascade: for any pair without a WS tick, fetch via `_sg_cached_live_prices_cascade` and merge | XDC/SHX/ZBCN heroes populate prices instead of "—" |
| D-2 | `app.py:2463-2475` (`_ds_build_hero`) | Use the merged `_live_prices` from D-1 — no helper-side change needed | Hero cards display real prices |

**Sprint D line-count: ~10 lines.**

### Sprint E — Plain-Streamlit-surface card-shells

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| E-1 | `ui/sidebar.py` (or new `ui/shells.py`) | Add `ds_section()` context manager helper (~30 lines) | Reusable shell primitive |
| E-2 | `app.py:6809` (Funding Rate Monitor expander body) | Wrap controls + table in `with ds_section(...)` | Funding Rate looks ds-card-shelled |
| E-3 | `app.py:6955` (Hyperliquid DEX expander body) | Wrap in `ds_section` | Same |
| E-4 | `app.py:7053` (Alerts History view) | Wrap filter row + table | Same |
| E-5 | `app.py:5169-5800` (Trade History sub-tabs) | Wrap each sub-tab body | Heaviest lift — ~200 lines per sub-tab section |
| E-6 | `app.py:5800-6500` (Backtester Advanced) | Same | Same |
| E-7 | `app.py:3303-4400` (Settings tabs) | Same | Same |

**Sprint E line-count: ~30 (helper) + ~50 (per quick page) × 3 quick pages
+ ~600 (heavy lifts split across sub-tabs) = ~780 lines, can split
across multiple PRs.**

### Sprint F — Token consolidation polish

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| F-1 | `ui_components.py:68-139` legacy `:root` block | Inline-comment audit each token, mark `--bg-0..3` and `--accent` as TO_BE_DELETED, migrate any remaining inline-style references in `app.py` to use DS tokens | Eliminates the dual-token-block conflict — collapses to a single source of truth |
| F-2 | `ui_components.py:54` Inter font import | Drop weights 300, 800 (only used by legacy h1 gradient at 657-662 which §1 deletes) | Saves ~250ms cold-load |
| F-3 | `ui_components.py:610-810` light-mode block | Audit each rule against DS light-mode + flag duplicates; eventually delete in favour of `inject_theme(theme="light")` | Single light-mode source of truth |

**Sprint F line-count: ~150 (audit pass + deletions) — large change, lower priority.**

### Sprint G — Regime state bar full-label fix (Image 4)

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| G-1 | `ui/sidebar.py:1730` | `label = str(name).title()[:5]` → render full state name (Bull/Bear/Trans/Accum/Dist) with overflow handling for narrow segments. If segment width < 60px, drop the label entirely (segment color carries the info) | Image 4 truncated "Regim" labels resolve |

**Sprint G line-count: ~5 lines.**

### Sprint H — Streamlit theme + DS reconcile (longer term)

| # | File | Lines touched | Expected impact |
|---|---|---|---|
| H-1 | `.streamlit/config.toml` | Align all four colors (primaryColor, backgroundColor, secondaryBackgroundColor, textColor) with DS sibling-dark scale | Streamlit-internal widgets stop drifting from DS |
| H-2 | New file `tests/test_token_consistency.py` | Add a test that scrapes `ui/design_system.py`, `ui_components.py`, `.streamlit/config.toml` and asserts the seven core tokens (`--accent`, `--bg-0`, `--bg-1`, `--text-primary`, `--text-secondary`, `--border`, `--card-radius`) are defined exactly once or have a documented duplicate-with-explanation | Prevents future drift |

**Sprint H line-count: ~80 lines.**

---

## 10. Bucket-coded summary table

Every issue across §1-9, with bucket per the legacy-look-audit-in-
progress doc taxonomy:

| Bucket | Count | Notes |
|---|---|---|
| (a) incomplete port | 4 | EX-2 (sidebar Legal expander), TB-1..4 (topbar narrow viewport), SL-1 (sidebar expander nowrap), G-1 (regime bar truncation) |
| (b) no mockup yet | 11 | WW-1..4, WW-6..11 (all the bare-Streamlit-surface pages), SL-2 (Legal label copy choice) |
| (c) hybrid / inconsistent token | 22 | All §1 BG-1..9, MS-1..3, SB-1..2, EX-1, EX-3, TD-1..3, TY-1..3, TX-1, LM-1..4, SP-1..3 |
| (d) functional / data bug | 6 | ES-2, ES-3, ES-4, ES-6, ES-12, WW-5 |
| (e) empty-state polish | 11 | ES-1, ES-5, ES-7..11, ES-13..14, plus C-2 / C-3 (overlap with d) |

**Total line-items: 54** (count of named issues). Most cluster around
buckets (b) and (c) — i.e. the surface area is large, but the *kinds*
of fix are repeated and small.

---

## 11. Concrete priority recommendation

If only one sprint can be shipped this week, ship **Sprint A**
(70 deletions + 30 additions). It single-handedly resolves bright-green
saturation across every primary CTA and tab on every page, which is the
recurring complaint in 4 of 8 user screenshots.

If two sprints — Sprint A + Sprint B (Legal nowrap + topbar
breakpoint). These two together fix every screenshot from Images 4,
6, 7, 8 except the on-chain functional bug in Image 8 (which needs
Sprint C-5).

If three — A + B + C. Sprint C is honesty-first: it removes every
dishonest "live" pill + every silent "—" / "None" cell where the user
can take an action.

Sprints D, E, F, G, H are quality-of-life rather than headline issues.
D is small enough (10 lines) that it can ride along with any other
sprint.

---

## 12. Resume protocol

To resume this audit:
1. Read this doc + `2026-05-02_legacy-look-audit-in-progress.md`.
2. Pick a sprint letter (A → H).
3. Each sprint is self-contained — no cross-sprint dependencies.
4. After Sprint A, re-run the screenshot review (Images 4, 6, 7, 8)
   to confirm the bright-green saturation is gone before moving to B.

---

## Appendix A — Token cross-reference

Every place `--accent` appears (verified `var(--accent)`, not the
legacy `--accent: #8b5cf6` indigo):

- `ui/design_system.py:165, 183, 322, 327-329, 335` — token defs +
  compliance callout helper (correct usage: thin strokes / 5% mix
  background)
- `ui/overrides.py:581-582` — main-area primary button (WRONG — should
  be `--accent-soft`)
- `ui/overrides.py:710` — tab-active underline (correct — thin stroke)
- `ui/overrides.py:736-737` — beg-panel input focus (correct — 1px
  ring is a thin stroke usage)
- `ui/overrides.py:787` — `.ds-regime .dot` (correct — small dot, not
  a CTA surface)
- `ui/overrides.py:882` — `.ds-bar-fill` composite-score progress fill
  (correct — graphical chart, not a CTA)
- `ui/overrides.py:946` — `.ds-bt-runbtn` decorative-only (left over
  from C2 fix; harmless because rendered hidden by default)
- `ui/overrides.py:984` — `.ds-bt-opt-row .sh` Sharpe column color
  (correct — emphasis color, not a CTA)
- `ui/sidebar.py:1424` — composite score number color (correct —
  emphasis text, not a CTA)
- `ui/sidebar.py:1575, 1788` — backtester KPI value tone, macro overlay
  overall label (correct — emphasis color)

Bottom line: of the 11 `var(--accent)` usages in our DS files, only
**one** (overrides.py:581) is the wrong CTA-fill use. That's the entire
Sprint-A-4 fix in one selector.

---

## Appendix B — Files NOT inspected (out of scope or low-impact)

- `ui/__init__.py` (re-exports only, no styling)
- `ui/plotly_template.py` (Plotly chart styling — separate concern)
- All `tests/test_*.py` files (regression tests, not styling)
- `data_feeds.py` upstream parsers (referenced for ES-3 / ES-4 fixes
  but the rendering bug lives in `app.py`, not the parser)

---

*End of audit. — 2026-05-02.*
