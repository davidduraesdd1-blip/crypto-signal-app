# Tier 7 — Capacitor Compatibility
**Date:** 2026-05-05
**Capacitor version:** 8.3.1
**Bundle ID (pending):** com.polaris.edge (config currently set to `com.polaris-edge.app` — must be updated)
**Methodology:** Read-only static audit of `web/` (Next.js 16.2.4 / React 19.2.4). Greps for module-level browser globals across `app/`, `components/`, `lib/`, `hooks/`, `providers/`. Inspection of `next.config.mjs`, `capacitor.config.ts`, `app/layout.tsx`, `globals.css`, and the produced `out/` static export. Byte-level grep of `out/_next/static/chunks/*.js` to verify the `NEXT_PUBLIC_API_BASE` inlining behavior.

## Summary
- Module-level browser API access: **0 violations** (every `window.`/`document.`/`localStorage.` call is gated by `typeof window !== "undefined"` or wrapped in `useEffect` / `useCallback` / `useState` lazy initializer)
- Hard-coded incompatible URLs: **1 critical** (`API_BASE` fallback `"http://localhost:8000"` is the value actually inlined into the current `out/` bundle — see Static bundle URL inlining check)
- Static-export-incompatible features: **0** (no `middleware`, no `app/api/`, no `force-dynamic`, no `revalidate`, no `next/headers`, no `generateStaticParams`, no `headers()`/`redirects()`/`rewrites()` in `next.config.mjs`)
- Native plugins to add for V1 (B3): **5** (`@capacitor/app`, `@capacitor/preferences`, `@capacitor/network`, `@capacitor/push-notifications`, biometric — see Native plugin recommendations)

## Findings

### Module-level browser globals
All call sites traced. Every one is either inside a hook callback, `useEffect`, or guarded with a `typeof window !== "undefined"` check. **No violations.**

| File | Line | Usage | Verdict |
| ---- | ---- | ----- | ------- |
| `web/hooks/use-mobile.ts` | 9, 11, 14 | `window.matchMedia` / `window.innerWidth` | Inside `React.useEffect` — safe |
| `web/components/ui/use-mobile.tsx` | 9, 11, 14 | duplicate of above (shadcn-shipped copy) | Inside `React.useEffect` — safe |
| `web/components/topbar.tsx` | 19 | `typeof window === "undefined"` early-return guard inside `readPersistedLevel()` | Module-defined helper, but only invoked from `useState(() => readPersistedLevel())` lazy initializer (runs on mount, not at import) and from a `useEffect` resync — safe |
| `web/components/topbar.tsx` | 21, 52 | `window.localStorage.getItem` / `setItem` | Inside guarded helper + event handler — safe |
| `web/components/ui/sidebar.tsx` | 86 | `document.cookie = ...` | Inside `useCallback` — safe |
| `web/components/ui/sidebar.tsx` | 108-109 | `window.addEventListener("keydown")` | Inside `useEffect` — safe |
| `web/app/error.tsx` | 28-30 | `console.error` after `typeof window` guard | Inside `useEffect` — safe |
| `web/app/global-error.tsx` | 23-25 | `console.error` after `typeof window` guard | Inside `useEffect` — safe |
| `web/lib/api.ts` | 64-95 | `process.env.NEXT_PUBLIC_API_BASE` / `_API_KEY` reads at module level + production hard-throw guarded by `typeof window !== "undefined"` | Module top-level, but the `process.env.*` reads are static (replaced at build time); the `throw` is browser-gated — safe for SSR / static export prerender, will fire at WebView runtime if env is missing |

Note on the api.ts hard-throw (line 70): the throw IS browser-gated, which is correct for prerender. But it means a Capacitor packaged app whose `NEXT_PUBLIC_API_BASE` was unset at build time will throw the moment any client component imports `lib/api.ts`. Since the current `out/` bundle was built with `NEXT_PUBLIC_API_BASE` unset (see Static bundle URL inlining check below), the throw won't fire (because the fallback `"http://localhost:8000"` is inlined as a real string, so `_RAW_API_BASE` is **truthy** at the byte-level — the check is on the build-time replacement, not runtime). The user instead silently sees a broken app trying to reach `http://localhost:8000` from the WebView. That's the more dangerous failure mode.

### Incompatible URLs

