"""
tests/verify_deployment.py — automated smoke test against a live Streamlit deploy.

Usage
-----
    python tests/verify_deployment.py --env prod
    python tests/verify_deployment.py --url https://cryptosignal-ddb1.streamlit.app/

Restored 2026-04-28 from the audit baseline (P0 item 21). The original
script existed pre-2026-04-23 (per MEMORY.md "Deployment verification
baseline" entry — 5/5 passed) but went missing in the redesign-branch
churn before the redesign branch landed. This restoration matches the
documented 5-check shape so the §25 deployment verification protocol
keeps working unchanged.

Checks
------
1. Base URL reachable     — HTTP 200, latency reported.
2. No Python error sig    — body must NOT contain "Traceback", "RuntimeError",
                             "ModuleNotFoundError", "Streamlit error", etc.
3. Expected shell markers — body must contain "streamlit", "<script", "root".
4. All configured pages   — pulled from --pages (comma list); 0-page config
                             is fine for a single-page Streamlit app.
5. Health endpoint        — GET /_stcore/health → HTTP 200.

Exit codes
----------
0  — all checks passed
1  — at least one check failed (prints which)
2  — argument / configuration error

This script intentionally has only stdlib + requests dependencies so it can
run in CI without installing the full requirements.txt.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Tuple

try:
    import requests  # noqa: E402  — runtime dep, listed in requirements.txt
except ImportError:
    print("[verify_deployment] requests module not available — install via requirements.txt")
    sys.exit(2)


_DEFAULT_URLS = {
    "prod":    "https://cryptosignal-ddb1.streamlit.app/",
    "staging": "https://cryptosignal-ddb1.streamlit.app/",
    "local":   "http://localhost:8501/",
}

# Patterns that indicate the app crashed before fully rendering. Streamlit
# usually catches Python exceptions and renders them inside the page, so
# these strings showing up in the HTML body means something is wrong.
_ERROR_SIGNATURES = (
    "Traceback (most recent call last)",
    "RuntimeError",
    "ModuleNotFoundError",
    "ImportError",
    "AttributeError",
    "Streamlit error",
    "uncaught exception",
)

# Streamlit's HTML shell always contains these strings on a healthy render.
_SHELL_MARKERS = ("streamlit", "<script", "root")


def _check_base_url(url: str, timeout: float = 30.0) -> Tuple[bool, str]:
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=timeout)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    elapsed = time.perf_counter() - t0
    if r.status_code != 200:
        return False, f"HTTP {r.status_code} (latency {elapsed:.2f}s)"
    return True, f"HTTP 200 (latency {elapsed:.2f}s)"


def _check_no_errors(body: str) -> Tuple[bool, str]:
    for sig in _ERROR_SIGNATURES:
        if sig in body:
            return False, f"found error signature: {sig!r}"
    return True, "clean (no error signatures)"


def _check_shell_markers(body: str) -> Tuple[bool, str]:
    body_lc = body.lower()
    missing = [m for m in _SHELL_MARKERS if m.lower() not in body_lc]
    if missing:
        return False, f"missing markers: {missing}"
    return True, f"all shell markers present ({', '.join(_SHELL_MARKERS)})"


def _check_pages(base_url: str, pages: list[str], timeout: float = 30.0) -> Tuple[bool, str]:
    if not pages:
        return True, "0 pages configured — single-page app, skipping"
    base = base_url.rstrip("/") + "/"
    failed = []
    for page in pages:
        page_url = base + page.lstrip("/")
        try:
            r = requests.get(page_url, timeout=timeout)
            if r.status_code != 200:
                failed.append(f"{page} → HTTP {r.status_code}")
        except Exception as e:
            failed.append(f"{page} → {type(e).__name__}")
    if failed:
        return False, f"page failures: {failed}"
    return True, f"all {len(pages)} pages rendered"


def _check_health(base_url: str, timeout: float = 10.0) -> Tuple[bool, str]:
    health_url = base_url.rstrip("/") + "/_stcore/health"
    try:
        r = requests.get(health_url, timeout=timeout)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    return True, "HTTP 200"


def _resolve_url(env: str | None, url: str | None) -> str:
    if url:
        return url
    if env in _DEFAULT_URLS:
        return _DEFAULT_URLS[env]
    print(f"[verify_deployment] unknown env {env!r}; pass --url or one of {list(_DEFAULT_URLS)}")
    sys.exit(2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test a live Streamlit deploy of the Crypto Signal App."
    )
    parser.add_argument("--env", default="prod",
                        help=f"named environment (one of {list(_DEFAULT_URLS)})")
    parser.add_argument("--url", default=None,
                        help="explicit base URL — overrides --env")
    parser.add_argument("--pages", default="",
                        help="comma-separated list of page sub-paths to also fetch")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="per-request timeout in seconds (default 30)")
    args = parser.parse_args()

    base_url = _resolve_url(args.env, args.url)
    pages = [p.strip() for p in args.pages.split(",") if p.strip()]

    print(f"[verify_deployment] target: {base_url}")
    print(f"[verify_deployment] timeout: {args.timeout}s, pages: {pages or '(none)'}\n")

    # Check 1 — base URL reachable
    ok1, msg1 = _check_base_url(base_url, timeout=args.timeout)
    print(f"[1/5] base URL reachable        — {'PASS' if ok1 else 'FAIL'} — {msg1}")

    # Pull body once for content checks
    body = ""
    if ok1:
        try:
            body = requests.get(base_url, timeout=args.timeout).text
        except Exception:
            body = ""

    # Check 2 — no Python error signatures
    ok2, msg2 = _check_no_errors(body)
    print(f"[2/5] no error signatures       — {'PASS' if ok2 else 'FAIL'} — {msg2}")

    # Check 3 — Streamlit shell markers present
    ok3, msg3 = _check_shell_markers(body)
    print(f"[3/5] shell markers present     — {'PASS' if ok3 else 'FAIL'} — {msg3}")

    # Check 4 — all configured pages render
    ok4, msg4 = _check_pages(base_url, pages, timeout=args.timeout)
    print(f"[4/5] all pages render          — {'PASS' if ok4 else 'FAIL'} — {msg4}")

    # Check 5 — Streamlit /_stcore/health
    ok5, msg5 = _check_health(base_url, timeout=min(args.timeout, 10.0))
    print(f"[5/5] /_stcore/health           — {'PASS' if ok5 else 'FAIL'} — {msg5}")

    passed = sum([ok1, ok2, ok3, ok4, ok5])
    print(f"\n[verify_deployment] {passed}/5 checks passed")
    return 0 if passed == 5 else 1


if __name__ == "__main__":
    sys.exit(main())
