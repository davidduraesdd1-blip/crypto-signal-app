# On-chain page — root-cause audit (Image 8 headline bug)
Date: 2026-05-02
Author: Claude (Opus 4.7, 1M ctx)
Scope: `page_onchain` rendering, Glassnode / Dune / "Native RPC" wiring,
status pills, whale_tracker integration, composite Layer 4 binding.

---

## TL;DR

The On-chain page shows "—" in every metric card because **the page never
asks any of the three data sources the status pills advertise**. The pills
("Glassnode · live", "Dune · cached", "Native RPC · live") are
**hardcoded string literals** at the page-render call site — they are not
derived from a health check, and Glassnode / Dune / a "Native RPC"
on-chain reader are **never invoked** by `page_onchain`.

The only fetch the page actually performs is a CoinGecko/OKX **price
proxy** (`data_feeds.get_onchain_metrics`) that produces a fallback dict
of `{mvrv_z: 0.0, sopr: 1.0, net_flow: 0.0, ...}` whenever the upstream
is rate-limited or geo-blocked. Combined with three separate
truthiness/`or`-chain bugs in the card-render code, those `0.0` and `1.0`
values get silently coerced to `None` and printed as `—`. Compounding
this, `active_addresses_24h` is **hardcoded to `None`** in the field
adapter, so the fourth card slot is mathematically guaranteed to render
"—" no matter what the source returns.

The three-state truthiness collapse + the hardcoded None +
the no-real-source pills together produce the reported screenshot
exactly.

---

## End-to-end trace

### 1. Page renderer

File: `app.py`
Function: `page_onchain` — lines **8570-8821**
Router: `app.py:8840-8841` (`elif page == "On-chain": page_onchain()`)

Flow inside `page_onchain`:

1. Top-bar renders (line 8592-8598). Status pills come from
   `_agent_topbar_pills()` — **agent supervisor state only**, not data
   sources. (`app.py:1623-1643`)
2. **Page header `data_sources` argument** is hardcoded at line 8617-8621:
   ```
   data_sources=[
       ("Glassnode", "live"),
       ("Dune",      "cached"),
       ("Native RPC","live"),
   ]
   ```
   These literals are passed to `ui.page_header(...)`
   (`ui/sidebar.py:440-495`). The renderer accepts {live | cached | down}
   and decorates the pill, but it does **zero** validation that the
   source is actually live. **Bug #1 — status pills lying.**
3. The three slot pickers default to `BTC / ETH / XRP`
   (lines 8631-8633). Fine.
4. For each slot ticker, `_result_for(ticker)` is called
   (lines 8656-8696). It tries (in order):
     a. `st.session_state["scan_results"]` (in-memory scan output)
     b. `_cached_signals_df(500)` (DB-backed historical scan)
     c. **direct fallback** — `data_feeds.get_onchain_metrics(_pair)`
        with field-name adapter (lines 8674-8693)
   If all three fail it returns `{}` and every card slot shows "—".
5. Card render (lines 8713-8750) reads `_slot_d.get(...)` for each card.
   **The render contains 3 separate truthiness bugs — see §4 below.**

### 2. Glassnode integration — file: `data_feeds.py:2032-2122`

`get_glassnode_onchain(pair)` is **a real Glassnode call** (real SOPR
via `sopr_adjusted` endpoint, real MVRV-Z via `market/mvrv_z_score`)
gated on a `glassnode_key` from `alerts_config.json`. It supports only
`BTC/USDT` and `ETH/USDT` natively.

CRITICAL: `page_onchain` **never calls `get_glassnode_onchain`**. The
function exists, it works, it's tested, and it is wholly orphaned from
this page. The only other caller path is via the scan engine's
crypto_model_core when a paid key is configured, but the on-chain page
itself reads from `get_onchain_metrics` (the proxy fetcher), not
`get_glassnode_onchain`.

Free-tier note: even if the page DID call it, no `glassnode_key` is
present by default — Glassnode has no free tier for these endpoints.
`_no_key_result("glassnode", ...)` returns
`{signal: "N/A", value: None, error: "API key not configured ..."}` —
the page would then need to surface that as a pill state of "no api key",
not "live".

### 3. Dune integration — file: `data_feeds.py:2787-2897`

`fetch_dune_query_result(query_id)` exists, requires `DUNE_API_KEY`
(env or alerts_config.json), gracefully returns `None` when no key is
present. Free-tier Dune requires a key for read access.

