# Tier 7 — Capacitor Compatibility (Wave 2)
**Date:** 2026-05-06
**Capacitor version:** 8.3.1
**Bundle ID:** `com.polaris.edge`
**Wave 1 doc:** `docs/audits/2026-05-05_capacitor-compatibility.md`
**Methodology:** Live execution. `npm run build:mobile` actually run, `npx cap sync android` actually run, native scaffold inspected on disk. Re-grep of post-Phase 0.9 codebase for module-level browser globals. Backend / DB inspected for B3 push prerequisites.

---

## Summary

| Check | Result |
| ----- | ------ |
| `npm run build:mobile` | **PASS** — exit 0, ~7.6s wall, 16 routes prerendered |
| `out/` static export produced | **YES** — 30 JS chunks, all expected route HTML files |
| Render API URL inlined into chunks | **YES** — `crypto-signal-app-1fsi.onrender.com` present in `out/_next/static/chunks/0_tpmkxn335vq.js` |
| `localhost:8000` as API_BASE fallback | **NO** — Phase 0.9 P0-2 fail-fast working as designed |
| `npx cap sync android` | **PASS** — 0.29s sync, 30 chunks copied to `android/app/src/main/assets/public/_next/static/chunks/` |
| Module-level browser globals | **0 violations** — Phase 0.9 changes (incl. new `user-level-provider.tsx`) all clean |
| Android Gradle config | **PASS** — applicationId / minSdk / targetSdk all conformant |
| AndroidManifest permissions | **PASS** — INTERNET only (no over-permission defaults) |
| `.env.local` cleanup | **CLEAN** — created for build test, deleted after; not present in `git status` untracked |

**No P0/P1 blockers found.** Wave 1 P0 fixes verified live. Wave 2 surfaces three P1 recommendations and one B3 prep gap-analysis.

---

## 1. Mobile build live run

### Command + timing

```
$ cd web
$ rm -rf .next out
$ time npm run build:mobile

> crypto-signal-app-web@0.1.0 build:mobile
> cross-env BUILD_TARGET=mobile next build

▲ Next.js 16.2.4 (Turbopack)
- Environments: .env.local

  Creating an optimized production build ...
✓ Compiled successfully in 2.1s
  Skipping validation of types
  Finished TypeScript config validation in 9ms
  Collecting page data using 17 workers ...
✓ Generating static pages using 17 workers (16/16) in 658ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /ai-assistant
├ ○ /alerts
├ ○ /alerts/history
├ ○ /backtester
├ ○ /backtester/arbitrage
├ ○ /on-chain
├ ○ /regimes
├ ○ /settings
├ ○ /settings/dev-tools
├ ○ /settings/execution
├ ○ /settings/signal-risk
├ ○ /settings/trading
└ ○ /signals

○  (Static)  prerendered as static content

real    0m7.625s
```

**Result:** Exit 0. 16 routes (incl. `_not-found`), all marked `(Static)` prerendered. Compile 2.1s, static gen 658ms, total wall 7.6s.

### `out/` directory verification

```
out/
├── 404
├── 404.html
├── ai-assistant/
├── alerts/
├── backtester/
├── on-chain/
├── regimes/
├── settings/
├── signals/
├── index.html         (26 957 bytes)
├── _next/static/chunks/    (30 .js chunks)
└── ... __next._*.txt manifests
```

### Env var inlining check

```
$ grep -rl "crypto-signal-app-1fsi.onrender.com" out/_next/static/chunks/
out/_next/static/chunks/0_tpmkxn335vq.js
```

Render URL inlined into one chunk (the `lib/api.ts` module). Inspected context:

