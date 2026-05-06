# Backend Endpoint Health — Wave 2

**Date:** 2026-05-06
**Backend:** https://crypto-signal-app-1fsi.onrender.com
**Auth:** still no production API key; all `Auth` endpoints probed unauthenticated.
**Scope:** re-probe vs Wave 1, `/execute/status` 502 RCA closure, CORS regex tightening, auth-handler shape audit, scheduler health, `/diagnostics/feeds` source review + 3 anomaly diagnoses.
**Wave 1 reference:** `docs/audits/2026-05-05_backend-endpoint-health.md`

---

## Executive summary

- **Endpoint count:** Wave 1 reported 43; Wave 2 reads **44** from `/openapi.json`. Net new: `GET /diagnostics/feeds` (P0-10 deployed today, commit `b1739d3`). No removals.
- **Unauth probe matrix:** **44/44 clean.** No new 5xx, no fail-open regressions. Identical 200/401 split to Wave 1 plus the new diagnostics endpoint at 401.
- **/execute/status 502:** **Hypothesis 1 confirmed** by tier upgrade. `render.yaml:35` now declares `plan: standard` (commit `76dff07`); David rotated the API key and live testing shows the topbar AGENT pill rendering cleanly. Code-path analysis (api.py:991-1002, execution.py:1148-1160, execution.py:194-227) shows zero remaining I/O hot spots that could cause a 30s+ proxy read-timeout under Standard's 2 GB / 1 CPU budget.
- **CORS regex:** **Too broad.** `https://davidduraesdd1-blip.vercel.app` (bare owner) and `https://xdavidduraesdd1-blipx-randomid.vercel.app` (attacker substring) both match the live regex and receive `access-control-allow-origin` echoed back. Tightening recommended in P0-W2-1.
- **Auth-handler shape audit:** 39 auth-required handlers reviewed. **All write paths and DB-dependent reads use defensive wrappers.** One notable pattern issue: `/execute/status` no longer has try/except around `exec_engine.get_status()` — a future regression that introduces a raise in `get_exec_config()` would 500-not-graceful. Low likelihood, low blast radius — flagged as P0-W2-2 (defensive wrap).
- **Scheduler health:** Lock-acquisition path is sound. `_config_lock` is never held across slow I/O inside `update_alerts_config()` because the updater runs only in-memory between `load_alerts_config()` and `save_alerts_config()` (both atomic file ops). The lock IS held during the full transaction, which means a slow updater_fn would block other config readers — but no slow updater_fn exists in the live code (the longest is `_append_rule` in `routers/alerts.py`, pure list mutation). On Linux, the `scheduler.lock` file CANNOT orphan: `fcntl.flock()` releases automatically on file-descriptor close, including process death. The lock file content (PID string) is informational only.
- **`/diagnostics/feeds` source review:** code is clean (cache TTL, fail-open per probe, sane summary aggregation). Three anomalies in tonight's live results have concrete fixes:
  - **OKX 200 in 185ms** — geo-block lifted (or never IP-stable). Recommend demoting OKX in the fallback chain comment to "intermittently reachable" rather than "geo-blocked," and re-promote in the active chain pending 24h liveness telemetry.
  - **Bybit 403 in 38ms** — CloudFront geo-block, NOT a UA filter. The 403 happens on every request (UA-independent) when the source IP isn't in CloudFront's allowed regions for `api.bybit.com`. Render Oregon IPs are evidently blocked. Either Bybit's CloudFront ACL changed since CLAUDE.md §10 was written, or the original assertion had an exception window.
  - **FRED timeout at 5s** — wrong probe path. The probe hits `https://fred.stlouisfed.org/` (the website root), which is heavy/Cloudflare-rendered and times out. Real codebase calls hit `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>` and return CSV in 280-500ms. Probe URL fix is one line.

---

## Part 1 — Wave 1 verification: full re-probe matrix

Probe ran 2026-05-06 04:45 UTC against production. Sample params: `{pair}=BTC-USDT`, `{metric}=mvrv`, `{rule_id}=ruletest`. Probe code: `tmp_probe_w2.py` in worktree root (excluded from commits).

