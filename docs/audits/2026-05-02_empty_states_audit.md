# Empty-State and Error-Message Audit — Crypto Signal App

**Date:** 2026-05-02
**Scope:** every Python file in project root + `ui/`. Focused on what the user
sees when data is missing or a fetch fails.
**Trigger:** user has now flagged this twice. First in the legacy-look audit
(images 1, 7, 8) and again in `feedback_empty_states.md`:
> "Empty states should use truthful labels — say 'geo-blocked', 'rate
> limited', 'run a scan to populate' instead of silent 'None' / '—'."
**Standards:** CLAUDE.md §8 (no exception traces; plain English with next
action) and CLAUDE.md §7 (detail scales with user level).

---

## TL;DR

Three structural problems, repeated across the app:

1. **Status pills lie.** Every page-header pill is hardcoded to `"live"`
   or `"cached"` regardless of whether the upstream actually responded.
   When Glassnode is rate-limited or Binance is geo-blocked from US
   Streamlit Cloud, the pill still says "live" while the cards under it
   render `"—"`. (Image 8 headline bug.)
2. **`"—"` is overloaded.** It currently means *any* of: "loading",
   "no scan yet", "geo-blocked", "rate-limited", "API key not set",
   "this metric isn't tracked for this asset", or "value is genuinely
   zero". The user can't tell which.
3. **Silent except-pass swallows errors.** 54 `except: pass` and 19
   `except: return None` sites across the codebase strip the failure
   reason at the source. By the time data reaches the UI there is no
   way to render a truthful label even if we wanted to — the cause is
   already gone.

The good news: data feeds already produce structured failure metadata
(`_empty_result(reason, ts)` in data_feeds.py:412 and `_no_key_result`
at data_feeds.py:1783). The UI just throws it away. Wiring is the fix,
not new plumbing.

---

## Reproducible patterns

### Pattern A — hardcoded `"live"` status pill

**Files:** `app.py` (4 occurrences)

| File:line | Pill claim | Reality (today) |
|-----------|------------|-----------------|
| `app.py:2247-2251` (Dashboard) | OKX live, Glassnode live, News cached | OKX may be rate-limited; Glassnode requires a key (returns `_no_key_result` if absent); news status not checked |
| `app.py:7556-7560` (Signals) | OKX live, Glassnode live, News cached | same |
| `app.py:8219-8223` (Regimes) | OKX live, Glassnode live, FRED cached | same; FRED never checked |
| `app.py:8617-8621` (On-chain) | Glassnode live, Dune cached, Native RPC live | **Image 8 headline lie** — none of these are checked. The cards underneath rendered all `"—"` while pill said "live". |

These literals live directly in the page render block, no health probe.
Severity: **critical**. Pills are the primary "is this working?" signal
for the user.

### Pattern B — `None` displayed literally in funding-rate table

**File:** `app.py:6841-6868` (Funding Rate Monitor)

```python
row[exch.upper()] = None if rd.get("error") else rate
```

When OKX/Binance/Bybit/KuCoin returns an error, the cell is set to
Python `None` and rendered as the literal string `None` in the
dataframe. The error reason was structured (`rd.get("error")` is one
of: "Funding N/A (spot pair or geo-blocked)", "OKX N/A", "Bybit N/A",
"KuCoin: rate limited", "KuCoin: no symbol mapping", etc. from
data_feeds.py:412+) — but it gets discarded.

Caption underneath says "N/A = geo-blocked or pair not listed on that
exchange" (app.py:6908) but the cell shows "None", not "N/A". So the
caption refers to a value that never appears.

Severity: **critical** (Image 7 headline bug — user explicitly flagged).

### Pattern C — bare `"—"` for "no value" with no cause distinction

54 sites in app.py + ui_components.py + ui/sidebar.py + alerts.py +
pdf_export.py. Listed exhaustively below in the by-screen breakdown.

The em-dash is canon (utils_format.py:20 `_EM_DASH = "—"` and the
`_is_missing()` helper). The convention is consistent — that's the
problem. It's now one symbol for all 6+ failure modes.

### Pattern D — silent except-swallow

Counts (`except: pass` / `except: return None|[]|{}`):

