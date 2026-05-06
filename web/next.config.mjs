/** @type {import('next').NextConfig} */

// Capacitor B1 (2026-05-05): split build target for web (Vercel SSR) vs
// mobile (Capacitor static export). Vercel runs `npm run build` which
// keeps the SSR build. Mobile runs `npm run build:mobile` which sets
// BUILD_TARGET=mobile, producing a static export in `out/` that
// Capacitor wraps into the iOS/Android shells.
const isMobileBuild = process.env.BUILD_TARGET === "mobile";

// P0-2 fail-fast (audit 2026-05-05, Tier 7): mobile builds inline
// NEXT_PUBLIC_API_BASE / NEXT_PUBLIC_API_KEY into the static bundle.
// If they're unset, the `??` fallback in lib/api.ts collapses to
// "http://localhost:8000" at compile time and a packaged Capacitor
// app silently calls the dev's laptop instead of Render. We prefer a
// loud build failure over a silent runtime regression.
if (isMobileBuild) {
  const required = ["NEXT_PUBLIC_API_BASE", "NEXT_PUBLIC_API_KEY"];
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length) {
    const msg =
      `\n[next.config] Mobile build aborted — missing env vars:\n` +
      missing.map((k) => `  - ${k}`).join("\n") +
      `\n\nCopy web/.env.local.example to web/.env.local and fill in the values.\n`;
    throw new Error(msg);
  }
}

const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // Mobile builds need a static export so Capacitor can ship a fully
  // self-contained `out/` directory inside the native app bundle.
  // SSR features (route handlers, middleware, ISR) are not used here,
  // so the export is lossless. If they're ever added, this branch must
  // be revisited or those features must be guarded with BUILD_TARGET.
  ...(isMobileBuild
    ? {
        output: "export",
        trailingSlash: true,
      }
    : {}),
};

export default nextConfig;
