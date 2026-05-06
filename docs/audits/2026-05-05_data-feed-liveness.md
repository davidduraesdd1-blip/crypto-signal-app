# Tier 4 — Data Feed Liveness on Render Oregon
**Date:** 2026-05-05
**Auditor:** Claude (read-only audit pass)
**Worktree:** `.claude/worktrees/exciting-lovelace-60ae5b`
**Branch:** `claude/exciting-lovelace-60ae5b`

## Methodology

1. **Code inventory.** Greps + targeted reads of `data_feeds.py` (8,603 lines), `crypto_model_core.py` (5,949 lines), `news_sentiment.py`, `cycle_indicators.py`, `arbitrage.py`, `whale_tracker.py`, `config.py`, `alerts.py`, `routers/*`. Cross-referenced the SSRF allowlist (`data_feeds.py:253-316`) against actual call sites.
2. **Reachability probes (`curl`).** `curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 10` against one canonical endpoint per source.
3. **CRITICAL CAVEAT:** The probes were issued from the **auditor's developer workstation**, not from Render Oregon. A 200 here does **not** prove Render-side reachability. The Render datacenter has well-known geo-blocks (OKX, Binance.com fapi). To trust these results in production, a backend-side `/diagnostics/feeds` endpoint is needed (see Recommended Additions §3 below — this gap is the single biggest finding of the audit).
4. **Cache TTL audit.** All `_TTL` / `_CACHE_TTL` / `expire_after` constants in `data_feeds.py` were extracted and compared against CLAUDE.md §12 windows.
5. **Recent commit triage.** `git log --oneline -50 --grep="feed|geo|rate.*limit|fallback"` — 6 hits, summarised in §6.

## Summary

| Metric | Count |
|---|---|
| Sources inventoried | **27** |
| Reachable from auditor IP | **20 / 27** (74%) |
| Geo-blocked / auth-required failures from auditor IP | 7 (Bybit 403, Binance.com 451, Glassnode 401, CryptoRank 401, CMC 401, LunarCrush 401, CryptoPanic 404 demo-token) |
| Confirmed geo-blocked from Render Oregon (per CLAUDE.md §10 + commits) | 2: **OKX**, **Binance.com fapi** |
| Cache TTL drift from §12 | **2 minor** (funding rate 5min vs §12 10min target — DEFENSIBLE; OI cache 2min — undocumented in §12 but reasonable) |
| Missing `/diagnostics/feeds` Render-side health probe | **YES — single biggest gap** |
| Sources where API key is required but rotation procedure undocumented | **8** (see §4) |
| Sources with no Render-side liveness check today | **all of them** (only WS spot-prices are surfaced via `/health`) |

## 1. Per-source matrix

Reachability column: `200`/`401`/`403`/`451` is the HTTP status code returned to the auditor's workstation.
"Render?" column: based on CLAUDE.md §10, recent commit messages, and the `_NO_RETRY_SESSION` / fallback-chain placement in code (a source demoted past geo-block-prone exchanges is implicitly trusted Render-side).

