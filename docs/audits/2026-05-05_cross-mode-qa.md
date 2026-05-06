# Tier 6 — Cross-Mode QA
**Date:** 2026-05-05
**Scope:** `web/app/` (16 routes) + `web/components/` (~45 custom components, ~50 shadcn primitives) — code-level audit, no browser interaction
**Methodology:** static read-through using Grep/Read across the Next.js 16 / React 19 frontend. Verified against CLAUDE.md master §7 (user tiers), §8 (design + a11y), §10 (markets), and the current globals.css design tokens. shadcn-ui primitives in `web/components/ui/*` are excluded from the design-token / touch-target audits unless explicitly noted (they ship with their own a11y baseline).

---

## Summary

- **Pages audited:** 16 (15 routes — see "User-level system audit" §A — plus the 4 settings sub-pages share `app/settings/layout.tsx`; route count 17 if `settings/page.tsx` redirect is counted, 16 if not. Master nav lists 8 top-level routes.)
- **User-level violations:** **15 of 15 user-facing pages.** Tier system is **completely non-functional** — `level` is local React state inside `<Topbar>`, persisted to `localStorage`, never exposed via context or hook. No page reads it, no page conditionally renders. Master agreement §7 ("Applies identically and fully across all 3 apps without exception") is currently aspirational only.
- **Theme token violations:** 2 hardcoded hex literals where a token was available (`watchlist.tsx:66` sparkline stroke, `alerts/page.tsx:192` slider thumb halo). 3 inline-style files use `var(--foo, #fallback)` patterns where the fallback is a *legacy* color (`#00d4aa` from the old teal accent, not the current `#22d36f` brand green). `global-error.tsx` is intentionally token-free per its own comment — acceptable.
- **Touch target violations:** 11 interactive elements below 44×44px on mobile, plus several toggle "switches" rendered as `h-6 w-11` (24px tall — the entire toggle hit area). One `<div onClick=>` that should be a `<button>`.
- **Color-only encoding violations:** 2. `decisions-table.tsx` uses 🟢🔴⚪ emoji circles (color-only); `funding-carry-table.tsx` and several percentage cells (`watchlist.tsx`, `signal-hero.tsx`, `trades-table.tsx` returns column) signal direction by red/green only.
- **A11y gaps:** 1 critical (no skip-to-content link anywhere), 1 high (`alert-type-card.tsx` is `<div onClick=>`), 1 medium (no global focus-visible rings on custom buttons in app/* — shadcn primitives are fine), several inline buttons without `aria-label`.

Overall, the visual + theme system is in good shape after the 05-03 / 05-04 a11y waves; the **gating issue is that the user-tier system was scaffolded but never wired to any page**. That is the single largest deviation from CLAUDE.md §7 across the 3-app portfolio.

---

## A. User-level system audit

CLAUDE.md §7 requires three tiers (Beginner / Intermediate / Advanced), with content density, tooltip behavior, signal explanations, and chart complexity all scaling with the selected level. Storage must persist across pages, and the level selector must be accessible in every sidebar.

### Storage / state plumbing

| Location | What it does | Status |
|---|---|---|
| `web/components/topbar.tsx:15-56` | Reads/writes `crypto-signal-app:user-level` to localStorage; default = Intermediate | OK — persists across reloads |
| `web/components/topbar.tsx:113-134` | Renders the radiogroup with 3 buttons | OK — visible on every page (via AppShell) |
| `web/providers/app-providers.tsx:11` | Code comment: `// Future additions (post-D4a): <UserLevelProvider>` | **Open TODO** — never landed |

**Critical finding:** `level` is a `useState` local to `<Topbar>`. There is **no `UserLevelProvider`, no `useUserLevel()` hook, no React context, no Zustand store**. The radiogroup writes to localStorage on click, but no page reads it. The Topbar instance also re-mounts on every page navigation (it's inside AppShell), so the in-memory state is fresh every time — only localStorage saves the value across navs.

### Per-page audit

| Page | Reads `level`? | Conditional render? | Selector visible (via Topbar)? | Honors §7? |
|---|---|---|---|---|
| `app/page.tsx` (Home) | No | No | Yes | **No** |
| `app/signals/page.tsx` | No | No | Yes | **No** |
| `app/regimes/page.tsx` | No | No | Yes | **No** |
| `app/on-chain/page.tsx` | No | No | Yes | **No** |
| `app/alerts/page.tsx` | No | No | Yes | **No** |
| `app/alerts/history/page.tsx` | No | No | Yes | **No** |
| `app/backtester/page.tsx` | No | No | Yes | **No** |
| `app/backtester/arbitrage/page.tsx` | No | No (but **mocked** "Beginner view · same data, plain English" is *always shown* with hardcoded copy "shown when level = Beginner" — line 152) | Yes | **No — and the page actively misleads** |
| `app/ai-assistant/page.tsx` | No | No | Yes | **No** |
| `app/settings/page.tsx` | (redirect-only) | n/a | n/a | n/a |
| `app/settings/layout.tsx` | No | line 18 mentions `"Title shows 'Config Editor' at Advanced level."` (subtitle copy only — never executed) | Yes | **No** |
| `app/settings/trading/page.tsx` | No | No | Yes | **No** |
| `app/settings/signal-risk/page.tsx` | No | No | Yes | **No** |
| `app/settings/dev-tools/page.tsx` | No | No | Yes | **No** |
| `app/settings/execution/page.tsx` | No | No | Yes | **No** |
| `app/error.tsx` / `app/not-found.tsx` / `app/global-error.tsx` | No (and shouldn't — error fallbacks should be tier-agnostic) | n/a | Error pages have no AppShell → no Topbar → **no selector** | n/a (acceptable) |

**Net: 15 of 15 user-facing pages do not honor the tier system.** The radiogroup is decorative.

### What CLAUDE.md §7 requires the pages to do, that they don't

- Beginner: tooltips always visible, color-coded gauges, "What does this mean for me?" summary after every signal/score, simplest error messages.
- Intermediate: condensed plain-English signal interpretations, tooltips on demand.
- Advanced: full raw indicator values, no hand-holding, max data density.

Every page currently renders **one density** — closest to the Intermediate tier. Examples of content that should branch but doesn't:
- `signal-hero.tsx` shows "▲ Buy · Strong · 4h" — should show "▲ Strong upward momentum, suggest buy" at Beginner; full RSI/MACD/ADX layer scores at Advanced.
- `composite-score.tsx` shows raw 0–100 layer scores — at Beginner this should be color gauges + plain-English ("Technical: very strong"); at Advanced this should expose the regime-adjusted weights inline.
- `app/settings/signal-risk/page.tsx` has the same fields for all tiers — Beginner should see preset bundles ("Conservative / Balanced / Aggressive"); Advanced should see Optuna-tuned values.
- `app/backtester/arbitrage/page.tsx:147-174` literally hardcodes a "Beginner view" preview block that is **shown to all tiers**. Misleading.

---

## B. Theme token audit

### Token system (globals.css)

`app/globals.css` defines a clean two-mode token system:
- Brand: `--accent: #22d36f` (signal-green), `--accent-soft: rgba(34,211,111,0.12)`, `--accent-ink: #0a0a0f`
- Gray ladder: `--gray-0` through `--gray-9`
- Semantic: `--success #22c55e`, `--danger #ef4444`, `--warning #f59e0b`, `--info #3b82f6`
- Regime: `--teal #14b8a6`, `--orange #f97316`
- Mode-aware tokens: `--bg-0/1/2/3`, `--text-primary/secondary/muted`, `--border`, `--border-strong`
- Tailwind exposure via `@theme inline` in lines 118-176 — `bg-bg-0`, `text-text-muted`, `bg-accent-brand`, `bg-accent-soft`, `text-success`, etc. all available as utilities.

The system is well-designed. The audit below catches places that bypass it.

### Hardcoded hex literals outside `globals.css`

| File:Line | Color | Where it's used | Suggested token | Severity |
|---|---|---|---|---|
| `components/watchlist.tsx:66` | `#22c55e` / `#ef4444` | SVG sparkline `stroke` attribute (cannot use Tailwind classes on SVG attrs directly) | `var(--success)` / `var(--danger)` via inline style | **Medium** — works but bypasses dark/light awareness; SVG strokes look fine in both modes only because both modes share the same semantic colors |
| `app/settings/execution/page.tsx:54` | `var(--accent-brand, #00d4aa)` and `var(--bg-2, #1a1a22)` (×2 each) | Range input `<input>` style background gradient | Drop the `#00d4aa` fallback (it's the **legacy** teal accent, not the current `#22d36f` green); fallback should be the brand green or omit | **Low** — fallback only fires if the CSS variable is missing, which never happens in practice |
| `app/settings/signal-risk/page.tsx:64` | same pattern as above | same | same | **Low** |
| `components/agent-config-card.tsx:57` | `var(--accent-brand, #22d36f)` and `var(--bg-2, #1a1a22)` | same — but **with the correct brand green** | OK — matches the live token | **None** (consistent) |
| `app/alerts/page.tsx:192` | `rgba(34,211,111,0.2)` | Slider thumb `box-shadow` halo (3px ring) | Could be `var(--accent-soft)` (which is `rgba(34,211,111,0.12)` — close enough, slightly less opaque) or stay literal | **Medium** — copy of the brand color in raw rgba; if accent ever changes, this won't update |
| `app/global-error.tsx:35,36,61,77,88,105,106` | `#0a0a0f, #e8e8f0, #ef4444, #8a8a9d, #5d5d6e, #22d36f` | Inline styles on the global error fallback | **Acceptable** per the file's own comment (lines 11-13): "Keep it dependency-free… inline styles so it works even if the global stylesheet failed to load." | **None (justified)** |
| `app/layout.tsx:43` | `'#0a0a0f'` | `viewport.themeColor` | `var(--bg-0)` would not work here (themeColor is metadata, evaluated at build-time, can't be a CSS var). **Acceptable.** | **None (justified)** |

### Hardcoded Tailwind color classes (non-token)

| File:Line | Class | Suggested fix | Severity |
|---|---|---|---|
| `components/agent-config-card.tsx:119` | `bg-white` (toggle thumb) | OK — `bg-white` is intentional on a colored switch in both themes (the dot stays white-on-color) | **None** |
| `components/toggle-switch.tsx:42` | `bg-white` (same pattern) | OK | **None** |
| `app/settings/execution/page.tsx:148,186` | `bg-white` (toggle thumbs) | OK | **None** |
| `app/settings/trading/page.tsx:397` | `bg-white` (toggle thumb) | OK | **None** |
| `components/ui/toast.tsx:80` | `text-red-300`, `hover:text-red-50`, `focus:ring-red-400`, `focus:ring-offset-red-600` | shadcn defaults; should use `text-destructive` + design tokens | **Low** — shadcn primitive, off the critical path |
| `components/ui/badge.tsx:17`, `components/ui/button.tsx:14`, `components/ui/dialog.tsx:41`, `components/ui/sheet.tsx:39`, `components/ui/drawer.tsx:40`, `components/ui/alert-dialog.tsx:39` | `bg-black/50` (overlay scrims), `text-white` (destructive variant) | shadcn defaults; `bg-black/50` is a standard semi-transparent scrim and is fine in both themes; `text-white` on a destructive red button is OK contrast | **None** |
| `components/ui/slider.tsx:52` | `bg-white` (slider handle) | shadcn default; OK | **None** |

### Tailwind class typos that break in *some* files

The five files below contain comments referencing class names that **don't exist** in the theme; the comments are stale post-fix audit notes — flagged here so a future dev doesn't revert. They're already correctly using the live tokens:
- `components/macro-overlay.tsx:20-23` — refs `bg-semantic-*` (gone)
- `components/macro-overlay.tsx:54-58` — refs `text-semantic-*` (gone)
- `components/equity-curve.tsx:57-60` — refs `border-gray-6` (gone)
- `components/funding-carry-table.tsx:17-22` — refs old startsWith logic (fixed)

### `next-themes` provider verification

- `app/layout.tsx:53-62` mounts `<AppProviders>` which mounts `<ThemeProvider>` (line 22-26) with `attribute="class"`, `defaultTheme="dark"`, `enableSystem={false}`, `disableTransitionOnChange`.
- `<html className={...} suppressHydrationWarning>` — correct, prevents hydration warnings from theme-class flicker.
- `web/components/theme-provider.tsx` is a thin wrapper over `next-themes`.
- `topbar.tsx:64-65` uses `useTheme()` — wired.
- `globals.css:101-116` defines `.light { … }` overrides on a documented WCAG AA-passing palette (`text-muted: #65676f` gives 5.0:1 on white per the inline comment).

**`next-themes` setup is correct.**

---

## C. Touch target audit

§8 mandates every interactive element ≥44×44px on mobile. Tailwind `h-11` and `min-h-[44px]` both satisfy.

### Pass — components with explicit ≥44px

`signal-card.tsx:51`, `topbar.tsx:126,141,161` (radiogroup level pills + refresh + theme), `coin-picker.tsx:21,36` (with `md:min-h-0` reduce on desktop, OK), `timeframe-strip.tsx:37`, `segmented-control.tsx:44` (with sm-variant 36 — see below), `regime-card.tsx:78`, `control-button.tsx:22`, `agent-config-card.tsx:85,197`, `agent-status-card.tsx:50,63`, `emergency-stop-card.tsx:22`, `onchain-card.tsx:36`, `sidebar.tsx:42,82` (mobile nav), `app/error.tsx:57,63`, `app/not-found.tsx:20`, `app/backtester/page.tsx:162`, `app/backtester/arbitrage/page.tsx:113`, `app/settings/trading/page.tsx:235,280,349,358`, `app/settings/execution/page.tsx:237,248,259,276,291,309,388,397,423`, `app/settings/dev-tools/page.tsx:334,346,357,361`, `app/global-error.tsx:101`.

### Fail — under 44px

| File:Line | Element | Current size | Severity |
|---|---|---|---|
| `components/watchlist.tsx:28-33` | "Customize ▾" header button | `min-h-[32px]` | **Medium** — easy to miss-tap on mobile |
| `components/channel-row.tsx:43-50` | "Edit" / "Connect" channel button | `<Button size="sm">` + `h-8 px-2.5` (32px) | **Medium** — primary action on alert config row |
| `app/ai-assistant/page.tsx:336-343` | "Ask Claude" submit button | `min-h-[40px]` | **Low** (close to 44 — only 4px shy) |
| `app/ai-assistant/page.tsx:282-288, 294-306, 312-320, 327-334` | Pair / Signal / Confidence / Question form inputs | `min-h-[36px]` | **Medium** — form inputs on mobile |
| `app/settings/trading/page.tsx:199-205` | "×" (remove pair) chip button | no min-h, just text — visually <16px | **High** — tap-target unusable on mobile, despite having `aria-label` |
| `app/settings/trading/page.tsx:208-219` | "+ Add pair" button | no min-h, paddings only (~28px) | **High** |
| `app/settings/trading/page.tsx:254-266` | Timeframe toggle pills (1m, 5m, etc.) | `min-h-[36px]` | **Medium** |
| `components/decisions-table.tsx:41,47,53` | Filter dropdowns (`<select>`) | `min-h-[36px]` | **Medium** |
| `app/alerts/history/page.tsx:159,164,169,174,179` | Range/Type/Status/Channel/Export buttons | `h-9` (36px) | **Medium** |
| `app/alerts/history/page.tsx:213-217, 220-231, 232-240` | Pagination buttons | `h-7` (28px) | **High** — primary navigation |
| `app/alerts/page.tsx:202-205` | "Save Config" / "Send Test Email" | `h-9` (36px) | **Medium** |
| `app/alerts/page.tsx:143,157,168` | Recipient / Sender / SMTP password inputs | `h-9` (36px) | **Medium** |
| `app/settings/dev-tools/page.tsx:210` | "Reload diagnostic" sub-card buttons | `px-3 py-1.5` (~28px) | **Medium** |
| `app/settings/execution/page.tsx:138-152` | LIVE TRADING toggle button | `h-6 w-11` (24px tall) | **High** — destructive switch with sub-44 hit area |
| `app/settings/execution/page.tsx:177-191` | "Enable auto-execute" toggle | `h-6 w-11` (24px tall), **and missing `aria-label`** | **High** |
| `app/settings/trading/page.tsx` toggle rows (`ToggleRow` instances at 306-317) | All toggles | `h-6 w-[42px]` (24px tall) — pattern reused from `toggle-switch.tsx` | **High** (cross-cutting; inherent to ToggleSwitch.tsx:35-46) |

The toggle-switch tap-target deficit is the single most repeated violation — it appears in 6+ places with the same `h-6 w-11` pattern. Per shadcn convention, switches are meant to be 24px tall but with a parent label/row handling tap; in our pattern the `<button>` itself is the only tap target on Settings cards.

---

## D. Responsive design audit

Every page uses at least one breakpoint utility. Per-page count from Grep (excluding `globals.css`):

| Page | `md:`/`lg:`/`sm:`/`xl:` count | Status |
|---|---|---|
| `app/page.tsx` (Home) | 2 | OK |
| `app/signals/page.tsx` | 3 | OK |
| `app/regimes/page.tsx` | 2 | OK |
| `app/on-chain/page.tsx` | 1 | **Marginal** — only one `lg:grid-cols-3` on the BTC/ETH/XRP grid; the rest of the page (whale activity, footnote) relies on intrinsic flex/grid wrap. Acceptable but thin. |
| `app/alerts/page.tsx` | 1 | **Marginal** — single `lg:grid-cols-2` on the 2-card layout. Cards collapse to single column on mobile via the parent grid; OK, but no other responsive tweaks (e.g. inputs don't shrink padding). |
| `app/alerts/history/page.tsx` | 1 | **Marginal** — single `md:grid-cols-2 lg:grid-cols-4` on the stat strip. Pagination + filter row uses `flex-wrap` only; OK at 768px but cramped. |
| `app/backtester/page.tsx` | 2 | OK |
| `app/backtester/arbitrage/page.tsx` | 1 | **Marginal** |
| `app/ai-assistant/page.tsx` | 2 | OK |
| `app/settings/dev-tools/page.tsx` | 4 | OK |
| `app/settings/execution/page.tsx` | 3 | OK |
| `app/settings/signal-risk/page.tsx` | 1 | **Marginal** |
| `app/settings/trading/page.tsx` | 2 | OK |

No page is **broken** at 768px (every page has at least one responsive class), but on-chain, alerts, alerts/history, arbitrage, and signal-risk are at the floor. Recommend explicit checks at 360/414/768/1024 widths during the manual click-test.

The shared `app-shell.tsx:19` grid uses `md:grid-cols-[var(--rail-w)_minmax(0,1fr)]` — the sidebar is hidden below md and replaced by `<MobileNav>` (sidebar.tsx:62-99). That layout is correct.

---

## E. Color-only encoding audit

§8 requires shape + color. Components ranked by signal-rendering responsibility:

### Pass — shape + color paired

| Component | Shapes | Color | Notes |
|---|---|---|---|
| `signal-card.tsx:27-41` | ▲ ■ ▼ | success/warning/danger | Reference impl |
| `signal-hero.tsx:21-39` | ▲ ■ ▼ | (color-mix) | OK |
| `signal-history.tsx:16-20` | ▲ ■ ▼ | success/warning/danger | OK |
| `timeframe-strip.tsx:19-23` | ▲ ■ ▼ | success/warning/danger | OK |
| `regime-card.tsx:21-55` | ▲ ▼ ◆ ● ○ | success/danger/warning/teal/orange | All 5 regimes have unique shape |
| `regime-timeline.tsx:20-26` | (color-only — segments are colored bars) | success/danger/warning/teal/orange | **Acceptable** — segments are a horizontal histogram, shape would not improve clarity; color + label above the bar provides redundancy |
| `regime-weights.tsx:24-29` | ▲ ▼ ● ○ | OK | OK |
| `arb-spread-table.tsx:19-41` | ▲ ■ — | success/warning/muted | OK |
| `alert-log-table.tsx:22-32` | ▲ ▼ ◈ ⬡ ⚡ 🔓 | success/danger/info/warning/warning/muted | OK |
| `whale-activity.tsx:67,107` | ▲ ▼ | success/danger | OK + footnote explicitly explains the encoding |
| `trades-table.tsx:57-59` | ▲ ▼ | success/danger | OK for side; **return-pct column at line 63-69 is color-only** (no ± in shape) — minor |

### Fail — color-only

| Component | Where | Fix |
|---|---|---|
| `decisions-table.tsx:22-26` | Decision column uses 🟢🔴⚪ emoji circles. These are **color-only** — color-blind users can't distinguish 🟢 from 🔴. | Replace with ▲ ▼ ■ to match the rest of the app, or use ✓ ✗ — |
| `funding-carry-table.tsx:23-25` | `rateClass()` returns `text-success` / `text-danger` for 8h funding rates (no shape) | Pair with ± or ▲▼ in the cell |
| `watchlist.tsx:51-58` | Change column is text-success/text-danger only (no ▲▼). The sparkline alongside is also color-coded green/red without shape. | Add ▲▼ before `+` / `-` or pair with up/down arrow glyph |
| `signal-hero.tsx:69-80` | 24h / 30d / 1Y change spans use color only | Add small ▲▼ or ± before each value |
| `composite-score.tsx:38-45` | Layer score bars use `bg-accent-brand` / `bg-warning` / `bg-danger` based on threshold — bar position itself encodes value, but the *bar color* is the only signal-strength signal | Acceptable (bar length is the primary signal; color is secondary) |
| `kpi-card.tsx:23-44` | `valueColor: "success" | "danger"` — color only on KPI metric values | **Acceptable** — context (label like "Max drawdown" / "Win rate") makes direction obvious; numeric ± conveys the rest |
| `alert-log-table.tsx:87-93` | Status dot color (sent/failed/suppressed) without shape | The status text label sits next to the dot, so screen readers + color-blind users still get the info from the word "sent"/"failed". OK |

The two "Fail" entries that matter for §8 compliance are `decisions-table.tsx` (high — primary table on AI Assistant page) and the percentage-direction cells in `watchlist.tsx` + `funding-carry-table.tsx` + `signal-hero.tsx` (medium — the surrounding context usually disambiguates, but raw `+0.012%` in a column of greens and reds is the textbook color-blind failure).

---

## F. Accessibility audit

Prior audit waves (05-03, 05-04) closed many issues. Remaining gaps:

### F.1 — Skip-to-content link
**Status:** Missing. Grep across `web/` finds zero matches for `skip` / `skip-to-content` / `href="#main"`. The main element in `app-shell.tsx:29` has no `id="main"` either.
**Severity:** Medium-High — required for keyboard users who otherwise tab through the entire sidebar (8+ links) on every page navigation. CLAUDE.md §8 doesn't explicitly call out skip links, but WCAG 2.4.1 does.

### F.2 — `<label>` association on form inputs
**Pass:**
- `app/settings/trading/page.tsx` — 5 IDs via `useId()`, all associated (lines 46-50, 226-237, 273-282)
- `app/settings/signal-risk/page.tsx` — `SliderField` and `InputField` use `useId()` (lines 39, 89)
- `app/settings/dev-tools/page.tsx:107-109` — apiKey/host/port IDs
- `app/ai-assistant/page.tsx:255-259` (AskClaudeCard) — pair/signal/conf/question all associated
- `components/agent-config-card.tsx:34, 77` — both fields use `useId()`

**Fail / partial:**
- `app/alerts/page.tsx:137-148, 151-159, 161-175` — 3 inputs (Recipient, Sender, SMTP Password) use `<label>` siblings WITHOUT `htmlFor` association. The labels are styled `<label>` elements but the inputs have no matching `id`. Screen readers on these inputs announce "edit" with no field name.
- `app/settings/execution/page.tsx:230-262` — same pattern: `<label>` with no `htmlFor`, `<input>` with no `id`. (Inputs are disabled `password` fields, so the impact is lower, but still flagged.)

**Severity:** Medium for alerts page (active form), low for execution page (disabled).

### F.3 — Icon-only buttons missing `aria-label`
**Pass:** `topbar.tsx:144,159` (refresh, theme), `app/settings/trading/page.tsx:202` (× remove), `app/settings/execution/page.tsx:144` (live mode toggle).

**Fail:**
- `app/settings/execution/page.tsx:177-191` — `autoExecute` toggle button has no `aria-label` and no visible text inside.
- `components/watchlist.tsx:28-33` — "Customize ▾" button: ▾ chevron alone reads as "down arrow". Acceptable since "Customize" is visible text.
- `components/topbar.tsx:118-133` — the level radiogroup buttons have visible text labels ("Beginner" etc.) — OK.
- `app/backtester/arbitrage/page.tsx:189-195` — historical-log expander button has descriptive inner text — OK.

### F.4 — Focus-visible outlines
**Pass:** All 24 shadcn `components/ui/*` primitives include `focus-visible:ring-2` or `focus:ring` patterns (Grep'd 24 files).
**Fail:** Custom buttons in `app/*/page.tsx` and most non-ui `components/*.tsx` have **no** `focus:` or `focus-visible:` classes. Reliance on the global `* { @apply outline-ring/50 }` rule in `globals.css:181` does provide *some* focus indication, but it's `outline-ring/50` — a thin half-opacity outline that is hard to see against `bg-bg-1` cards in dark mode.

Specific places where the global outline is the only focus indicator:
- `topbar.tsx` level pills, refresh button, theme button
- `sidebar.tsx` nav links
- `signal-card.tsx` ticker button
- `regime-card.tsx` card button
- `coin-picker.tsx` coin pills
- `timeframe-strip.tsx` cells
- All `<button>` and `<input>` instances in the 5 settings pages

**Severity:** Medium — keyboard navigation is functional but visual focus is muted. Adding `focus-visible:ring-2 focus-visible:ring-accent-brand` on the major interactive elements would close it.

### F.5 — Tab order / negative `tabIndex`
**Pass:** Only one match for `tabIndex={-1}` across the codebase: `components/ui/sidebar.tsx:290` (shadcn primitive, used to mark a non-focusable hover-trigger inside a managed flyout — correct).

No custom code uses negative tabindex. Tab order should follow DOM order; layouts are mostly flex/grid in DOM order, so this is fine.

### F.6 — `<div onClick=>` patterns
**Fail (1):** `components/alert-type-card.tsx:18-26` — entire card is a `<div onClick={onToggle}>`. This is **not keyboard accessible**. No `role`, no `tabIndex`, no `onKeyDown`. The 5-row alert-type list on `app/alerts/page.tsx` is therefore mouse-only.

**Pass:** `components/regime-card.tsx:73` was previously a `<div onClick=>` and was refactored to `<button>` in the 05-04 a11y wave (visible in the AUDIT comment at lines 70-72). Same pattern needs to apply to AlertTypeCard.

---

## G. Dark/light parity check

Both modes use the same semantic colors (`--success`, `--danger`, `--warning`, `--info`, `--accent`); only `--bg-*`, `--text-*`, `--border*`, `--accent-soft` differ. Per the inline comment at `globals.css:108-111`, `--text-muted` was specifically tuned to pass WCAG AA on both modes (3.06:1 → 5.84:1 in dark; 3.28:1 → 5.0:1 in light).

### Spot-checks

| Surface | Dark mode | Light mode | Verdict |
|---|---|---|---|
| Body text on `bg-bg-0` | `--text-primary #e8e8f0` on `#0a0a0f` (~16:1) | `#0f1014` on `#fafafb` (~17:1) | OK both modes |
| `text-text-muted` on cards | `--text-muted #8a8a9d` on `bg-bg-1 #121218` (~5.49:1) | `#65676f` on `#ffffff` (~5.0:1) | OK both modes |
| `text-success` on bg-1 (P&L cells) | `#22c55e` on `#121218` — light green on near-black, ~7:1 | `#22c55e` on `#ffffff` — light green on white, **~2.6:1 — fails AA** | **Light-mode fail** — `text-success` for body-size text is borderline-illegible on white. Acceptable on **filled** badges (`bg-success/15`) but standalone text usage in light mode is risky. |
| `text-danger` on bg-1 | `#ef4444` on `#121218` — ~5.4:1 | `#ef4444` on `#ffffff` — ~3.8:1 | **Light-mode marginal** — passes AA-large (3:1) but fails AA-normal (4.5:1) for body text |
| `text-warning` on bg-1 | `#f59e0b` on `#121218` — ~7.2:1 | `#f59e0b` on `#ffffff` — ~2.5:1 | **Light-mode fail** for body text |
| `bg-accent-brand` button with `text-bg-0` foreground | `#22d36f` bg / `#0a0a0f` text — ~10:1 | `#22d36f` bg / `#0a0a0f` text — same (text-bg-0 is the same color in both modes via `--accent-ink`) | OK both modes |
| Sparkline strokes (`watchlist.tsx:66`) | `#22c55e` / `#ef4444` on `bg-bg-1` | same colors on white card | Light-mode strokes are visible (~2.5:1 minimum for graphical objects per WCAG 1.4.11) but thin 1.5px stroke is on the edge |
| Colored badges (`bg-success/15 text-success`) | translucent green wash + green text — sits on bg-1 | same wash on light bg-1 (#fff) — text is on a 15%-opacity green tint, effectively #d2f5dd — `text-success` on that becomes ~3.5:1 | **Light-mode marginal** — readable but below AA |

**Net:** Dark mode is solid. Light mode has a systemic risk with the semantic color tokens (success/danger/warning) when used as **standalone body-size text** on white backgrounds. The codebase mitigates this in most places by:
- Using filled badges with bigger/heavier text (signal-card, signal-hero, alert-log)
- Pairing color with shape so the meaning isn't lost even at low contrast

But `watchlist.tsx`, `signal-hero.tsx` (24h/30d/1Y small text), `signal-history.tsx` (return % cell), and `trades-table.tsx` (return % cell) all use `text-success`/`text-danger` for inline percentages. **In light mode these will be hard to read.** Recommend the manual click-test explicitly verify legibility.

---

## H. Manual click-test plan for the user

**The user should manually verify:**

### H.1 — Theme parity (high priority)
- [ ] Walk every page in **dark mode**, scroll to bottom, verify all text is legible
- [ ] Toggle to **light mode**, walk every page again, verify all text is legible
- [ ] On Home page in light mode, check whether the watchlist `+0.91%` / `-1.44%` percentages are readable on the white card
- [ ] On Signals page in light mode, check the 24h / 30d / 1Y small percentage row in the hero card
- [ ] On Backtester in light mode, check the `text-success` "+342.8%" return column in the Optuna table
- [ ] On AI Assistant in light mode, check the green/red emoji circles in the Decisions table
- [ ] Toggle back to dark, verify no flicker / hydration mismatch

### H.2 — User tier (block-listed — system not wired)
The user-tier system is decorative. Click the **Beginner / Intermediate / Advanced** pills in the topbar and confirm:
- [ ] **Expected (per §7):** Page content density should change. Specifically, on Signals: Beginner should hide raw RSI/MACD/ADX values; Advanced should expose more.
- [ ] **Actual:** Pages render identically across all 3 tiers. The pill highlight changes (it's a real radiogroup) but no page reads the value.
- [ ] On `app/backtester/arbitrage/page.tsx`, scroll to the "Beginner view · same data, plain English" card. **It is shown to all 3 tiers** despite the label saying "shown when level = Beginner".

This is the **highest-impact open item** — needs a `<UserLevelProvider>` + `useUserLevel()` hook before the system can be considered functional.

### H.3 — Touch targets (mobile only)
On a phone or DevTools narrowed to 375px width:
- [ ] On `Settings → Trading`, try to remove a pair using the `×` button — confirm whether the tap target is usable
- [ ] On `Settings → Trading`, try the timeframe pills (1m, 5m, …) — confirm tap reliability
- [ ] On `Settings → Execution`, try the LIVE TRADING toggle — confirm tap target (currently 24px tall)
- [ ] On `Alerts → History`, try the pagination buttons — confirm tap reliability (currently 28px)
- [ ] On Watchlist (Home), tap "Customize ▾" — confirm 32px is workable
- [ ] On Channels (Alerts), tap "Connect" / "Edit" — confirm 32px is workable

### H.4 — Color-blind safety
- [ ] On AI Assistant → Recent Decisions table, ask a color-blind reviewer (or use a CB simulator) whether 🟢/🔴/⚪ are distinguishable. If not, flag for shape-pair fix.
- [ ] On Watchlist (Home), confirm whether the up/down change percentages are distinguishable without color.
- [ ] On Funding-Rate Carry Trades (Backtester → Arbitrage), confirm whether positive/negative funding rates are distinguishable without color.

### H.5 — Keyboard navigation
- [ ] Press Tab from page load on Home — count how many tabs to reach the first watchlist row. (No skip-to-content link, so all 8 sidebar nav links must be traversed first.)
- [ ] On Alerts page, press Tab through the 5 alert-type cards — confirm whether they're keyboard-reachable. **Expected: they are NOT (`<div onClick=>`).** Confirm the failure.
- [ ] On any page, focus a button with Tab and confirm whether the focus outline is visible. (Currently relies on global `outline-ring/50` — may be hard to see on dark cards.)

### H.6 — Live data fallbacks (sanity)
- [ ] On On-chain page, verify each card shows real values from `/onchain/dashboard` rather than "—". Status pill should say "live · 24h" or similar.
- [ ] On Backtester, verify the KPI strip populates from `/backtest/summary`. If empty, "Loading recent trades…" should show in the trades panel.

---

## I. Recommended P0 fix order

Ordered by impact-to-effort:

1. **(P0) Wire the user-tier system end-to-end.** Add a `<UserLevelProvider>` (mentioned as TODO in `providers/app-providers.tsx:11`) + `useUserLevel()` hook. Refactor `Topbar` to consume the context. Then either branch content per tier on each page or expose tier-aware UI primitives (e.g. `<TieredText beginner="…" intermediate="…" advanced="…" />`). Without this, §7 is fiction and the radiogroup misleads users. **Highest-impact item in the audit.** Effort: 1–2 days for the plumbing, 2–4 days for tier-aware copy across 15 pages. (For arbitrage page line 152 — fix or delete the "shown when level = Beginner" copy in the same patch.)

2. **(P0) Make `alert-type-card.tsx` keyboard accessible.** Convert `<div onClick=>` to `<button type="button" role="checkbox" aria-checked=...>` with the same visual styling. Mirror the regime-card.tsx 05-04 fix. Effort: 15 minutes.

3. **(P0) Add a skip-to-content link.** In `app-shell.tsx`, before the sidebar, add `<a href="#main" className="sr-only focus:not-sr-only ...">Skip to main content</a>` and add `id="main"` to the `<main>` element on line 29. Effort: 10 minutes.

4. **(P1) Lift toggle-switch tap targets above 44px.** Modify `toggle-switch.tsx` (and the inline copies in `agent-config-card.tsx`, `app/settings/execution/page.tsx`, `app/settings/trading/page.tsx`) to use a `min-h-[44px]` parent label that captures the tap, with the visible 24px switch positioned inside. Pattern: `<label className="flex min-h-[44px] items-center …"><span>Label</span><button role="switch" …>{thumb}</button></label>`. Effort: 1–2 hours, cross-cutting.

5. **(P1) Fix decisions-table color-only encoding.** Replace 🟢🔴⚪ with the existing ▲ ▼ ■ shape vocab. Effort: 5 minutes (`components/decisions-table.tsx:22-26`).

6. **(P1) Add `aria-label` to the auto-execute toggle in execution settings.** `app/settings/execution/page.tsx:177-191`. Effort: 1 minute.

7. **(P1) Light-mode legibility pass for `text-success` / `text-danger` / `text-warning` body text.** Either:
   - (a) define light-mode-only darker variants of these colors (e.g. `--success-text-light: #16a34a`), or
   - (b) restrict their use to filled badges (`bg-success/15 text-success`) and use a more contrasted text color for inline cells (e.g. `text-text-primary` with a small ▲▼ shape next to the value). 
   Affected places: watchlist.tsx, signal-hero.tsx (24h/30d/1Y), signal-history.tsx return col, trades-table.tsx return col, optuna-table.tsx return col, funding-carry-table.tsx all rate cells. Effort: 2–3 hours.

8. **(P2) Touch targets <44px on settings filters + alerts pagination.** alerts/history pagination buttons (h-7) are the worst offender. Effort: 1 hour.

9. **(P2) `<label htmlFor>` association on alerts page form inputs.** 3 inputs on `app/alerts/page.tsx`, 3 on `app/settings/execution/page.tsx`. Effort: 30 minutes.

10. **(P2) Add explicit `focus-visible:ring-2 focus-visible:ring-accent-brand` on custom buttons across the app.** Most leveraged on topbar, sidebar, settings tabs, and signal-card. Effort: 1–2 hours.

11. **(P3) Replace `rgba(34,211,111,0.2)` with `var(--accent-soft)` in `app/alerts/page.tsx:192`.** Effort: 1 minute.

12. **(P3) Replace SVG sparkline `stroke="#22c55e"` with `stroke="var(--success)"` in `components/watchlist.tsx:66`.** Effort: 1 minute.

13. **(P3) Update `#00d4aa` legacy fallback in execution + signal-risk slider gradients to `#22d36f` (or omit the fallback).** Effort: 2 minutes.

---

## J. Out-of-scope items observed

These are real bugs noticed during the audit that aren't tier-6 in scope but should be flagged:

- `app/page.tsx:31-99` — Home page hero / macro / watchlist still use **mock data** with `TODO(D-ext)` comments. Live wiring requires `/data-sources`, `/macro`, and per-pair sparkline endpoints that don't exist. This is documented in the file header comment.
- `app/ai-assistant/page.tsx:93-98` — agent metric strip uses `"—"` placeholders pending `/agent/summary` endpoint.
- `app/backtester/arbitrage/page.tsx:147-174` — "Beginner view" mock card is shown to all tiers (see §A and P0 #1).
- `components/decisions-table.tsx:39-60` — three filter dropdowns are not wired to any state; clicking them does nothing.
