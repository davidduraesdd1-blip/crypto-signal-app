# Legacy-Look Audit — IN PROGRESS

**Started:** 2026-05-02 (session immediately after the state-persistence-audit
+ df-trades hotfix shipped — see git tag `df-trades-hotfix-shipped-2026-05-02`)

**Workflow:** user is sending screenshots one at a time of pages/tabs that
"still look like the old version." For each, classify into a bucket and log
the specific issue. After all screenshots are in, propose a fix sprint
grouped by bucket.

---

## Bucket definitions

- **(a)** Mockup exists in `docs/mockups/sibling-family-crypto-signal-*.html`
        but the redesign port is incomplete. Need to finish the port.
- **(b)** No mockup exists for this page/section. Need to either accept
        legacy look, design a mockup first, or apply the design-system
        shell (cards, fonts, spacing) without a pixel-perfect spec.
- **(c)** Hybrid — partial port, design-system tokens applied
        inconsistently.
- **(d)** Functional bug, not a redesign gap. Data not flowing, fields
        empty when they should populate, etc.
- **(e)** Minor data-population items that resolve themselves once a
        scan completes (placeholder "—" until first scan run).

---

## Screenshot inventory (in order received)

### Image 1 — Home / Market home
- **Issue:** Hero cards (XDC, SHX, ZBCN selected) show "—" for price + no
  24h change.
- **Root cause:** Same as the original C-fix-19 watchlist issue — pairs
  without OKX SWAP markets have no WebSocket tick. The hero-card price
  lookup uses a separate code path that wasn't wired to the
  `_sg_cached_live_prices_cascade` (CMC → CG → Kraken → OKX → MEXC).
- **Bucket:** (d) functional bug
- **Fix scope:** ~10-line change in `page_dashboard` to route hero-card
  price source through the cascade fallback.

### Image 2 — Signals (XRP detail, top section)
- **Status:** ✅ No issues. Gold standard for a fully-redesigned page.
- 9-cell timeframe strip working (1m–1M, 1d active, 4 short tfs greyed-out).
- Hero card with 24h / 30d / 1Y deltas all populated.
- Composite score panel (59.9) + layer breakdown.
- "Insufficient indicator data — run a scan to populate" is correct
  empty-state copy.

### Image 3 — Signals (XRP detail, lower section)
- **Status:** ✅ Redesigned correctly, no layout issues.
- VOL $103,485 (cascade fallback ✓), ATR placeholder, FUNDING +0.003%,
  RSI 47.9, ADX 13.6 "no trend", Supertrend "Downtrend", Fear & Greed 39.
- "—" placeholders for MVRV-Z / SOPR / Exch. Reserve / Active Addr /
  Google Trends / News Sent. / MACD Hist / Beta — expected empty states
  until first scan completes.
- **Minor nit:** ATR shows "$0" instead of "—" — formatter inconsistency.
- **Bucket:** none structural; minor (e)

### Image 4 — Regimes
- **Issue 1:** "BTC REGIME STATE · LAST 90D" timeline bar shows two
  greyed-out bands labeled "Regim" (truncated text). Should display
  color-coded bands per regime state (green=trending, orange=ranging,
  red=crisis, neutral=normal) with full labels and time-axis markers.
- **Issue 2:** Bright green saturation on active pair pills (BTC/USDT)
  reads as outdated vs sidebar's accent-soft active state.
- **Bucket:** Mix of (a) and (c). Regime timeline is a partial port;
  bright-green pills is an inconsistent token application.

### Image 5 — Backtester → Arbitrage → Spot Price Spread
- **Issue:** Buy On / Sell On / Buy Price / Sell Price columns all "—"
  for every row even though "All Prices" column has real per-exchange
  data. Currently only populate when `Signal != NO_ARB`. User
  expectation: even when no arb exists, show min-price exchange in
  Buy On + max-price exchange in Sell On so the table reveals where
  price differences live.
- **Bucket:** (d) data-display gap. ~10-15 line fix in arb opportunity
  builder.