| # | Source | Hostname | Used in (file:line) | Cache TTL (code) | §12 target | API key | Auditor reach | Render reach | Notes |
|---|---|---|---|---|---|---|---|---|---|
| **OHLCV chain** ||||||||||
| 1 | Kraken (CCXT) | `api.kraken.com` | `crypto_model_core.py:573-581`, `data_feeds.py:6830` | OHLCV: 5min `_TF_TTL` | 5min | none | 200 / 217ms | OK | Primary. CCXT handles markets. |
| 2 | Gate.io REST | `api.gateio.ws` | `crypto_model_core.py:583-590`, `data_feeds.py:621` | OHLCV: 5min | 5min | none | 200 / 1108ms | OK | #2 fallback (post-`0940681`). |
| 3 | Bybit REST (direct) | `api.bybit.com` | `crypto_model_core.py:592-599`, `data_feeds.py:333,650,470` | Funding: 5min `_CACHE_TTL_SECONDS` | 10min (drift, see §3) | none | **403** / 257ms | OK | Auditor 403 likely Cloudflare bot fingerprint, NOT geo. Render path proven by `41e6a8c`. |
| 4 | MEXC REST | `api.mexc.com` | `crypto_model_core.py:601-608`, `data_feeds.py:684,6149` | OHLCV: 5min | 5min | none | 200 / 532ms | OK | #4 fallback. |
| 5 | OKX REST | `www.okx.com` | `crypto_model_core.py:610-617`, `data_feeds.py:334,582,997,1382,3284,4228,4345,…` | OHLCV: 5min, Funding: 5min | 5min/10min | none | 200 / 300ms | **GEO-BLOCKED** | Per CLAUDE.md §10 + `0940681` commit + comments at `data_feeds.py:445-451`, `crypto_model_core.py:495-501`: confirmed `ConnectionResetError(104)` from Render Oregon. Demoted to #5 in OHLCV chain, #2 in funding chain. |
| 6 | CoinGecko OHLCV | `api.coingecko.com` | `crypto_model_core.py:643`, `data_feeds.py:539,726,3051,3134,3842,5760,6803` | Price: 5min `_CG_PRICE_TTL`, Trending: 15min, Global: 5min | 5min | optional `SUPERGROK_COINGECKO_API_KEY` (free demo) / `COINGECKO_PRO_KEY` (paid) | 200 / 174ms | OK | Last-resort fallback (free tier ≤30 days, daily-only). Limiter set to 0.4 req/s (24/min). |
| **Sentiment / market data** ||||||||||
| 7 | Fear & Greed | `api.alternative.me` | `data_feeds.py:691,3573,3945`, `crypto_model_core.py:691`, `ui_components.py:3641` | F&G: **86,400s (24h)** `_FNG_TTL` + duplicate `_FNG2_TTL`; requests-cache: 300s | **24h** | none | 200 / 367ms | OK | Matches §12 exactly. NB: `ui_components.py:3637` ALSO fetches with `@st.cache_data(ttl=3600)` 60min — third TTL on the same endpoint. |
| 8 | Funding (OKX) | `www.okx.com/api/v5/public/funding-rate` | `data_feeds.py:334,1457,4228` | 5min `_CACHE_TTL_SECONDS` (single-pair) / 5min `_MULTI_FR_TTL` | **10min** | none | 200 / 300ms | **GEO-BLOCKED** | Demoted to #2 in `41e6a8c`. |
| 9 | Funding (Bybit) | `api.bybit.com/v5/market/tickers` | `data_feeds.py:333,470,1486` | 5min | 10min | none | 403 (auditor) | OK | Now PRIMARY funding source per `41e6a8c`. |
| 10 | Google Trends (pytrends) | client lib via Google internal | `cycle_indicators.py:80-180`, `data_feeds.py:3000-3018`, `app.py:572-584` | 24h (in `_cached_google_trends_score`) + module-level cache | n/a (sentiment) | none | n/a | LIKELY DEGRADED | pytrends is rate-limited from datacenter IPs at the best of times. Graceful fallback exists (`returns None`). No production telemetry confirms it works on Render. |
| 11 | LunarCrush | `lunarcrush.com/api4/public/coins/.../v1` | `news_sentiment.py:80,158`, `data_feeds.py:1894` | 10min `_LC_TTL` | n/a | optional `LUNARCRUSH_API_KEY` | 401 (no key) | OK | Returns 401 unauth without key; free tier: 10 req/min. |
| 12 | CryptoPanic (news) | `cryptopanic.com/api/v1/posts/` | `news_sentiment.py:77,118`, `app.py:3766` | 15min `_NEWS_CACHE_TTL` | n/a | optional `CRYPTOPANIC_API_KEY` | 404 demo-token | OK | Free public mode (~50 req/24h) without key; 50,000 req/month with key. |
| 13 | Coinalyze | `api.coinalyze.net` | `data_feeds.py:5149` | 1h | n/a | env `SUPERGROK_COINALYZE_API_KEY` / `COINALYZE_API_KEY` | not probed | OK | Optional. |
| **On-chain (BTC, ETH)** ||||||||||
| 14 | Glassnode | `api.glassnode.com/v1/metrics` | `data_feeds.py:2138-2210`, `app.py:2257,7668,8819,8896,8996` | **1h** `_GN_TTL` + 30min `_rl_until` rate-limit cache | **1h** | required `glassnode_key` (from alerts_config.json or env) | 401 | OK | Free tier rate-limited; on-chain helper uses `_NO_RETRY_SESSION` so 429s don't burn budget. ETH+BTC only. |
| 15 | Dune Analytics | `api.dune.com` | `data_feeds.py:2873-2920,315` | 1h `_DUNE_RESULTS_TTL` | 1h | env DUNE key | 404 (auditor — wrong endpoint, normal) | OK | Most queries require key. Returns None gracefully. |
| 16 | CoinMetrics community | `community-api.coinmetrics.io` | `data_feeds.py:307,4136-4150,5501,5806` | 1h `_CM_TTL` / `_CM_OC_TTL` | 1h | none | 200 (with v4 path) | OK | "Slow but reliable" per CLAUDE.md §10. |
| 17 | blockchain.info | `blockchain.info`, `api.blockchain.info` | `data_feeds.py:284,290`, `whale_tracker.py` | n/a | n/a | none | 200 / 295ms | OK | BTC active addresses + MVRV fallback. |
| 18 | Etherscan | `api.etherscan.io` | `data_feeds.py:282,289`, fallback chain | n/a | n/a | optional `ETHERSCAN_API_KEY` | 200 / 498ms | OK | Token list fallback for wallet read. |
| **Token unlocks / VC fundraising** ||||||||||
| 19 | Cryptorank (unlocks) | `api.cryptorank.io/v1/currencies/unlock-events` | `data_feeds.py:2488-2598` | **8h** `_CRYPTORANK_UNLOCKS_TTL` | n/a (RWA-style) | optional `CRYPTORANK_API_KEY` | 401 | OK | Returns None gracefully when key missing → fallback chain. |
| 20 | Cryptorank (funding rounds) | `api.cryptorank.io/v1/funding-rounds` | `data_feeds.py:2600-2700` | **4h** `_CRYPTORANK_FUNDING_TTL` | n/a | optional `CRYPTORANK_API_KEY` | 401 | OK | Falls through to `/v0/funds` aggregate when 401/404. |
| **Macro** ||||||||||
| 21 | FRED CSV | `fred.stlouisfed.org/graph/fredgraph.csv` | `data_feeds.py:308,4712-4781,4940`, `composite_signal.py:25,461,479,522,542` | **2h** `_MACRO_TTL`, **12h** `_M2_CHART_TTL` | **2h** | none | 200 / 365ms | OK | Matches §12 exactly. Uses dedicated `_FRED_SESSION` with retry=1, read=0 to fail fast. |
| 22 | yfinance (DXY/VIX/UST/M2) | Yahoo Finance (no public API host — lib internal) | `data_feeds.py:142-205,5091,4632`, `app.py:620-633,8576-8590` | **2h** `_MACRO_TTL` | **2h** | none | n/a | OK (with 8s timeout wrapper) | Critical: `_yf_history` / `_yf_download` enforce hard timeout to dodge 60s health-check 503 (`data_feeds.py:142-205`). |
| 23 | DefiLlama | `api.llama.fi`, `yields.llama.fi` | `data_feeds.py:301-303,4074-4085,2249-2280` | 5min `_LLAMA_TTL` / 5min `_TVL_TTL` | n/a | none | 200 / 462ms | OK | Direct `requests.get(...)` no retry, 5s timeout — slow from US AWS per inline comment. |
| 24 | exchangerate-api | `api.exchangerate-api.com` | `data_feeds.py:264,6447` | 1h `_FX_TTL` | n/a | none | 200 / 356ms | OK | FX rates for regional premium calc. |
| **Other** ||||||||||
| 25 | Deribit | `www.deribit.com/api/v2/public/...` | `data_feeds.py:263,6336-6360`, `data_feeds.py:7898` | 5min `_DERIBIT_OI_TTL` / 1h `_IV_TTL` | 1h (on-chain) | none | 200 / 286ms | OK | Options OI + DVOL. |
| 26 | GeckoTerminal | `api.geckoterminal.com` | `data_feeds.py:305,6211-6259` | 1min `_DEX_PRICE_TTL` | n/a | none | 200 / 344ms | OK | DEX pools. |
| 27 | CoinPaprika | `api.coinpaprika.com` | `data_feeds.py:283,3196-3218` | n/a (`_NO_RETRY_SESSION`) | n/a | none | 200 / 122ms | OK | Global market fallback when CG fails. |

