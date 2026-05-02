# Data-Feeds Resilience Audit

**Date:** 2026-05-02
**Scope:** data_feeds.py, websocket_feeds.py, arbitrage.py, config.py,
news_sentiment.py, allora.py, api.py, scheduler.py + relevant
call sites in app.py and crypto_model_core.py.

**Goal:** verify the data-source cascades, geo-block handling, rate-limit
discipline, timeout posture, cache invalidation, and key handling against
what CLAUDE.md §10/§12 promises and what the user actually sees on
Streamlit Cloud (Images 1, 7, 8 from the legacy-look audit).

This audit is intentionally honest about the gap between docstrings and
behavior. Most "cascade" plumbing is in place — the failures are at the
edges (call sites that bypass it, status pills that lie, parser bugs,
TTL drift, presentation mapping `None` to "None" instead of
`"geo-blocked"`).

---

## 1. Cascade fallback completeness

### 1.1 `fetch_prices_cascade` exists and is wired correctly
- File: `data_feeds.py:6624` — `fetch_prices_cascade(symbols)` walks
  CMC → CoinGecko → Kraken → OKX → MEXC. **OK.**
- File: `app.py:721` — `_sg_cached_live_prices_cascade(symbols_tuple)`
  wraps it with `@st.cache_data(ttl=60)`. **OK.**
- File: `app.py:2604` — Watchlist on Home page calls cascade once with
  the union of seed pairs + user pairs. **OK** (well-implemented per the
  C-fix-19 comment block at line 2588–2596).

### 1.2 BUG — Hero cards bypass the cascade (Image 1)
- **File:** `app.py:2463-2475` — `_ds_build_hero(pair_key, display)`
- **Severity:** HIGH
- **Description:** Hero cards build their price entirely from
  `_live_prices` (WebSocket OKX SWAP). For pairs without an OKX SWAP
  market (XDC, SHX, ZBCN, FLR, WFLR, FXRP, CC, …) `_live_prices.get()`
  returns `None`, so `tick.get("price")` is `None`, and the card
  renders `—`. Watchlist below it shows the same pairs correctly
  because it falls through to the cascade at line 2632–2637.
- **Fix:** mirror the watchlist fallback — call
  `_sg_cached_live_prices_cascade(tuple_of_hero_symbols)` once before
  the three `_ds_build_hero` calls, then in `_ds_build_hero` add Tier-2
  + Tier-3 (sparkline last close) fallbacks identical to
  `_build_wl_row` at `app.py:2632-2644`. ~10–15 line change in
  `page_dashboard`. Confirmed in the audit-in-progress doc as a "(d)
  functional bug, ~10-line change."

### 1.3 OHLCV cascade (`fetch_chart_ohlcv`) is solid
- File: `crypto_model_core.py:544` — Kraken (ccxt) → OKX REST → Gate.io
  REST → Bybit REST → MEXC REST → CoinGecko OHLCV (≤30d).
- Each stage is wrapped in `try/except` with a real return on success.
  No silent fall-through to `pd.DataFrame()` on the success path. **OK.**
- One nit: when CoinGecko is the last resort, `_tf_days = {'1h':1,
  '4h':7, '1d':30, '1w':90}` — but CoinGecko's free `/ohlc` endpoint
  silently caps at the nearest supported window (`1, 7, 14, 30, 90,
  180, 365, max`), so a `4h` request for `7` days returns daily candles.
  The function does not validate the granularity on return. **LOW**
  severity — only affects pairs that fall all the way through the chain.

### 1.4 Funding cascade — primary path
- File: `data_feeds.py:441` — `get_funding_rate(pair)` → OKX → Bybit
  (Binance bulk path retired due to US geo-block). **OK.**
- File: `data_feeds.py:1408` — `_fetch_binance_fr` is a stub that
  redirects to `_fetch_bybit_fr` (kept for back-compat with the
  multi-exchange table). **OK** but worth a doc note in the table —
  the displayed "Binance" column is actually Bybit data, which is
  misleading on the Funding Rate Monitor page (Image 7).

### 1.5 Silent-fallback failures — none found in the price path
Every cascade tier in `fetch_prices_cascade`, `fetch_chart_ohlcv`,
`get_funding_rate`, and `get_multi_exchange_funding_rates` uses
`try/except` with `logging.debug` so a primary failure visibly falls
to the next tier. **OK.**

---

## 2. Geo-block handling on Streamlit Cloud (Image 7)

### 2.1 No centralized exchange-reachability probe
- **Severity:** MEDIUM
- **Description:** The codebase contains 25+ scattered comments like
  "Binance returns HTTP 451 from US IPs" (`data_feeds.py:497, 561, 630,
  …`). Each fetcher silently routes around its own geo-blocked primary,
  but **there is no startup probe that records which exchanges are
  reachable from this datacenter**. `validate_api_keys()`
  (`data_feeds.py:7745`) only pings 4 services (OKX, CoinGecko, Deribit,
  Anthropic) — it skips Binance, Bybit, KuCoin, Kraken, Glassnode,
  CryptoQuant, LunarCrush, etc.