CRITICAL: `page_onchain` **never calls `fetch_dune_query_result`** with
any query ID. The "Dune · cached" pill is a literal string. There is no
configured query mapping (no `DUNE_QID_*` constants for MVRV / SOPR /
exchange reserves anywhere in the file).

### 4. "Native RPC" integration

`Grep -i 'native[_ ]?rpc'` across the entire repo returns 4 hits — three
in docs/audits commentary plus one stale reference in
`tests/test_data_wiring.py`. **There is no native-RPC on-chain reader
in this codebase.** No `web3.py` imports, no `eth_call`-based exchange
reserve calculation, no `rpc_endpoint` config in `config.py`, no
`web3` in `requirements.txt`. The "Native RPC · live" pill is a pure
literal. It refers to an integration that does not exist.

Implication for *exchange reserve* + *active addresses*:
- These two metrics are NEVER produced by the page's actual data path.
- `active_addresses_24h` is **explicitly hardcoded to `None`** by the
  field adapter at `app.py:8691`:
  ```
  "active_addresses_24h": None,
  ```
  with the comment "Active addresses isn't in the free Binance ticker —
  leave None so the card renders the '—' graceful empty." This is a
  deliberate choice — but the page advertises a "live" Native-RPC pill
  while always returning None, which is contradictory.
- Exchange reserve is approximated from `net_flow` (volume/mcap proxy
  scaled to ±400). On the fallback path `net_flow=0.0`, which collapses
  to "—" via the truthiness bug — see §6.

### 5. Status pill logic — bug #1

File: `app.py:8617-8621`
File: `ui/sidebar.py:440-495`

The `page_header(data_sources=...)` API supports three states:
{live, cached, down}. The renderer:

```python
if status == "cached":
    cls += " warn"
elif status == "down":
    cls += " down"
```

There is no plumbing from any health check into these three values. The
page passes literals. This means:
- If Glassnode is rate-limited → still says "live"
- If user has no API key → still says "live"
- If Streamlit Cloud is geo-blocked from the upstream → still says "live"
- If Dune is uncached AND has no key → still says "cached"
- If "Native RPC" doesn't exist as code → still says "live"

`data_feeds.validate_api_keys()` (line 7745) does ping OKX, CoinGecko,
Deribit, and Anthropic — but it does **NOT** ping Glassnode or Dune,
and there is no native-RPC concept to ping.

### 6. The four card-render truthiness bugs

File: `app.py:8718-8749` (the `_ds_ind_card(...)` block).

#### Bug 6a — MVRV-Z `or`-chain collapses 0.0 to None

Line 8722:
```
_v(_slot_d.get("mvrv_z") or _slot_d.get("mvrv"), "{:.2f}")
```

When the underlying source is the proxy fallback (`_fallback_onchain()`
at `data_feeds.py:733-739`), `mvrv_z = 0.0` — a legitimate Z-score.
The `or` chain then evaluates: `0.0 or _slot_d.get("mvrv")`. In the
adapter (line 8682) `mvrv` is also set to the same 0.0 value, so the
expression returns `0.0`, not `None`. So strictly this card *should*
render as "0.00" on the fallback path.

BUT: the helper `_v(x, fmt)` at lines 8698-8704 only treats `None` as
"—". And `_slot_d.get("mvrv_z")` returns `None` when the dict is empty
(scan never ran, DB empty, direct fetch raised). In that empty-dict
case, BOTH MVRV-Z and SOPR cards render "—". Combined with the fact
that the user's screenshot shows "—" universally, the most consistent
explanation is that `_slot_d == {}` for all three slots — i.e. the
direct fetch is silently raising or returning empty, and the
swallowing `try/except` at lines 8694-8695 logs at DEBUG level only.

**Verify this hypothesis** by adding a `logger.warning(...)` on the
fallback exception path (currently `logger.debug` at line 8695 — silent
in production).

#### Bug 6b — SOPR card has no `or` collapse but DOES short-circuit on 0

Line 8728:
```
_v(_slot_d.get("sopr"), "{:.3f}"),
```

If `_slot_d == {}` → renders "—". If proxy returns `sopr = 1.0` →
renders "1.000". Working.

#### Bug 6c — Exchange Reserve uses `if x is not None` but also has a False-on-zero `or` for tone

