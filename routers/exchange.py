"""
routers/exchange.py — Exchange connection diagnostics.

Surfaces the existing `execution.test_connection()` helper as a REST
endpoint so the Settings · Execution page's "Test OKX Connection"
button can show a live connection status without placing any order.

D-extension batch (post-D1, pre-D4): closes the gap surfaced by the
D4 code-wire plan.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

import execution as exec_engine

from .deps import require_api_key
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/test-connection",
    summary="Test OKX API key connection without placing an order",
    dependencies=[Depends(require_api_key)],
)
def test_connection():
    """Validate the configured OKX API credentials.

    Calls the read-only balance fetch to verify auth + connectivity.
    Returns:
      - 200 with `{ok: true, balance_usdt, error: null}` on success
      - 200 with `{ok: false, balance_usdt: 0, error: <message>}` on
        credential or connectivity failure (frontend renders this as
        a soft warning, not an HTTP error)
      - 503 only if no keys are configured at all (operator action
        required before the test can run)
    """
    status = exec_engine.get_status()
    if not status.get("keys_configured", False):
        raise HTTPException(
            status_code=503,
            detail=(
                "OKX API keys are not configured. Set them in Settings · "
                "Execution before testing the connection."
            ),
        )
    try:
        result = exec_engine.test_connection()
    except Exception as exc:
        logger.warning("[exchange] test_connection raised: %s", exc)
        result = {"ok": False, "balance_usdt": 0.0, "error": str(exc)}
    return serialize(result)
