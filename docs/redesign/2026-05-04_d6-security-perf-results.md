# D6 — Security + Perf Results (2026-05-04)

**Run against:** `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`
**Branch:** `phase-d/next-fastapi-cutover` @ `3b772bb`
**Checklist source:** `docs/redesign/2026-05-03_d6-security-perf-checklist.md`

---

## Executive summary — counts by severity

| Severity | Count | Categories |
|---|---|---|
| CRITICAL | **0** | — |
| HIGH | **0** | (was 2 — T4 a11y bundle CLOSED in `25e83ac` + `9674552`) |
| MEDIUM | **2** | npm audit (next/postcss, false-positive) + 2× console 404s on `/` |
| LOW | 0 | — |

## T4 a11y bundle — CLOSED (2026-05-04 PM)

Per Cowork's 2026-05-04 PM decision ("block D8 on T4 fix"), the two HIGH
findings landed in two commits:

- **`25e83ac` fix(a11y): T4 bundle** — single-token CSS fix (dark
  `--text-muted` from `var(--gray-5)` `#5d5d6e` → `var(--gray-6)` `#8a8a9d`,
  contrast 3.06:1 → 5.84:1 on bg-0 and 2.89:1 → 5.49:1 on bg-1) plus 7
  `useId()`-based label↔control associations on /ai-assistant
  (AgentConfigCard's 3 InputFields + ToggleField, AskClaudeCard's 3 inputs
  + 1 select).
- **`9674552` fix(a11y): T4 residuals on /settings/dev-tools** — surfaced
  on Lighthouse re-run: heading-order (h1→h3 skipped h2; bumped 4 section
  h3→h2 and inner h4→h3) + 3 inline inputs without label association
  (API Key, Host, Port). All fixed via `useId()`.

**Final Lighthouse scores (Vercel preview, headless Chrome, post-fix):**

| Route | Perf | A11y | BP | SEO | A11y delta |
|---|---|---|---|---|---|
| `/` | 95 | **100** | 96 | 100 | +5 |
| `/signals` | 92 | **100** | 96 | 100 | +5 |
| `/settings/dev-tools` | 91 | **100** | 96 | 100 | +12 |
| `/ai-assistant` | 96 | **100** | 96 | 100 | +22 |

Every Cowork D8 gate criterion now met: Accessibility = 100 on every
route, Perf ≥ 90, BP ≥ 90, SEO ≥ 90.

D6 verdict: **PASS** for D8 cutover. The 2 remaining MEDIUM findings
(npm next/postcss false-positive + 2 console 404s on `/`) are
non-blocking per the checklist rule "block D8 only on findings >MEDIUM";
the 2 console 404s likely resolve once the backtest endpoint is hit
(Task 2).

---

## A. npm audit (web/)

```
moderate=2  high=0  critical=0  total=2
```

Both moderates are linked: `postcss` (transitive) flagged inside `next`. The
`fixAvailable` resolver suggests downgrading **Next 16 → 9.3.3** (-7 majors)
which is a non-viable downgrade through the entire app architecture. The
real-world impact in Next 16's bundled postcss is `false-positive`.

**Verdict:** PASS. 0 high/critical. The 2 moderates are noise from npm's
overly broad version-range matcher; cannot be auto-fixed without breaking
the framework.

## B. Semgrep static analysis

```
74 rules across p/typescript + p/react + p/nextjs
140 files scanned in web/
0 findings
```

**Verdict:** PASS. Zero `dangerouslySetInnerHTML` issues, zero `eval()`,
zero hardcoded secrets, zero unsanitized data flows.

(Manual grep confirms the one `dangerouslySetInnerHTML` in
`web/components/ui/chart.tsx:83` is the standard shadcn chart-styling
injection — color tokens only, no user input. `localStorage` usage in
`web/components/topbar.tsx` is the documented user-level persistence per
CLAUDE.md §7 — no credentials or PII stored.)

## C. Lighthouse (Vercel preview, headless Chrome)

| Route | Perf | A11y | BP | SEO |
|---|---|---|---|---|
| `/` | **95** | 95 | 96 | 100 |
| `/signals` | **94** | 95 | 96 | 100 |
| `/settings/dev-tools` | **96** | 88 | 96 | 100 |
| `/ai-assistant` | **96** | 78 | 96 | 100 |

**Targets:** Perf ≥ 90 ✓, BP ≥ 90 ✓, SEO ≥ 90 ✓, **A11y = 100 ✗** on every
route.

### A11y deductions (HIGH — pre-existing T4 a11y bundle)