### Image 6 — Backtester → Arbitrage → Funding Rate Monitor + Hyperliquid DEX (collapsed)
- **Issues:**
  1. Bright green saturation on Load Rates button + multiselect tag pills
     (Streamlit default chips).
  2. Duplicated description text (section subtitle + info card below
     repeat the same content with slightly different wording).
  3. Plain Streamlit expander styling — chevron + rounded box, no
     `ds-card` shell.
  4. Multiselect dropdown uses Streamlit default tag rendering.
- **Bucket:** Mix of (b) no mockup + (c) hybrid.

### Image 7 — Backtester → Arbitrage → Funding Rate Monitor (after Load Rates) + Hyperliquid DEX (loaded)
- **Functional issues:**
  1. Binance / Bybit / KuCoin columns all "None" for every pair
     (geo-blocked from US Streamlit Cloud — known per CLAUDE.md §10).
     Should show "geo-blocked" or "unreachable" instead of misleading
     "None".
  2. "Best Rate" column references exchanges (COINEX, HTX, PHEMEX) NOT
     shown in the row's columns. System queries 9 exchanges internally
     but only displays 4. Either expand columns or add tooltip
     explaining the broader source universe.
  3. Hyperliquid funding all shows +0.0000% while OI values look real.
     Funding-rate parser may be broken / not parsing the response.
- **Cosmetic:** same bright-green button + plain Streamlit table
  rendering.
- **Bucket:** Mix of (d) functional + (b) no mockup styling.

---

## Cross-cutting themes

Already surfaced from images 1-7:

1. **Bright-green saturation problem** (recurring in 4+ screenshots) —
   `--accent` (#00d4aa) is being used directly on active states and CTAs
   where the sidebar's `--accent-soft` muted treatment is the modern
   standard. Buttons with `kind="primary"` and Streamlit multiselect
   default tags are the main offenders. Single CSS pass can fix all
   instances.

2. **Plain Streamlit widgets without `ds-card` wrap** — appears on every
   "deeper" page that didn't have a mockup. Funding Rate Monitor,
   Hyperliquid DEX, deep arbitrage controls. Need a design-system
   "any-content shell" pattern.

3. **Multiselect tag styling** — Streamlit's default tag chips (bright
   green pills with × buttons) look heavy. Need a CSS pass to muted +
   smaller padding.

4. **Empty-state messaging** — "None", "—", and silent failures all over.
   Should be replaced with truthful labels: "geo-blocked",
   "rate-limited", "no data yet — run a scan", etc.

---

## Pending screenshots

User indicated they have more pages to capture. Still expecting screens of
(potentially):
- Backtester → Trade History sub-tabs (Master Log, Paper Trades, Feedback,
  Execution, Slippage)
- Backtester → Advanced (Walk-Forward, Deep OHLCV-Replay, Signal
  Calibration, IC & WFE Metrics)
- On-chain page deeper sections
- Settings → Trading / Signal & Risk inner content
- Settings → Dev Tools inner sections (Build Info, Wallet Import,
  Circuit Breakers, etc.)
- AI Assistant page (Agent UI)
- Alerts page (Configure / History views)

---

## Resume protocol

To resume in a new session:

1. New session reads `MEMORY.md` automatically (it's small).
2. The `MEMORY.md` index points at this file.
3. User says: "Read `docs/audits/2026-05-02_legacy-look-audit-in-progress.md`
   and resume the legacy-look audit. I'll continue sending screenshots
   one at a time."
4. Claude reads this file, picks up the inventory, continues numbering
   from Image 8.

---

## Open user preferences (durable, also stored in `feedback_*.md` memory)

- **Bright green active states look outdated.** Prefer `--accent-soft`
  muted teal background + `--text-primary` text — same treatment as
  the sidebar's active nav item. Apply to: topbar Update button,
  active pair pills, active level pills, multiselect tag chips,
  any other `kind="primary"` Streamlit button surfaced in the rail.
- **Empty-state messages should be truthful** — say "geo-blocked",
  "rate-limited", "no data yet — run a scan" instead of misleading
  "None" / silent dashes when the user can take an action to resolve.