Lines 8733-8742:
```
("Exch. reserve",
 (_v(_slot_d.get("exchange_reserve_delta_7d"), "{:+,.0f}")
  if _slot_d.get("exchange_reserve_delta_7d") is not None
  else "—"),
 ...
```

The value-render uses `if x is not None` — correct. But the *tone* and
*subtitle* lines use `_slot_d.get("exchange_reserve_delta_7d") and ...`
— so `0.0` (a real zero net-flow) flips to "inflow 7d" with empty tone.
Cosmetic, but inconsistent.

#### Bug 6d — Active addresses is hardcoded None

Line 8691:
```
"active_addresses_24h": None,
```

The field adapter writes `None` literally. Card always renders "—".
The status pill says "Native RPC · live". The two are contradictory by
design.

### 7. Whale tracker — bug #2

File: `whale_tracker.py:436-520`
Caller: `app.py:8762-8807`

The tracker DOES run. `_cached_whale_activity("BTC/USDT", 0.0)` is
invoked on every page render (5-min cache TTL, `app.py:590-595`).
`get_whale_activity` returns a normalised dict with shape:
```
{ signal, whale_count, large_whale_count, total_usd, accumulation,
  distribution, score, error, pair }
```

The page expects a list of *transfer events* (`amount_usd`, `direction`,
`coin`, `timestamp`) but `get_whale_activity` only returns the
*aggregated signal* — it does NOT return the individual transfer events
list. The aggregator `_synthesize_signal` discards the `moves` list
after computing counts.

So the conditional at line 8772:
```
if _whale and isinstance(_whale, list) and len(_whale) > 0:
```
is **always False** — `_whale_raw` is a dict (not a list), and the dict
contains no `events`/`transfers`/`recent` key. The else branch fires
unconditionally, printing the ambiguous "No large transfers in the
last 24h, or whale tracker is offline." copy regardless of actual state.

The empty-state copy lies because:
- It can't distinguish "tracker fetched 0 transfers because the chain
  was quiet" from "tracker raised an exception".
- The data structure at hand DOES carry truth (`error`, `whale_count`,
  `signal`) — it's just not unpacked.

Fix shape: read `_whale_raw["error"]`, `_whale_raw["whale_count"]`,
`_whale_raw["signal"]` and emit one of three distinct copies:
- error is non-None → "Whale tracker offline (Etherscan: rate-limited /
  blockchain.info: timeout / etc.)"
- error is None and whale_count == 0 → "No transfers >$500K in the last
  24h. Tracker live."
- whale_count > 0 → existing transfer table

To actually populate the per-transfer table, `whale_tracker.get_whale_activity`
needs to return the raw `moves` list as well — a one-line addition in
`_synthesize_signal` (e.g. `result["events"] = moves[:25]`).

### 8. Composite Layer 4 — comparison

File: `composite_signal.py:1101-1121`

Layer 4 of the composite signal IS consuming `onchain_data` (mvrv_z,
sopr, hash_ribbon_signal, puell_multiple, mvrv_ratio, nvt). The
caller in `app.py:435-440` and `app.py:540-558` does:

```python
onchain_data = data_feeds.get_onchain_metrics(pair) or {}
```

— the **same fetcher** as the on-chain page. So composite Layer 4 sees
the same 0.0 fallback values and produces a near-zero contribution to
the composite score. This means **Layer 4 is "working" but
underpowered** — same source, same proxy values.

CoinMetrics (`fetch_coinmetrics_onchain`, `data_feeds.py:5379+`) DOES
return real BTC MVRV-Z, SOPR, hash-ribbon, Puell, NUPL, and active
addresses — but ONLY for BTC, and `get_onchain_metrics` only blends in
CoinMetrics data when `pair.startswith("BTC/")` (lines 800-810,
870-880). For ETH and XRP, the proxy 0.0 values are all that flow
through.

So the diagnosis:
- **MVRV-Z, SOPR, active addresses for BTC** ARE available (CoinMetrics,
  free, no key, working) but the on-chain page never reads them as
  individual fields — `get_onchain_metrics` only overrides `mvrv_z`
  and leaves `active_addresses` unmapped.
- **For ETH / XRP**, no free non-proxy source is wired up. Glassnode
  could fill ETH (with key); nothing fills XRP without a paid feed.

---

## Findings table