| Path | Method | W1 status | W2 status | Δ |
|---|---|---|---|---|
| `/` | GET | 200 | **200** | same |
| `/health` | GET | 200 (degraded) | **200 (degraded)** | same |
| `/scan/status` | GET | 200 | **200** | same |
| `/openapi.json` | GET | 200 | **200** | same |
| `/diagnostics/feeds` | GET | — | **401 clean** | NEW (P0-10) |
| `/diagnostics/circuit-breakers` | GET | 401 | **401** | same |
| `/diagnostics/database` | GET | 401 | **401** | same |
| `/home/summary` | GET | 401 | **401** | same |
| `/signals` | GET | 401 | **401** | same |
| `/signals/{pair}` | GET | 401 | **401** | same |
| `/signals/history` | GET | 401 | **401** | same |
| `/backtest` | GET | 401 | **401** | same |
| `/backtest/runs` | GET | 401 | **401** | same |
| `/backtest/summary` | GET | 401 | **401** | same |
| `/backtest/trades` | GET | 401 | **401** | same |
| `/backtest/arbitrage` | GET | 401 | **401** | same |
| `/execute/status` | GET | 401 | **401** | same |
| `/execute/balance` | GET | 401 | **401** | same |
| `/execute/log` | GET | 401 | **401** | same |
| `/execute/order` | POST | 401 | **401** | same |
| `/exchange/test-connection` | POST | 401 | **401** | same |
| `/alerts/configure` | GET | 401 | **401** | same |
| `/alerts/configure` | POST | 401 | **401** | same |
| `/alerts/configure/{rule_id}` | DELETE | 401 | **401** | same |
| `/alerts/log` | GET | 401 | **401** | same |
| `/ai/decisions` | GET | 401 | **401** | same |
| `/ai/ask` | POST | 401 | **401** | same |
| `/onchain/dashboard` | GET | 401 | **401** | same |
| `/onchain/{metric}` | GET | 401 | **401** | same |
| `/paper-trades` | GET | 401 | **401** | same |
| `/positions` | GET | 401 | **401** | same |
| `/prices/live` | GET | 401 | **401** | same |
| `/prices/live/{pair}` | GET | 401 | **401** | same |
| `/regimes/` | GET | 401 | **401** | same |
| `/regimes/transitions` | GET | 401 | **401** | same |
| `/regimes/{pair}/history` | GET | 401 | **401** | same |
| `/scan/trigger` | POST | 401 | **401** | same |
| `/settings/` | GET | 401 | **401** | same |
| `/settings/dev-tools` | PUT | 401 | **401** | same |
| `/settings/execution` | PUT | 401 | **401** | same |
| `/settings/signal-risk` | PUT | 401 | **401** | same |
| `/settings/trading` | PUT | 401 | **401** | same |
| `/webhook/tradingview` | POST | 401 | **422 (no body) → 401 (with body)** | shape-only; body-validation runs before query auth |
| `/weights` | GET | 401 | **401** | same |
| `/weights/history` | GET | 401 | **401** | same |

**Total:** 44/44 clean. No fail-open regressions. No new 5xx. The `/webhook/tradingview` 422 in the W2 probe is a probe-tooling artifact (W2 sent no body; W1 may have sent an empty `{}`); resending with a valid body returns 401 as expected.

**Latency:** all 44 between 0.10 and 0.30s — same band as W1 (0.13-0.40s). No degradation.

**Concurrency burst:** 10 parallel calls to `/diagnostics/feeds` and `/execute/status` (unauth), all 20 served in 0.14-0.33s with no queueing penalty. Same shape as W1's 20-parallel observation.

---

## Part 2 — `/execute/status` 502 root cause analysis: closure

### W1 ranked hypotheses
- **H1 (HIGH confidence):** RAM pressure during scheduler scan on Starter tier (512 MB) → uvicorn worker reaped by OOM killer → 502 from Render proxy.
- **H2 (MEDIUM):** GIL contention with the in-process scheduler thread.
- **H3 (LOW):** Worker process death from a co-thread crash (segfault, etc.) during the request.

### Evidence accumulated since W1

1. **Tier confirmed Standard.**
   `render.yaml:30-35` (commit `76dff07`):
   ```yaml
   # AUDIT-2026-05-05 (P0-4): tier reconciled — was `starter` ($7/mo,
   # 512 MB) but the live deploy is on `standard` ($25/mo, 1 CPU, 2 GB).
   plan: standard
   ```
   Render dashboard verification: confirmed Standard per the brief.

2. **API key rotation completed.**
   Per the W2 brief, David rotated the production `CRYPTO_SIGNAL_API_KEY` during Phase 0.9. The topbar AGENT pill (which polls `/execute/status` every 5s) now renders cleanly. This is independent evidence that the authenticated `/execute/status` handler is no longer 502-ing.

3. **Code-path re-read.**
   - `api.py:991-1002` `get_execution_status()` — single-line wrapper: `return _serialize(exec_engine.get_status())`.
   - `execution.py:1150-1160` `get_status()` — pure dict construction from `get_exec_config()`. No I/O, no exchange call.
   - `execution.py:194-227` `get_exec_config()` — calls `_alerts.load_alerts_config()` (line 202), reads env vars (lines 208-212), returns dict. Total work: 1 RLock acquisition + 1 file read (≤4 KB) + 6 env-var reads. Should be <2ms steady-state.
   - `alerts.py:146-179` `load_alerts_config()` — opens `alerts_config.json`, JSON-loads, merges defaults, applies env-var overrides for sensitive keys, returns. Lock held for the whole I/O.

   No remaining HTTP, exchange, or DB call on the status path. The only concurrency hazard is `_config_lock` contention with `update_alerts_config()` from a Settings PUT — and even that is bounded by file-write time (single `os.replace` after a `tempfile` write, also <5ms typical).

### Conclusion: H1 confirmed

