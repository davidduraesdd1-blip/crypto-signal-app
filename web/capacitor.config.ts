import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Polaris Edge — Capacitor configuration
 *
 * Wraps the Next.js static export in `out/` into native iOS + Android
 * shells. The `webDir` MUST point to the Next.js export output (`out/`),
 * which is produced by `npm run build:mobile` (BUILD_TARGET=mobile).
 *
 * Bundle ID: `com.polaris-edge.app` — must match what's registered in
 * App Store Connect (iOS) and Google Play Console (Android) when those
 * accounts are created (Day 4-5 of the mobile sprint).
 *
 * Adding platforms:
 *   - Android (any OS):  `npx cap add android`
 *   - iOS (macOS only):  `npx cap add ios`   (CocoaPods + Xcode required)
 *
 * Daily dev loop:
 *   - `npm run cap:sync`            — rebuild static export, copy into native shells
 *   - `npm run cap:open:android`    — open in Android Studio
 *   - `npm run cap:open:ios`        — open in Xcode (Mac only)
 *
 * Push notifications, biometric auth, etc. are added via separate plugin
 * packages in B3 (see Phase 1 plan). This config stays minimal until
 * those land.
 */
const config: CapacitorConfig = {
  appId: "com.polaris-edge.app",
  appName: "Polaris Edge",
  webDir: "out",
  server: {
    // HTTPS scheme inside the Android WebView so cookies + secure-context
    // APIs (crypto.subtle, getUserMedia for biometrics) work the same
    // way they do on the public Vercel build.
    androidScheme: "https",
  },
};

export default config;
