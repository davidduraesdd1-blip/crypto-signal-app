# D6 — Security + Perf Pass Checklist

**Trigger:** runs after D5 Vercel deploy lands. Audits the live preview
URL before D7 regression / D8 cutover.

**Effort:** ~1 day (D4 plan §6 D6).

**Pre-condition:** Vercel preview URL exists and renders all 8 routes.

---

## Section A — npm audit (10 min)

```bash
cd web
npm audit --audit-level=moderate 2>&1 | tee /tmp/npm-audit.log
```

Expected outcomes:
- ✅ "found 0 vulnerabilities" — pass
- ⚠ "found N vulnerabilities" — review each:
  - `low`: defer to follow-up
  - `moderate`: fix unless it requires a major-version bump
    (track in audit doc)
  - `high` / `critical`: must fix before D8 cutover

```bash
# To auto-fix non-breaking ones:
npm audit fix
# To force breaking changes (USE CAUTION):
npm audit fix --force
```

**Audit doc:** record findings + fix decisions in
`docs/audits/2026-05-XX_d6-security-perf.md`.

---

## Section B — Semgrep static analysis (15 min)

Install Semgrep if not already:

```bash
pip install semgrep
# or via brew/scoop/etc.
```

Run with the curated TypeScript + React + Next.js rule set:

```bash
cd /c/dev/Cowork/crypto-signal-app/.claude/worktrees/phase-d-resume
semgrep --config=p/typescript --config=p/react --config=p/nextjs web/ \
  --json --output /tmp/semgrep-results.json
```