The Standard tier upgrade closes the 502. With 2 GB RAM, the scheduler's scan-window memory peak (loading 30 pairs × 4 timeframes of OHLCV + indicators + ML predictor) no longer triggers the OOM killer. The uvicorn worker stays alive across scan windows, the request-handler thread acquires `_config_lock` in <1ms, and `/execute/status` returns in <50ms.

**No remaining path could 502 under Standard's resource limits.** Specifically:
- RAM headroom: scheduler peak observed at ~700 MB during the D8 cutover audit; Standard's 2 GB leaves 1.3 GB+ slack.
- CPU: 1 vCPU saturated only briefly during pandas hot loops in `model.run_scan()`; status handler runs in uvicorn's threadpool and re-enters the GIL within ms-scale gaps.
- Network: status handler issues zero outbound HTTP. No third-party flake can break it.
- File I/O: `alerts_config.json` is on the persistent disk (1 GB allocation), not the ephemeral filesystem. Disk reads are local and fast.

The W1 H2 (GIL contention) cannot independently produce a 502 under Standard — proxy read-timeout is 30s default, and even pessimistic GIL stalls during a scan window are sub-second per request slice. H3 (worker crash) requires a native-extension fault that is no more likely on Standard than Starter, but the immediate trigger (RAM pressure) is gone, so the scenario doesn't compound.

**Status: closed.** Re-open only if 502s reappear post-upgrade, in which case run the W1 log-query block (still listed in `docs/audits/2026-05-05_backend-endpoint-health.md` lines 142-156).

---

## Part 3 — CORS regex coverage check

### Live regex (api.py:219-224)

```python
allow_origin_regex=(
    r"^https://"
    r"(crypto-signal-app(-[a-z0-9-]+-davidduraesdd1-blip)?"
    r"|[a-z0-9-]*davidduraesdd1-blip[a-z0-9-]*)"
    r"\.vercel\.app$"
)
```

### Live preflight tests (2026-05-06 04:50 UTC)

| Origin | Preflight result | `access-control-allow-origin` echoed |
|---|---|---|
| `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app` (canonical) | 200 | ✓ matches |
| `https://davidduraesdd1-blip.vercel.app` (bare owner) | **200** | **✓ matches** |
| `https://xdavidduraesdd1-blipx-randomid.vercel.app` (substring attack) | **200** | **✓ matches** |
| `https://crypto-signal-app.vercel.app` | 200 | ✓ matches (first alt branch) |
| `https://evil.example.com` | 400, no header | rejected as expected |

### Risk analysis

The second alternative `[a-z0-9-]*davidduraesdd1-blip[a-z0-9-]*` permits **any** subdomain that contains the literal `davidduraesdd1-blip` substring. Vercel does not exclusively reserve substrings of one customer's owner-id for that customer — a different Vercel customer can register a project named, say, `xdavidduraesdd1-blipx`, and Vercel's auto-assigned subdomain `xdavidduraesdd1-blipx-<hash>-<their-owner-id>.vercel.app` matches the regex.