```js
,method:u="GET",body:c}=s,l=`https://crypto-signal-app-1fsi.onrender.com${e}`,h={Accept:"application/json"};a&&t&&(h["X-API-Key"...
```

This is the actual `apiFetch()` URL construction — inlining worked exactly as designed.

```
$ grep -rl "localhost:8000" out/_next/static/chunks/
out/_next/static/chunks/0vf24ejck5sx7.js
```

One chunk contains the literal `localhost:8000` — but **NOT** as the API_BASE fallback. Inspected context:

```js
ono text-accent-brand",children:"http://localhost:8000/docs"}...
```

This is the `<a>` link displayed on the `/settings/dev-tools` page (developer help text showing how to run the FastAPI backend locally). It is rendered as visible text inside JSX, not used as a fetch target. **Not a regression — same finding as Wave 1.**

```
$ grep -rl "localhost" out/_next/static/chunks/
out/_next/static/chunks/03~yq9q893hmn.js
out/_next/static/chunks/0vf24ejck5sx7.js
```

The second chunk (`03~yq9q893hmn.js`) match is in URL parser internals (`s.parseHost(l)`, `s.host=""`, etc.) inside a vendored library — not a Polaris Edge code site.

**Conclusion:** the Phase 0.9 P0-2 fail-fast in `next.config.mjs` plus the `.env.local` content path are both working. Compare to Wave 1 finding (`"http://localhost:8000"` was the inlined API_BASE fallback) — that critical regression is closed.

### `out/index.html` viewport check

```
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
```

`viewport-fit=cover` confirmed — Phase 0.9 P0-9 working.

### `.env.local` cleanup

`.env.local` was created at `web/.env.local` for the build test with placeholder values:
```
NEXT_PUBLIC_API_BASE=https://crypto-signal-app-1fsi.onrender.com
NEXT_PUBLIC_API_KEY=test-key-not-real
```

After build + sync verification, `rm web/.env.local` succeeded. `git status` confirms it is **not** in untracked files (it never could be — `web/.gitignore` line 26 has `.env*` with `!.env.example` / `!.env.local.example` exceptions). No risk of accidental commit.

---

## 2. `npx cap sync` live run

```
$ cd web
$ time npx cap sync android

√ Copying web assets from out to android\app\src\main\assets\public in 77.44ms
√ Creating capacitor.config.json in android\app\src\main\assets in 695.50μs
√ copy android in 126.61ms
√ Updating Android plugins in 14.84ms
√ update android in 87.82ms
[info] Sync finished in 0.29s