Triage findings:
- `dangerouslySetInnerHTML` without sanitization → CRITICAL
- Hardcoded secrets, API keys, JWTs → CRITICAL
- `eval()` / `Function()` constructors → HIGH
- `localStorage` / `sessionStorage` writing user data → MEDIUM
  (audit what's being stored — credentials in localStorage is bad)
- `target="_blank"` without `rel="noopener noreferrer"` → LOW
- Missing prop types / `any` usage → LOW (already typed via TS)

For each finding: file:line, severity, decision (fix/defer/false-positive).

---

## Section C — Lighthouse on Vercel preview (20 min)

Use Chrome DevTools Lighthouse panel OR the CLI:

```bash
npm install -g lighthouse
lighthouse https://crypto-signal-app-web-<hash>.vercel.app/ \
  --output=html --output-path=/tmp/lighthouse-home.html \
  --view
```

Run on representative pages:
- `/` (Home)
- `/signals`
- `/settings/dev-tools` (heaviest data fetch)
- `/ai-assistant` (heaviest UI complexity)

**Targets per D4 plan §8 D4d:**
- Performance: ≥ 90
- Accessibility: 100
- Best Practices: ≥ 90
- SEO: ≥ 90

If Performance < 90:
- Inspect "Reduce JavaScript execution time" — likely culprit:
  TanStack Query devtools in production bundle. Confirm
  `query-provider.tsx` only mounts ReactQueryDevtools when
  `process.env.NODE_ENV !== "production"`. ✅ already guarded
  (line 22).
- "Largest Contentful Paint" — first hero card. If slow, check
  font-loading in `app/layout.tsx` (currently uses `display: "swap"`
  for both Inter + JetBrains Mono — should be fine).
- "Total Blocking Time" — heavy chart components. v0 charts use
  Recharts which is non-trivial. Acceptable if < 200ms.

If Accessibility < 100:
- Check `aria-label` on icon-only buttons (Topbar Refresh, Test OKX,
  X close on alert chips). Current code has `aria-label="Refresh all
  data"` and `aria-label={`Remove ${pair}`}` — good.
- Check color contrast — both themes (dark + light) need WCAG AA.

---

## Section D — Manual walk on real device (30 min)

Test the live Vercel URL on:
- **Desktop:** Chrome, Safari, Firefox (latest)
- **Mobile:** iOS Safari (real iPhone if possible), Chrome Android
  (real device or DevTools mobile emulator)
- **Tablet viewport:** iPad mode in DevTools

For each route, walk through:

| Route | Expected behavior |
|---|---|
| `/` Home | Hero cards populated; BacktestCard live; data-source pills |
| `/signals` | Coin picker; hero card; "Scan now" works; tech indicators populate |
| `/regimes` | 8-card grid; selecting a card highlights it |
| `/on-chain` | BTC/ETH/XRP cards live; status pills reflect `source` |
| `/backtester` | KPIs live; trades table live |
| `/backtester/arbitrage` | Spot Spread table populates or shows truthful empty |
| `/alerts` | Email config form renders; tab navigation works (router.push, not full reload) |
| `/alerts/history` | Log table populates; pagination works |
| `/ai-assistant` | AGENT pill + Recent Decisions live; Ask Claude form submits |
| `/settings/trading` | Form hydrates; chip add/remove; Save persists |
| `/settings/signal-risk` | Sliders move; Save persists |
| `/settings/dev-tools` | 7-gate card live; DB KPIs live; "All N gates operational" or "N of 7 measured" pill |
| `/settings/execution` | Live trading toggle; Test OKX button; Save persists |

Edge cases to probe:
- Refresh All button on every page → spinner animates → all data refreshes
- Submit a Settings form with a bad value (e.g. `min_confidence_threshold = 200`) → confirm `rejected[]` field renders inline
- Submit AI Ask with `confidence = 250` → confirm 422 surface (pre-validation client-side or server-side)
- Toggle Live Trading mode → confirm danger banner visual updates
- Theme toggle → confirm persist via `next-themes` localStorage
- User-level toggle → confirm persist via `crypto-signal-app:user-level` localStorage; reload → still selected

---

## Section E — Bundle size (10 min)

```bash
cd web
ANALYZE=true npm run build
# OR:
npx @next/bundle-analyzer .next/analyze
```

Targets:
- First-load JS shared by all pages: < 300 kB gzipped
- Per-route JS additions: < 100 kB gzipped each
- Total JS for `/` landing: < 400 kB gzipped

Common bloat sources to inspect:
- `lucide-react` — tree-shaken? Confirm only-imported icons land in the
  bundle.
- `recharts` — heavy. Lazy-load via `dynamic(() => import())` if
  Lighthouse Performance suffers.
- `@tanstack/react-query-devtools` — confirmed dev-only via guard.

---

## Section F — CORS + CSP verification (15 min)

Open the Vercel preview in a browser. In dev console, run:

```js
fetch("https://crypto-signal-app-1fsi.onrender.com/health")
  .then(r => console.log(r.status))
```

Expected: `200`. If CORS error, the FastAPI side's `allow_origin_regex`
may not include the Vercel preview URL. Update `api.py:103-114`:

```python
# AUDIT-2026-05-02 — owner-prefix-only Vercel allowlist:
allow_origin_regex = (
    r"^https://crypto-signal-app(-[a-z0-9-]+-davidduraesdd1-blip)?\.vercel\.app$"
)
```

The `(-[a-z0-9-]+-davidduraesdd1-blip)` middle segment matches
auto-generated preview URLs like
`https://crypto-signal-app-web-abc123-davidduraesdd1-blip.vercel.app`.
If your project name differs, adjust accordingly.

CSP headers:
- Vercel doesn't set CSP by default. If we want one (post-D8), add
  via `vercel.json` or `next.config.mjs` headers config.
- For D6: NOT a blocker. Defer.

---

## Section G — Source-map exposure (5 min)

Check that production source maps aren't publicly exposed:

```bash
curl -I https://crypto-signal-app-web-<hash>.vercel.app/_next/static/chunks/main.js.map
```

Expected: `404` (Next.js default — source maps in `.next` are
server-side only). If it returns 200, that's a leak — set
`productionBrowserSourceMaps: false` (the default) in
`next.config.mjs`.

---

## Section H — Findings → audit doc

Create `docs/audits/2026-05-XX_d6-security-perf.md` with the
following sections:

1. Executive summary — count by severity
2. npm audit findings + fix decisions
3. Semgrep findings + triage
4. Lighthouse scores per route (table)
5. Manual walk results (per-route checklist with ✓/✗/⚠)
6. Bundle size analysis (top 10 modules + first-load JS sizes)
7. CORS / CSP verification
8. Source map exposure check
9. Recommendations for the post-cutover hardening backlog

Restore tag before any fix work: create
`pre-d6-fixes-2026-05-XX` so D6 fixes are roll-back-able.

---

## What constitutes "D6 done"

- ✅ npm audit: 0 high or critical
- ✅ Semgrep: 0 critical, ≤ 3 high (each documented)
- ✅ Lighthouse Performance ≥ 90 on every route
- ✅ Lighthouse Accessibility = 100
- ✅ Manual walk: every route renders + every form persists + every
  CRUD action works on both desktop + mobile viewport
- ✅ CORS allowlist verified for the Vercel preview URL
- ✅ Bundle size within targets (< 300kB shared first-load JS)
- ✅ Audit doc committed to `docs/audits/`

Then D7 (§22 regression diff — already covered by today's
`2026-05-03-d7-section22-compliance-review.md` so D7 is largely a
double-check of the production deploy against the doc) → D8
(merge phase-d → main + 30-day Streamlit overlap).

---

## Quick-fire commands (copy/paste once preview URL is live)

```bash
# Set the preview URL once:
export VERCEL_URL="https://crypto-signal-app-web-<hash>.vercel.app"

# Section A — npm audit
cd web && npm audit --audit-level=moderate

# Section B — Semgrep
semgrep --config=p/typescript --config=p/react --config=p/nextjs web/

# Section C — Lighthouse 4 routes
for route in "" "signals" "settings/dev-tools" "ai-assistant"; do
  lighthouse "$VERCEL_URL/$route" \
    --output=html --output-path=/tmp/lh-${route//\//-}.html \
    --quiet --chrome-flags="--headless" || true
done

# Section F — CORS
curl -s -I -H "Origin: $VERCEL_URL" \
  https://crypto-signal-app-1fsi.onrender.com/health \
  | grep -i "access-control"

# Section G — source maps
curl -s -I "$VERCEL_URL/_next/static/chunks/main.js.map" | head -1

# Bundle size
cd web && ANALYZE=true npm run build
```