(WebSocket spot price streams in `websocket_feeds.py` are surfaced live via `api.py:/health` — separate liveness path, working.)

## 2. Geo-block / regional risks

| Source | Status | Evidence | Mitigation in code |
|---|---|---|---|
| **OKX** | **CONFIRMED geo-blocked from Render Oregon** | CLAUDE.md §10; commit `0940681` ("ohlcv: reorder fallback chain — demote OKX past Gate.io/Bybit/MEXC"); `41e6a8c` ("perf(data-feeds): Bybit-primary funding rate + open interest, OKX fallback"); inline comments at `data_feeds.py:445-451`, `crypto_model_core.py:495-501`, `crypto_model_core.py:553-560`. Logs: `ConnectionResetError(104)`. | Demoted to #5 in OHLCV chain, #2 in funding chain. Still attempted because comment says "kept for Streamlit Cloud parity." Each call wastes a TCP handshake. **Recommended: gate OKX behind an env var** (e.g. `RENDER=true → skip-OKX`) to save the round-trip on every fetch. |
| **Binance.com (fapi)** | Geo-blocked from US datacenter IPs | `data_feeds.py:332` comment: "geo-blocked for US; kept for reference only — not called". Auditor confirms: `https://api.binance.com/api/v3/ping` returns **451** from a US IP. | Already not called. `_fetch_binance_fr` is a stub that delegates to Bybit (`data_feeds.py:1474-1483`). |
| **Binance US** | Reachable from auditor 200 / 269ms | CLAUDE.md §10 warns "datacenter-IP blocks". Not directly used in primary chains anymore (was demoted). Listed in SSRF allowlist (`data_feeds.py:256`). | Conservative: assume sometimes-blocked. Test via /diagnostics/feeds when added. |
| **Bybit** | Auditor saw 403 (likely Cloudflare bot, not geo) | Code path proven by `41e6a8c` — works from Render. | None needed. |
| **pytrends (Google Trends)** | High risk from datacenter IPs (Google rate-limits aggressively) | No production telemetry. `cycle_indicators.py:84` retries=1 short timeout — fails graceful. | Already returns None on failure. **Recommended:** confirm via /diagnostics/feeds whether it ever succeeds from Render — if not, save the call entirely. |