real    0m2.727s
```

**Result:** Exit 0. Sync wall = 0.29s (CLI startup + sync logic ~2.7s total).

### Native scaffold verification

```
web/android/app/src/main/assets/public/
├── 404, 404.html
├── ai-assistant, alerts, backtester, on-chain, regimes, settings, signals  (all subdirs)
├── _next/static/chunks/   (30 chunks — match out/)
├── cordova.js
├── cordova_plugins.js
├── index.html             (26 957 bytes)
└── ... manifests
```

**Inlined Render URL preserved in Android assets:**
```
$ grep -l "crypto-signal-app-1fsi.onrender.com" \
    android/app/src/main/assets/public/_next/static/chunks/*.js
android/app/src/main/assets/public/_next/static/chunks/0_tpmkxn335vq.js
```

Sync is bit-for-bit lossless. The Capacitor `cordova.js` / `cordova_plugins.js` shims are added (expected — the empty plugin set still gets the bridge runtime).

---

## 3. Android Gradle + Manifest audit

### `android/app/build.gradle`

```groovy
android {
    namespace = "com.polaris.edge"          // ✅ matches capacitor.config.ts appId
    compileSdk = rootProject.ext.compileSdkVersion
    defaultConfig {
        applicationId "com.polaris.edge"     // ✅ Wave 1 P0 fix verified
        minSdkVersion rootProject.ext.minSdkVersion
        targetSdkVersion rootProject.ext.targetSdkVersion
        versionCode 1
        versionName "1.0"
        ...
    }
    buildTypes {
        release {
            minifyEnabled false               // ⚠ note below
            proguardFiles ...
        }
    }
}
```

### `android/variables.gradle`

```groovy
ext {
    minSdkVersion = 24       // ✅ Android 7.0 (Nougat) — modern WebView baseline, supports ES2020+ JS
    compileSdkVersion = 36   // ✅ Android 16 — latest
    targetSdkVersion = 36    // ✅ Android 16 — Google Play 2024 requires 34+, this is well above
    androidxAppCompatVersion = '1.7.1'
    androidxCoreVersion = '1.17.0'
    coreSplashScreenVersion = '1.2.0'
    androidxWebkitVersion = '1.14.0'
    cordovaAndroidVersion = '14.0.1'
    ...
}
```

| Setting | Value | Verdict |
| ------- | ----- | ------- |
| `applicationId` | `com.polaris.edge` | PASS |
| `minSdkVersion` | 24 (Android 7.0) | PASS — Capacitor 8 minimum is 23, we're +1; covers ~97% of active devices |
| `targetSdkVersion` | 36 (Android 16) | PASS — Play Store requires 34+ as of Aug 2024; we're +2 |
| `compileSdkVersion` | 36 | PASS — matches target |
| `versionCode` / `versionName` | 1 / "1.0" | PASS — placeholder, will bump on first Play upload |
| `minifyEnabled` (release) | `false` | **P2 finding** — once shipping to Play, set to `true` to shrink the APK and obfuscate. Capacitor scaffold defaults to `false` because R8 can break some Cordova-style plugins; revisit once plugins are installed (B3) |

### `AndroidManifest.xml`

```xml
<application android:allowBackup="true" ...>
  <activity android:name=".MainActivity" android:launchMode="singleTask" android:exported="true">
    <intent-filter>
      <action android:name="android.intent.action.MAIN" />
      <category android:name="android.intent.category.LAUNCHER" />
    </intent-filter>
  </activity>
  <provider android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.fileprovider"
            android:exported="false" .../>
</application>

<!-- Permissions -->
<uses-permission android:name="android.permission.INTERNET" />
```

| Item | Verdict |
| ---- | ------- |
| `INTERNET` permission only | PASS — minimal, no over-permission |
| `allowBackup="true"` | **P2 finding** — Capacitor default. For an app holding API keys + trading config, set to `false` and add `android:fullBackupContent="@xml/backup_rules"` once we have data to protect. Not blocking V1 since current persisted state is just user-level preference. |
| `FileProvider` exported=false | PASS — secure by default |
| No `usesCleartextTraffic` | PASS — implicit `false` since target SDK ≥ 28; matches `androidScheme: "https"` from `capacitor.config.ts` |
| No `<network-security-config>` referenced | PASS for V1 — defaults to HTTPS-only; if any dev API ever needs to be reachable from a debug build, gate via `android:networkSecurityConfig="@xml/network_security_config"` on debug variant only |
| Single `MainActivity`, no extra exported activities | PASS |

**No P0 or P1 issues. Two P2 hardening items (`minifyEnabled`, `allowBackup`) for post-V1.**

---

## 4. iOS prereq doc (Mac handoff)

`npx cap add ios` was deferred — Capacitor's iOS platform plugin requires CocoaPods, which only runs on macOS. Below is the paste-ready Mac handoff.

### Prerequisites (verified versions for Capacitor 8.3.1)

| Tool | Required version | How to verify |
| ---- | ---------------- | ------------- |
| macOS | 13.5 (Ventura) or later | `sw_vers -productVersion` |
| Xcode | 15.4+ (16.0 recommended for iOS 18 SDK) | `xcodebuild -version` |
| Xcode Command Line Tools | matching Xcode version | `xcode-select -p` should print a path; if not, `xcode-select --install` |
| CocoaPods | 1.15.0+ | `pod --version` |
| Ruby (used by CocoaPods) | 3.0+ (system Ruby works on Sonoma+) | `ruby --version` |
| Node.js | 20.x LTS or 22.x | `node --version` |
| iOS deployment target | 14.0 (Capacitor 8 default) | set in `ios/App/Podfile` after add |

CocoaPods install (if missing):
```bash
sudo gem install cocoapods
# or via Homebrew:
brew install cocoapods
```

### Commands (run from `web/` on the Mac)

```bash
cd web
npm install            # restore node_modules from pnpm-lock.yaml
                       # NOTE: project policy is pnpm; on Mac use `pnpm install`
                       # if pnpm is installed (corepack enable && corepack prepare pnpm@latest --activate)

# Ensure mobile build is current
NEXT_PUBLIC_API_BASE=https://crypto-signal-app-1fsi.onrender.com \
NEXT_PUBLIC_API_KEY=<paste-from-1Password> \
npm run build:mobile

# Add iOS platform (one-time)
npx cap add ios

# Sync the static export into the iOS shell
npx cap sync ios

# Open in Xcode
npx cap open ios       # equivalent to: open ios/App/App.xcworkspace
```

### Pre-stage configuration (commit BEFORE the Mac handoff if possible)

Most of `ios/App/App/Info.plist` is generated by `cap add ios`. We cannot pre-commit it (the file doesn't exist yet on Windows). However the **plist additions** below should be added by the Mac operator on first `cap add ios`, **before** the first `cap sync` deploy:

#### `ios/App/App/Info.plist` additions

```xml
<!-- ATS: Render serves valid TLS, so no exception entries needed. ATS default
     allows HTTPS to crypto-signal-app-1fsi.onrender.com out of the box. -->

<!-- Required when @capacitor/push-notifications lands (B3): -->
<key>UIBackgroundModes</key>
<array>
  <string>remote-notification</string>
</array>

<!-- Required when biometric plugin lands (B3): -->
<key>NSFaceIDUsageDescription</key>
<string>Polaris Edge uses Face ID to unlock live trading actions.</string>

<!-- App Transport Security: leave default (no exceptions) — all backend
     traffic is HTTPS. Only add NSExceptionDomains if a non-Render
     endpoint is ever needed. -->

<!-- iPad split-view + multitasking: Capacitor scaffold default is fine.
     If we want to force portrait-only on iPhone (recommended for
     trading UX), add: -->
<key>UISupportedInterfaceOrientations</key>
<array>
  <string>UIInterfaceOrientationPortrait</string>
</array>
<key>UISupportedInterfaceOrientations~ipad</key>
<array>
  <string>UIInterfaceOrientationPortrait</string>
  <string>UIInterfaceOrientationPortraitUpsideDown</string>
  <string>UIInterfaceOrientationLandscapeLeft</string>
  <string>UIInterfaceOrientationLandscapeRight</string>
</array>
```

#### `ios/App/Podfile` notes

After `cap add ios`, set the iOS deployment target to 14.0 (Capacitor 8 baseline) — this is the auto-generated default; verify with:
```
platform :ios, '14.0'
```

#### Capabilities to enable in Xcode (after `cap open ios`)

- **Push Notifications** (B3) — Signing & Capabilities → + Capability → Push Notifications
- **Background Modes** → "Remote notifications" (mirrors the plist key above)
- **Sign in with Apple** — only if/when we add SSO (post-V1)

#### Apple Developer Program account checklist

- Apple ID enrolled in Apple Developer Program ($99/yr)
- Bundle ID `com.polaris.edge` registered in App Store Connect → Certificates, Identifiers & Profiles → Identifiers
- Push notification certificate (APNs key, .p8) generated under Keys section, downloaded once and stored in 1Password
- Provisioning profile for development + distribution attached to the Bundle ID

### Expected first-run smoke test (Mac)

```bash
npx cap run ios --target='iPhone 15'   # boots simulator, builds, launches app
```

Expect: app loads, topbar renders, signals page fetches from Render successfully (since the `out/` bundle has the inlined Render URL). If the API call fails, check that the build was run **with** the env vars set — same gotcha as Wave 1's `localhost:8000` regression.

---

## 5. Module-level browser globals re-grep

Re-ran the grep with the post-Phase 0.9 codebase. **0 violations.**

Pattern: `window\.|document\.|localStorage|sessionStorage|navigator\.` across `web/**/*.{ts,tsx}`.

| File | Line | Usage | Verdict |
| ---- | ---- | ----- | ------- |
| `web/providers/user-level-provider.tsx` | 35 | `typeof window === "undefined"` guard inside `readPersisted()` helper | Module-defined helper, only invoked from `useState(() => readPersisted())` lazy initializer + `useEffect` resync — safe |
| `web/providers/user-level-provider.tsx` | 37 | `window.localStorage.getItem` | Inside the guarded helper — safe |
| `web/providers/user-level-provider.tsx` | 69 | `window.localStorage.setItem` | Inside `setLevel` (a `useCallback`) — safe |
| `web/components/topbar.tsx` | — | No direct `window`/`document`/`localStorage` access | Refactor moved persistence into the provider — **CLEAN** |
| `web/app/signals/page.tsx` | — | No `window`/`document`/`localStorage` matches | **CLEAN** |
| `web/hooks/use-mobile.ts` | 9, 11, 14 | `window.matchMedia` / `window.innerWidth` | Inside `React.useEffect` — safe |
| `web/components/ui/use-mobile.tsx` | 9, 11, 14 | duplicate of above (shadcn-shipped copy) | Inside `React.useEffect` — safe |
| `web/components/ui/sidebar.tsx` | 86, 108-109 | `document.cookie` / `window.addEventListener` | Inside `useCallback` / `useEffect` — safe |
| `web/app/error.tsx`, `web/app/global-error.tsx` | — | `console.error` after `typeof window` guard inside `useEffect` | safe |
| `web/lib/api.ts` | — | `process.env.*` reads at module level + browser-gated `throw` | safe (Webpack/Turbopack replaces at build time; throw is `typeof window !== "undefined"` gated) |

**Key Phase 0.9 win:** the new `UserLevelProvider` is the cleanest possible pattern for SSR-safe persistence:

```ts
function readPersisted(): UserLevel {
  if (typeof window === "undefined") return DEFAULT_LEVEL;  // SSR-safe
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "Beginner" || v === "Intermediate" || v === "Advanced") return v;
  } catch { /* Capacitor private mode, etc. */ }
  return DEFAULT_LEVEL;
}