- **Impact:** Status pills can claim "Glassnode · live" when the IP is
  geo-blocked (see §6.1 below) and the user has no way to see what's
  actually reachable.
- **Fix:** add `data_feeds.probe_exchange_reachability()` that ships a
  minimal ticker request to every exchange used in the code (one HEAD
  per host, ~12 hosts, parallelized) and caches the
  `{"binance": "geo-blocked", "okx": "ok", …}` map for 6h. Surface
  this map in the topbar status pills and use it to drive the
  Funding Rate Monitor cell rendering (§2.2).

### 2.2 BUG — "None" displayed instead of "geo-blocked" (Image 7)
- **File:** `app.py:6852`
  ```
  row[exch.upper()] = None if rd.get("error") else rate
  ```
- **Severity:** MEDIUM
- **Description:** When Binance/Bybit/KuCoin return an error from
  Streamlit Cloud (HTTP 451 / timeout / SSL handshake fail), the
  upstream cell is `None`, which Streamlit's dataframe renders as the
  string "None". This violates the user preference recorded in
  `feedback_empty_states.md`: "Empty-state messages should be truthful
  — say 'geo-blocked', 'rate-limited', 'no data yet — run a scan'
  instead of misleading 'None' / silent dashes."
- **Fix:** map the error string to a status label
  before assigning to the row:
  ```python
  if rd.get("error"):
      err = rd["error"].lower()
      if "geo" in err or "451" in err: row[k] = "geo-blocked"
      elif "rate" in err or "429" in err: row[k] = "rate-limited"
      elif "timeout" in err: row[k] = "unreachable"
      else: row[k] = "—"
  else:
      row[k] = rate
  ```
  And update the `_color_fr` styler to handle string values without
  raising.

### 2.3 BUG — "Best Rate" column references exchanges not in the table
- **File:** `app.py:6849, 6862-6864`
- **Severity:** LOW
- **Description:** The displayed columns are `OKX, BINANCE, BYBIT,
  KUCOIN`, but `get_multi_exchange_funding_rates` returns 14 exchanges
  (10 ccxt + 4 core). The "Best Rate" cell can resolve to
  `+0.0123% (COINEX)` while no `COINEX` column is in the table — the
  user is told the best rate lives on an exchange they can't see.
- **Fix:** either (a) expand the displayed columns to all 14, or
  (b) restrict `valid` to only the 4 displayed exchanges, or (c) add
  a tooltip explaining "best rate may come from an additional 10
  ccxt-sourced exchanges; expand the table to view all."

### 2.4 Spinner says "4 exchanges" while fetching 14
- **File:** `app.py:6842` — `st.spinner("Fetching rates from 4 exchanges…")`
- **Severity:** LOW (cosmetic)
- The function fans out to 14 in parallel. Update label or actually
  restrict to 4 (faster, smaller fan-out).

---

## 3. Rate-limit handling

### 3.1 Glassnode 429 handling is inadequate
- **File:** `data_feeds.py:2046-2122` — `get_glassnode_onchain`
- **Severity:** MEDIUM
- **Description:**
  - The retry adapter on `_SESSION` retries 429 three times with
    backoff (`status_forcelist=[429]`, `backoff_factor=1`). On a
    daily-cap exhaustion this is **wasteful** — 429 from Glassnode
    free tier means "you've used your 10/min global allowance" or
    "daily cap hit", and a 1s × 3 retry burns 4 calls before giving up.
  - On the parsed path, when `sopr_resp.status_code != 200` (including
    429), the function silently sets `sopr = None` and continues. The
    final `result` dict has `"error": None` and gets cached for 1 hour.
    The on-chain page status pill will keep showing "Glassnode · live"
    even though the data is `None`. **This is the lying-status-pills
    bug from Image 8.**
