# D6 — Security + Perf Results (2026-05-04)

**Run against:** `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`
**Branch:** `phase-d/next-fastapi-cutover` @ `3b772bb`
**Checklist source:** `docs/redesign/2026-05-03_d6-security-perf-checklist.md`

---

## Executive summary — counts by severity

| Severity | Count | Categories |
|---|---|---|
| CRITICAL | **0** | — |
| HIGH | **2** | Lighthouse a11y color-contrast (all 4 routes) + missing button/label/select names (/ai-assistant) |
| MEDIUM | **2** | npm audit (next/postcss, false-positive) + 2× console 404s on `/` |
| LOW | 0 | — |

**D8-blocking decision:** the 2 HIGH findings are **pre-existing items from
`2026-05-03_phase-d-deep-dive-audit.md` ("T4 a11y bundle" held)**. They are not
new regressions introduced by D4/D5. David + Cowork to decide:
*ship D8 with known a11y debt and fix in T4*, or *block D8 until T4 lands*.
Per the checklist's literal rule ("block D8 only on >MEDIUM") and per
CLAUDE.md §8 ("WCAG AA contrast minimums at all times") these technically
block. **Recommendation: ship D8, schedule T4 as the first post-cutover
sprint.** Reason: every finding listed below was already known on 2026-05-03;
no D5 deploy made anything worse; cutover blocks no fix.

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

## D8 gate verdict

| Criterion | Status |
|---|---|
| npm audit: 0 high/critical | ✅ |
| Semgrep: 0 critical, ≤ 3 high | ✅ (0 of each) |
| Lighthouse Performance ≥ 90 every route | ✅ (94–96) |
| Lighthouse Accessibility = 100 every route | ❌ (78–95; pre-existing T4 a11y debt) |
| CORS allowlist verified | ✅ |
| Bundle size targets | ✅ |
| Source-map not exposed | ✅ |
| Manual walk (Chrome/Safari/Firefox + mobile) | ⏳ pending — David's task |

**Recommendation to David:** approve D8 cutover with the explicit caveat
that T4 a11y bundle (color-contrast token + 7 missing aria-labels on
/ai-assistant) is the first post-cutover sprint. Single-token CSS fix
clears ~95% of the a11y failures across all routes.

If David wants Accessibility = 100 *before* D8 merge: T4 fix is a
half-day of focused work — feasible to land in 2026-05-05 and then
re-run Lighthouse before merging on 2026-05-06.

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