| File | `except: pass` | `return None`/`[]` |
|------|----|----|
| `app.py` | 16 | 16 |
| `data_feeds.py` | 10 | 9 (excluding internal) |
| `ui_components.py` | 3 | 1 |
| `crypto_model_core.py` | 7 | 4 |
| `alerts.py` | 4 | 0 |
| `whale_tracker.py` | 1 | 22 (every chain handler) |
| `news_sentiment.py` | 0 | 13 |
| `arbitrage.py` | 0 | 15 |
| (others) | 13 | — |

Many of these are benign control-flow (e.g. fallback-chain "try OKX
then Binance then Bybit"). The harmful ones are the **outer-loop
swallows** that wrap an entire page render and return empty — the user
sees a blank section with no clue what failed.

Examples below.

---

## By screen / section

### 1. Hero / dashboard cards (Image 1)

**Files:** `app.py:2463-2516`, `ui/sidebar.py:540-622`

| File:line | Symptom | Why ambiguous | Truthful replacement |
|-----------|---------|---------------|----------------------|
| `ui/sidebar.py:553` | `price_str = "—"` when price is None | Could be: cold-start (no scan yet), pair has no OKX SWAP market (XDC/SHX/ZBCN — known per legacy audit Image 1), WebSocket not connected, cascade rate-limited | "Fetching…" if still loading; "Not on this venue" if pair-not-listed; "Cached 12m" if only cascade has data |
| `ui/sidebar.py:564, 675` | `change_str = "—"` when change_pct is None | Same as above — can also mean spot-only pair with no 24h reference window | Match the price label so the two never disagree |
| `app.py:2472` | `signal=_ds_signal_label(r) if r else None` | `r={}` means "no scan result for this pair yet" — but the badge just disappears, no copy | "Run a scan" badge or "Pending first scan" caption |
| `app.py:2473-2474` | `regime_label`, `regime_confidence` are blank if no scan | Same — no copy explaining why | "Pending first scan" pill in the regime line |
| `ui/sidebar.py:634, 663` | `r.get("ticker", "—")` in watchlist | Should never trigger (caller always sets ticker), but the placeholder is wrong | If this fires it's a programming error — log a debug and use "(missing)" or skip the row |

Severity for hero cards: **medium-high** (they are the first thing the
user sees on Home).

### 2. Macro strip (Image 1, lower hero)

**File:** `app.py:2349-2360`

| File:line | Symptom | Why ambiguous | Truthful replacement |
|-----------|---------|---------------|----------------------|
| `app.py:2352` | `str(int(_fng)) if _fng is not None else "—"` | F&G API failed (alternative.me returns 24h cache normally) — but cache could also be stale | "Cached 23h ago" or "Fear & Greed: API offline" |
| `app.py:2354` | DXY shown as `"—"` if yfinance failed | yfinance is the only source; if it's down everything DXY-related goes missing simultaneously | "DXY feed offline (yfinance)" |
| `app.py:2356` | Funding 0.000% rendered with no qualifier | Could be a real near-zero rate or could be the `_empty_result` 0.0 default | The data_feeds layer already distinguishes — surface `error` field as a tooltip |
| `app.py:2358` | `_macro_regime` shown as `"—"` | Means enrichment hasn't run AND the inline derivation also bailed | "Pending first scan" with "▶ Run scan" link |

### 3. Signal-detail & sub-cards (Image 3 — XRP detail)

**File:** `app.py:7752-8169`, `ui_components.py:4101+`

| File:line | Symptom | Why ambiguous | Truthful replacement |
|-----------|---------|---------------|----------------------|
| `app.py:7752` | composite score `"—"` | No scan yet vs scan failed mid-run | "Pending first scan" / "Scan errored — see logs" |
| `app.py:7896, 7913, 7921, 7930, 7936` | unlock signal `"—"` | Could be: cryptorank API key missing (token unlocks), pair not in cryptorank universe, rate-limited | Token-unlock fetcher returns a structured `signal` field already (NO_UNLOCK / N/A / UNLOCK_SOON) — surface that |
| `app.py:7910` | `_unlock_signal = "None"` (literal) | Should say "No vesting in next 30d" | Replace literal `"None"` with "None scheduled" or "No upcoming unlock" |
| `app.py:8084-8169` | `_v(..., fmt) if x is not None else "—"` for ATR, MACD, RSI, exch reserve, active addr | Indicator wasn't computed yet (cold-start), or fetcher failed | Two distinct labels: "Pending scan" vs "Source unavailable" |
| `app.py:7940-7941` | ATR `"—"`, Beta `"—"` | Same as above | (Image 3 nit: ATR shows `$0` instead of `"—"` — formatter inconsistency in legacy audit) |
| `ui_components.py:4101` | Funding gauge skipped if `_fund in ("N/A", "—", "")` | Silently hides the gauge — user doesn't know whether it's loading or unavailable | Render the gauge with a "Funding source unavailable" caption |

### 4. Backtester / Arbitrage tables (Images 5, 7)

**File:** `app.py:6680-6790, 6840-6953, 6970-7000`

| File:line | Symptom | Why ambiguous | Truthful replacement |
|-----------|---------|---------------|----------------------|
| `app.py:6687-6690` | Buy On / Sell On / Buy/Sell Price `"—"` | Image 5 user-confirmed bug: only populated when Signal != NO_ARB. User wants min/max-price exchange even on NO_ARB rows | (Functional fix outside this audit's scope) Show the min/max regardless |
| `app.py:6759` | `st.info("No spot prices returned — check network connectivity.")` | Could be no exchanges returned ANY price (real network) or arbitrage scanner module failed to import | Distinguish: "Arbitrage module failed to load" (logger.exception path) vs "Exchanges all geo-blocked or rate-limited" |
| `app.py:6789` | `"No funding-rate opportunities found above threshold."` | Decent message — but doesn't distinguish "we got data, none qualifies" from "every funding fetch errored" | Append a parenthetical: "(checked N pairs across M exchanges)" |
| `app.py:6852` | **The `None` cell** — `row[exch.upper()] = None if rd.get("error") else rate` | Image 7 headline bug. The `error` reason from `_empty_result()` is discarded | Replace with: `"geo-blocked"` / `"rate-limited"` / `"not listed"` / `"key missing"` per the structured error |
| `app.py:6867` | `row["Best Rate"] = "—"` when no valid exchange | All 4 exchanges errored — but the user sees "—" identical to "data missing" | "All sources failed — see Funding column for details" |
| `app.py:6908` | Caption "N/A = geo-blocked…" but cells display "None" | Caption refers to symbol that never appears | Either change cells to "N/A" or change caption to "None = geo-blocked or…" — actually just use truthful labels per cell so caption isn't needed |
| `app.py:6953` | `"No carry trade opportunities above 0.01% threshold for the selected pairs."` | Could be 0 valid rates returned vs 0 rates above threshold | Append "(N pairs returned valid rates)" |
| `app.py:6980, 6982` | Hyperliquid Mark Price `"—"`, Open Interest `"—"` | Image 7 bug 3: funding shows +0.0000% with real OI — parser may be broken | Functional bug outside this audit. UI-side: surface `d.get("error")` if present |
| `app.py:6999` | `"No Hyperliquid data returned for the selected pairs."` | Could mean parser broken vs Hyperliquid down | Surface error from the dict directly |
| `app.py:6513-6514` | Pair backtest result rows show `"—"` for Return/PnL/MaxDD/Vol with status "No data" | Status "No data" is honest but the metrics row is repetitive — 4 dashes is visual noise | Collapse to a single "No data" row when all 4 are empty |
| `app.py:6807` | `"No historical records yet — run a scan to populate."` | Good. **Use this as the template** for other empty states. |

### 5. Status pills (Images 1, 8) — **CRITICAL**

**File:** `app.py:2247, 7556, 8219, 8617`

All four pages hardcode `(label, "live")` regardless of whether the
source is actually responding. Image 8 confirmed: "Glassnode · live"
shown while every Glassnode-backed card rendered "—".

The fix is a `data_source_health()` helper that probes (or reads a
recent ts from) each feed and returns one of:
- `live` — last successful fetch within the §12 cache window
- `cached(Xm)` — last fetch was older but within tolerance
- `rate-limited` — last call returned 429 or its in-process counter is at limit
- `no-api-key` — `_no_key_result` was returned (already structured!)
- `geo-blocked` — last call returned 403/451 or hit a known datacenter-block list
- `fetching` — call in flight (use a session-state flag)
- `error(short reason)` — anything else, with the first-line of the exception

This helper does NOT exist today. Recommendation in the helpers section
below.

Severity: **critical** for all 4 page headers.

### 6. On-chain page (Image 8) — **CRITICAL — entirely blank**

**File:** `app.py:8616-8821`

| File:line | Symptom | Why ambiguous | Truthful replacement |
|-----------|---------|---------------|----------------------|
| `app.py:8617-8621` | Status pills "Glassnode · live", "Dune · cached", "Native RPC · live" | All three are hardcoded. Glassnode without an API key returns `_no_key_result` — which the UI never sees | See pattern A. Wire to `data_source_health()` |
| `app.py:8700` | `_v` returns `"—"` for any None | "—" appears 12+ times across MVRV-Z / SOPR / Exch reserve / Active addr × 3 slots | Distinguish: no-key vs rate-limited vs not-tracked-for-asset (e.g. active addresses isn't free for XRP) |
| `app.py:8691` | Comment says "leave None so the card renders the '—' graceful empty" | Hardcoded for Active addr 24h | Replace with `"Glassnode key required"` if no key, otherwise `"—"` |
| `app.py:8722-8748` | Tone hints ("mid-cycle", "outflow 7d") shown only when value is present, otherwise blank | When data is missing the user sees a metric label and nothing else — no clue | Always show the cause line: "Pending first scan" / "Glassnode rate-limited" / etc. |
| `app.py:8802` | Whale activity empty: `"No large transfers in the last 24h, or whale tracker is offline."` | Image 8 user-flagged: mixes two states into one OR | Resolve to one truth: probe whale_tracker first, then say either "Tracker offline (Etherscan timeout)" or "No whale moves above $500k in last 24h" |

### 7. Funding rate monitor (Image 7) — **CRITICAL**

Covered in section 4 (it's the same page-tab). The single most
important fix: replace `app.py:6852` Python-`None` with a string from
the source's `error` field.

Suggested mapping at the wiring site:

```python
err = (rd.get("error") or "").lower()
if rd.get("error") is None:
    row[exch.upper()] = rate              # genuine rate, color-format
elif "geo-block" in err or "451" in err:
    row[exch.upper()] = "geo-blocked"
elif "rate limit" in err or "429" in err:
    row[exch.upper()] = "rate-limited"
elif "not listed" in err or "no symbol" in err:
    row[exch.upper()] = "not listed"
elif "key" in err:
    row[exch.upper()] = "key required"
else:
    row[exch.upper()] = "unavailable"
```

Then drop the Python None and the `_color_fr` branch can stop guarding
on `isinstance(val, (int, float))`.

### 8. Whale tracker disambiguation (Image 8 issue 5)

**Files:** `whale_tracker.py:53-538`, `app.py:8762-8807`

| File:line | Symptom | Why ambiguous | Truthful replacement |
|-----------|---------|---------------|----------------------|
| `whale_tracker.py:64, 82, 132, 198, 214, 223, 246, 249, 266, 280, 303, 322, 348, 361, 382` | Every chain handler returns `[]` on any exception | The on-chain page can't distinguish "no whales today" from "Etherscan returned 502" from "blockchain.info refused connection" | Refactor return shape to `{"events": list, "status": "ok"|"timeout"|"rate-limited"|"key-missing", "error": str}` |
| `app.py:8772-8805` | `_whale and len > 0` else "No large transfers… OR whale tracker is offline" | One sentence covers two distinct states | Render based on `status` field: only "no transfers" if status=="ok" with empty events |

Severity: **medium**. The headline impact is on Image 8 plus the
section's "lying" feel.

### 9. Settings / API key configuration screens

**Files:** `app.py:3173, 3218, 3232, 4210` (Settings), `data_feeds.py:1783` (helper)

| File:line | Symptom | Severity |
|-----------|---------|----------|
| `app.py:4210` | `st.warning("No API keys saved — enter and save keys first.")` | OK; clear, actionable |
| `app.py:3173, 3218, 3232` | "Settings could not be saved — check file permissions and try again." | OK at Beginner level. Advanced should see the actual exception (CLAUDE.md §7 — detail scales with level) |
| `app.py:3956` | `st.error(f"Retune failed: {_e_rt}")` | **Bug — leaks raw exception.** Violates CLAUDE.md §8 "never show a Python exception." Wrap with the friendly-message helper |
| `data_feeds.py:1783-1792` | `_no_key_result` returns `error: "API key not configured — add {service}_key to Config Editor → API Keys"` | Already structured perfectly — the UI just needs to read it (currently 0 callers do) |
| `app.py:7148` | `"agent.py failed to import. Check logs for details."` | Beginner-hostile. Use level-scaled message |

### 10. Generic "page failed to load — check logs" errors

**Files:** `app.py:4464, 7024, 7060, 7148, 7524, 8205, 8588`

```python
st.error("Arbitrage scanner failed to load — check logs.")     # 4464
st.error("Alerts page failed to load — check logs.")            # 7024
st.error("Alert history database helper unavailable — check logs.")  # 7060
st.error("agent.py failed to import. Check logs for details.")  # 7148
st.error("Signal page failed to load — check logs.")            # 7524
st.error("Regimes page failed to load — check logs.")           # 8205
st.error("On-chain page failed to load — check logs.")          # 8588
```

These are 7 copies of the same generic catch-all wrapping each `def
page_*()` body. They all violate §7 (no level scaling) and §8
(suggested next action is "check logs" — not actionable for a Beginner).

Severity: **medium**. Not lying, just unhelpful.

### 11. Other notable empty-state messages that ARE good

These read well today and should be **the template** for fixes:

- `app.py:6807` `"No historical records yet — run a scan to populate."`
- `ui_components.py:4045` `"No RSI/MACD divergences detected in current scan data. Run a scan first."`
- `ui_components.py:4132` `"No extreme funding rates detected — market is balanced. Run a scan to populate."`
- `ui_components.py:4365` `"Run a multi-timeframe scan to see trader vs investor split."`
- `ui_components.py:4538` `"Run a scan to generate liquidation cluster data."`
- `app.py:7104` `"No alerts have fired yet — once an email or webhook dispatches, the row appears here."`

Reuse this voice everywhere.

---

## Beginner / Intermediate / Advanced tier scaling (§7)

**Verdict: not implemented for empty states.** Every "—" / "None" /
"check logs" message is the same string regardless of `user_level`.
Examples that should differ:

| Beginner | Intermediate | Advanced |
|----------|--------------|----------|
| "Market data couldn't load — try refreshing in 30 seconds" | "OKX rate-limited (HTTP 429) — retry after 30s" | "OKX `/v5/public/funding-rate` 429; X-RateLimit-Reset = 1746400000" |
| "Run a scan to see this metric" | "Pending first scan" | "Pending first scan (last_scan_ts=None)" |
| "On-chain data isn't available right now" | "Glassnode rate-limited (free tier)" | "Glassnode 429 on `sopr_adjusted` for BTC; cooldown 60s" |

Recommended: a `friendly_error(reason: str, level: str)` helper that
pulls from a 3-column dictionary keyed by reason code.

---

## Proposed central helpers

Both helpers belong in **`utils_format.py`** (same module that already
owns `_is_missing` / `_EM_DASH`). All callers can `from utils_format
import truthful_empty_state, data_source_health`.

### Helper 1 — `truthful_empty_state()`

```python
# Reason codes — short, machine-friendly. Map to per-level user copy.
EMPTY_REASONS = {
    "loading":         {"b": "Loading…",         "i": "Fetching…",            "a": "fetch in flight"},
    "pending_scan":    {"b": "Run a scan",       "i": "Pending first scan",   "a": "no scan_ts yet"},
    "geo_blocked":     {"b": "Not available here","i": "Geo-blocked",         "a": "geo-blocked (HTTP 451 / datacenter IP)"},
    "rate_limited":    {"b": "Try again in a min","i": "Rate-limited",        "a": "HTTP 429 — backoff active"},
    "no_api_key":      {"b": "Setup required",   "i": "API key not configured","a": "key missing — see Settings → API Keys"},
    "not_listed":      {"b": "Not on this venue","i": "Pair not listed",      "a": "instId/symbol not found"},
    "not_tracked":     {"b": "Not tracked",      "i": "Not tracked for asset","a": "metric not available for this asset"},
    "source_offline":  {"b": "Source offline",   "i": "Upstream timeout",     "a": "connection refused / timeout"},
    "no_data":         {"b": "No data yet",      "i": "No data returned",     "a": "empty response, no error"},
    "error":           {"b": "Couldn't load",    "i": "Fetch error",          "a": "{detail}"},
}

def truthful_empty_state(
    reason: str,
    level: str = "beginner",
    detail: str | None = None,
) -> str:
    """Return a per-level user-facing string for a structured empty state.

    `reason` should be one of EMPTY_REASONS keys. Unknown reasons fall
    back to "error". `detail` (if provided) is interpolated into the
    advanced-level copy via {detail}.
    """
    bucket = EMPTY_REASONS.get(reason, EMPTY_REASONS["error"])
    key = {"beginner":"b", "intermediate":"i", "advanced":"a"}.get(level, "b")
    txt = bucket[key]
    if detail and "{detail}" in txt:
        return txt.format(detail=detail)
    return txt
```

### Helper 2 — `data_source_health()`

```python
from typing import Literal

HealthStatus = Literal[
    "live", "cached", "rate-limited", "no-api-key",
    "geo-blocked", "fetching", "error"
]

def data_source_health(
    source: str,
    *,
    last_ts: float | None = None,
    last_error: str | None = None,
    cache_ttl_s: int = 300,
) -> tuple[HealthStatus, str]:
    """Return (status, short_label_for_pill).

    Probe-free: relies on the most recent recorded fetch metadata.
    Each data_feeds.py fetcher should record its last (ts, error)
    into a module-level `_HEALTH[source] = (ts, error)` dict.

    label is what to show inside the pill — e.g. "OKX · live" or
    "OKX · cached 12m" or "Glassnode · key required".
    """
    now = time.time()
    if last_error:
        err = last_error.lower()
        if "429" in err or "rate" in err and "limit" in err:
            return "rate-limited", f"{source} · rate-limited"
        if "451" in err or "geo" in err:
            return "geo-blocked", f"{source} · geo-blocked"
        if "key" in err and ("missing" in err or "not config" in err):
            return "no-api-key", f"{source} · key required"
        return "error", f"{source} · error"
    if last_ts is None:
        return "fetching", f"{source} · fetching"
    age = now - last_ts
    if age <= cache_ttl_s:
        return "live", f"{source} · live"
    age_min = int(age // 60)
    return "cached", f"{source} · cached {age_min}m"
```

To wire this in: every fetcher in `data_feeds.py` records its
`(time.time(), None_or_error)` into a shared dict keyed by the source
name. Each `page_header` call replaces its hardcoded `("Glassnode",
"live")` with a call to `data_source_health("glassnode", last_ts=...,
last_error=...)`.

This is a 4-place fix in app.py (the four `data_sources=[...]`
literals) plus ~20 record sites in data_feeds.py.

---

## "What to fix first" — top 10 lying / silent messages

Ordered by user impact × frequency × ease of fix.

| # | File:line | Issue | Why it tops the list |
|---|-----------|-------|----------------------|
| 1 | `app.py:8617-8621` | On-chain status pills hardcoded "live" | **Image 8 headline.** Every On-chain card was blank while pills lied. Single biggest credibility hit. |
| 2 | `app.py:6852` | Funding-rate cell = Python `None` rendered as literal "None" | **Image 7 headline.** User explicitly called out. Trivial fix — replace one ternary with a structured-error mapper. |
| 3 | `app.py:2247-2251, 7556-7560, 8219-8223` | Hardcoded "live" on Dashboard / Signals / Regimes too | Same fix template as #1 — apply once to all 4 sites. |
| 4 | `app.py:6867` | "Best Rate" = "—" when all 4 exchanges errored | Reads identical to "data missing" but means "all sources broken" |
| 5 | `app.py:8800-8803` | Whale activity: "No large transfers… OR whale tracker is offline" | **Image 8 user-flagged.** Refactor whale_tracker to return status field; resolve to one true case. |
| 6 | `app.py:3956` | `st.error(f"Retune failed: {_e_rt}")` | **Violates §8.** Raw exception leaked to UI. |
| 7 | `app.py:7910` | `_unlock_signal = "None"` literal | Replace with "No upcoming unlock" |
| 8 | `app.py:8700, 7921-7936` | On-chain `_v()` returns "—" for None — no level scaling | Apply `truthful_empty_state("pending_scan", level)` |
| 9 | `app.py:4464, 7024, 7060, 7148, 7524, 8205, 8588` | 7 copies of "page failed to load — check logs" | Replace with level-scaled "Beginner / Intermediate / Advanced" messages from helper |
| 10 | `ui/sidebar.py:553, 564, 667, 675` (hero cards) | `"—"` for hero card price/change with no cause | Wire into `truthful_empty_state` per-state ("pending_scan" / "not_listed" / "fetching") |

---

## Out-of-scope / functional bugs noted in passing

These showed up in the audit but belong in the legacy-look fix sprint,
not this empty-state pass:

- `app.py:6687-6690` — Buy On / Sell On show "—" for NO_ARB rows
  (Image 5 user request: show min/max-price exchange anyway).
- `app.py:6970-7000` — Hyperliquid funding shows +0.0000% while OI
  values look real (Image 7 issue 3 — funding parser likely broken).
- `app.py:7896-7916` — Token-unlock signal mapping uses string
  literals "N/A", "None" — should use the structured signal enum
  from cryptorank.

---

## File-line reference appendix

Full em-dash inventory (135 occurrences across the codebase).
Grouped by file, ordered by line.

**app.py** (76):
402, 411, 576, 2308, 2312, 2331, 2337, 2340, 2344, 2352, 2703, 2711,
2717, 2762, 3569, 3732, 4617, 4625, 4662, 4670, 4784, 4786, 4793,
4887, 4893, 4981, 4982, 4983, 5050, 5052, 5054, 5318, 5441, 5464,
5490, 5491, 5499, 5565, 5583, 5728, 5731, 5735, 6049, 6073, 6181,
6189, 6223, 6274, 6276, 6338, 6342, 6344, 6513, 6514, 6683, 6687,
6688, 6689, 6690, 6772, 6774, 6775, 6867, 6980, 6982, 7117, 7118,
7220, 7221, 7507, 7752, 7867, 7895, 7896, 7913, 7921, 7930, 7936,
7940, 7941, 8084, 8091, 8097, 8112, 8113, 8149, 8169, 8690, 8700,
8736, 8746, 8783

**ui_components.py** (20):
868, 916, 917, 1270, 1271, 1499, 1504, 2361, 2370, 2595, 2603, 3037,
3062, 3544, 3545, 3874, 3996, 4040, 4041, 4101, 4186, 4203, 4266,
4273, 4275, 4333, 4408, 4508, 4704, 4710, 4716, 4722, 4813, 4814

**ui/sidebar.py** (16):
553, 564, 634, 663, 667, 675, 799, 1332, 1406, 1486, 1494, 1495,
1611, 1613, 1616, 1623, 1669, 1676, 1677, 1680, 1779, 1850

**alerts.py** (4): 164, 174, 194, 203

**pdf_export.py** (8): 104, 182, 184, 185, 186, 187, 188, 189, 277, 282

**utils_format.py** (4): 10, 20, 27, 50, 85, 109 (helper definitions; not user-facing)

**Tests** mention `"—"` as documented expected behavior — leave alone:
- `tests/test_indicator_fixtures.py:139, 411, 421, 426, 443`
- `tests/test_data_wiring.py:200, 229, 648`
- `tests/test_composite_fallback.py:8`

---

## Recommended execution order

1. **Land the two helpers** (`truthful_empty_state`, `data_source_health`)
   into `utils_format.py`. Pure additions, no behavior change. Add
   unit tests for each reason-code → per-level mapping.
2. **Wire `data_source_health` into the 4 page headers** (top-10 #1, #3).
   Requires recording `(ts, error)` in data_feeds.py for ~6 sources
   (OKX, Glassnode, Dune, Native RPC, FRED, news_sentiment). One PR.
3. **Fix the funding-rate cell** (top-10 #2) — replace Python `None`
   with the structured-error mapper. ~10 lines in app.py:6841-6868.
4. **Whale tracker status field** (top-10 #5) — refactor return shape;
   update on-chain page renderer to branch on status.
5. **Replace `st.error(f"…: {e}")`** at app.py:3956 (top-10 #6).
6. **Apply `truthful_empty_state` at the top 20 "—" sites** (top-10
   #7-#10) — Hero cards, on-chain `_v()`, `_unlock_signal`, the 7
   page-load catch-alls.
7. **Sweep the remaining ~110 "—" sites** in a second pass once the
   pattern is proven. These are lower-value but worth the consistency
   pass to prevent regressions.

Estimated scope: 1 sprint-day for steps 1–3 (the high-impact fixes
the user has explicitly flagged), 1 more day for 4–6, and a
half-day cleanup for step 7.

---

## Cross-references

- CLAUDE.md §7 (user level scaling), §8 (no exceptions to UI), §12
  (data refresh + cache labels)
- `MEMORY.md` → `feedback_empty_states.md` (durable preference)
- `docs/audits/2026-05-02_legacy-look-audit-in-progress.md` (Images
  1, 5, 7, 8 — the user's flagged screens that motivated this audit)
- `utils_format.py:_is_missing` / `_EM_DASH` (existing primitives to
  build on)
- `data_feeds.py:_empty_result` (line 412) and `_no_key_result`
  (line 1783) — already structured, just unused by UI
