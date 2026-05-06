# Tier 4 — Data Feed Liveness, Wave 2 (Render Oregon ground-truth diagnosis)
**Date:** 2026-05-06
**Auditor:** Claude (read-only diagnosis pass — NO code modified)
**Worktree:** `.claude/worktrees/exciting-lovelace-60ae5b`
**Branch:** `claude/exciting-lovelace-60ae5b`
**Inputs:** Wave 1 findings (`docs/audits/2026-05-05_data-feed-liveness.md`) + tonight's
`/diagnostics/feeds` payload from prod (`crypto-signal-app-1fsi.onrender.com`).

## Render Oregon ground-truth — what tonight's probe actually proved

| Source | HTTP | ms | Status | Probe URL |
|---|---:|---:|---|---|
| Kraken (CCXT) | 200 | 230 | ok | `api.kraken.com/0/public/Time` |
| Gate.io REST | 200 | 399 | ok | `api.gateio.ws/api/v4/spot/time` |
| Bybit REST | 403 | 38 | warn | `api.bybit.com/v5/market/time` |
| MEXC REST | 200 | 219 | ok | `api.mexc.com/api/v3/time` |
| **OKX REST (geo-blocked)** | **200** | **185** | **ok** | `www.okx.com/api/v5/public/time` |
| CoinGecko | 429 | 277 | warn | `api.coingecko.com/api/v3/ping` |
| alternative.me F&G | 200 | 281 | ok | `api.alternative.me/fng/?limit=1` |
| **FRED** | — | 5169 | **unreachable** | `fred.stlouisfed.org/` (HEAD; 5s timeout) |

Two of these contradict the code's running assumptions. Two are downstream
symptoms of upstream-chain failures. The diagnosis follows.

---

## §1. OKX — the "geo-block" was probably never real on `www.okx.com`

### What `0940681` actually documented
Commit message (`git show 0940681`):
> "Render Oregon datacenter IPs are geo-blocked by OKX (post-cutover logs
> show ConnectionResetError(104) on every OKX REST call)."

But the commit itself does **not** preserve any of the `ConnectionResetError(104)`
log evidence. It cites "post-cutover logs" without linking them. The reorder
landed on `2026-05-04 16:50` based on Render logs that have since rolled off.

### What tonight's probe proves
- `/diagnostics/feeds` from inside Render Oregon hits `https://www.okx.com/api/v5/public/time` → **HTTP 200 in 185ms**.
- Same call from auditor IP → **HTTP 200 in 326ms**.
- No `ConnectionResetError`, no TLS reset, no 4xx.

That's clean reachability of the **public-time** endpoint. The commit was
written assuming OKX as a host was geo-blocked. **The host is not blocked.**

### What we don't yet know
The probe URL only exercises `/api/v5/public/time` — a no-op timestamp ping.
The actually-load-bearing OKX endpoints are different paths on the same host:

| Code site | Endpoint hit | File:line |
|---|---|---|
| OHLCV (chart fallback #5) | `https://www.okx.com/api/v5/market/candles?instId=…&bar=…` | `data_feeds.py:582` |
| Funding (rate fallback #2) | `https://www.okx.com/api/v5/public/funding-rate?instId=…-SWAP` | `data_feeds.py:334,487` |
| Open-interest (#2 of 2) | `https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=…` | `data_feeds.py:997` |
| Long/short ratio | `https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio` | `data_feeds.py:4228` |
| Taker buy/sell volume | `https://www.okx.com/api/v5/rubik/stat/taker-volume` | `data_feeds.py:4345` |
| Tickers / instruments | `https://www.okx.com/api/v5/market/ticker`, `…/public/instruments` | many — `:709, 1382, 6135, 6477, 6857, 7197, 7383, 7490, 7586, 7676` |

Auditor-side probes confirm all of these return 200 from the auditor IP today
(I tested `/v5/market/candles?instId=BTC-USDT&bar=1H&limit=5` → 200, 263ms;
`/v5/public/funding-rate?instId=BTC-USDT-SWAP` → 200, 282ms; OI → 200, 258ms).
That doesn't prove they work from Render Oregon — but it does prove they're
not broadly geo-fenced at the network layer.

### Three possibilities, ranked by likelihood
1. **OKX briefly blocked the Render Oregon /16 around 2026-05-04 cutover, then
   un-blocked it.** Akamai/CloudFront/CDN-layer geo-fencing is rolled
   weekly. The `0940681` commit captured a real but transient block.
   Tonight's 200 means the block has lifted.
2. **The 104 errors were caused by something other than geo-fencing** — e.g.
   missing `User-Agent`, OKX cf-bot fingerprinting on the legacy `_SESSION`
   header set, or a TCP keepalive race in an old urllib3 version. Note:
   `_SESSION` sends a Chrome 122 UA (`data_feeds.py:73`), but `urllib.request`
   (used by `_probe_feed`) sends `PolarisEdge-DiagnosticsProbe/1.0`. Same
   IP, different UA, different result is possible — but probe got 200, so
   if anything `_SESSION`'s richer UA should fare *better*.
3. **The block applies only to specific OKX endpoints** (e.g. the v5 OHLCV
   path) but not `/public/time`. This is the pattern at FRED (see §3).

### Recommendation — DO NOT revert the chain reorder yet
The `0940681` reorder still has merit even if the geo-block is gone:
Gate.io's Render-side latency (399ms) is comparable to OKX's (185ms), and
Gate.io has wider tier-2 alt coverage (TAO, ZBCN, SHX). Keeping OKX at #5 in
chart-OHLCV and #2 in funding doesn't cost much when Kraken hits on the
majors. **But we need data before reverting** — adding an OKX-OHLCV probe to
`/diagnostics/feeds` is the only clean way to get it.

### Concrete change (Wave 2 quick win — REQUIRES APPROVAL TO LAND)
Extend `_FEED_PROBES` in `routers/diagnostics.py:311-325` to add three
OKX endpoint variants. **Do NOT push without approval.**

```python
# routers/diagnostics.py — proposed addition, line ~319
_FEED_PROBES: list[dict[str, Any]] = [
    # … existing entries …
    {"name": "OKX REST (geo-blocked)", "url": "https://www.okx.com/api/v5/public/time", "method": "GET", "category": "ohlcv"},
    # NEW — distinguishes whether OHLCV/funding/OI paths share the public-time path's reachability
    {"name": "OKX OHLCV (BTC-USDT)", "url": "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1H&limit=1", "method": "GET", "category": "ohlcv"},
    {"name": "OKX funding (BTC swap)", "url": "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP", "method": "GET", "category": "ohlcv"},
    {"name": "OKX OI (BTC swap)", "url": "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP", "method": "GET", "category": "ohlcv"},
    # … existing CoinGecko / F&G / FRED …
]
```

After deploy, re-check `/diagnostics/feeds`. If all three return 200, file
**revert recommendation R-1** and bump OKX back to position #2 in
`fetch_chart_ohlcv` (saves ~200ms of Gate.io latency on every Kraken miss).
If any return non-200, the current chain stays as-is and we have evidence.

### Decision needed from David
- Approve the /diagnostics/feeds extension (4 new probe URLs)?
- If post-extension data shows OKX OHLCV is reachable — approve revert of
  `0940681`'s chart-chain reorder?

---

## §2. Bybit — 403 is not a geo-block on Render, it's CloudFront on the auditor

### What I tested
| Probe | UA | Result |
|---|---|---|
| `https://api.bybit.com/v5/market/time` | (curl default) | 403 |
| `https://api.bybit.com/v5/market/time` | `PolarisEdge-DiagnosticsProbe/1.0` | 403 |
| `https://api.bybit.com/v5/market/time` | `Mozilla/5.0` | 403 |
| `https://api.bybit.com/v5/market/time` | full Chrome desktop UA + Accept | 403 |
| `https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&…` | `Mozilla/5.0` | 403 |
| `https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT` | `Mozilla/5.0` | 403 |
| `https://api.bybit.nl/v5/market/time` | (default) | 403 |
| `https://api.bytick.com/v5/market/time` | (default) | 403 |
| `https://api2.bybit.com/v5/market/time` | (default) | 404 (no such host pattern) |

### Body of the 403 — definitive proof
```
{ error: The Amazon CloudFront distribution is configured to block access
  from your country }
```

**This is geo-fencing on the AUDITOR's IP, not on Render.** Tonight's
`/diagnostics/feeds` from Render → 403 in **38ms**. That's faster than
Render's typical TLS handshake to CloudFront from Oregon. Possibilities:

1. CloudFront is rejecting at TLS-edge based on IP — same as the auditor.
2. Render's request is missing some required header that all Bybit clients
   include (e.g. `X-BAPI-API-KEY` is *required* on certain v5 paths even for
   public read; `X-BAPI-RECV-WINDOW`).
3. Bybit recently moved API gating; `api.bybit.com` may now require
   `api.bybit.com/v5/...` with `X-BAPI-SIGN` headers even on public reads.

The 38ms latency from Render is suspicious — it's CloudFront's own L1 edge
rejecting at TLS without proxying to origin. That looks like **a
country-level block** — but Render Oregon is in `us-west-2`, the friendliest
geo for Bybit. So this is likely a **referrer / UA / request-fingerprint block**.

### Code site that depends on Bybit
- `data_feeds.py:333` `_BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"`
- `data_feeds.py:470-481` — funding rate primary fetcher
  ```python
  resp = _SESSION.get(_BYBIT_TICKERS_URL, params={"category": "linear", "symbol": symbol}, timeout=6)
  ```
  Uses `_SESSION` which carries Chrome 122 UA. Should work… but didn't.
- `data_feeds.py:650` `fetch_bybit_klines` — chart OHLCV fallback #3
  ```python
  resp = _SESSION.get("https://api.bybit.com/v5/market/kline", params={...}, timeout=8)
  ```
- `data_feeds.py:980` (NOT 921) — open-interest primary fetcher

### What the 403 in production means
The user-facing tile saying "backfill pending" tonight is **consistent with
the funding fetcher silently 403-ing**. Trace:
1. `get_funding_rate(pair)` calls Bybit at `data_feeds.py:470` → 403
2. Falls through to OKX at `:487` → 200 (OKX is reachable, see §1)
3. Returns OKX-sourced funding rate, marked `source="okx"`
4. **OR:** OKX silently fails for non-major pairs (no `BTC-USDT-SWAP` analog
   for some symbols) → returns `_empty_result("Funding N/A...")` (line 508)
5. UI shows "backfill pending"

So **the D8-era promotion of Bybit to primary funding (`41e6a8c`) is not
actually firing**. Render is hitting OKX (the supposed-fallback) for every
funding call. That's the OPPOSITE of what `41e6a8c` aimed for.

### Two diagnostic gaps to close
**a)** The probe URL `https://api.bybit.com/v5/market/time` is a separate
endpoint from `/v5/market/tickers` and `/v5/market/kline`. CloudFront
sometimes block-lists by path. Probe-vs-actual mismatch. Same fix pattern as
§1 — add probes for the actual code-site URLs.

**b)** Bybit's CloudFront block may key on `User-Agent` or missing API
headers. The `_SESSION` UA is full Chrome 122 — should pass. But the
`_probe_feed` UA is the diagnostics-probe string, which IS likely blocked.

### Recommendation — three steps, in order
**[B-1, P0, NOW]** Extend `/diagnostics/feeds` with the actual Bybit code
URLs (and use `_SESSION` UA, not the diagnostics-probe UA, for these only):

```python
# routers/diagnostics.py — replace the single Bybit probe
{"name": "Bybit ticker (linear BTC)", "url": "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", "method": "GET", "category": "ohlcv"},
{"name": "Bybit kline (spot BTC)",   "url": "https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&interval=60&limit=1", "method": "GET", "category": "ohlcv"},
```
Plus optionally: in `_probe_feed`, send a Chrome UA when the URL hostname is
`api.bybit.com` to mirror what `_SESSION` actually does:

```python
# routers/diagnostics.py:336-338 (_probe_feed)
if "bybit.com" in spec["url"]:
    req.add_header("User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36")
else:
    req.add_header("User-Agent", "PolarisEdge-DiagnosticsProbe/1.0")
```

**[B-2, P1, depends on B-1]** If even with Chrome UA Bybit still 403s from
Render, then the funding-rate primary chain is broken in prod. Either:
  - **Promote OKX back to primary** in `get_funding_rate` (revert
    `41e6a8c` for funding only — keep the OI reorder which has its own data).
  - **OR** investigate Bybit testnet (`api-testnet.bybit.com`) for read-only
    public endpoints (sometimes loosely gated). NOT recommended — testnet
    funding rates are synthetic and not market-truthful.
  - **OR** add Coinalyze or a paid funding source. Out-of-scope for tonight.

**[B-3, P2]** Add a metrics counter `funding_source_used{source=...}` so the
team can see at a glance which fallback is firing. 5 LOC + Prometheus
exporter. Not blocking.

### Decision needed from David
- Approve the /diagnostics/feeds Bybit URL replacement?
- If post-deploy probe confirms Render still 403s on Bybit kline/ticker,
  approve reverting `41e6a8c`'s funding-rate reorder (Bybit→OKX)?

---

## §3. FRED — probe URL is wrong AND the host is unreachable from Render

### What the probe hits vs what the code hits
- **Probe** (`routers/diagnostics.py:324`):
  `HEAD https://fred.stlouisfed.org/` — the HTML site root.
- **Code** (`data_feeds.py:4723, 4751, 4829, 4964`):
  `GET https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}` — same
  host, different path. CSV download endpoint.

Probe and code share a host but exercise different routes. Both are on the
**Akamai edge** (`fred.stlouisfed.org` → `e13502.b.akamaiedge.net`).

### What I observed from auditor IP
| URL | UA | Result |
|---|---|---|
| `HEAD https://fred.stlouisfed.org/` | curl default | 200, 339ms |
| `HEAD https://fred.stlouisfed.org/` | `PolarisEdge-DiagnosticsProbe/1.0` | 000 (timeout, 10s) |
| `GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL` | curl default | 000 (timeout, 12s) |
| `GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL` | `Mozilla/5.0` | 000 (timeout, 30s) |
| `HEAD https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL` | `Mozilla/5.0` | 000 (timeout, 10s) |

The probe URL works **only** with no/curl UA. With either of our two used
UAs (`PolarisEdge-DiagnosticsProbe/1.0` from the diagnostics path, and
`Mozilla/5.0` from `_FRED_SESSION`), it times out. **The CSV download path
times out under every UA.**

### What tonight's `/diagnostics/feeds` proved
From inside Render Oregon: `fred.stlouisfed.org/` HEAD → 5169ms timeout.
That's the urllib 5s timeout firing; the kernel was either still in
TCP-handshake or got SYN-blocked by Akamai's bot WAF.

### Why this matters
`fetch_fred_macro` fetches **5 series** in parallel, each via the CSV
endpoint (`data_feeds.py:4723`):
- `M2SL` — M2 money supply
- `DGS10` — 10-year Treasury yield
- `DGS2` — 2-year Treasury yield (yield curve spread)
- `CPIAUCSL_PC1` — CPI YoY %
- `NAPM` — ISM Manufacturing PMI

When all 5 fail, `_macro_cached_get` returns `None` →
`_FRED_MACRO_FALLBACKS_SG` kicks in (`data_feeds.py:4776-4779`). Those
fallbacks are **hardcoded constants from late 2024**:
```python
"m2_supply_bn":      21_500.0,
"ten_yr_yield":          4.35,
"two_yr_yield":          4.70,
"cpi_yoy":               3.2,
"ism_manufacturing":    52.0,
```

So tonight's signal output, if FRED is down on Render, **uses 6+ month-old
macro values for Layer-2 input**. The composite signal still computes a BUY/HOLD/
SELL but with stale macro context. CLAUDE.md §9's Layer 2 is silently degraded.

### Three possible fixes
**Path A — switch to FRED's actual API host.** `api.stlouisfed.org` redirects
to `research.stlouisfed.org/docs/api/` (verified — auditor `HEAD` returns
301 in 300ms). The official FRED API requires a free API key:
- `GET https://api.stlouisfed.org/fred/series/observations?series_id=M2SL&api_key=…&file_type=json`
- Free; 120 req/min limit; documented at https://fred.stlouisfed.org/docs/api/api_key.html
- Returns JSON, smaller payload than CSV.
- Allowlist already includes `api.stlouisfed.org` (`data_feeds.py:256`).
- **Net change:** rewrite `fetch_fred_macro` to use the API host with a key
  read from `FRED_API_KEY` env var. Falls back to constants if no key. Lift
  ~40 LOC. No new env-var pattern needed.

**Path B — switch to a different macro source entirely.** Options:
- **U.S. Treasury Direct** for yields (`https://home.treasury.gov/`): no
  geo-fence on Render; CSV/XML; lift ~60 LOC.
- **BLS** (Bureau of Labor Statistics) for CPI: API key required; 25/day
  free; `https://api.bls.gov/publicAPI/v2/timeseries/data/`.
- **yfinance** is already used (`data_feeds.py:142-205`) for DXY/VIX/UST/M2
  and works from Render today. Worth checking if it covers all 5 series.
- This path is the most resilient long-term but the highest LOC.

**Path C — just fix the probe to match code, document the outage, leave
the data path alone.** Acknowledge that FRED is degraded on Render and lean
on the existing fallback constants until the next sprint window. This is
the cheapest tonight (~5 LOC change) but means stale macro until paid-tier
upgrade.

### Recommendation — F-1 + F-2 stack
**[F-1, P0, quick win]** Fix the probe URL to match the code path so we get
real signal:
```python
# routers/diagnostics.py:324 — replace
{"name": "FRED CSV (M2SL)", "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL", "method": "GET", "category": "macro"},
```
This will surface the truth (probably "unreachable" / TimeoutError, matching
what the actual code hits). Operators see what the system experiences.

**[F-2, P1, weekend lift]** Migrate to FRED API (Path A) with `FRED_API_KEY`
env. Add `FRED_API_KEY` to `_ENV_MAP` (`data_feeds.py:7857`) and the
allowlist. Render dashboard adds the secret. Net: macro source restored,
no fallback-constant drift, ~40 LOC.

### Decision needed from David
- Sign up for a free `FRED_API_KEY` at https://fred.stlouisfed.org/docs/api/api_key.html?
  (1 minute, no credit card; sets us up for Path A).
- If yes — approve F-2 lift this week.

---

## §4. CoinGecko 429 — last-resort fallback is being hit too often

### What's actually happening
`/diagnostics/feeds` from Render hits `https://api.coingecko.com/api/v3/ping`
→ 429. The `ping` endpoint is rate-limited the same as everything else (free
tier ~30 req/min, no per-route exemption).

CoinGecko 429 in tonight's snapshot is a smoking gun for **upstream chain
exhaustion** — when Kraken/Gate.io/Bybit all miss for a tier-2 alt, the
chart-OHLCV path falls all the way through to CoinGecko (position #6 in
`fetch_chart_ohlcv`, `crypto_model_core.py:619-654`). That's a deliberate
last-resort, not a hot path.

### Where CoinGecko gets called from
**OHLCV fallback** (last resort, `crypto_model_core.py:642-646`):
```python
_r = _df._SESSION.get(
    f"https://api.coingecko.com/api/v3/coins/{_cg_id}/ohlc",
    params={"vs_currency": "usd", "days": str(_days)},
    timeout=10,
)
```
Uses `_SESSION` which has `status_forcelist=[429, 500, 502, 503, 504]` and
**3 retries with `backoff_factor=1`** (`data_feeds.py:64-66`). On a 429:
- Try 1 → 429 → wait 1s
- Try 2 → 429 → wait 2s
- Try 3 → 429 → return 429 to caller

That's **3 hits to CoinGecko per logical request** when we're already over
budget. With the `_COINGECKO_LIMITER` set to 0.4 calls/second
(`data_feeds.py:241` — 24/min cap, free tier limit is 30/min), the limiter
should prevent client-side overrun, BUT:
- **The OHLCV fallback at `crypto_model_core.py:642` does NOT acquire the
  limiter.** Compare to `data_feeds.py:846` which does
  (`_COINGECKO_LIMITER.acquire()` before its CoinGecko call).
- Result: every cascade-fallback to CoinGecko OHLCV bypasses the global rate
  budget. With multiple pairs and timeframes scanning concurrently, this
  exhausts the budget fast.

### Other call sites — limiter audit
Grep confirms `_COINGECKO_LIMITER.acquire()` is used at only a handful of
the ~9 CoinGecko call sites (`data_feeds.py:539, 726, 3051, 3134, 3842,
5760, 6803` per Wave 1). The others rely on `_SESSION`'s urls_expire_after
cache + retry adapter, which **doesn't enforce a rate budget** — it caches
hits and retries 429s.

### Daily rate budget tracker
**There is no budget tracker.** The system has:
- A token-bucket `_COINGECKO_LIMITER` (`data_feeds.py:241`) — short-window
  smoothing, not daily.
- The `_SESSION` cache (`data_feeds.py:60` + `_URLS_EXPIRE_AFTER`) — caches
  responses, not requests.
- No counter logging "we made N CoinGecko requests today, free tier is M."

So we don't know how close to the cap we run each day, only that we
periodically hit it.

### Why backoff is "implemented but probably misbehaving"
The geometric backoff is in `_SESSION` via `Retry(backoff_factor=1)`. That
gives delays of 1s, 2s, 4s, 8s, 16s on consecutive retries (backoff_factor
× 2^(retry-1)). On a 429, this means **per failed request: 7s of in-thread
sleep**. With our scanner running multiple pairs in parallel, three or four
simultaneous 429s pile up to 21–28s of blocked-thread time on the
indicator-fetch worker pool. That's not a hard outage but it DOES make
scans feel slow when CoinGecko is angry.

Worse: when CoinGecko returns `Retry-After`, urllib3 doesn't honor it
unless `respect_retry_after_header=True` is passed to `Retry`. We don't pass
it. So we ignore CoinGecko's hint to wait 60s and retry in 1–4–8.

### Recommendation — three improvements
**[CG-1, P1, easy]** Wire `_COINGECKO_LIMITER.acquire()` into the OHLCV
fallback at `crypto_model_core.py:642`:

```python
# crypto_model_core.py:641-646 — proposed change
if _cg_id:
    _df._COINGECKO_LIMITER.acquire(timeout=10.0)  # NEW LINE
    _r = _df._SESSION.get(
        f"https://api.coingecko.com/api/v3/coins/{_cg_id}/ohlc",
        params={"vs_currency": "usd", "days": str(_days)},
        timeout=10,
    )
```
3 LOC; immediately respects the 24-req/min budget instead of bypassing it.

**[CG-2, P1, easy]** Honor `Retry-After`:
```python
# data_feeds.py:63-67 — replace the Retry config
retry = Retry(
    total=3, backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"], raise_on_status=False,
    respect_retry_after_header=True,  # NEW LINE
)
```
1 LOC; lets CoinGecko's CDN-side hint override our 1-2-4 fallback.

**[CG-3, P2, medium]** Add a daily request counter so we know our budget
posture:
```python
# data_feeds.py — new helper at top of file
_CG_DAILY_COUNT = {"day": "", "count": 0}
_CG_DAILY_LOCK = threading.Lock()

def _cg_daily_tick() -> int:
    """Increment today's CoinGecko request counter; return new value."""
    today = time.strftime("%Y-%m-%d")
    with _CG_DAILY_LOCK:
        if _CG_DAILY_COUNT["day"] != today:
            _CG_DAILY_COUNT["day"] = today
            _CG_DAILY_COUNT["count"] = 0
        _CG_DAILY_COUNT["count"] += 1
        return _CG_DAILY_COUNT["count"]
```
Wire `_cg_daily_tick()` into every CoinGecko call site, then expose it via
`/diagnostics/feeds` as a new field `coingecko_daily_count`. ~30 LOC.

**[CG-4, P3, decision]** Free tier is 10K req/month + 30 req/min hard cap.
Pro tier is 500 req/min + 500K req/month at $129/mo. **If CG-3 logging
shows we routinely exhaust 10K/mo or hit 30 req/min, recommend Pro.**
That's a David-level decision.

### Decision needed from David
- Approve CG-1 + CG-2 (4 LOC total, low-risk quick wins)?
- Approve CG-3 (daily counter; 30 LOC, no API change)?
- After 1 week of CG-3 data — re-evaluate Pro upgrade?

---

## §5. Cache TTL audit follow-up — drift NOT reconciled

### Wave 1 findings vs current code
| §12 directive | Code (`data_feeds.py`) | Wave 1 status | Wave 2 verification |
|---|---|---|---|
| Funding rates: 10 min | `_CACHE_TTL_SECONDS = 300` (line 340) | DRIFT | **STILL DRIFT** — verified 2026-05-06 |
| Funding rates: 10 min | `_MULTI_FR_TTL = 300` (line 1454) | DRIFT | **STILL DRIFT** |
| On-chain: 1 hour | `_GN_TTL = 3600` (line 2108) | OK | OK |
| On-chain: 1 hour | `_ONCHAIN_TTL = 3600` (line 519) | OK | OK |
| On-chain: 1 hour | `_CQ_TTL = 600` (line 2028) | DRIFT | **STILL DRIFT** — CryptoQuant cache is 6× more aggressive than §12 |
| F&G: 24 hour | `_FNG_TTL = 86400` + `_FNG2_TTL = 86400` | OK (but duplicated) | Still duplicated; LOW |

`git log --since="2026-05-04" -- data_feeds.py` returns no commits — no
reconciliation has happened since Wave 1.

### Recommendation — Wave 2 quick win batch
**[T-1, P1, 6 LOC]** Pick one direction. CLAUDE.md §12 is the spec. I
recommend updating CODE to match SPEC, since §12 was authored deliberately:

```python
# data_feeds.py:340
_CACHE_TTL_SECONDS = 600  # 10-minute cache (per CLAUDE.md §12 funding rate TTL)

# data_feeds.py:1454
_MULTI_FR_TTL  = 600  # 10-minute cache (per CLAUDE.md §12)

# data_feeds.py:2028
_CQ_TTL = 3600  # 1-hour cache (per CLAUDE.md §12 on-chain TTL)
```

Alternative: if 5min funding TTL is intentional (funding flips matter for
live signal), update CLAUDE.md §12 to "5 min" instead. Either way is
defensible — what's NOT defensible is leaving the discrepancy. **Pick one
and document.**

### Decision needed from David
- T-1: change code to match §12 (600/600/3600)? OR change §12 to match
  code? Either works; we just need a single source of truth.

---

## §6. Glassnode key fragility — Wave 1 finding still stands

### Verification
`get_glassnode_onchain` reads the key via `_load_api_keys()` → file-only:
```
data_feeds.py:2121-2122
    keys = _load_api_keys()
    api_key = keys.get("glassnode_key", "").strip()
```

`_load_api_keys()` at `data_feeds.py:1831-1846` reads `alerts_config.json`
**only**. No env-var fallback path. There IS an `_ENV_MAP` table at
`data_feeds.py:7839-7857` mapping `glassnode_key → GLASSNODE_API_KEY`, but
that table is consumed only by `_get_runtime_key()`, which Glassnode does
not call.

`alerts.py:127-143` `_SENSITIVE_ENV_MAP` is a similar table for OKX trading
keys + email_pass — also doesn't include `glassnode_key`.

So the Wave 1 finding is unchanged: **Glassnode key lives only on the
persistent disk's `alerts_config.json`. Render service deletes will lose
it. Env-var rotation cannot touch it.**

### Concrete fix — exact code change
Wire `_load_api_keys()` to honor environment-variable overrides, the same
way `alerts.load_alerts_config()` does for OKX trading creds. Smallest
surface change:

```python
# data_feeds.py:1831 (REPLACEMENT for the function body)
import os as _os

# Map of API key fields → env var names. Mirrors _ENV_MAP at 7839 but
# applied to _load_api_keys so paid sources read env > file.
_API_KEY_ENV_MAP = {
    "coingecko_key":     "SUPERGROK_COINGECKO_API_KEY",
    "lunarcrush_key":    "LUNARCRUSH_API_KEY",
    "coinmarketcap_key": "COINMARKETCAP_API_KEY",
    "glassnode_key":     "GLASSNODE_API_KEY",
    "cryptoquant_key":   "CRYPTOQUANT_API_KEY",
    "coinglass_key":     "COINGLASS_API_KEY",
    "coinalyze_key":     "SUPERGROK_COINALYZE_API_KEY",
    "tokenomist_key":    "TOKENOMIST_API_KEY",
    "etherscan_key":     "ETHERSCAN_API_KEY",
    "cryptorank_key":    "CRYPTORANK_API_KEY",
    "dune_key":          "DUNE_API_KEY",
    "cryptopanic_key":   "CRYPTOPANIC_API_KEY",
}

def _load_api_keys() -> dict:
    """Load API keys from env vars (priority) merged with alerts_config.json (fallback).

    P0 audit fix (2026-05-06 Wave 2): Glassnode and other paid keys
    previously lived ONLY in alerts_config.json on the persistent disk.
    Env-var rotation didn't apply, and Render service deletes lost the
    keys. Now: env var wins; file is a backup for legacy installs.
    """
    global _paid_key_cache, _paid_key_cache_ts
    now = time.time()
    with _cache_lock:
        if now - _paid_key_cache_ts < _PAID_KEY_TTL:
            return dict(_paid_key_cache)
        # Start with file values (legacy / dev-mode)
        file_keys: dict = {}
        try:
            if _os.path.exists(_API_KEYS_FILE):
                with open(_API_KEYS_FILE, "r", encoding="utf-8") as f:
                    file_keys = _json.load(f)
        except Exception:
            pass
        # Env vars override file values
        for json_key, env_name in _API_KEY_ENV_MAP.items():
            env_val = _os.environ.get(env_name, "").strip()
            if env_val:
                file_keys[json_key] = env_val
        _paid_key_cache = file_keys
        _paid_key_cache_ts = now
        return dict(_paid_key_cache)
```

~30 LOC; existing callers see no surface change; test impact is one new
unit test fixture (env var set → key returned even without JSON file).

Then in `render.yaml`, add:
```yaml
- key: GLASSNODE_API_KEY
  sync: false
- key: CRYPTOQUANT_API_KEY
  sync: false
- key: LUNARCRUSH_API_KEY
  sync: false
- key: CRYPTORANK_API_KEY
  sync: false
- key: COINMARKETCAP_API_KEY
  sync: false
- key: COINGLASS_API_KEY
  sync: false
- key: TOKENOMIST_API_KEY
  sync: false
- key: COINALYZE_API_KEY
  sync: false
- key: DUNE_API_KEY
  sync: false
- key: CRYPTOPANIC_API_KEY
  sync: false
```
(Some of these may already exist in `render.yaml` — verify before adding.)

### Decision needed from David
- Approve KEY-1 (~30 LOC + 11 render.yaml entries)? Strict env-var-wins
  semantics on `_load_api_keys()` mirroring `_SENSITIVE_ENV_MAP` for OKX.

---

## §7. Quick-win batch — fits one commit, low blast radius

If David approves these together as one Wave-2 commit:

| ID | Description | LOC | Risk |
|---|---|---:|---|
| F-1 | Fix FRED probe URL to match code path (CSV download) | 2 | None |
| B-1 | Replace Bybit `/v5/market/time` probe with two real-code URLs (kline + ticker), use Chrome UA on Bybit only | ~15 | None |
| OKX-PROBE | Add 3 OKX probes (OHLCV, funding, OI) — keeps existing `/public/time` for comparison | ~6 | None |
| CG-1 | Acquire `_COINGECKO_LIMITER` in OHLCV fallback path | 3 | None |
| CG-2 | `respect_retry_after_header=True` on `_SESSION` Retry config | 1 | None |
| T-1 | Reconcile funding TTL (300→600) + CryptoQuant TTL (600→3600) to match §12 | 6 | None |

Total: ~33 LOC across `data_feeds.py`, `crypto_model_core.py`,
`routers/diagnostics.py`. All are diagnosis-improvements or align-with-spec
fixes — no behavioral surprise. `pytest -m "not slow"` should pass without
edits.

KEY-1 (Glassnode env-var fallback) is medium-risk because it changes
`_load_api_keys()` semantics for everyone. Recommend separate commit + at
least one new test fixture.

OKX chain-revert (R-1) and Bybit funding revert (B-2) BOTH depend on
post-deploy probe data and SHOULD NOT land in the quick-win batch.

---

## §8. Items needing David's input

1. **OKX-PROBE deploy + revert decision (R-1 / §1).** Approve the four
   OKX endpoint probes? After post-deploy data shows OKX OHLCV is or isn't
   reachable from Render, revert `0940681`'s chain reorder?
2. **Bybit probe replacement + revert decision (B-1 / B-2 / §2).** Approve
   replacing the Bybit `/v5/market/time` probe with kline+ticker probes? If
   data shows Bybit still 403s, revert `41e6a8c`'s funding promotion?
3. **FRED API migration (F-2 / §3).** Sign up for free `FRED_API_KEY` at
   https://fred.stlouisfed.org/docs/api/api_key.html ? Approve ~40 LOC
   migration to `api.stlouisfed.org`?
4. **CoinGecko Pro tier (CG-4 / §4).** After CG-3 logs a week of usage,
   re-evaluate $129/mo Pro upgrade?
5. **Cache TTL reconciliation direction (T-1 / §5).** Update code to match
   §12 (600s funding, 3600s CryptoQuant)? Or update §12 to "5 min funding"?
6. **Glassnode env-var rotation (KEY-1 / §6).** Approve `_load_api_keys()`
   env-var precedence rewrite? Add 11 secret entries to `render.yaml`?

---

## §9. Render-side log capture proposal (out-of-scope for tonight)

The single biggest reason Wave 2 has any uncertainty is that `0940681`'s
"ConnectionResetError(104)" log evidence has rolled off. If we'd preserved
it (one screenshot, one log excerpt in the commit), we wouldn't be guessing
whether OKX is currently blocked.

**Suggestion for next sprint:** any commit message that cites observed
upstream behavior should include either:
- A 30-line log excerpt in the commit body (with PII/tokens scrubbed), or
- A path to a saved log file (e.g. `docs/incident-logs/2026-05-04_okx-104.log`).

This isn't tonight's work, but it would have made Wave 2 a 30-minute
diagnosis instead of a 90-minute one.

---

## Footer — file:line index of every claim in this report

| Section | Claim | Evidence path |
|---|---|---|
| §1 | OKX `/v5/public/time` reachable from Render today | tonight's `/diagnostics/feeds` JSON |
| §1 | OKX OHLCV path: `data_feeds.py:582` | grep + read |
| §1 | OKX funding path: `data_feeds.py:334, 487` | grep + read |
| §1 | OKX OI path: `data_feeds.py:997` | grep + read |
| §1 | Original 0940681 commit didn't preserve log evidence | `git show 0940681` |
| §2 | Bybit 403 body: "CloudFront blocks access from your country" | `curl https://api.bybit.com/v5/market/time` |
| §2 | Bybit primary funding fetcher: `data_feeds.py:470` | read |
| §2 | Bybit chart-OHLCV fallback: `data_feeds.py:650` | read |
| §2 | Bybit OI primary: `data_feeds.py:980` | read |
| §3 | FRED CSV path used by code: `data_feeds.py:4723, 4751, 4829, 4964` | grep |
| §3 | FRED probe URL: `routers/diagnostics.py:324` | read |
| §3 | FRED hardcoded fallback constants: `data_feeds.py:4618-4624` | read |
| §3 | FRED is on Akamai edge | `nslookup fred.stlouisfed.org` |
| §3 | FRED CSV times out from auditor: 12s | `curl https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL` |
| §4 | CoinGecko OHLCV fallback bypasses limiter: `crypto_model_core.py:642-646` | read |
| §4 | `_COINGECKO_LIMITER` set to 0.4/s: `data_feeds.py:241` | read |
| §4 | `_SESSION` 3 retries with `backoff_factor=1`: `data_feeds.py:63-66` | read |
| §4 | `respect_retry_after_header` not passed: `data_feeds.py:63-66` | read |
| §5 | `_CACHE_TTL_SECONDS = 300`: `data_feeds.py:340` | read |
| §5 | `_MULTI_FR_TTL = 300`: `data_feeds.py:1454` | read |
| §5 | `_CQ_TTL = 600`: `data_feeds.py:2028` | read |
| §5 | No reconciliation commits since Wave 1 | `git log --since=2026-05-04 -- data_feeds.py` |
| §6 | Glassnode reads via `_load_api_keys()`: `data_feeds.py:2121-2122` | read |
| §6 | `_load_api_keys()` reads file only: `data_feeds.py:1831-1846` | read |
| §6 | `_ENV_MAP` exists but only used by `_get_runtime_key`: `data_feeds.py:7839-7857` | read |
| §6 | `alerts._SENSITIVE_ENV_MAP` doesn't include glassnode: `alerts.py:127-143` | read |

End of Wave 2 findings. No code modified.