## 3. Cache TTL audit vs CLAUDE.md §12

| §12 directive | Code value | Location | Status |
|---|---|---|---|
| OHLCV intraday: **5 min** | 300s `_OHLCV_CACHE_TTL` (default in `_TF_TTL`) | `crypto_model_core.py:480` | OK |
| Fear & Greed: **24 hour** | 86,400s `_FNG_TTL` + 86,400s `_FNG2_TTL` (duplicate) | `data_feeds.py:3534,3913` | OK — but **two FNG fetchers exist** (`fetch_fear_greed_30d` and a second `_FNG2_CACHE` path) with two TTL constants. Risk: code drift. **MEDIUM finding (DEDUP-1).** Also a third path in `ui_components.py:3637` uses a 1h Streamlit cache. |
| Funding rates: **10 min** | 300s `_CACHE_TTL_SECONDS` + 300s `_MULTI_FR_TTL` | `data_feeds.py:340,1454` | **DRIFT** — code is 2× more aggressive (5min vs 10min target). Defensible: funding flips matter for live signal. **MEDIUM finding (TTL-1):** either update §12 to "5 min" or relax the cache to 600s. |
| On-chain metrics: **1 hour** | 3600s `_GN_TTL` / `_CM_TTL` / `_DUNE_RESULTS_TTL` / `_ONCHAIN_TTL` / `_CM_OC_TTL` / `_CQ_TTL` (note: CryptoQuant uses 600s — DRIFT) | `data_feeds.py:519,2028,2108,4136,5501,2873` | OK except CryptoQuant (`_CQ_TTL=600s`) — 6× more aggressive than §12. **LOW finding (TTL-2).** |
| Regime detection: **15 min** recompute | not directly in `data_feeds.py` — handled in `regimes.py` / scheduler | n/a | not audited in this pass |
| Composite signal: **5 min** recompute | scheduler-driven | n/a | not audited in this pass |
| (Undocumented in §12) Open interest: **2 min** `_OI_TTL` | `data_feeds.py:921` | n/a | OK — fast-moving by nature, defensible |
| (Undocumented in §12) Order books: **30 sec** `_OB_TTL` | `data_feeds.py:1363` | n/a | OK |
| (Undocumented in §12) IV / DVOL: **1 hour** `_IV_TTL` | `data_feeds.py:1277` | n/a | OK |
| (Undocumented in §12) Cryptorank unlocks: **8 hour**, funding: **4 hour** | `data_feeds.py:2489-2490` | n/a | OK — RWA-style window per CLAUDE.md §10 |

## 4. API key inventory