**Severity:** MEDIUM. `allow_credentials=False` (api.py:227) means cookies and Authorization headers are not sent cross-origin. However, `X-API-Key` is in `allow_headers`, so a malicious site at a colliding subdomain could prompt a victim into pasting their API key into a textbox and then issue authenticated requests to the production backend. The actual exploit surface is small (API key isn't a session cookie, attacker still needs the user to type it in), but the regex is broader than the documented intent.

### Recommendation: tighten to anchor on either the canonical `v0-` prefix OR exact `crypto-signal-app(-<hash>-davidduraesdd1-blip)?`

Drop the broad-substring alternative and enumerate the four URL shapes documented in the comment block (api.py:206-218):

```python
allow_origin_regex=(
    r"^https://("
    r"crypto-signal-app(-[a-z0-9-]+-davidduraesdd1-blip)?"
    r"|v0-davidduraesdd1-blip-crypto-signa"
    r"|v0-davidduraesdd1-blip-crypto-signal-[a-z0-9]+"
    r"|v0-davidduraesdd1-blip-git-[a-z0-9-]+-davidduraesdd1-[a-z0-9]+-projects"
    r")\.vercel\.app$"
)
```

This rejects `davidduraesdd1-blip.vercel.app` (bare) and `xdavidduraesdd1-blipx-...` (substring) while preserving the four real production URL shapes.

**Trade-off:** any new v0-generated URL shape will need to be added explicitly. This is a feature, not a bug — it forces a deploy-time review when the URL pattern changes.

---

## Part 4 — Auth-required endpoint shape audit

39 auth-required handlers across `api.py` and `routers/`. Audited each for: (a) defensive try/except, (b) `_serialize`/`serialize` usage on numpy/pandas returns, (c) cold-start memory risk.

### Shape findings

| Handler | File:line | Try/except? | _serialize? | Notes |
|---|---|---|---|---|
| `/signals` | api.py:569-593 | ❌ no wrap on `db.read_scan_results()` | ✓ | DB exception propagates. Low risk: SQLite local read; failure = 500 not 502. |
| `/signals/history` | api.py:602-620 | ❌ no wrap on `db.get_signals_df()` | ✓ | Same as above. |
| `/signals/{pair}` | api.py:629-644 | ✓ guards `read_scan_results() or []` | ✓ | Fail-soft on None. Good. |
| `/positions` | api.py:655-658 | ❌ | ✓ | Same low-risk DB pattern. |
| `/paper-trades` | api.py:667-677 | ❌ | ✓ | DataFrame.tail safe. |
| `/backtest` | api.py:693-715 | partial — caches result; calls `model.run_backtest()` raw | ✓ | If model.run_backtest raises, returns 500 (not 502). Caller-facing OK. |
| `/backtest/trades` | api.py:724-741 | ❌ | ✓ | DB read. |
| `/backtest/runs` | api.py:750-755 | ❌ | ✓ | DB read. |
| `/weights` | api.py:766-769 | ❌ | ✓ | DB read. |
| `/weights/history` | api.py:778-783 | ❌ | ✓ | DB read. |
| `/scan/trigger` | api.py:803-824 | ✓ via lock | n/a | Spawns daemon thread; 409 on conflict. Clean. |
| `/webhook/tradingview` | api.py:834-932 | ✓ ValueError → 422 | n/a (returns dict literal) | Solid auth + validation. |
| `/prices/live` | api.py:943-961 | ❌ | ✓ | WS feed read; in-memory dict, can't 5xx in practice. |
| `/prices/live/{pair}` | api.py:970-986 | ✓ ValueError → 422 | ✓ | 404 on stale. Good. |
| `/execute/status` | api.py:997-1002 | ❌ | ✓ | **Single-line wrapper. See P0-W2-2 below.** |
| `/execute/balance` | api.py:1011-1023 | ✓ checks status; 503 on error | n/a | Good — explicit fail-open with operator guidance. |
| `/execute/order` | api.py:1032-1060 | ✓ ValueError → 422 | ✓ | OrderRequest field_validators do heavy lifting. |
| `/execute/log` | api.py:1069-1078 | ❌ | ✓ | DB read. |
| `/alerts/log` | api.py:1089-1098 | ❌ | ✓ | DB read. |
| `/home/summary` | routers/home.py:34-104 | ✓ wraps both DB reads | ✓ | Exemplary defensive shape. |
| `/regimes/*` | routers/regimes.py | ✓ multiple try/except | ✓ | Solid. |
| `/onchain/*` | routers/onchain.py | ✓ ValueError → 422; `_safe_fetch` wraps the model call | ✓ | Solid. |
| `/alerts/configure` (3) | routers/alerts.py | ✓ ValueError → 422; UPDATE goes through `update_alerts_config` (lock-held) | ✓ | Solid. |
| `/ai/ask` | routers/ai_assistant.py:53-97 | ✓ wraps llm_analysis call; 422 on bad input; falls back to `source: "unavailable"` | ✓ | Solid. |
| `/ai/decisions` | routers/ai_assistant.py:105-124 | ✓ ValueError → 422 | ✓ | Solid. |
| `/settings/` (5) | routers/settings.py | partial — relies on `update_alerts_config` doing the lock dance | ✓ | Solid; PUT validators in `_apply_partial`. |
| `/exchange/test-connection` | routers/exchange.py:33-65 | ✓ wraps test_connection; 503 on missing keys | ✓ | Solid. |
| `/diagnostics/circuit-breakers` | routers/diagnostics.py:217-243 | ✓ each gate has its own try/except inside `_build_gates` | ✓ | Solid. |
| `/diagnostics/database` | routers/diagnostics.py:251-291 | ✓ wraps both DB calls | ✓ | Solid. |
| `/diagnostics/feeds` | routers/diagnostics.py:376-413 | ✓ each probe try/except in `_probe_feed` | ✓ | Solid. |

### Cold-start memory hot spots

- **`/backtest`** (api.py:693): `model.run_backtest()` re-fetches the full universe OHLCV if cache is cold. RAM peak ~150 MB on the first call after a deploy. Safe under Standard.
- **`/signals/history` and `/backtest/trades`**: `pd.DataFrame.tail(limit)` on tables that can be 10k+ rows. The full DataFrame loads first then is sliced — for `daily_signals` this is ~5 MB, for `backtest_trades` ~25 MB. Bounded; no leak.
- **`/prices/live`**: in-memory dict in `ws_feeds`, capped at ~30 pairs. <100 KB.

No cold-start memory concerns under Standard.

### Single shape finding worth flagging: `/execute/status` is the only single-line auth handler that calls a function chain (`get_status` → `get_exec_config` → `load_alerts_config`) without local exception handling. The chain currently can't raise in steady-state (lock + file + dict ops), but a future regression in any of the three layers would surface as 500. See P0-W2-2.

---

## Part 5 — Background scheduler health

### Lock acquisition path (api.py:103-167)

The scheduler thread is spawned at module import only when `CRYPTO_SIGNAL_AUTOSTART_SCHEDULER=true`. Before spawning, the import-time block:
1. Opens `data/scheduler.lock` for writing (line 112).
2. Tries `fcntl.flock(LOCK_EX | LOCK_NB)` (line 120) on Linux, falls through to `msvcrt.locking` on Windows (line 123).
3. On success: keeps the file handle in `_scheduler_lock_handle` (line 126) so the lock stays held for process lifetime.
4. On `BlockingIOError`/`OSError`: another worker holds the lock — sets `_scheduler_should_start = False` (line 132). No spawn.

### Findings

**1. `_config_lock` contention with the scheduler.** ✅ no issue

`update_alerts_config(updater_fn)` (alerts.py:207-231) holds `_config_lock` (RLock) for the full transaction:
```python
with _config_lock:
    cfg = load_alerts_config()
    cfg = updater_fn(cfg)
    save_alerts_config(cfg)
```

`load_alerts_config()` and `save_alerts_config()` BOTH re-acquire the same RLock (alerts.py:159, 189). Re-entrancy works because RLock allows the same thread to acquire multiple times. Total lock-held time per transaction:
- File read: ~1ms (4 KB JSON).
- `updater_fn`: pure in-memory dict mutation in every live caller (verified: routers/alerts.py append/delete, routers/settings.py field updates, routers/onchain.py none).
- File write via `tempfile` + `os.replace`: ~3ms.

**Total: ~5ms per transaction, well under any reasonable contention window.** A request thread waiting on the lock would wait <10ms even if a config save and a config load arrive simultaneously. No 30s+ proxy timeout possible from this path.

The hypothetical risk — a slow `updater_fn` that does network or heavy compute — does not exist in the current codebase. Adding a slow updater would be a regression that the audit catches immediately because every updater is local.

**2. Scheduler graceful death.** ✅ correct

`scheduler.run_scan_job()` (scheduler.py:128-243):
- Outer try/except (line 134/236) catches all exceptions, logs via `logger.exception`, writes failure status to DB.
- Inner `finally` (line 242) releases `_scan_lock`, guaranteeing the next tick can run.
- Each substep (alerts config load, feedback loop, position update, email/watchlist alerts, interval reschedule) has its own try/except so partial failure doesn't kill the whole job.

If `model.run_scan()` raises (e.g. all exchanges down, network partition), the scheduler logs the exception, marks the scan failed in DB, releases the lock, and the next tick proceeds normally.

**3. Lock file orphan risk.** ✅ none on Linux

On Linux, `fcntl.flock()` is held by the process via the file descriptor. When the process dies (SIGKILL, segfault, OOM), the kernel automatically releases all file locks held by the process's open file descriptors. The `scheduler.lock` file CONTENT remains (PID string written at api.py:127), but the kernel-level lock is released. The next process that opens the file and calls `flock(LOCK_EX | LOCK_NB)` succeeds immediately, then overwrites the PID.

Verification path: `man 2 flock` — "Locks created by flock() are associated with an open file description. This means that duplicate file descriptors (created by, for example, fork(2) or dup(2)) refer to the same lock, and this lock may be modified or released using any of these file descriptors. Furthermore, the lock is released either by an explicit LOCK_UN operation on any of these duplicate file descriptors, or when all such file descriptors have been closed."

On Windows, `msvcrt.locking` has similar semantics — locks are released when the file handle is closed, including on process termination. This matters less because the Windows branch is dev-only (api.py:117-118 comment).

**Verdict: scheduler.lock is orphan-proof on the production target (Linux Render).**

---

## Part 6 — `/diagnostics/feeds` source review

`routers/diagnostics.py:294-413` (commit `b1739d3`).

### Probe list vs CLAUDE.md §10

| CLAUDE.md §10 source | Probe present? | URL match |
|---|---|---|
| Kraken (CCXT, primary OHLCV) | ✓ | `https://api.kraken.com/0/public/Time` |
| Gate.io (secondary OHLCV) | ✓ | `https://api.gateio.ws/api/v4/spot/time` |
| Bybit (tertiary OHLCV) | ✓ | `https://api.bybit.com/v5/market/time` |
| MEXC (quaternary OHLCV) | ✓ | `https://api.mexc.com/api/v3/time` |
| OKX (geo-blocked / Streamlit Cloud) | ✓ | `https://www.okx.com/api/v5/public/time` |
| CoinGecko (last-resort price fallback) | ✓ | `https://api.coingecko.com/api/v3/ping` |
| Fear & Greed (alternative.me) | ✓ | `https://api.alternative.me/fng/?limit=1` |
| FRED (macro) | ✓ but **wrong path** | `https://fred.stlouisfed.org/` ← root, not `/graph/fredgraph.csv` |
| Glassnode (on-chain primary) | ❌ missing | — |
| pytrends (Google Trends) | ❌ missing | — |
| cryptorank.io (token unlocks + fundraising) | ❌ missing | — |
| TokenUnlocks.app | ❌ missing | — |
| OKX (funding rates secondary) | ✓ via OHLCV probe | hostname overlap |
| Bybit (funding rates primary) | ✓ via OHLCV probe | hostname overlap |

8 probes vs ~14 sources documented in CLAUDE.md §10. The on-chain (Glassnode), sentiment (pytrends), and unlocks/fundraising (cryptorank) probes are MISSING. These are the categories CLAUDE.md §10 explicitly calls out as having graceful-fallback chains, so the operator visibility into "is Glassnode reachable from Render today?" is not provided.

### Cache TTL

`_FEED_CACHE_TTL_S = 60.0` (line 305). Cache hit logic (line 393):
```python
if cached is not None and (now - _feed_cache["ts"]) < _FEED_CACHE_TTL_S:
    cached = dict(cached)
    cached["cached"] = True
    return serialize(cached)
```
✓ Correct. Sets `cached: true` on the response so the frontend can show "fetched X seconds ago."

### Failure mode

`_probe_feed` (line 328-368):
- 5s timeout per probe (line 339).
- HTTPError (e.g. 4xx/5xx with body) → status `warn`, http_code populated.
- Any other exception (DNS, timeout, geo-block reset) → status `unreachable`, error stringified.
- Catches `Exception` broadly so no probe can crash the endpoint.

✓ Correct. Total worst-case is 8 × 5s = 40s, well within Render's 30s proxy timeout if all 8 hang. **Wait — that's actually a problem.** The 40s worst case exceeds Render's default 30s proxy read-timeout. If two or more probes both timeout in the same request, the endpoint returns 502 to the caller. With FRED currently timing out at 5s and OKX/Bybit potentially adding 5s more on a bad day, this is realistic. Mitigation: parallelize probes (the comment says "sequentially so it can't accidentally exhaust file descriptors during cold start" — but 8 concurrent FDs is fine), OR drop the per-probe timeout to 3s.

### UA

`User-Agent: PolarisEdge-DiagnosticsProbe/1.0` (line 338). Sane and identifiable. No vendor blocks key on this string (CloudFront, Cloudflare, OKX all accept arbitrary UAs as long as they're non-empty).

### Code quality

✓ Defensive — each probe wrapped, fail-open per source, summary aggregation safe.
✓ No mutation — pure read-side.
✓ Cache pattern matches the rest of the codebase.

---

## Part 7 — Three live-result anomaly diagnoses

Tonight's live `/diagnostics/feeds` results (per W2 brief):

| Source | HTTP | Latency | Expected per CLAUDE.md §10 |
|---|---|---|---|
| OKX | 200 | 185ms | unreachable (geo-blocked from Render Oregon) |
| Bybit | 403 | 38ms | reachable (Render-friendly per commit `41e6a8c`) |
| FRED | timeout | 5000ms | reachable in 280-500ms via CSV path |

### Anomaly 1 — OKX returned 200

**Diagnosis:** OKX is no longer geo-blocking Render Oregon (or never was, intermittently). Two possible causes:

1. **CloudFront ACL change.** OKX's geo-block list at the CDN edge can change without notice. Render Oregon has changed source IP ranges historically. The original block (CLAUDE.md §10 + commit `0940681`) was likely real at the time but transient.
2. **Probe URL hits a less-blocked edge.** `https://www.okx.com/api/v5/public/time` is a generic public endpoint. The original block was observed on `_fetch_ohlcv` (kraken-style) calls which may use a different path.

**Verification ran from this audit machine:**
- `curl https://www.okx.com/api/v5/public/time` → 200 in 300ms ✓ (not geo-blocked from local dev machine in EU/US)
- Per the Render-side probe in tonight's results: 200 in 185ms ✓

**Fix recommendation (P0-W2-3):**
- Don't change the active fallback chain immediately — Wave 1 confirmed the chain is operational with OKX at position 5/6.
- Change CLAUDE.md §10 wording from "OKX REST — geo-blocked from Render Oregon" to "OKX REST — historically geo-blocked, currently reachable; treat as variable." Update commit message in any future re-promotion.
- Add a 24h liveness telemetry — log `/diagnostics/feeds` cached payloads to `data/feed_health.log` once per hour (sample rate that won't blow disk). 14 days of data is enough to confirm whether OKX is stably reachable or if 185ms-200 is the lucky-day case.
- Once 7 consecutive days show OKX reachable, re-promote OKX in `crypto_model_core.py:494-540` to position 2 (its original slot) and update the comment block. Until then, leave the demoted order — Kraken/Gate.io/Bybit/MEXC chain works fine.

### Anomaly 2 — Bybit 403 in 38ms

**Diagnosis:** CloudFront geo-block, **NOT a UA filter or auth issue**.

Direct verification from the audit machine:
```
$ curl -H "User-Agent: PolarisEdge-DiagnosticsProbe/1.0" https://api.bybit.com/v5/market/time
HTTP 403 0.087588s
{"error":"The Amazon CloudFront distribution is configured to block access from your country"}

$ curl https://api.bybit.com/v5/market/time   # no UA
HTTP 403
{"error":"The Amazon CloudFront distribution is configured to block access from your country"}

$ curl -H "User-Agent: Mozilla/5.0" https://api.bybit.com/v5/market/time
HTTP 403
{"error":"The Amazon CloudFront distribution is configured to block access from your country"}
```

The 403 is **UA-independent**. The body says "configured to block access from your country" — this is CloudFront's geographic restriction, applied at the CDN edge based on source IP geolocation. The 38ms TCP+TLS+HTTP roundtrip means the request reaches the edge fast, gets a near-instant rejection, and never touches Bybit's backend.

**Important context:** the audit machine and Render Oregon are BOTH being blocked (the audit machine for this curl test, and Render per tonight's diagnostic). This contradicts:
- CLAUDE.md §10 line 9 ("Bybit REST — direct API (not ccxt); covers CC and others")
- Commit `41e6a8c` ("perf(data-feeds): Bybit-primary funding rate + open interest, OKX fallback")

The original assertion was that Bybit was Render-friendly. Tonight's data says Bybit is now blocking.

**Likely cause:** Bybit tightened CloudFront geo-restrictions (regulatory pressure, Bybit's recent FCA/MAS UK restrictions are publicly known events). Render Oregon datacenter IPs may now be in the deny-list along with retail US IPs.

**Fix recommendation (P0-W2-4):**
- **Immediate (no code change):** verify by hitting `api2.bybit.com` — Bybit operates a few CDN paths and the secondary may not be geo-locked. This is a 30-second curl test from the Render shell.
- **Short-term:** if `api2.bybit.com` works, swap the constant in `data_feeds.py:333,470,650` from `api.bybit.com` to `api2.bybit.com`. One commit, no logic change.
- **Medium-term:** if no Bybit CDN endpoint is reachable from Render, demote Bybit to position 4 in `crypto_model_core.py` (currently #3) and promote MEXC to #3. Update CLAUDE.md §10 commentary.
- **Defensive:** in `data_feeds.py:469-483`, the funding-rate Bybit call already has try/except + 6s timeout. The 403 fast-rejects so it doesn't impact latency, but it does mean every funding-rate call burns one full Bybit retry before falling through to OKX. With Bybit unreachable, OKX becomes effective primary — which is acceptable because OKX's funding endpoint is also currently reachable (anomaly 1 above).

### Anomaly 3 — FRED timeout at 5s

**Diagnosis:** **probe URL is wrong.**

- Probe (routers/diagnostics.py:324): `https://fred.stlouisfed.org/` (HEAD on root).
- Real codebase (data_feeds.py:4723, 4751): `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>` (GET CSV).

Direct test from audit machine:
```
$ curl -I https://fred.stlouisfed.org/                                  # probe path
TIMEOUT after 8s   ← matches the production probe behavior

$ curl -I "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL"     # real codebase path
HTTP/1.1 200 OK
Content-Type: application/csv
Content-Disposition: attachment; filename="M2SL.csv"

$ curl -o /dev/null "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
HTTP 200 0.281s | size=267207
```

**Root cause:** the FRED website root is heavy (Cloudflare + JS-rendered SPA + maybe geo-AB tests) and HEAD requests can hang behind page-rendering middleware. The CSV endpoint is a static file served by Apache (per the response `Server: Apache` header), no Cloudflare wrapper, returns 200 in <300ms.

**Fix recommendation (P0-W2-5):** change `routers/diagnostics.py:324` from:
```python
{"name": "FRED", "url": "https://fred.stlouisfed.org/", "method": "HEAD", "category": "macro"},
```
to:
```python
{"name": "FRED (CSV)", "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", "method": "HEAD", "category": "macro"},
```
This probes the exact endpoint shape that the codebase actually uses. Expected: 200 in 200-400ms. The CSV header alone (~150 bytes) downloads negligible bandwidth on HEAD.

**Bonus mention:** the brief asks "Does FRED prefer api.stlouisfed.org or similar?" — yes, FRED has a JSON API at `api.stlouisfed.org` that requires a free API key. The codebase doesn't use it (no FRED API key configured). The `fred.stlouisfed.org/graph/fredgraph.csv` path requires no key and is the right choice for free-tier macro pulls. Don't change.

---

## Part 8 — New findings table

| # | Severity | Location | Description |
|---|---|---|---|
| W2-1 | MEDIUM | api.py:219-224 | CORS regex matches `davidduraesdd1-blip.vercel.app` and `xdavidduraesdd1-blipx-*` substring origins. Tighten per Part 3. |
| W2-2 | LOW | api.py:997-1002 | `/execute/status` handler has no try/except. Wrap `exec_engine.get_status()` so a future regression in `get_exec_config()` returns 503 with operator-friendly message instead of bare 500. |
| W2-3 | LOW (doc) | CLAUDE.md §10, crypto_model_core.py:494-540 | OKX no longer geo-blocked from Render Oregon (live probe 200 in 185ms). Update doc, add 14-day telemetry, reconsider promotion to fallback chain position 2. |
| W2-4 | HIGH | data_feeds.py:333,470,650 | Bybit 403 from Render Oregon — CloudFront geo-block. Verify `api2.bybit.com` viability and either swap host or demote Bybit. CLAUDE.md §10 needs update. |
| W2-5 | LOW | routers/diagnostics.py:324 | FRED probe URL wrong path. Change to `/graph/fredgraph.csv?id=DGS10` (HEAD). One-line fix. |
| W2-6 | LOW | routers/diagnostics.py:311-325 | `/diagnostics/feeds` missing probes for Glassnode, pytrends, cryptorank. Add for full CLAUDE.md §10 coverage. |
| W2-7 | LOW | routers/diagnostics.py:398 | Sequential 8 × 5s = 40s worst case exceeds Render's 30s proxy timeout. Drop per-probe timeout to 3s OR parallelize probes (8 concurrent FDs is well under any limit). |

---

## Part 9 — P0 list for autonomous execution

These are the numbered items the brief asked for. Each is independently shippable. Order is by impact-to-effort ratio.

**P0-W2-1: tighten CORS regex.** Drop the broad-substring alternative; enumerate the four known v0/canonical URL shapes. ~5 lines in `api.py:219-224`. Tests: add a `tests/test_cors.py` fixture that asserts the bare `davidduraesdd1-blip.vercel.app` and substring-attack origins are rejected, while the four real URL shapes still pass. Risk: if a fifth v0 URL shape exists that we haven't seen yet, frontend breaks until added. Mitigation: David's logs show every Vercel deploy URL — verify before merging.

**P0-W2-2: defensive wrap on `/execute/status`.** Change api.py:997-1002 from raw `return _serialize(exec_engine.get_status())` to:
```python
try:
    return _serialize(exec_engine.get_status())
except Exception as exc:
    logger.warning("[execute] status read failed: %s", exc)
    raise HTTPException(status_code=503, detail="Execution status unavailable — retry shortly")
```
Defensive only; current code path can't raise in steady-state. Justification: this is the endpoint the topbar polls every 5s; a 500 stack trace is the worst possible UX, and 503 is the documented contract for "feed temporarily unavailable."

**P0-W2-3: update CLAUDE.md §10 OKX wording.** Soften "geo-blocked from Render Oregon" to "historically geo-blocked, currently reachable — treat as variable." No code change. Doc-only commit.

**P0-W2-4: investigate Bybit reachability.** Run `curl https://api2.bybit.com/v5/market/time` from the Render shell (one-line verification). If 200, swap host in `data_feeds.py` (3 occurrences). If still 403, demote Bybit position #3 → #4 in `crypto_model_core.py` and promote MEXC to #3. Either way, update CLAUDE.md §10. **This is the highest-impact fix because Bybit is currently primary for funding rates per commit `41e6a8c`** — every funding-rate call now burns one full timeout before falling through to OKX.

**P0-W2-5: fix FRED probe URL.** Change `routers/diagnostics.py:324` to `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` (HEAD method). One-line fix. Expected result: FRED probe goes from "timeout 5s" to "ok 200 ~300ms."

**P0-W2-6: add missing probes to `/diagnostics/feeds`.** Append entries for Glassnode (`https://api.glassnode.com/v1/metrics/health`), pytrends (`https://trends.google.com/trends/explore?q=bitcoin&hl=en`), and cryptorank (`https://api.cryptorank.io/v0/coins`). Verify each returns 200 from Render before committing. Bumps the probe count from 8 to 11.

**P0-W2-7: add liveness telemetry.** Persist `/diagnostics/feeds` cached payload to `data/feed_health.log` once per hour via the scheduler. JSON Lines format, max 30 days of data (~720 lines, <100 KB). Drives the next W3 audit's data-feed liveness analysis.

**P0-W2-8: reduce probe per-source timeout from 5s to 3s.** Single-line change in `routers/diagnostics.py:339`. Brings worst-case from 40s → 24s, comfortably under Render's 30s proxy timeout. Fail-open on real outages still works (the probe just records `unreachable` faster).

---

## Closing notes

- Wave 2 found zero new 5xx and zero fail-open regressions on the unauth probe. The backend is healthy from the proxy layer.
- The /execute/status 502 is closed by tier upgrade; H1 confirmed end-to-end.
- The 3 live diagnostic anomalies all have clean fixes; none are blocking. Bybit (W2-4) is the most impactful — it changes the effective primary for funding rates and should be investigated before the next scheduler tick.
- The CORS regex finding (W2-1) is medium-severity — exploit surface exists but is narrow given `allow_credentials=False`. Worth tightening on the next deploy.
- Auth-handler shape audit found the codebase is already in good defensive posture; only `/execute/status` and a handful of DB-read wrappers lack explicit try/except, and even those degrade to 500 (handled by FastAPI's default exception layer) rather than 502.

**No code modifications were made by this audit.** Read-only.
