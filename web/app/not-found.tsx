import Link from "next/link";

/**
 * AUDIT-2026-05-04 (H1): explicit 404 fallback so unrouted URLs don't
 * render a blank page. Next.js triggers this on any unmatched route.
 */
export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-md text-center">
        <div className="mb-4 font-mono text-5xl text-text-muted">404</div>
        <h1 className="mb-2 text-xl font-semibold text-text-primary">
          Page not found
        </h1>
        <p className="mb-6 text-sm text-text-secondary">
          The page you&rsquo;re looking for doesn&rsquo;t exist or has moved.
        </p>
        <Link
          href="/"
          className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