| Source | Required? | Env var name | Other locations | Rotation procedure |
|---|---|---|---|---|
| Anthropic Claude | optional but core | `ANTHROPIC_API_KEY` | `st.secrets["ANTHROPIC_API_KEY"]` (Streamlit fallback) | **UNDOCUMENTED.** Render dashboard → re-deploy. No rotation runbook. |
| Anthropic master switch | n/a | `ANTHROPIC_ENABLED` | render.yaml default `"false"` | Toggle in dashboard. |
| CoinGecko free | optional | `SUPERGROK_COINGECKO_API_KEY` | `config.py:10` | UNDOCUMENTED. |
| CoinGecko Pro | optional | `COINGECKO_PRO_KEY` (canonical) / `SUPERGROK_COINGECKO_PRO_KEY` (legacy) | `config.py:17-20` | UNDOCUMENTED. |
| CryptoPanic | optional | `CRYPTOPANIC_API_KEY` | render.yaml `sync: false` | UNDOCUMENTED. |
| CoinMarketCap | optional | `COINMARKETCAP_API_KEY` | render.yaml `sync: false` | UNDOCUMENTED. |
| Etherscan | optional | `ETHERSCAN_API_KEY` | render.yaml `sync: false` | UNDOCUMENTED. |
| Zerion | optional | `ZERION_API_KEY` | render.yaml `sync: false` | UNDOCUMENTED. |
| Cryptorank | optional | `CRYPTORANK_API_KEY` (env, mapped to `cryptorank_key` runtime) | render.yaml `sync: false`, `data_feeds.py:7853` | UNDOCUMENTED. |
| Glassnode | required for on-chain | **`glassnode_key`** field in `alerts_config.json` only — **NO env var binding** | `alerts.py:91`, `data_feeds.py:2122` | **HIGH finding (KEY-1):** Glassnode key is read from `alerts_config.json` only — not via `_SENSITIVE_ENV_MAP` (`alerts.py:127-136`). On Render this means it lives on the persistent disk and is invisible to env-var rotation. Recommend wiring `GLASSNODE_API_KEY` env via `_SENSITIVE_ENV_MAP`. |
| LunarCrush | optional | `LUNARCRUSH_API_KEY` | `data_feeds.py:1894`, `news_sentiment.py:159` | UNDOCUMENTED. |
| Coinalyze | optional | `SUPERGROK_COINALYZE_API_KEY` / `COINALYZE_API_KEY` | `data_feeds.py:5149` | UNDOCUMENTED. Two env names accepted. |
| OKX (live trade) | optional | `OKX_API_KEY` / `OKX_API_SECRET` (canonical) / `OKX_SECRET` (legacy) / `OKX_PASSPHRASE` | render.yaml + `alerts.py:127-143` (`_SENSITIVE_ENV_MAP` + fallbacks) | Best-handled of the lot. Env var precedence over JSON file (P1 audit fix). Still no formal rotation runbook. |
| FRED | none | n/a | n/a | n/a |
| alternative.me | none | n/a | n/a | n/a |
| Sentry DSN | optional | `SUPERGROK_SENTRY_DSN` | `config.py:21` | UNDOCUMENTED. |

**Cross-cutting finding (KEY-2):** there's no central "API keys live in env vars" doc. The `_ENV_MAP` table in `data_feeds.py:7820-ish` is one place, `alerts._SENSITIVE_ENV_MAP` is another, `config.py` reads several directly, and the Glassnode key is a file-only outlier. **Recommend:** consolidate into a `docs/api-keys.md` checklist + `validate_api_keys()` (`data_feeds.py:7870`) becomes the runtime ground truth.

## 5. Render-side health check recommendation

**Current state:**
- `/health` (`api.py:515`) covers DB stats + WebSocket spot-price feed health. **It does not cover any of the 27 external sources audited above.**
- `/diagnostics/circuit-breakers` (`routers/diagnostics.py:206`) — agent gates only, no feeds.
- `/diagnostics/database` (`routers/diagnostics.py:240`) — DB stats, no feeds.
- `data_feeds.validate_api_keys()` (`data_feeds.py:7870`) is in code but **not exposed as a route** anywhere I could find.

**Gap:** there is no Render-side liveness probe for OHLCV / funding / on-chain / macro / sentiment sources. Operators cannot tell whether OKX, Glassnode, Cryptorank, FRED, or pytrends are succeeding from inside Render Oregon without inspecting logs — and many of these helpers are designed to fail silently.

**Recommendation — add `/diagnostics/feeds` endpoint:** wraps + extends `validate_api_keys()` to ping one canonical endpoint per source from inside Render, with a 5s per-source timeout and a 5min response cache. Single payload schema:

```json
{
  "checked_at": "2026-05-05T18:00:00Z",
  "sources": [
    {"name":"kraken","host":"api.kraken.com","status":"ok","latency_ms":217,"http":200,"ttl_remaining_s":4500},
    {"name":"okx","host":"www.okx.com","status":"geo_blocked","latency_ms":null,"http":null,"error":"ConnectionResetError(104)"},
    {"name":"glassnode","host":"api.glassnode.com","status":"no_key","key_required":true},
    ...
  ]
}
```

**Priority order to implement** (highest → lowest):
1. OKX (confirm geo-block; if confirmed, hard-disable from Render)
2. Bybit (newly-promoted primary funding source — must verify Render reachability daily)
3. Glassnode (paid, rate-limited; surface 429 budget state)
4. pytrends (likely degraded — confirm or remove)
5. Kraken / Gate.io / MEXC (primary OHLCV chain)
6. FRED / CoinGecko / alternative.me (high-frequency)
7. CryptoRank / CryptoPanic / LunarCrush / Coinalyze (key-gated; tile up "no key" status)
8. Dune / CoinMetrics / DefiLlama / blockchain.info (fallback layer)

**Lift estimate:** ~150 LOC new router + 30 LOC of test fixtures. Reuses `validate_api_keys()` plumbing.

## 6. Recent commits suggesting active issues

```
2c0b378 fix(audit-wave): H1-H6 — error boundaries, a11y wave 2, env hard-fail, scheduler single-flight, OI cleanup
02ffaf6 fix(B1+B2): watchlist alerts dead-key + OKX_SECRET env-var name schism
41e6a8c perf(data-feeds): Bybit-primary funding rate + open interest, OKX fallback
0940681 perf(ohlcv): reorder fallback chain — demote OKX past Gate.io/Bybit/MEXC
4cf4e15 phase 6: data-feed resilience polish — cache, CryptoPanic auth, funding TTL, .env
3bee35c fix(c-stab-19): live-price REST cascade — CMC → CG → Kraken → OKX → MEXC
```

**Reading between the lines:**
- `0940681` + `41e6a8c` (today / yesterday): **active OKX geo-block firefighting.** Two reorderings of two different chains in 2 days. Suggests the team is still discovering Render-side reachability deltas. **Strong signal that `/diagnostics/feeds` would have prevented both.**
- `02ffaf6`: env var name schism (`OKX_SECRET` vs `OKX_API_SECRET`) — exactly the kind of drift an env-var inventory doc (KEY-2 above) prevents.
- `4cf4e15`: explicit "data-feed resilience polish" — funding TTL touched, but no holistic Render-aware audit happened.

## 7. Recommended P0 fixes

1. **[P0] Add `/diagnostics/feeds` endpoint** — single biggest gap. Without it, every Render-vs-local discrepancy turns into log archaeology. (Lift: ~half a day.)
2. **[P0] Wire `GLASSNODE_API_KEY` env var into `_SENSITIVE_ENV_MAP`** (`alerts.py:127`) so the on-chain primary key isn't tied to a disk file. Render disks survive deploys but not service deletes. (Lift: ~10 LOC + 1 test.)
3. **[P1] Gate OKX behind an env flag** (`SKIP_OKX_FALLBACK=true` on Render). Today every OKX call from Render eats a TCP handshake before failing — there are at least 12 distinct `okx.com` callsites in `data_feeds.py`. (Lift: ~30 min, mostly a helper + grep replace.)
4. **[P1] Reconcile §12 vs code on funding TTL.** Code is 5min; §12 says 10min. Pick one and unify. Same for CryptoQuant's 10min TTL (vs §12 1h). (Lift: ~1 LOC if you trust §12, plus a doc edit otherwise.)
5. **[P1] Dedupe the F&G fetcher and TTL constants** (`_FNG_TTL`, `_FNG2_TTL`, plus the Streamlit-side cache). Risk: two paths with two different stale-data behaviors. (Lift: ~20 LOC delete.)
6. **[P2] Add a one-pager `docs/api-keys.md`** that lists every env var, the source it gates, and a rotation procedure. Today: no rotation runbook exists for any key. (Lift: 1 hour.)
7. **[P2] Confirm pytrends works on Render.** If not, save the rate-limit hits and the misleading "google_trends_score" field on every signal payload. (Lift: depends on /diagnostics/feeds — would close the question in one read.)
8. **[P3] Document undocumented TTLs in §12.** OI, order books, IV, Cryptorank unlocks/funding all have caches not covered by the §12 table. Either codify or note "scope: out of §12." (Lift: doc-only.)