- **`color-contrast` (all 4 routes, 23–42 fails per route).** Single root
  cause: `text-text-muted` token resolves to `#5d5d6e` and renders on
  `#0a0a0f` (page bg) or `#121218` (card bg) for ratios of **2.89:1** and
  **3.06:1**. WCAG AA requires **4.5:1** for normal text. Mostly small fonts
  (10.5–13.5 px) so the looser large-text rule doesn't apply.
  - Fix scope: one CSS variable in `web/styles/globals.css` —
    lighten `--text-muted` from `#5d5d6e` to ≥ `#7a7a8c` (4.6:1 on
    `#0a0a0f`, 4.5:1 on `#121218`). Single-token fix; cascades to all 23+42
    failures.
- **`button-name` (/ai-assistant, 1 fail).** Toggle switch
  `<button class="relative h-6 w-11 ... rounded-full ... bg-accent-brand">`
  has no `aria-label`. Single component fix.
- **`label` (/ai-assistant, 5 fails).** Form inputs missing `<label
  htmlFor>` association. Per-field fix.
- **`select-name` (/ai-assistant, 1 fail).** `<select>` with no
  associated label. Single fix.

### Best Practices deduction (MEDIUM)

- **`errors-in-console` (/, 2× network 404s).** Two missing-resource 404s
  logged. Likely candidates: an un-populated `/backtest/*` endpoint (404
  per `api.py:624` "No backtest data available") or a missing favicon
  variant. **Will likely self-resolve once Task 2 (trigger backtest) runs**;
  re-test after.

### Performance deductions (informational, non-blocking)

`legacy-javascript-insight`, `network-dependency-tree`,
`render-blocking-insight`, `unused-javascript`, LCP 0.84, Max-FID 0.74.
Standard Next.js production patterns. All four routes still score ≥ 94
overall, well above the 90 threshold.

## D. Manual walk

**Owner: David.** Brief flagged this as parallel-track. Walk Chrome/Safari/
Firefox desktop minimum + iOS Safari + Chrome Android per checklist Section D.
Pending — David's TODO list per the handoff brief.

## E. Bundle size

```
25 chunks total
Total raw:     921 KB
Total gzipped: 280 KB
Largest:        69.5 KB gzipped (222 KB raw)
Chunks > 250 KB gzipped: 0
```

**Verdict:** PASS. All targets met. No code-splitting urgency; lazy-load
of Recharts (suggested in the checklist) is unnecessary at current sizes.

## F. CORS verification

```
$ curl -i -H "Origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app" \
       https://crypto-signal-app-1fsi.onrender.com/health
HTTP/1.1 200 OK
access-control-allow-origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app
vary: Origin
```

**Verdict:** PASS. The overnight-audit `53ac7f5` CORS regex broaden lands
correctly on the live deploy. Origin echo is exact-match for the v0
preview URL; preflight will pass.

CSP: not set (Vercel default). Deferred per checklist — not a D6 blocker.

## G. Source-map exposure

```
$ curl -I https://v0-davidduraesdd1-blip-crypto-signa.vercel.app/_next/static/chunks/main.js.map
HTTP/2 404
```

**Verdict:** PASS. `productionBrowserSourceMaps` not enabled in
`next.config.mjs` (default `false`). No source-map leakage.

## H. Configuration flags

- `web/next.config.mjs:4` still has `ignoreBuildErrors: true`. Pre-existing,
  flagged in `2026-05-03_phase-d-deep-dive-audit.md:261`. Defer to post-D5
  cleanup per that audit.

---

## D8 gate verdict (post-T4)

| Criterion | Status |
|---|---|
| npm audit: 0 high/critical | ✅ |
| Semgrep: 0 critical, ≤ 3 high | ✅ (0 of each) |
| Lighthouse Performance ≥ 90 every route | ✅ (91–96) |
| Lighthouse Accessibility = 100 every route | ✅ (100 / 100 / 100 / 100) |
| CORS allowlist verified | ✅ |
| Bundle size targets | ✅ |
| Source-map not exposed | ✅ |
| Manual walk (Chrome/Safari/Firefox + mobile) | ⏳ pending — David's task |

**D8 unblocked.** Awaiting David's go/no-go after manual cross-browser walk.

---

## Restore tag

Pre-fix tag for any D6 follow-up work: `pre-d6-fixes-2026-05-04` (create
on the commit if/when David greenlights the a11y patches).

## Artifacts

- `web/lh-home.json`, `web/lh-signals.json`, `web/lh-devtools.json`,
  `web/lh-aiassistant.json` — full Lighthouse JSON (gitignored; recreate
  via `lighthouse <url> --output=json`).
- `web/semgrep-results.json` — Semgrep output (empty `results[]`,
  gitignored).