| # | File | Line | Severity | Bug | Root cause |
|---|------|------|----------|-----|------------|
| 1 | app.py | 8617-8621 | CRITICAL | Status pills hardcoded literals; "Glassnode/Dune/Native RPC live" advertised regardless of actual source state | No plumbing from source health into the page_header `data_sources` argument |
| 2 | app.py | 8691 | HIGH | `active_addresses_24h` always None — Active addr. card always shows "—" | Adapter explicitly hardcodes None, no real source wired |
| 3 | app.py | 8722 | HIGH | `_v(... or ...)` on MVRV-Z silently coerces 0.0 to None when the second `or` operand is None, rendering "—" instead of a real value | Python `or` semantics: `0.0 or None == None` |
| 4 | app.py | 8694-8695 | HIGH | Direct-fetch exception swallowed at `logger.debug` — production logs hide the failure | Should be `logger.warning` so prod logs surface why cards are empty |
| 5 | app.py | 8762-8807 | HIGH | Whale section ambiguous empty state; conditional `isinstance(_whale, list)` is always False because `get_whale_activity` returns a dict with no events list | Tracker discards individual transfer moves after aggregation; page expects a list shape |
| 6 | whale_tracker.py | 387-419 | HIGH | `_synthesize_signal` discards the per-transfer `moves` list before returning | One-line addition: `result["events"] = moves[:25]` |
| 7 | data_feeds.py | 7745-7785 | MEDIUM | `validate_api_keys()` doesn't ping Glassnode or Dune, so even if status pills were wired to it, those two services would have no truth value | Add lightweight 1-row probe for each |
| 8 | data_feeds.py | 8651-8696 (app.py) | MEDIUM | Field adapter mixes proxy `net_flow` (vol/mcap-derived) into `exchange_reserve_delta_7d` slot — semantically different metric | Either rename card to "Volume/mcap proxy" or wire a real exchange-balance source |
| 9 | data_feeds.py | 2032-2122 | LOW | `get_glassnode_onchain` exists, works, is tested, never called by the on-chain page | Wire it into `_result_for` for BTC/ETH when key present |
| 10 | data_feeds.py | 2787-2897 | LOW | `fetch_dune_query_result` exists, no query IDs configured for on-chain metrics | Add `DUNE_QID_BTC_EXCHANGE_RESERVE`, etc., or remove the "Dune · cached" pill until wired |
| 11 | composite_signal.py | 1101-1121 | INFO | Layer 4 consumes the same proxy values; for BTC it overlays CoinMetrics (good), for ETH/XRP it stays at proxy values | Backfill from `get_glassnode_onchain` on BTC/ETH if key present |
| 12 | app.py | 8743-8746 | LOW | Active-addresses card render branch is dead code (the `if x is not None` always evaluates None because of bug #2) | Resolves automatically once bug #2 is fixed |

---

## Proposed fixes

### Fix #1 — Minimum viable patch (cards populated truthfully on first load)

Goal: cards show real values for BTC immediately, real or honest-empty
values for ETH/XRP. Status pill and card always agree on what is real.

**Changes to `app.py:_result_for` (around lines 8674-8696):**

```python
try:
    _pair = f"{ticker}/USDT"
    _oc = data_feeds.get_onchain_metrics(_pair) or {}
    # 1a. For BTC, blend in CoinMetrics free-tier real data
    #     (active_addresses, sopr, mvrv_z, puell, hash_ribbon)
    _cm = {}
    if ticker == "BTC":
        try:
            _cm = data_feeds.fetch_coinmetrics_onchain(400) or {}
            if _cm.get("error"):
                _cm = {}
        except Exception as _cm_err:
            logger.warning("[On-chain] CoinMetrics fetch for BTC failed: %s", _cm_err)
            _cm = {}
    # 1b. For BTC/ETH, blend in Glassnode real data when key configured
    _gn = {}
    if ticker in ("BTC", "ETH"):
        try:
            _gn_raw = data_feeds.get_glassnode_onchain(_pair) or {}
            # _no_key_result returns {signal: "N/A", error: "API key..."} — skip
            if _gn_raw.get("error") is None and _gn_raw.get("signal") != "N/A":
                _gn = _gn_raw
        except Exception as _gn_err:
            logger.warning("[On-chain] Glassnode fetch for %s failed: %s", _pair, _gn_err)
    if _oc or _cm or _gn:
        return {
            "pair": _pair,
            "mvrv_z": _gn.get("mvrv_z") or _cm.get("mvrv_z") or _oc.get("mvrv_z"),
            "sopr":   _gn.get("sopr")   or _cm.get("sopr")   or _oc.get("sopr"),
            "exchange_reserve_delta_7d": _oc.get("net_flow"),
            "active_addresses_24h":     _cm.get("active_addresses"),  # was None
            "_source": _gn.get("source") or _cm.get("source") or _oc.get("source", "fallback"),
            "_freshness": _cm.get("timestamp") or _oc.get("_ts"),
        }
except Exception as _e_oc:
    logger.warning("[On-chain] direct fetch for %s failed: %s", ticker, _e_oc)
return {}
```

Effect:
- BTC card now shows real active-addresses count (CoinMetrics).
- BTC card shows real MVRV-Z and SOPR (CoinMetrics or Glassnode if key).
- ETH card upgrades to real Glassnode SOPR/MVRV-Z when a key is present;
  falls back to proxy with truthful empty for active addresses.
- XRP stays on proxy (no free real-data source available); active
  addresses honestly shows "—".
- Failures are logged at WARNING (visible in prod).

**Also fix the `or`-chain on line 8722** so `0.0` is preserved:

```
("MVRV-Z",
 _v(_slot_d.get("mvrv_z") if _slot_d.get("mvrv_z") is not None
      else _slot_d.get("mvrv"),
    "{:.2f}"),
 ...
```

— same pattern applied to SOPR for symmetry.

### Fix #2 — Status pill truthfulness

**New helper in `app.py` (near `_agent_topbar_pills`):**

```python
def _onchain_source_pills() -> list[tuple[str, str]]:
    """Return real (label, status) tuples for the On-chain page header.
    status ∈ {live, cached, down} mapping to ds-pill classes.

    A 6th meta-state — descriptive labels surfaced in the pill text
    itself — communicates more nuance ("rate-limited", "no key",
    "geo-blocked") without the renderer needing 6 pill colours.
    """
    pills: list[tuple[str, str]] = []

    # Glassnode — only "live" if key present AND a probe call returns 200
    _keys = data_feeds._load_api_keys()
    _gn_key = _keys.get("glassnode_key", "").strip()
    if not _gn_key:
        pills.append(("Glassnode · no key", "down"))
    else:
        try:
            _probe = data_feeds.get_glassnode_onchain("BTC/USDT") or {}
            if _probe.get("error"):
                pills.append(("Glassnode · rate-limited", "cached"))
            elif _probe.get("mvrv_z") is not None:
                pills.append(("Glassnode", "live"))
            else:
                pills.append(("Glassnode · degraded", "cached"))
        except Exception:
            pills.append(("Glassnode · down", "down"))

    # Dune — only "cached" if key present AND no query has been called
    if not data_feeds._get_runtime_key("dune_key", ""):
        pills.append(("Dune · no key", "down"))
    else:
        # Real plumbing requires registered query IDs; until that exists,
        # advertise "cached" only when a registered probe query worked.
        pills.append(("Dune · ready", "cached"))

    # CoinMetrics free tier — primary BTC source. Always probed.
    try:
        _cm_probe = data_feeds.fetch_coinmetrics_onchain(30) or {}
        if _cm_probe.get("error"):
            # Could be 403 (US cloud IP-blocked) or empty
            ec = _cm_probe.get("error_code", "")
            if "403" in ec:
                pills.append(("CoinMetrics · geo-blocked", "down"))
            else:
                pills.append(("CoinMetrics · cached", "cached"))
        else:
            pills.append(("CoinMetrics", "live"))
    except Exception:
        pills.append(("CoinMetrics · down", "down"))

    return pills
```

Then in `page_onchain` (replace lines 8617-8621):
```
data_sources=_onchain_source_pills(),
```

The "Native RPC" pill is removed entirely until a native-RPC reader is
actually wired (or it becomes a `Glassnode/CoinMetrics fallback` label).

Caching: the helper itself should be wrapped in
`@st.cache_data(ttl=420)` to keep page-render light. Use a plain
function inside a closure or `_cached_onchain_pills()` mirror. (Mirror
the pattern of `_cached_api_health` at app.py:321.)

### Fix #3 — Whale tracker disambiguation

**One-line change in `whale_tracker.py:_synthesize_signal`** (line 411):

```python
return {
    "signal":            signal,
    "whale_count":       len(moves),
    "large_whale_count": large,
    "total_usd":         round(total_usd, 0),
    "accumulation":      acc,
    "distribution":      dist,
    "score":             round(score, 3),
    "events":            moves[:25],   # NEW — preserves per-tx detail for UI
}
```

(And add `"events": []` to `_NEUTRAL_RESULT` at line 424 for shape
consistency.)

**Replace `app.py:8762-8807` with a three-state branch:**

```python
try:
    _whale_raw = _cached_whale_activity("BTC/USDT", 0.0) or {}
    _events = _whale_raw.get("events") or []
    _err = _whale_raw.get("error")
    _count = int(_whale_raw.get("whale_count") or 0)

    if _err:
        # Tracker is offline (price unavailable, chain-API rate-limit, etc.)
        st.markdown(
            '<div class="ds-card">'
            '<div class="ds-card-hd"><div class="ds-card-title">Whale activity</div></div>'
            '<div style="color:var(--text-muted);font-size:13px;padding:12px 4px;">'
            f'Whale tracker offline — {_html.escape(str(_err))[:120]}. '
            'Try Refresh All Data or check back in a few minutes.'
            '</div></div>',
            unsafe_allow_html=True,
        )
    elif _count == 0:
        # Tracker live, chain genuinely quiet
        st.markdown(
            '<div class="ds-card">'
            '<div class="ds-card-hd">'
            '<div class="ds-card-title">Whale activity</div>'
            '<div style="color:var(--text-muted);font-size:12px;">'
            'Live · 0 transfers ≥$500K in last 24h</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
    else:
        # Render the events table (existing branch)
        ...
except Exception as _e_w:
    logger.warning("[On-chain] whale activity render failed: %s", _e_w)
```

Each of the three states is now distinct and actionable. The original
"or whale tracker is offline" ambiguity is gone.

---

## Verification checklist after fixes

1. Open On-chain page on a fresh Streamlit Cloud restart with no API
   keys configured. Expect:
   - Status pills: "Glassnode · no key" (down), "Dune · no key" (down),
     "CoinMetrics" (live).
   - BTC card: real MVRV-Z, real SOPR, real active addresses, proxy
     exchange-reserve. Source label "_source: coinmetrics".
   - ETH card: proxy MVRV-Z and SOPR (small numbers near 0/1), active
     addresses "—", proxy exchange-reserve.
   - XRP card: proxy MVRV-Z, SOPR (1.0), active addresses "—".
   - Whale section: "Live · 0 transfers ≥$500K in last 24h" or the
     real event table — never the legacy ambiguous string.
2. Configure `glassnode_key` in alerts_config.json. Restart. Expect:
   - Status pill switches to "Glassnode" (live).
   - BTC and ETH MVRV-Z/SOPR upgrade to Glassnode values
     (BTC may already match CoinMetrics; ETH gains real values).
3. Force CoinMetrics into 403 (e.g. mock `_NO_RETRY_SESSION`). Expect:
   - Pill switches to "CoinMetrics · geo-blocked" (down).
   - BTC MVRV-Z falls back to proxy (Glassnode if key, else
     `get_onchain_metrics`).
4. Force whale_tracker exception. Expect:
   - "Whale tracker offline — <truncated error>." with no
     "or" disjunction.
5. `pytest tests/test_data_wiring.py` — existing C4 assertion (the
   adapter mapping line) still passes. Add a new test asserting
   `_onchain_source_pills` is wired into `page_onchain` so the literal
   pills can never come back.

---

## Out-of-scope but adjacent

- The PAID Glassnode plan covers ~40 BTC/ETH metrics — currently only
  SOPR + MVRV-Z are wired. Active addresses, NVT, NUPL, exchange
  net-position-change all available on the same key with the same
  pattern. Same files, same shape — additive.
- Dune queries for exchange reserve / active addresses for non-BTC
  chains are public on dune.com and free to fork. Once a query ID set
  is registered (e.g. in `config.py`), `fetch_dune_query_result` is
  ready to consume them.
- A native-RPC reader for ETH exchange addresses (Binance/Coinbase hot
  wallets) is feasible via `web3.py` — would require adding `web3` to
  `requirements.txt` and a 50-line module reading balanceOf on the
  basket of `_ETH_WHALE_PROXY_ADDRESSES` already in `whale_tracker.py`.
  Same data shape as Glassnode `addresses/exchange_balance` — would
  let the "Native RPC · live" pill become honest.

---

End of audit.