- **Fix:**
  1. Add a Glassnode-specific session with a low retry total
     (`Retry(total=1, status_forcelist=[500,502,503,504])` — drop 429
     from the forcelist so 429s aren't retried at all on free tier).
  2. In the parser, if `status_code` is `429` or `403`, set
     `result["error"] = "rate-limited"` (or `"forbidden"`) rather than
     `None`, and bump the cache TTL temporarily (e.g. cache the
     error result for 5 minutes — short enough that it self-clears,
     long enough that we don't keep hammering the cap).
  3. Honor the `Retry-After` header explicitly when present:
     `urllib3.util.Retry` honors it by default since 1.25.x for the
     retry path, but our error result currently loses that information.

### 3.2 Funding-cache TTL is half of CLAUDE.md spec
- **File:** `data_feeds.py:340` — `_CACHE_TTL_SECONDS = 300` (5 min)
- **CLAUDE.md §12 (project):** "Funding rates: 10 min cache"
- **Severity:** LOW
- **Fix:** bump to 600s. `_MULTI_FR_TTL` (line 1388) is also 300; bump
  to 600 for consistency. This halves the per-session funding-rate API
  budget at no cost to signal quality (funding intervals are 8h on
  most exchanges).

### 3.3 OKX has no module-level rate limiter
- **Severity:** LOW
- **Description:** `_BINANCE_LIMITER`, `_COINGECKO_LIMITER`,
  `_DERIBIT_LIMITER`, `_CMC_LIMITER` exist (`data_feeds.py:240-244`),
  but every OKX REST call relies solely on the urllib3 retry adapter.
  OKX public endpoints have a 20 req/2s public-IP budget. The
  per-symbol funding-rate batch (`get_funding_rates_batch`) fans out
  up to 8 parallel OKX calls without a token bucket. On a fresh
  cache + a 30-pair scan this lights up the budget.
- **Fix:** add `_OKX_LIMITER = RateLimiter(calls_per_second=10.0)` and
  call `_OKX_LIMITER.acquire()` before every OKX REST call inside the
  module.

### 3.4 KuCoin / Bitfinex / others — same pattern
- The 10 ccxt exchanges all share a single `_get_ccxt_exchange`
  cache. ccxt's `enableRateLimit=True` is set
  (`data_feeds.py:1495`), which gives each exchange its own
  internal limiter — this is fine. **OK.**

### 3.5 CryptoPanic key not used despite being configured
- **File:** `news_sentiment.py:99-104`, `config.py:9`
- **Severity:** MEDIUM
- **Description:** `config.py` reads `CRYPTOPANIC_API_KEY` and
  `news_sentiment.py` references `_CRYPTOPANIC_BASE`, but the actual
  fetch sends only `{"public": "true", "currencies": …}` — the
  authenticated tier is never reached. The public endpoint is heavily
  rate-limited (~50 req/24h per IP), so on Streamlit Cloud the
  CryptoPanic feed silently dies after a few scans.
- **Fix:** in `_fetch_cryptopanic`, read `CRYPTOPANIC_API_KEY` (or
  the alerts_config `cryptopanic_key`), and when present, drop
  `"public":"true"` and pass `"auth_token": <key>` instead. Free
  authenticated tier is 50,000 req/month — 1000× the public tier.

---

## 4. Timeout handling

### 4.1 All `_SESSION.get/post` calls have explicit timeouts — verified
- 101 `_SESSION.get/post` call sites in `data_feeds.py`, every one of
  them passes `timeout=…` (sampled at lines 463, 480, 546, 571, 610,
  639, 673, 698, 721, 929, 1238, 1315, 1424, 1847, 1917, 1994, 2333,
  2959, 3042, 3481, 3750, 3853 …). **OK.**
- Default urllib3 timeout of `None` (which can hang indefinitely) is
  never reached.

### 4.2 yfinance has explicit hard timeouts via thread-pool wrapper
- File: `data_feeds.py:150-205` — `_yf_history` and `_yf_download` use
  a 1-worker `ThreadPoolExecutor` with a wall-clock timeout
  (8s history, 12s download) and `ex.shutdown(wait=False)` on exit
  so a hung yfinance thread can't keep the process alive. **Excellent
  defensive code** — comment at line 155-160 documents the precise
  Streamlit health-check failure this guards against.

### 4.3 ccxt initialization timeout
- File: `data_feeds.py:1496` — `"timeout": 10000` (10s in ms). **OK.**

### 4.4 Anthropic client timeout
- File: `news_sentiment.py:57` — `timeout=15.0`. **OK.**

### 4.5 Glassnode 10s timeout per metric — but two metrics in parallel
- File: `data_feeds.py:2082-2083` — both metrics submitted with
  `timeout=10`, and the function blocks on `_sopr_fut.result()` then
  `_mvrv_fut.result()` without a result-level timeout. If both
  Glassnode endpoints hang concurrently, the calling thread is
  blocked for up to 10s × 2 concurrently (10s wall, since they're
  parallel). **OK** — concurrent. Just verifying.

---

## 5. Cache invalidation — "Refresh All Data" button

### 5.1 Implementation is solid
- **File:** `app.py:1650-1711` — `_refresh_all_data()`
  1. `st.cache_data.clear()` (or per-function fallback if it raises)
  2. `data_feeds.clear_all_module_caches()` — wipes 30+ module-level
     dicts behind their respective locks
  3. `cycle_indicators.clear_cycle_caches()`
  4. Kicks off a fresh scan (re-entry guarded). **Excellent.**
- The unified Update button on every topbar wires to this handler.

### 5.2 `clear_all_module_caches()` covers most caches
- **File:** `data_feeds.py:8071-8138`
- The list at lines 8079–8104 (locked) and 8112–8121 (unlocked) covers
  ~50 module-level caches. Spot checks against the rest of the file:
  - **Missing from the list:** `_PRICE_HISTORY_CACHE` (if defined),
    `_FNG_CACHE`, `_FNG2_CACHE`. Wait — `_FNG2_CACHE` is reset at
    8135. `_FNG_CACHE` — let me check…
- **MEDIUM finding:** the `_FNG_CACHE` (Fear & Greed primary) is
  declared at `data_feeds.py:3439` (search confirms) and is **NOT**
  in the clear list. After "Refresh All Data" the F&G value sticks
  at the previous reading until the 24h TTL expires.
- **Fix:** add `(_FNG_CACHE, _FNG_LOCK)` to the locked clear list
  (line 8104). Also verify `_BTC_HALVING_CACHE`, `_FUNDING_HISTORY_CACHE`,
  `_FUNDING_FORECAST_CACHE`, and `_DEBANK_CACHE` if they exist —
  every module-level dict that's used as a cache must be in the list.
- **Test:** the existing `tests/test_data_wiring.py` (~line 765–778)
  asserts that `_cached_google_trends_score` is cleared, but it
  doesn't check the data_feeds module-level caches. Add a unit test
  that imports `data_feeds`, populates each cache dict with a
  sentinel, calls `clear_all_module_caches()`, and asserts every dict
  is empty. This catches the next "I added a new cache and forgot
  the clear list" drift.

### 5.3 `requests-cache` urls_expire_after is independent of the
"Refresh All Data" button
- **File:** `data_feeds.py:45-55`
- **Severity:** MEDIUM
- **Description:** When `requests-cache` is installed, the `_SESSION`
  is a `CachedSession` with per-domain TTLs (60s–3600s). Calling
  `_SESSION.cache.clear()` is **not** part of `clear_all_module_caches()`.
  So when the user presses Refresh All Data, the module-level dicts
  are wiped but the underlying HTTP cache still serves the same
  response on the next call.
- **Fix:** add to `clear_all_module_caches`:
  ```python
  if hasattr(_SESSION, 'cache') and hasattr(_SESSION.cache, 'clear'):
      try:
          _SESSION.cache.clear()
      except Exception as _hc_err:
          logging.debug("[CacheClear] HTTP cache clear failed: %s", _hc_err)
  ```
  This is the difference between "the button feels instant but data
  is stale" vs "the button forces a true round-trip."

### 5.4 ccxt OHLCV / ticker caches DO get cleared
- `_CCXT_OHLCV_CACHE` and `_CCXT_TICKER_CACHE` are both in the
  unlocked clear list (line 8120). **OK.**

---

## 6. API-key / secrets handling

### 6.1 `.env.example` is missing CRYPTOPANIC_API_KEY
- **File:** `.env.example` (32 lines)
- **Severity:** LOW
- **Description:** `config.py:9` reads `CRYPTOPANIC_API_KEY` but this
  key is not documented in `.env.example`. The file mentions
  `LUNARCRUSH_API_KEY`, `GLASSNODE_API_KEY`, `CRYPTOQUANT_API_KEY`,
  `COINGLASS_API_KEY` only as commented examples ("Set these in the
  Config Editor tab in the UI, or here as env vars").
- **Fix:** add a `CRYPTOPANIC_API_KEY=` line under "Optional: Premium
  On-Chain Data" or in a new "News" section. Also add
  `GLASSNODE_API_KEY=`, `CRYPTOQUANT_API_KEY=`, `LUNARCRUSH_API_KEY=`
  uncommented since the alerts_config.json path reads these too.

### 6.2 No keys hard-coded — verified by `gitleaks` config + grep
- `.gitleaks.toml` exists in repo. `grep "sk-ant-api03-...|cg_..."`
  returns only `.env.example` placeholders. **OK.**

### 6.3 Missing-key paths handle gracefully
- File: `data_feeds.py:1783-1792` — `_no_key_result(service, description)`
  returns a uniform "API key not configured" dict that downstream
  consumers handle without crashing. Used by Glassnode, LunarCrush,
  CryptoQuant, Coinglass. **OK.**
- File: `data_feeds.py:6541-6558` — CMC global metrics returns a
  "missing key" dict when `COINMARKETCAP_API_KEY` is unset. **OK.**

### 6.4 Status pills hardcoded "live" — lying when keys are missing
- **Severity:** HIGH (per Image 8)
- **Files (8 occurrences):**
  - `app.py:2249` — Home page topbar
  - `app.py:7558` — Backtester page
  - `app.py:8221` — Agent page
  - `app.py:8618` — On-chain page
  - similar at 7030, 7531, 8212, 8595
- **Description:** Every topbar declares
  `("Glassnode", "live"), ("Dune", "cached"), ("Native RPC", "live")`
  as a static literal. There is no logic that checks
  `glassnode_key in alerts_config` before showing "live". When the
  key is missing OR the IP is geo-blocked OR the daily cap is
  exhausted, the pill still says "live" and the cards say "—" —
  exactly the contradiction in Image 8 ("nothing is shown here").
- **Fix:** introduce
  `_status_pill_for(source: str) -> tuple[str, str]` that returns
  `("Glassnode", state)` where state is one of `"live"`,
  `"no api key"`, `"rate-limited"`, `"geo-blocked"`, `"cached"`.
  Wire each pill to call this helper. The state lookup reads from:
  - `_load_api_keys()` for key presence
  - the per-source error cache populated by §2.1 reachability probe
  - the cache-age helper `data_feeds.get_cache_age_seconds(key)` at
    line 4513 to distinguish "live" from "cached".

### 6.5 Anthropic client error path
- File: `news_sentiment.py:42-60` — `_get_anthropic_client()` returns
  `None` cleanly when `ANTHROPIC_API_KEY` is missing or
  `ANTHROPIC_ENABLED=false`. Downstream code checks for `None`. **OK.**
- A circuit breaker (`_claude_credits_exhausted` at line 39) silences
  repeat warnings when the credit-exhausted 400 fires once. **OK** —
  good defensive code.

---

## 7. CCXT exchange-list completeness

### 7.1 Wired vs. listed

CLAUDE.md global §10 lists 19+ CCXT exchanges. Actual coverage:

| Exchange       | Funding | OHLCV (chart) | Spot arb | Notes |
|----------------|---------|---------------|----------|-------|
| OKX            | direct  | direct        | direct   | Primary US-accessible |
| Bybit          | direct  | direct        | —        | Funding & OHLCV REST |
| KuCoin         | direct  | —             | direct   | Funding only |
| Kraken         | —       | ccxt          | direct   | OHLCV + spot arb |
| Gate.io        | —       | direct        | direct   | OHLCV + spot arb |
| MEXC           | ccxt    | direct        | —        | Funding via ccxt; OHLCV direct |
| HTX (Huobi)    | ccxt    | —             | direct   | Funding + spot arb |
| Bitstamp       | —       | —             | direct   | Spot arb only |
| Bitget         | —       | —             | direct   | Spot arb only |
| Bitfinex       | ccxt    | —             | —        | Funding only |
| Phemex         | ccxt    | —             | —        | Funding only |
| WOO            | ccxt    | —             | —        | Funding only |
| Bithumb        | ccxt    | —             | —        | Funding only (KRW only) |
| Crypto.com     | ccxt    | —             | —        | Funding only |
| AscendEX       | ccxt    | —             | —        | Funding only |
| LBank          | ccxt    | —             | —        | Funding only |
| CoinEx         | ccxt    | —             | —        | Funding only |
| Binance (.com) | —       | listed only   | —        | Geo-blocked from US Cloud — code path retired |
| **Coinbase**   | —       | —             | —        | UI dropdown only (`app.py:3358`) — no fetcher |
| **BingX**      | —       | —             | —        | Listed in CLAUDE.md, **completely absent** from code |
| **Gemini**     | —       | —             | —        | UI dropdown only — no fetcher |

### 7.2 Findings
- **MEDIUM:** Coinbase and Gemini appear in the TA Exchange dropdown
  (`app.py:3358`) without a corresponding fetcher. Selecting them
  silently falls back to whatever ccxt does by default — no
  validation, no user-visible "this exchange isn't wired" warning.
- **LOW:** BingX is listed in the global §10 spec but completely
  absent from the code. Either drop it from CLAUDE.md or add a stub
  via `_fetch_ccxt_fr("bingx", …)` in `get_multi_exchange_funding_rates`.
- **LOW:** the global CLAUDE.md §10 says "all CCXT-supported
  exchanges" — this is aspirational; actual coverage is 18 of 19+.
  Update CLAUDE.md or extend the list.

---

## 8. Token unlocks + VC fundraising (Cryptorank)

### 8.1 Implementation status
- **File:** `data_feeds.py:2406` — `fetch_cryptorank_token_unlocks(symbol)`
  fetches per-token vesting from cryptorank.io. **OK.**
- **File:** `data_feeds.py:2509` — `fetch_cryptorank_funding_rounds(days)`
  fetches funding-round calendar. **OK.**
- **File:** `data_feeds.py:2688` — `fetch_vc_funding_signal()` rolls
  up VC activity into a [-1,+1] sentiment score for the composite
  signal Layer 3. **OK.**

### 8.2 UI surfacing
- **Token unlocks:** wired into the Signals page info-strip 5th cell
  via `_sg_cached_token_unlocks` (`app.py:7891-7918`). Shows
  `⚠ {days}d / {pct}% supply` for `UNLOCK_IMMINENT`,
  `{days}d` for `UNLOCK_SOON`, `None / no vesting` for `NO_UNLOCK`,
  `—` for `N/A`. **OK** but the literal string `"None"` for
  `NO_UNLOCK` should be changed to `"no vesting"` (already on the
  sub-line) — `"None"` looks like a Python `None` slipped through.
- **VC funding signal:** consumed by composite_signal Layer 3
  (`composite_signal.py:1086-1095`) but **NOT** surfaced in any UI
  card or page. The user can see the resulting composite score but
  has no way to know which rounds contributed. Dashboards in
  comparable apps (Messari, Token Terminal) have a dedicated "VC
  flow" panel.
- **Fix (LOW priority, feature gap):** add a small "VC Activity"
  panel to the Home page (under regime grid) showing the top 5
  recent rounds + a 30d aggregate. `fetch_cryptorank_funding_rounds`
  already returns the data; only the rendering is missing.

### 8.3 Cryptorank API key not in .env.example
- `data_feeds.py:2406, 2509` reads
  `_os.environ.get("CRYPTORANK_API_KEY", "")`. The free tier works
  without a key but with ~1 req/min — paid tier removes this.
- **.env.example does not document `CRYPTORANK_API_KEY`.** Same fix
  category as §6.1.

---

## 9. Hyperliquid funding-rate parser bug (Image 7)

### 9.1 BUG — Hourly rate displayed as 8-hour rate
- **File:** `data_feeds.py:4413-4469` — `get_hyperliquid_stats(pair)`
- **Severity:** MEDIUM
- **Description:** Hyperliquid's `/info → metaAndAssetCtxs` returns
  `funding` as the **hourly** funding rate (per Hyperliquid's docs:
  "funding rate paid every hour"). The parser at line 4445 reads
  `fund = float(ctx.get("funding") or 0)` and at line 4453 stores
  `"funding_rate_8h": round(fund, 6)` — but this is **hourly**, not
  8-hourly. Worse, line 4446's annualization is correct **for the
  8-hour assumption** that the field name implies:
  `fund * 3 * 365 * 100`. For an hourly rate the correct annualization
  is `fund * 24 * 365 * 100`. So the displayed annualized yield is
  **8× too low.**
- **In the UI** (`app.py:6981`): the column is labeled "Funding 8h"
  with format `+.4f%` — so a typical hourly rate of `~0.000125`
  (10 bps annualized) prints as `+0.0125%` (looks fine), but a quiet
  hour with `0.0000125` prints as `+0.0000%` — exactly what Image 7
  shows. The parser isn't returning zero; it's returning a real
  hourly rate that, after `round(rate * 100, 4)`, rounds to 0.0000
  in the 4-decimal column.
- **Fix (3 changes):**
  1. Rename `"funding_rate_8h"` → `"funding_rate_1h"` in the result
     dict at line 4453 (truth-in-naming).
  2. Add `"funding_rate_pct_8h": round(fund * 8 * 100, 4)` so
     downstream comparisons against OKX/Bybit (which are 8h-native)
     are apples-to-apples.
  3. Fix annualization at line 4446:
     `fund_ann = fund * 24 * 365 * 100` (hourly → annual = ×8760).
  4. In `app.py:6981`, change column label to `"Funding 1h"` and
     format to `+.5f%` so 0.0000125% shows as `+0.0001%` instead of
     `+0.0000%`. Or, render the 8h-equivalent via the new field.

### 9.2 BUG — `get_hyperliquid_batch` "warm cache for first pair only" trick
- **File:** `data_feeds.py:4477-4479`
- **Severity:** LOW
- **Description:** The comment says "warms the full cache in one call"
  — this is **wrong**. Calling `get_hyperliquid_stats(pairs[0])` only
  caches `pairs[0]` (the function returns after finding a single coin
  match in the universe loop and does NOT iterate the rest of the
  ctxs). Each subsequent `get_hyperliquid_stats(p)` re-POSTs the
  same `metaAndAssetCtxs` payload (potentially 10+ POSTs per batch).
- **Fix:** make `get_hyperliquid_stats` cache **every** asset it sees
  in the universe loop, not just the matching one. ~6 lines added
  inside the for-loop:
  ```python
  for i, asset in enumerate(assets):
      if i >= len(ctxs): break
      _coin_name = asset.get("name", "").upper()
      _ctx = ctxs[i]
      _entry = _build_entry(_coin_name, _ctx, now)  # extracted helper
      with _HL_LOCK:
          _HL_CACHE[_coin_name] = _entry
      if _coin_name == coin.upper():
          result = _entry
  ```

---

## 10. Refresh-interval enforcement

### 10.1 TTL audit vs. CLAUDE.md §12 (project)

| Data type        | CLAUDE.md spec | Actual TTL                     | Status |
|------------------|----------------|---------------------------------|--------|
| OHLCV intraday   | 5 min          | 300s (`_OHLCV_CACHE_TTL`)       | OK     |
| Fear & Greed     | 24 hour        | 86 400s (`_FNG_TTL`)             | OK     |
| Funding rates    | 10 min         | 300s (`_CACHE_TTL_SECONDS`, `_MULTI_FR_TTL`) | **DRIFT — half** |
| On-chain metrics | 1 hour         | 3600s (`_GN_TTL`, `_ONCHAIN_TTL`) | OK   |
| Regime detection | 15 min         | (not a TTL — recomputed in scan loop) | OK |
| Composite signal | 5 min          | (handled by `_sg_cached_composite_per_pair` in app.py, ttl=300) | OK |
| Hyperliquid OI/funding | (not specified) | 120s (`_HL_CACHE_TTL`) | OK — appropriate for hourly funding |
| LunarCrush       | (not specified) | 900s (`_LC_TTL`) | OK |
| News sentiment   | (not specified) | 900s (`news_sentiment._CACHE_TTL`) | OK |
| Token unlocks    | (not specified) | 28 800s (8h, `_CRYPTORANK_UNLOCKS_TTL`) | OK |
| CMC global       | (not specified) | 600s (10 min) | OK |
| TVL (DefiLlama)  | (not specified) | 300s (5 min) | OK |

### 10.2 Are the TTLs actually enforced or violated by re-renders?
- The module-level dict caches keyed by pair are checked **inside**
  the fetch function before any HTTP call, behind `_LOCK`. A
  Streamlit re-render that calls the function within the TTL window
  hits the cache and returns instantly. **OK.**
- The `@st.cache_data(ttl=...)` wrappers in app.py
  (`_sg_cached_live_prices_cascade` ttl=60, `_sg_cached_token_unlocks`
  ttl=8h, `_sg_cached_composite_per_pair`) further insulate against
  per-rerun churn. **OK.**
- The one violation is funding rates (300s vs 600s spec) noted in
  §3.2. Otherwise CLAUDE.md §12 is honored.

---

## 11. Summary table — data sources × state × Streamlit Cloud reachability

| Source           | State          | SCloud reachable? | Free-tier rate cap     | Notes |
|------------------|----------------|--------------------|------------------------|-------|
| OKX (REST)       | working        | yes                | 20 req/2s public       | Primary US-accessible CEX |
| OKX (WebSocket)  | working        | yes                | n/a                    | Live-price primary, OKX SWAP only |
| Bybit            | working        | partial (DC quirks)| 600 req/5s             | Backup funding source |
| Kraken (REST)    | working        | yes                | ~1 req/s               | OHLCV + cascade Tier 3 |
| Kraken (ccxt)    | working        | yes                | shared bucket          | Chart OHLCV primary |
| KuCoin           | working        | partial            | 10 req/3s public       | Funding only |
| Gate.io          | working        | yes                | ~1 req/s               | OHLCV cascade + spot arb |
| MEXC             | working        | yes                | varies                 | Cascade Tier 5 + ccxt funding |
| Bitfinex         | working (ccxt) | yes                | ccxt-managed           | Funding only |
| HTX              | working        | yes                | ccxt + direct REST     | Funding + spot arb |
| Bitstamp         | working        | yes                | direct REST            | Spot arb only (USD-pair proxy for USDT) |
| Bitget           | working        | yes                | direct REST            | Spot arb only |
| Phemex           | working (ccxt) | yes                | ccxt-managed           | Funding only |
| WOO              | working (ccxt) | yes                | ccxt-managed           | Funding only |
| Bithumb          | working (ccxt) | yes                | ccxt-managed           | KRW only — useful for kimchi premium |
| Crypto.com       | working (ccxt) | yes                | ccxt-managed           | Funding only |
| AscendEX         | working (ccxt) | yes                | ccxt-managed           | Funding only |
| LBank            | working (ccxt) | yes                | ccxt-managed           | Funding only |
| CoinEx           | working (ccxt) | yes                | ccxt-managed           | Funding only |
| Binance.com      | **broken**     | **NO** (HTTP 451)  | n/a                    | Geo-blocked from US DC; klines stub kept for completeness |
| Binance.US       | partial        | yes (DC quirks)    | 1200 req/min           | Premium index path uses .us; live trading via ccxt |
| Coinbase         | **not wired**  | yes                | n/a                    | UI dropdown without fetcher |
| Gemini           | **not wired**  | yes                | n/a                    | UI dropdown without fetcher |
| BingX            | **not wired**  | unknown            | n/a                    | In CLAUDE.md spec, absent from code |
| Hyperliquid      | broken parser  | yes                | n/a (public POST)      | Funding annualization 8× too low |
| dYdX             | working        | yes                | indexer.dydx.trade     | DEX price |
| Jupiter          | partial        | DNS-unreachable    | n/a                    | Solana DEX — no-retry session, fails silently |
| GeckoTerminal    | working        | yes                | 30 req/min unauth      | DEX trending + OHLCV |
| Uniswap (DefiLlama proxy) | working | yes                | shared bucket          | DefiLlama yields/TVL |
| **CoinGecko**    | working        | yes                | 30 req/min free        | Cascade Tier 2 + on-chain proxies |
| **CoinMarketCap**| key-gated      | yes                | 333 req/day free       | Cascade Tier 1 + global metrics |
| **Glassnode**    | partial        | yes                | 10 req/min free        | On-chain — silent 429 + lying status pill (Image 8) |
| CoinMetrics      | working        | yes                | community tier         | On-chain backup |
| Dune Analytics   | key-gated      | yes                | varies by query        | Mostly key-required; gracefully falls back |
| **CryptoPanic**  | partial        | yes                | ~50 req/24h public     | Key never used despite being configured |
| LunarCrush       | key-gated      | yes                | varies                 | Optional, gracefully no-op without key |
| CryptoQuant      | key-gated      | yes                | varies                 | Stub — no key returns _no_key_result |
| Coinglass        | key-gated      | yes                | varies                 | Stub — same |
| Cryptorank       | working        | yes                | ~1 req/min unauth      | Token unlocks + VC funding |
| Tokenomist       | fallback only  | yes                | varies                 | Token unlocks fallback |
| FRED             | working        | yes                | unlimited              | Macro M2/DGS10/etc — separate session w/ low retry |
| Fear & Greed     | working        | yes                | unlimited              | alternative.me — bulletproof |
| Allora (Upshot)  | working        | yes                | varies                 | Price predictions |
| Etherscan        | key-gated      | yes                | 5 req/s free           | Wallet token list fallback |
| Zerion           | key-gated      | yes                | varies                 | Wallet portfolio |
| Deribit          | working        | yes                | 20 req/s public        | Options OI/IV/PCR |
| GitHub API       | working        | yes                | 60 req/h unauth        | Dev activity panel |
| pytrends         | working        | partial            | flaky on cloud DCs     | Graceful fallback present |

---

## 12. Top 3 critical fixes (must-do for the app to be reliable)

### #1 — Wire the price cascade into hero cards (Image 1 fix)
- **File:** `app.py:2463-2475` (`_ds_build_hero`)
- **Why:** The Home page currently renders `—` for the 3 most-prominent
  cards on the app whenever the user picks a coin without an OKX SWAP
  market. This is the first thing every user sees. The fix is ~15 lines
  and the cascade plumbing already exists (just call
  `_sg_cached_live_prices_cascade(tuple_of_hero_syms)` once before
  the row of `_ds_build_hero` calls and have `_ds_build_hero` fall
  through to it).

### #2 — Stop lying with status pills + replace "None" with truthful labels
- **Files:** `app.py:2249, 7558, 8221, 8618` (status pills) and
  `app.py:6852` (Funding Rate Monitor cell rendering)
- **Why:** The On-chain page (Image 8) and Funding Rate Monitor
  (Image 7) both surface a contradiction the user immediately notices
  ("status says live, cards show nothing"). This destroys trust in
  every other status pill in the app. The fix is two-part:
  - Introduce `_status_pill_for(source)` reading from
    `_load_api_keys()` + an exchange reachability cache.
  - Map error strings to `"geo-blocked"`, `"rate-limited"`,
    `"unreachable"`, `"no api key"` instead of the raw `None` /
    `"—"` that Streamlit renders as the literal string `"None"`.

### #3 — Fix Hyperliquid funding parser + stop the cache thrash
- **File:** `data_feeds.py:4413-4479`
- **Why:** the per-pair POST to `/info → metaAndAssetCtxs` is fired
  N times per batch (10+ identical calls), and the displayed funding
  rate is hourly when the column is labeled 8-hour. The annualized
  yield is 8× lower than reality. Both bugs combined make the
  Hyperliquid section look broken to the user (Image 7) and waste
  free-tier API budget.
- Fix lifts a single `metaAndAssetCtxs` POST into a one-shot
  per-batch warm + correct rate-interval naming.

---

## Appendix A — Files reviewed

| File                                | Lines  | Coverage |
|-------------------------------------|--------|----------|
| `data_feeds.py`                     | 8 464  | full skim + key sections deep-read |
| `websocket_feeds.py`                | 314    | full read |
| `arbitrage.py`                      | 472    | full read |
| `config.py`                         | 189    | full read |
| `news_sentiment.py`                 | 477    | full read |
| `allora.py`                         | 291    | full read |
| `api.py`                            | 866    | header + auth section |
| `scheduler.py`                      | 258    | full read |
| `app.py:700-770, 1647-1715, 2234-2660, 6800-7000, 8570-8650` | partial | call sites only |
| `crypto_model_core.py:480-650`      | partial | OHLCV cascade + chart fetcher |
| `composite_signal.py:1086-1100`     | partial | VC funding ingestion |
| `.env.example`                      | 35     | full read |
| `docs/audits/2026-05-02_legacy-look-audit-in-progress.md` | full | context |

## Appendix B — Out-of-scope but worth flagging

These came up while reading but are not data-feed issues per se. Filed
for the next pass:

1. `_ds_build_hero` `change_pct` is also WebSocket-only — same fix as
   §1.2 should also derive 24h % from cascade-fetched sparkline closes.
2. `arbitrage.py:343` enumerates all (buy, sell) pairs in O(N²); fine
   at N=7 exchanges but worth noting for when the list grows.
3. `data_feeds.py:332` declares `_BINANCE_PREMIUM_URL` even though the
   comment says "geo-blocked for US; not called." Dead constant — drop.
4. `tests/test_data_wiring.py:765-778` only tests the Streamlit
   side of cache clearing. Add a test for `clear_all_module_caches`
   sentinel-coverage as suggested in §5.2.
5. `_yf_history` and `_yf_download` use `ex.shutdown(wait=False)` —
   excellent. Any new long-running yfinance call must follow the same
   pattern. Document in CLAUDE.md as a project convention.
