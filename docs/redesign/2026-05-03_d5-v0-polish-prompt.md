# D5 v0 Polish Prompt — paste-ready

**When to use:** paste the prompt block below into the warm v0 chat
named **"Crypto Signal App"** (the same chat that produced the 13
accepted mockups across the 8 routes). The chat retains all design
tokens + component history, so v0 will diff against the existing
canvas rather than regenerating from scratch.

**After v0 accepts the polish:** click v0's GitHub panel → **Push to
GitHub** → target branch `phase-d/next-fastapi-cutover` → root path
`web/`. That export creates `web/` and unblocks D4 (wire to FastAPI).

**Why this prompt is small:** it's polish, not rework. Two well-scoped
changes. Don't add anything else here — broader redesigns belong in a
new v0 conversation.

---

## Paste this into v0

```
Polish pass on the 13 accepted mockups across the 8 routes (Home,
Signals, Regimes, On-Chain, Backtester+Arb, Alerts+History, AI
Assistant, Settings + 3 sub-pages). Two changes only — both
cosmetic / textual. Keep every component, layout, route, and
data shape exactly as accepted.

──────────────────────────────────────────────────────────────────
CHANGE 1 — Active-state color: `--accent` → `--accent-soft`
──────────────────────────────────────────────────────────────────

Reason: the bright #00d4aa accent is too saturated for active
states that the eye lands on every visit. Reserve full `--accent`
for emphasis (signal direction badges, primary CTAs, alert pills);
use a softened tint for states that say "you are here" without
shouting.

Define the soft tint in `web/styles/tokens.css`:

  --accent-soft: rgba(0, 212, 170, 0.18);   /* dark mode */

Light mode equivalent (already in the design system):

  --accent-soft-light: rgba(0, 168, 132, 0.12);

Apply `--accent-soft` (replacing `--accent`) on the following
active states only:

  1. Sidebar nav rail — the highlighted current-page item.
     Background goes from solid teal to the soft tint; the left
     accent stripe stays full `--accent`.

  2. User-level pills (Beginner / Intermediate / Advanced) in
     every page header — the selected pill.

  3. Timeframe selector (5m / 15m / 1h / 4h / 1d / 1w) on the
     Signals page — the selected button.

  4. Pagination controls — the current-page button.

  5. Tab bars on Settings sub-pages — the active tab.

Do NOT change:

  - Direction badges (BUY / SELL / STRONG BUY / STRONG SELL): keep
    full `--accent` / `--success` / `--danger` for fast scanning.
  - Primary CTAs ("Run Scan", "Save Settings"): keep full `--accent`.
  - Alert toast pills: keep full `--accent`.
  - Loading spinners + progress bars: keep full `--accent`.
  - Hover states: keep the existing `:hover` treatment (slightly
    lighter than rest), unrelated to this change.

Color-blind safety check: every active-state UI element above
already pairs an icon or shape with the color, so dropping
saturation does not regress accessibility.

──────────────────────────────────────────────────────────────────
CHANGE 2 — Secrets architecture: `.streamlit/secrets.toml` →
            Render env vars + `.env.local`
──────────────────────────────────────────────────────────────────

Reason: the Streamlit-era pattern of `.streamlit/secrets.toml`
goes away with Phase D. The Next.js + FastAPI architecture uses
two secret homes:

  - Production: Render dashboard env vars (FastAPI side) + Vercel
    dashboard env vars (Next.js side). Both are set out-of-band
    via the platform UI, never committed.
  - Local dev: `.env.local` at the Next.js project root. Listed
    in `.gitignore`. Mirrors the production env-var names so code
    paths are identical across environments.

Update the **Settings → Dev Tools** page text (and any docs/help
strings on the same page) to reflect this:

  Replace:
    "Secrets are read from .streamlit/secrets.toml at app start."

  With:
    "Secrets are environment-only. Production secrets live in
    Render (FastAPI) and Vercel (Next.js) dashboards. Local dev
    uses .env.local at the Next.js root (gitignored). The legacy
    .streamlit/secrets.toml path is no longer read."

Update any tooltip / help icon copy that references
`.streamlit/secrets.toml` similarly. The list of env-var names
stays exactly as is (CRYPTO_SIGNAL_API_KEY, OKX_API_KEY,
OKX_API_SECRET, OKX_PASSPHRASE, ANTHROPIC_API_KEY,
CRYPTOPANIC_API_KEY, etc.) — only the **storage location**
description changes.

If the Dev Tools page has a code snippet showing the old TOML
format, replace it with the .env.local equivalent:

  # .env.local (Next.js root — gitignored)
  NEXT_PUBLIC_API_BASE=http://localhost:8000
  CRYPTO_SIGNAL_API_KEY=<paste-from-render-dashboard>

──────────────────────────────────────────────────────────────────
WHAT NOT TO TOUCH
──────────────────────────────────────────────────────────────────

  - All 13 component shapes — no new fields, no removed fields.
  - The 8 routes + their data hooks — same shape as the accepted
    mockups.
  - Mockup-locked labels in any cards (e.g. the 7 circuit-breaker
    gate labels on Settings · Dev Tools, the 5 KPI strip labels on
    Settings · Dev Tools database card).
  - Page headers, sidebar shape, topbar — same as accepted.
  - Color tokens other than `--accent-soft` — no new tokens.

When done, regenerate the 13 components and confirm:
  ✓ npm run dev still renders all 8 pages
  ✓ Visual diff vs the accepted-mockup baseline shows only the
    five active-state recolorings + the Dev Tools text update
  ✓ No new lint warnings

Then push to GitHub via the v0 panel:
  - Branch: phase-d/next-fastapi-cutover
  - Root path: web/
  - Commit message: "polish: --accent-soft on active states + .env.local secrets copy"
```

---

## After v0 push lands

The export creates `web/` on `phase-d/next-fastapi-cutover`. Once
that lands, ping me and I'll execute the D4 wire-up (which is
already specced in `claude/awesome-moore-2850b6`'s
`docs/redesign/2026-05-02_phase-d-d4-code-wire-plan.md`):

  - Cherry-pick or merge the D4 plan doc into `phase-d/next-fastapi-cutover`
  - `web/lib/api.ts` — typed client functions, one per FastAPI endpoint
  - `web/lib/api-types.ts` — manual TS types + contract test against `/openapi.json`
  - 12 TanStack Query v5 hooks per the plan (Home, Signals, Regimes,
    On-Chain, Backtester+Arb, Alerts+History, AI Assistant, Settings)
  - Replace v0's mock-data calls with live API hooks
  - `staleTime` per CLAUDE.md §12 cache windows

Then D5 (Vercel deploy) + D7 (parity check) + D8 (cutover).

## Memory hooks

- `feedback_design_accent.md` — "prefer `--accent-soft` for active
  button/pill states; reserve full `--accent` for rare emphasis."
- `phase_d_render_auth_hardening_2026_05_03.md` — Render env-var
  secret strategy is verified live; this polish aligns the mockup
  copy with that architecture.