| File | Line | URL | Risk | Fix |
| ---- | ---- | --- | ---- | --- |
| `web/lib/api.ts` | 76 | `"http://localhost:8000"` (fallback) | **CRITICAL** when `NEXT_PUBLIC_API_BASE` is unset at mobile build time — see Static bundle URL inlining check; Capacitor on Android with `androidScheme: "https"` will block plain http and the WebView at `https://localhost` cannot reach a non-existent localhost API anyway. | Set `NEXT_PUBLIC_API_BASE=https://crypto-signal-app-1fsi.onrender.com` in the environment for `npm run build:mobile`. Consider failing the **build** (not the runtime) when `BUILD_TARGET=mobile && !NEXT_PUBLIC_API_BASE` so a misconfigured packaging cannot ship. |
| `web/app/settings/dev-tools/page.tsx` | 345, 376, 382, 395 | `0.0.0.0`, `http://localhost:8000`, `localhost:8000` | None — these are display-only text strings inside JSX `<pre>` blocks and an `<input defaultValue="0.0.0.0">` that doesn't wire to fetch. Developer-help content. | No action. |
| `web/app/settings/dev-tools/page.tsx` | 376 | `--host 0.0.0.0` | None — code block showing user how to run uvicorn locally | No action. |

No `vercel.app` self-references, no `file://` references, no `127.0.0.1` references, no other `http://` (non-https) URLs in source. **External links are all relative** (`<a href="/settings/dev-tools">` and friends).

### Static export check
`web/next.config.mjs` was inspected. With `BUILD_TARGET=mobile` it sets `{ output: "export", trailingSlash: true }` and merges with the always-on `{ typescript.ignoreBuildErrors: true, images.unoptimized: true }`. Confirmed clean:
- `images.unoptimized: true` — already set, required for static export.
- No `headers()`, `redirects()`, `rewrites()` config — clean.
- No `middleware.ts` — confirmed via Glob.
- No `app/**/route.ts` — confirmed via Glob.
- No `app/api/**` — confirmed via directory listing.
- No `export const dynamic = "force-dynamic"` — Grep returned 0 matches.
- No `export const revalidate = N` — Grep returned 0 matches.
- No `cookies()` / `headers()` from `next/headers` — Grep returned 0 matches.
- No `generateStaticParams` — Grep returned 0 matches.
- No service worker, no `manifest.json`, no `next-pwa` plugin — Grep returned 0 matches; `web/public/` does not exist.

The conditional `output: "export"` block is correctly gated and does not conflict with anything in the surrounding config object.

### Static bundle URL inlining check
**This is a P0 finding.** Greps against `web/out/_next/static/chunks/*.js`:

```
$ grep -oE '"http://localhost:8000"|API_BASE' web/out/_next/static/chunks/0vc11y.r8n42s.js | sort -u
"http://localhost:8000"
API_BASE
```

The fallback string `"http://localhost:8000"` is inlined into two chunks:
- `web/out/_next/static/chunks/0vc11y.r8n42s.js` (1 occurrence)
- `web/out/_next/static/chunks/0vf24ejck5sx7.js` (2 occurrences)

The Render API URL (`crypto-signal-app-1fsi.onrender.com`) is **not** present anywhere in `web/out/`. Confirmed by:
```
$ grep -rl "onrender.com" web/out/   →  no matches
$ grep -rl "vercel.app"  web/out/   →  no matches
```

