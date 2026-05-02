"""
routers/utils.py — shared helpers for the Phase D FastAPI routers.

Mirrors the helpers in api.py so the new routers don't have to import
from a top-level module that may grow further surface area. The
duplication is intentional and explicit in the D1 audit:

  > Reuse _serialize, _clean_scalar, _normalize_pair helpers from
  > api.py — extract these to a routers/utils.py once a second
  > router needs them.

A future D-extension batch may consolidate by replacing the api.py
copies with `from routers.utils import ...`. D1 deliberately does not
refactor api.py.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def clean_scalar(obj: Any) -> Any:
    """Convert numpy/pandas scalars to native Python types.

    NaN and Inf are replaced with None so consumers can distinguish
    "missing data" from "zero" — consistent with api.py._clean_scalar
    and app.py._numpy_serializer.
    """
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def serialize(obj: Any) -> Any:
    """Recursively make a dict/list JSON-safe for FastAPI responses."""
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, tuple):
        return [serialize(i) for i in obj]
    if isinstance(obj, pd.DataFrame):
        return serialize(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return serialize(obj.tolist())
    return clean_scalar(obj)


def normalize_pair(raw: str) -> str:
    """Accept BTCUSDT, BTC-USDT, BTC_USDT, BTC/USDT, BTC-USDT-SWAP → BTC/USDT.

    Mirrors api.py._normalize_pair. Raises ValueError on invalid input
    so callers can re-raise as 422.
    """
    s = (raw or "").upper().strip()
    for suffix in ("-SWAP", ":USDT", ":USDC", "PERP", "_PERP"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    s = s.replace("_", "/").replace("-", "/")
    if "/" not in s:
        for quote in ("USDT", "USDC", "BTC", "ETH", "BNB"):
            if s.endswith(quote) and len(s) > len(quote):
                s = s[: -len(quote)] + "/" + quote
                break
    if "/" not in s:
        raise ValueError(f"Cannot normalise pair: {raw!r}")
    base, quote = s.split("/", 1)
    if not base or not quote or not all(c.isalnum() for c in base) or not quote.isalpha():
        raise ValueError(f"Invalid pair after normalisation: {s!r} (from {raw!r})")
    return s
