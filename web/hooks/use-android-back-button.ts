"use client";
/**
 * web/hooks/use-android-back-button.ts
 *
 * AUDIT-2026-05-06 (W2 Tier 7 P0): wire Capacitor's hardware back-button
 * event so the Android device back gesture navigates within the app
 * instead of exiting it. Without this, every press of the back button
 * dismisses the WebView regardless of in-app history. Capacitor's
 * `@capacitor/app` plugin exposes `backButton` events that we map to
 * `router.back()` when there's history, or to a "press back again to
 * exit" pattern when at the root.
 *
 * No-op on web (the listener never fires outside Capacitor's WebView).
 * No-op on iOS (no hardware back button).
 *
 * Mounted at the layout level so every page benefits.
 */
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const EXIT_HINT_WINDOW_MS = 2_000;

export function useAndroidBackButton() {
  const router = useRouter();
  const lastBackRef = useRef<number>(0);

  useEffect(() => {
    let removeListener: (() => void) | null = null;
    let cancelled = false;

    // Lazy-import — @capacitor/app is a no-op outside Capacitor and
    // throws if loaded server-side. The dynamic import keeps the
    // server bundle slim.
    (async () => {
      try {
        // Detect Capacitor runtime — bail on web/SSR.
        if (typeof window === "undefined") return;
        const cap = (window as unknown as { Capacitor?: { isNativePlatform: () => boolean } })
          .Capacitor;
        if (!cap || !cap.isNativePlatform()) return;

        const { App } = await import("@capacitor/app");
        const handle = await App.addListener("backButton", () => {
          // If browser history has entries, go back; else exit
          // gracefully (or show a "press again to exit" hint).
          if (typeof window !== "undefined" && window.history.length > 1) {
            router.back();
            return;
          }
          const now = Date.now();
          if (now - lastBackRef.current < EXIT_HINT_WINDOW_MS) {
            // Second press within window — exit the app.
            App.exitApp();
            return;
          }
          lastBackRef.current = now;
          // First press — show a brief toast hint. We keep this
          // dependency-free; pages that mount Sonner can intercept
          // via their own state if they want a styled toast.
          // eslint-disable-next-line no-console
          console.info("[backButton] press again to exit");
        });
        if (cancelled) {
          handle.remove();
          return;
        }
        removeListener = () => handle.remove();
      } catch (err) {
        // Fail silent — nothing to do on web. eslint-disable-next-line no-console
        console.debug("[useAndroidBackButton] not available:", err);
      }
    })();

    return () => {
      cancelled = true;
      removeListener?.();
    };
  }, [router]);
}