Root cause: the worktree has no `web/.env.local` (only the project-root `.env.example` exists). The most recent local `npm run build:mobile` ran with `NEXT_PUBLIC_API_BASE` unset, so Webpack/Turbopack replaced the `process.env.NEXT_PUBLIC_API_BASE` reference with `undefined` at build time, and `_RAW_API_BASE ?? "http://localhost:8000"` collapsed to the literal `"http://localhost:8000"`. The browser-gated `throw` in api.ts runs **after** build-time replacement, so the runtime `_RAW_API_BASE` value is truthy (it's the fallback string baked in via `??`) and the throw never fires — the app silently tries to reach localhost.

This means: **the current `out/` bundle is unusable in a Capacitor packaged app.** Any sync into Android Studio / Xcode right now would ship localhost calls.

Vercel's SSR build (which David verified contains the inlined Render URL in `0m13g~ya4_f5t.js`) is fine because Vercel's project-level env vars set `NEXT_PUBLIC_API_BASE` for the build pipeline. The local mobile build needs the same env var passed at build time.

### Native plugin recommendations for B3

| Plugin | Purpose | Priority |
| ------ | ------- | -------- |
| `@capacitor/app` | Listen for the Android hardware back button via `App.addListener("backButton", ...)`; handle app pause/resume; expose app version/build number for the Diagnostics page | **P0** for Android — without it the back button defaults to closing the app on every screen, which violates user expectation on tab/route stacks |
| `@capacitor/preferences` | Replace `localStorage` for the user level (`crypto-signal-app:user-level` in `topbar.tsx`) and any future persistent settings; native KeyChain (iOS) / SharedPreferences (Android) survives WebView cache clears that would wipe `localStorage` | **P1** — `localStorage` works in Capacitor 8 WebView but is sometimes purged by the OS on storage pressure; native preferences are durable |
| `@capacitor/network` | Online/offline awareness so the empty-state copy in queries can say "you're offline" instead of generic "couldn't load" — pairs with the existing graceful-fallback pattern in `lib/api.ts` `ApiError` taxonomy | **P1** |
| `@capacitor/push-notifications` | Push alerts on signal direction changes — required for B3 "push + biometric auth" scope; pairs with the existing `/alerts/configure` API surface | **P0** for B3 scope |
| `@capacitor-community/native-biometric` (or `capacitor-biometric-auth`) | Touch ID / Face ID / Android biometric prompt for unlocking the live-trading toggle on the Settings → Trading page; required for B3 scope | **P0** for B3 scope |

Optional / nice-to-have for later:
- `@capacitor/status-bar` — set status bar style per theme
- `@capacitor/splash-screen` — branded splash instead of white flash
- `@capacitor/haptics` — light tap on signal change confirmation

### Viewport / safe-area
**One `MEDIUM` finding.** `web/app/layout.tsx:42-46`:

```ts
export const viewport: Viewport = {
  themeColor: '#0a0a0f',
  width: 'device-width',
  initialScale: 1,
}
```

Missing `viewportFit: 'cover'`. Without this, on iOS notch devices (iPhone X+) the WebView leaves white bars at the top/bottom. Fix: add `viewportFit: 'cover'` to the viewport export.

`globals.css` was searched for `safe-area-inset` / `env(safe-area`. **0 matches.** The sticky topbar (`web/components/topbar.tsx`, `position: sticky; top: 0`) and any bottom-fixed elements will collide with the iOS home indicator / Android gesture bar. Recommend adding `padding-top: env(safe-area-inset-top)` to the topbar wrapper and `padding-bottom: env(safe-area-inset-bottom)` to any bottom-anchored UI (currently none — but B3 may add a bottom tab bar for mobile nav).

Hardware Android back button: **not handled.** No `backbutton` listener anywhere. With `@capacitor/app` installed, B3 should add a `useEffect` in the root layout (or a dedicated `useAndroidBackButton` hook) that calls `router.back()` on the event, falling back to `App.exitApp()` only when the route stack is empty.

## Recommended P0 fix order

1. **(P0, blocks any mobile QA)** Set `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_API_KEY` for the mobile build pipeline. Two paths:
   - Create `web/.env.local` with `NEXT_PUBLIC_API_BASE=https://crypto-signal-app-1fsi.onrender.com` and `NEXT_PUBLIC_API_KEY=<value>` for local mobile builds.
   - Strengthen `web/lib/api.ts` so a `BUILD_TARGET=mobile` build with no `NEXT_PUBLIC_API_BASE` fails the **build** (not the runtime). E.g. inside `next.config.mjs` validate the env when `BUILD_TARGET === "mobile"` and throw before Next starts. This cannot be circumvented by accident.
   - Re-run `npm run build:mobile` and re-verify `out/_next/static/chunks/*.js` contains `onrender.com` and **no** `localhost:8000`.
2. **(P0, blocks App Store / Play submission)** Update `web/capacitor.config.ts` `appId` from `com.polaris-edge.app` to `com.polaris.edge` per spec. Hyphens are technically allowed in package names but iOS guidelines and Android best-practice prefer dot-separated lowercase without hyphens.
3. **(P0, iOS notch UX)** Add `viewportFit: 'cover'` to `app/layout.tsx` `viewport` export and add `env(safe-area-inset-*)` padding to the topbar (and any future bottom nav) in `globals.css`.
4. **(P1, Android UX)** Add `@capacitor/app` and wire the `backButton` listener in the root layout. Closes a 100% reproducible UX bug on Android.
5. **(P1, B3 scope)** Plan + install `@capacitor/push-notifications`, `@capacitor/preferences`, `@capacitor/network`, biometric plugin. Migrate the `crypto-signal-app:user-level` `localStorage` key in `topbar.tsx` to `Preferences.get/set`.
6. **(P2, hardening)** Native allowlist:
   - iOS `Info.plist`: `NSAppTransportSecurity` allow `crypto-signal-app-1fsi.onrender.com` (or rely on the default ATS allow for valid HTTPS — likely fine since Render serves valid TLS).
   - Android `AndroidManifest.xml`: nothing needed for HTTPS; if any non-HTTPS dev API ever needs to work in WebView, add `android:usesCleartextTraffic="true"` only on debug builds (gate via `network_security_config.xml`).
7. **(P2)** Sanity-check: re-run `npm run build:mobile` after changes 1-3 and confirm:
   - `out/_next/static/chunks/*.js` contains the Render URL.
   - `out/_next/static/chunks/*.js` contains **zero** occurrences of `localhost:8000` or `localhost`.
   - `out/index.html` includes `viewport-fit=cover` in the `<meta name="viewport">`.

No code was modified during this audit.