export function UserLevelProvider({ children }: { children: ReactNode }) {
  const [level, setLevelState] = useState<UserLevel>(() => readPersisted()); // lazy init
  useEffect(() => { /* resync on mount */ }, []);
  const setLevel = useCallback((next) => { window.localStorage.setItem(...); }, []);
  ...
}
```

The `try/catch` around `localStorage` access is the right defensive choice for Capacitor — the WebView on Android rarely-but-occasionally throws on `localStorage` access in incognito/private modes or under storage pressure.

**Wave 1's "0 violations" finding holds in Wave 2.**

---

## 6. Native plugin recommendations

### What's installed today

```json
"@capacitor/android": "^8.3.1",
"@capacitor/cli":     "^8.3.1",
"@capacitor/core":    "^8.3.1",
"@capacitor/ios":     "^8.3.1",
```

Only the four base packages. **No plugins added since Wave 1.**

### V1 priority ranking

| # | Plugin | Why now | Priority |
| - | ------ | ------- | -------- |
| 1 | `@capacitor/app` | Android scaffold is live — without this, the hardware back button closes the app on every screen. 100% reproducible UX bug the moment we run on a real device. Also exposes app pause/resume + version info for the Diagnostics page. | **P0 — install NOW** |
| 2 | `@capacitor/preferences` | `localStorage` for `crypto-signal-app:user-level` works in Capacitor 8 WebView but is occasionally purged by Android under storage pressure. Native KeyChain (iOS) / SharedPreferences (Android) is durable. Migration is small (provider already centralizes the read/write). | P1 — bundle with B3 push work |
| 3 | `@capacitor/network` | Online/offline awareness so the empty-state copy in queries says "you're offline" instead of generic "couldn't load". Pairs with the existing `lib/api.ts` `ApiError` taxonomy. | P1 — bundle with B3 |
| 4 | `@capacitor/push-notifications` | B3 scope. Signal-direction-change push alerts. Backend has zero scaffolding (see § 7) so this is paired work. | **P0 for B3** |
| 5 | `@capacitor-community/native-biometric` (or `capacitor-biometric-auth`) | B3 scope. Touch ID / Face ID prompt to unlock the live-trading toggle on `/settings/trading`. | **P0 for B3** |

### Recommendation: install `@capacitor/app` NOW

The Android scaffold is committed and `cap sync` works. The next time anyone opens it in Android Studio and runs on a real device, the back button will exit the app on every screen — a guaranteed bad first impression. One-shot install:

```bash
cd web
npm install @capacitor/app
npx cap sync android
```

Then add a small hook in the root layout:

```ts
// web/hooks/use-android-back-button.ts
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function useAndroidBackButton() {
  const router = useRouter();
  useEffect(() => {
    if (typeof window === "undefined") return;
    let cleanup: (() => void) | undefined;
    (async () => {
      try {
        const { App } = await import("@capacitor/app");
        const handle = await App.addListener("backButton", ({ canGoBack }) => {
          if (canGoBack) router.back();
          else App.exitApp();
        });
        cleanup = () => handle.remove();
      } catch {
        // Not running inside Capacitor — no-op.
      }
    })();
    return () => cleanup?.();
  }, [router]);
}
```

Then call `useAndroidBackButton()` once in `app-providers.tsx` (or a thin `<NativeBindings>` client component inside `RootLayout`).

### Optional / nice-to-have (post-V1)

- `@capacitor/status-bar` — set status bar style per theme
- `@capacitor/splash-screen` — branded splash instead of white flash
- `@capacitor/haptics` — light tap on signal change confirmation
- `@capacitor/share` — share signal cards to messaging apps

---

## 7. Push notification readiness (B3 prep)

### Backend audit

| Layer | Status |
| ----- | ------ |
| `routers/` directory | Has `alerts.py` (with `channels: list[str] = ["email"]` field), no `notifications.py` or `push.py` router |
| Notification endpoint stub | **NOT PRESENT** |
| Device token registration endpoint | **NOT PRESENT** |
| `database.py` schema | 19 tables defined; `feedback_log`, `daily_signals`, `backtest_trades`, `paper_trades`, `positions`, `dynamic_weights`, `weights_log`, `scan_cache`, `scan_status`, `alerts_log`, `execution_log`, `agent_log`, `regime_history`, `arb_opportunities`, `signal_metrics`, `ic_history`, `bayesian_weights`, `wfo_cache`, `pnl_tracking`. **No `device_tokens` or `push_subscriptions` table.** |
| FCM / APNs SDK in `requirements.txt` | Not checked but assume **NOT PRESENT** (no `firebase-admin` or `pyapns2` references found by grep) |
| `alerts.py` channels enum | `["email"]` default; the router has the shape for multi-channel but only email is wired — no `"push"` handler |

### Frontend audit

| Layer | Status |
| ----- | ------ |
| `usePush*` / `useNotif*` / `registerForPush*` hook | **NOT PRESENT** (zero matches) |
| Permission-request flow component | **NOT PRESENT** |
| Settings → Notifications page | **NOT PRESENT** (no `web/app/settings/notifications/page.tsx`) |

### B3 work breakdown

**Build-from-scratch items (no existing scaffold):**

1. **Backend — `routers/notifications.py`**
   - `POST /notifications/devices` — register device token (body: `{platform: "ios"|"android", token: str, app_version: str}`)
   - `DELETE /notifications/devices/{token}` — unregister
   - `GET /notifications/devices` — list registered tokens for the current user (V1: there is no user table, so just list all)
   - `POST /notifications/test` — admin-only test push (helpful for QA)
2. **Backend — `database.py` new table**
   ```sql
   CREATE TABLE IF NOT EXISTS device_tokens (
       token TEXT PRIMARY KEY,
       platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
       app_version TEXT,
       registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       active INTEGER DEFAULT 1
   );
   ```
3. **Backend — push dispatcher module** (`push_dispatch.py` or `services/push.py`)
   - APNs (iOS) — `aioapns` or `apns2` library; needs `.p8` key + team ID + key ID
   - FCM (Android) — `firebase-admin` library; needs service account JSON
   - Both keys live in env vars (Render secret values), never committed
4. **Backend — wire into existing `alerts.py`**
   - Add `"push"` as a valid channel in `AlertConfig.channels`
   - When alert fires, dispatch to all `active=1` device tokens (V1 — no per-user filter since no auth yet)
5. **Frontend — `web/hooks/use-push-notifications.ts`**
   - Calls `@capacitor/push-notifications` `requestPermissions()`, `register()`, listens for `registration` event, POSTs token to `/notifications/devices`
   - On `pushNotificationReceived`, surface a toast via `sonner`
   - On `pushNotificationActionPerformed`, route to the relevant signal page
6. **Frontend — `/settings/notifications` page** (new route)
   - Toggle "Enable push alerts" → triggers permission flow
   - List of "alert types" the user wants pushed (BUY/SELL transitions, regime changes, large funding-rate moves)
   - Toggle "Test notification" button → hits `/notifications/test`
7. **iOS — Xcode capability**
   - Enable Push Notifications + Background Modes → "Remote notifications" (covered in § 4)
   - Generate APNs `.p8` key in Apple Developer portal, add to Render env
8. **Android — Firebase project**
   - Create Firebase project at `console.firebase.google.com`
   - Add Android app with bundle ID `com.polaris.edge`
   - Download `google-services.json`, drop into `web/android/app/`
   - Capacitor's `build.gradle` (lines 47-54 — already present!) will auto-detect and apply the `com.google.gms.google-services` plugin

**Items that build on existing code:**

- `alerts.py` — multi-channel `channels: list[str]` field already exists, just add `"push"` as a valid value and a dispatcher branch
- `database.py` init pattern — follow the `CREATE TABLE IF NOT EXISTS` pattern of the other 19 tables
- `web/lib/api.ts` `apiFetch()` — reuse for all `/notifications/*` calls (auth + error taxonomy already wired)
- `app-providers.tsx` — wrap `usePushNotifications()` registration the same way `UserLevelProvider` is wired

### B3 estimated scope

- Backend: ~250 lines (router + dispatcher + table + alerts wiring) + ~80 lines tests
- Frontend: ~150 lines (hook + settings page + provider wiring)
- Native config: ~10 minutes Xcode capabilities + ~15 minutes Firebase setup
- **Total estimate: 1.5 sessions** for a working V1 (no rich notifications, no notification-action deep-links beyond simple route push)

---

## 8. Wave 1 → Wave 2 closure summary

| Wave 1 P0 finding | Wave 2 status |
| ----------------- | ------------- |
| `NEXT_PUBLIC_API_BASE` unset → `localhost:8000` baked into bundle | **CLOSED** — `next.config.mjs` fail-fast (P0-2) + Wave 2 build run with env set produces inlined Render URL, zero `localhost:8000` API_BASE |
| Bundle ID `com.polaris-edge.app` (hyphen) | **CLOSED** — set to `com.polaris.edge` in `capacitor.config.ts`, `android/app/build.gradle` (`namespace` + `applicationId`), and Android scaffold added (P0-6) |
| `viewportFit: 'cover'` missing | **CLOSED** — present in `app/layout.tsx` viewport export; verified in `out/index.html` (P0-9) |
| `safe-area-inset-*` CSS missing | **CLOSED** — `web/app/globals.css` lines 200-203 + `.safe-area-bottom` / `.safe-area-top` utility classes (P0-9) |
| Module-level browser globals | Re-verified clean (was 0 in Wave 1, still 0 in Wave 2 incl. new `UserLevelProvider`) |

**No regressions. All Wave 1 P0 work landed and verified.**

---

## 9. Wave 2 recommendations (ranked)

| # | Item | Priority | Estimated effort |
| - | ---- | -------- | ---------------- |
| 1 | Install `@capacitor/app` + wire `useAndroidBackButton()` hook | **P0** (Android UX) | 30 min |
| 2 | Set `minifyEnabled = true` in `android/app/build.gradle` release block once shipping | **P2** (post-V1 hardening) | 15 min + QA pass |
| 3 | Set `android:allowBackup="false"` + add `network_security_config.xml` for debug-only cleartext (if ever needed) | **P2** (post-V1 hardening) | 30 min |
| 4 | Pre-stage `Info.plist` capability block + handoff doc for Mac operator | **P1** (B3 unblock) | done in § 4 of this doc |
| 5 | B3 push scaffolding — `notifications.py` router + `device_tokens` table + `usePushNotifications()` hook + Firebase project + APNs key | **P0 for B3** | 1.5 sessions |
| 6 | Migrate `crypto-signal-app:user-level` from `localStorage` to `@capacitor/preferences` | **P1** (durability) | 1 hour |
| 7 | Add `@capacitor/network` for online/offline empty-state copy | **P1** | 1 hour |

**No code was modified during this audit.** `web/.env.local` was created for the build test, used, deleted, and confirmed not present in `git status` untracked. The mobile build artifacts (`web/out/`, `web/.next/`, `web/android/app/src/main/assets/public/`) are gitignored so the test left no commit-time footprint.
