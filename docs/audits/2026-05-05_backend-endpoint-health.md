# Tier 3 — Backend Endpoint Health
**Date:** 2026-05-05
**Backend:** https://crypto-signal-app-1fsi.onrender.com
**Methodology:** Pulled `/openapi.json`, ran an unauthenticated probe of every path × method, ran a CORS preflight from the canonical Vercel origin against every path × method, ran concurrency bursts (20 parallel), and read the relevant handler code (`api.py:991`, `execution.py:1150`, `execution.py:194`, `alerts.py:146`, `api.py:103-167`, `scheduler.py:128`, `render.yaml`). **No production API key available** — the actual 502 response cannot be reproduced from this audit context. The 502 RCA below is a code-path analysis of the authenticated handler, not a live repro.

## Summary
- Endpoints inventoried: **43** (42 unique paths; `/openapi.json` paths report 42 — the OpenAPI count excludes `/openapi.json` itself).
- Endpoints returning expected unauth code: **43 / 43** (3 documented public: `/`, `/health`, `/scan/status`, `/openapi.json`, all 200; 39 auth-required, all clean **401** with `{"detail":"Invalid or missing API key"}`).
- Endpoints with anomalies on the unauth path: **0** — no 502s, no 500s, no hangs, no leaked tracebacks.
- CORS preflight: **42 / 42 path × method combos return 200 with the correct `access-control-allow-origin` set to the Vercel origin.** Non-matching origin is correctly rejected with 400 + no `access-control-allow-origin`.
- CRITICAL bugs found: **0 confirmed** (the 502 is not reproducible without an API key); **3 ranked hypotheses** below for the user's authenticated repro.
- Notable infrastructure observation: `/health` reports `"status":"degraded"` because 4 long-tail pairs (FLR/XDC/SHX/ZBCN) are stale on the WS feed. This is cosmetic — it does not affect any endpoint. The last completed scan timestamp is **39 minutes old** at the time of this audit (default autoscan interval is 30 min) — overdue by ~9 min, worth checking.
- Tier discrepancy: brief says "Render Standard tier"; `render.yaml:30` declares `plan: starter`. Either the brief is stale or `render.yaml` was not bumped after a tier change. Worth confirming on the dashboard — it materially changes the OOM hypothesis below (Standard = 2 GB RAM, Starter = 512 MB).

## Endpoint matrix

Tags: `Public` = no auth dependency; `Auth` = `Depends(require_api_key)`. All `Auth` endpoints unauth-probe cleanly with 401 + 0.13–0.40 s. All preflights return 200 with full CORS headers (`ACAO=https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`, `ACAM=GET, POST, PUT, DELETE`, `ACAH=Accept, Accept-Language, Content-Language, Content-Type, X-API-Key`).

| Path | Method | Auth | Unauth status | OPTIONS preflight | Notes |
|---|---|---|---|---|---|
| `/` | GET | Public | 200 | 200 OK | service banner |
| `/health` | GET | Public | 200 (`status:"degraded"` — feeds-only) | 200 OK | 4 stale pairs flagged in feed |
| `/scan/status` | GET | Public | 200 (last scan 22:23:55, ~39 min ago) | 200 OK | scheduler likely behind on tick |
| `/openapi.json` | GET | Public | 200 | 200 OK | 42 documented paths |
| `/home/summary` | GET | Auth | 401 clean | 200 OK | |
| `/signals` | GET | Auth | 401 clean | 200 OK | |
| `/signals/history` | GET | Auth | 401 clean | 200 OK | |
| `/signals/{pair}` | GET | Auth | 401 clean | 200 OK | |
| `/backtest` | GET | Auth | 401 clean | 200 OK | |
| `/backtest/runs` | GET | Auth | 401 clean | 200 OK | |
| `/backtest/summary` | GET | Auth | 401 clean | 200 OK | |
| `/backtest/trades` | GET | Auth | 401 clean | 200 OK | |
| `/backtest/arbitrage` | GET | Auth | 401 clean | 200 OK | |
| `/diagnostics/circuit-breakers` | GET | Auth | 401 clean | 200 OK | |
| `/diagnostics/database` | GET | Auth | 401 clean | 200 OK | |
| `/execute/status` | GET | Auth | 401 clean | 200 OK | **502 reported by user when authed — see RCA below** |
| `/execute/balance` | GET | Auth | 401 clean | 200 OK | calls OKX live; expect 503 if keys absent |
| `/execute/log` | GET | Auth | 401 clean | 200 OK | |
| `/execute/order` | POST | Auth | 401 clean | 200 OK | |
| `/alerts/configure` | GET | Auth | 401 clean | 200 OK | |
| `/alerts/configure` | POST | Auth | 401 clean | 200 OK | |
| `/alerts/configure/{rule_id}` | DELETE | Auth | 401 clean | 200 OK | |
| `/alerts/log` | GET | Auth | 401 clean | 200 OK | |
| `/ai/decisions` | GET | Auth | 401 clean | 200 OK | |
| `/ai/ask` | POST | Auth | 401 clean | 200 OK | |
| `/exchange/test-connection` | POST | Auth | 401 clean | 200 OK | |
| `/onchain/dashboard` | GET | Auth | 401 clean | 200 OK | |
| `/onchain/{metric}` | GET | Auth | 401 clean | 200 OK | |
| `/paper-trades` | GET | Auth | 401 clean | 200 OK | |
| `/positions` | GET | Auth | 401 clean | 200 OK | |
| `/prices/live` | GET | Auth | 401 clean | 200 OK | |
| `/prices/live/{pair}` | GET | Auth | 401 clean | 200 OK | |
| `/regimes/` | GET | Auth | 401 clean | 200 OK | |
| `/regimes/transitions` | GET | Auth | 401 clean | 200 OK | |
| `/regimes/{pair}/history` | GET | Auth | 401 clean | 200 OK | |
| `/scan/trigger` | POST | Auth | 401 clean | 200 OK | |
| `/settings/` | GET | Auth | 401 clean | 200 OK | |
| `/settings/dev-tools` | PUT | Auth | 401 clean | 200 OK | |
| `/settings/execution` | PUT | Auth | 401 clean | 200 OK | |
| `/settings/signal-risk` | PUT | Auth | 401 clean | 200 OK | |
| `/settings/trading` | PUT | Auth | 401 clean | 200 OK | |
| `/webhook/tradingview` | POST | Auth (token query) | 401 clean | 200 OK | |
| `/weights` | GET | Auth | 401 clean | 200 OK | |
| `/weights/history` | GET | Auth | 401 clean | 200 OK | |

**Concurrency burst (20 parallel):** `/scan/status` and `/execute/status?bad-key` both serve all 20 within 110–150 ms each. No queueing penalty visible — the single uvicorn worker comfortably absorbs the burst on the unauth path. This means the 502 is not a generic "worker is overloaded" symptom; it's specific to the authenticated `/execute/status` code path.

**CORS observations (all positive):**
- Every preflight returns `access-control-allow-origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app` (the regex on `api.py:219-224` matches).
- `access-control-allow-methods: GET, POST, PUT, DELETE` — note: `OPTIONS` is NOT listed. Starlette's `CORSMiddleware` handles preflight before the explicit method allowlist, so this is harmless in practice (preflights still return 200), but worth noting if the user later adds endpoints expecting OPTIONS to be a documented method.
- `access-control-allow-headers` includes `X-API-Key` — required for the v0 frontend to attach the key.
- Non-matching origin (`https://evil.example.com`) is rejected with **400 Bad Request** and no `access-control-allow-origin` header — locks down the regex correctly.

**Note on the 502:** the unauth probe of `/execute/status` returns 401 every single time, in 140–170 ms. The unauth response leaves the handler before reaching `exec_engine.get_status()`. So the 502 the user is seeing in the browser only manifests **after** `require_api_key` accepts the request and the handler runs. None of the symptoms here (clean 401, sub-200 ms latency, no hung connections, all preflights pass) are consistent with a TCP/CORS/proxy issue. The fault is in the authenticated handler.

## /execute/status 502 root cause analysis

Render's load-balancer surfaces a **502 Bad Gateway** when the upstream uvicorn worker either (a) closes the TCP connection without sending a complete response, (b) doesn't respond within the proxy's read-timeout window (~30 s default), or (c) crashes hard enough that the worker process is restarted. The unauth path has none of these symptoms, so the trigger has to be inside `exec_engine.get_status()` (`execution.py:1150`) or its dependency chain.

Code path on a successful auth:

1. `api.py:997` `get_execution_status()` → `_serialize(exec_engine.get_status())`
2. `execution.py:1150` `get_status()` → `get_exec_config()` (line 1152)
3. `execution.py:194` `get_exec_config()` → `_alerts.load_alerts_config()` (line 202)
4. `alerts.py:146` `load_alerts_config()` acquires `_config_lock` (RLock) (line 159), reads `alerts_config.json` from CWD, releases.
5. Returns dict to handler. No HTTP, no exchange round-trip, no DB.

Total work: 1 RLock acquisition + 1 file read + 1 dict merge. Should be <5 ms. Yet the user sees persistent 502s. Three hypotheses, ranked by likelihood:

### Hypothesis 1: Render proxy read-timeout while the GIL is parked inside a scheduler-driven `model.run_scan()`
- **Confidence: HIGH**
- **Evidence:**
  - `api.py:103-167` — scheduler runs as a daemon thread inside the same uvicorn process (Path A from D8). `start_scheduler()` runs the `BlockingScheduler` on a daemon thread; every 30 min `run_scan_job` (`scheduler.py:128`) executes `model.run_scan()` (line 165) followed by `model.run_feedback_loop()` (line 170).
  - `model.run_scan()` does dozens of CCXT calls (Kraken, Gate.io, Bybit, MEXC, OKX) plus heavy pandas math. Many of those C-extension calls **release the GIL**, but the pandas/NumPy windows around them can hold it for tens to hundreds of ms each.
  - When uvicorn's request-handler coroutine wakes up to serve `/execute/status` and tries to acquire `_config_lock` (RLock) in `alerts.py:159` — that's **the same lock** the scheduler holds during its periodic `_alerts.load_alerts_config()` calls inside `run_scan_job`. While the lock is held, the request thread waits.
  - More damaging: `_alerts.send_scan_email_alerts(results, cfg)` and `_alerts.check_watchlist_alerts(results, cfg)` (`scheduler.py:204, 208`) run inside the scan job and may take real wall time (network for SMTP). They DON'T hold `_config_lock` (the lock is released after `load_alerts_config` returns), but the scan job as a whole easily takes 30–120 s on this universe size.
  - Render free/Starter tier has a **single uvicorn worker** by default (`render.yaml:37` does not pass `--workers`, so it's 1). FastAPI route handlers for the synchronous `def` form (which `get_execution_status` is — line 997 declares `def`, not `async def`) run in the threadpool, which mitigates this somewhat. But — and this is the critical point — `model.run_scan()` is also `def`-not-`async`-`def` inside the scheduler thread, AND the scheduler thread is NOT the threadpool. The scheduler thread is a daemon thread separate from uvicorn's threadpool, so in principle they shouldn't block each other.
  - **The actual likely failure mode:** the scan job consumes enough RAM (loading 30 pairs × 4 timeframes of OHLCV + indicators + ML predictor) that on the Starter tier (512 MB) the OOM killer reaps the uvicorn worker mid-scan. When the worker is being restarted, requests in flight return 502. This was the documented original symptom that prompted the "Standard tier upgrade" fix mentioned in the brief.
- **Critical to verify:** is the deploy actually on Standard or still on Starter? `render.yaml:30` says `starter`, brief says "Standard." If still Starter, RAM-during-scan is the prime suspect.
- **Verification in Render logs:**
  - `grep -E "Out of memory|Memory cgroup out of memory|MemoryError|Worker exiting|Worker .* received signal|received SIGKILL"` in the past 24 h.
  - Render UI → Service → Metrics → Memory chart: look for sawtooth pattern hitting the limit at scheduler tick boundaries (every 30 min).
  - Confirm tier on the Render dashboard (Settings → Instance Type).

### Hypothesis 2: WebSocket feed thread or scheduler thread starving the request thread, causing Render's read-timeout to fire (false 502)
- **Confidence: MEDIUM**
- **Evidence:**
  - `api.py:80` starts `ws_feeds.start(model.PAIRS)` at module import — that spawns a websocket-client thread per exchange.
  - The combined picture in this single process: uvicorn event loop + uvicorn threadpool (default 40) + WS feed thread(s) + scheduler daemon thread + scheduler's own thread for graceful resume + apscheduler's executor thread. That's 6+ persistent Python threads, plus burst threads from the threadpool.
  - Python's GIL means only one thread executes Python bytecode at a time. If the scheduler thread is in a tight pandas/NumPy hot loop (which doesn't always release the GIL), the request handler can sit in the threadpool waiting up to hundreds of ms per chance to run.
  - For a 5 s polling cadence (the topbar polls `/execute/status` every 5 s per the brief) over a 60 s scan window, that's 12 calls — if even one of them takes >30 s to serve because of GIL contention, Render's proxy emits 502.
  - The handler logic itself is trivial (~5 ms of work). The 502 is the proxy giving up, not the worker erroring.
- **Why ranked second, not first:** the unauth-path concurrency test (20 parallel /scan/status) returned all 20 in 110–150 ms each. If GIL contention with the scheduler were severe enough to cause 30 s+ stalls, we'd expect occasional latency spikes on /scan/status too. We didn't see any. This makes pure GIL contention less likely than RAM-during-scan as the primary cause — but it could be the secondary effect that compounds H1.
- **Verification in Render logs:**
  - Look for uvicorn access-log lines on `/execute/status` with response time > 25 s.
  - Cross-correlate with `[Scheduler] SCAN STARTED` log lines — are 502s clustered around scan windows?
  - `tail -F` on the live log during a scheduled scan and watch for the topbar's 5 s polls.

### Hypothesis 3: Unhandled exception in `get_status()` → `get_exec_config()` causing a worker crash on Starlette's BaseHTTPMiddleware path
- **Confidence: LOW (but easy to rule in/out from logs)**
- **Evidence:**
  - `api.py:231` registers a `BaseHTTPMiddleware` (`_security_headers`) that wraps every response. `BaseHTTPMiddleware` is known to surface obscure asyncio exceptions that aren't caught by FastAPI's default exception handler — Starlette's docs explicitly warn about this.
  - If `get_exec_config()` somehow raises during file I/O (e.g. a partial-write race during an in-progress save by the Settings PUT path), the exception bubbles into the `_security_headers` middleware. If the response object is already partially flushed, the connection is closed → Render proxy reports 502.
  - The save path in `alerts.py:182-204` uses atomic rename via `os.replace`, which is atomic on POSIX. So the load path can't see a half-written file. BUT — `load_alerts_config` calls `json.load(f)` inside a lock-protected block, and a JSON parse error from a corrupted file (e.g. someone manually edited the file via Render's shell) would crash the request and propagate.
  - If `get_exec_config()` then raised, the resulting `HTTPException` from FastAPI would be 500, not 502 — UNLESS the exception escaped the FastAPI handler chain entirely (e.g. a thread crash inside ccxt module-load — but `ccxt` is already imported at line 186 and `_CCXT_AVAILABLE` is set; on the status path no further ccxt work happens).
  - **The one specific way this becomes 502, not 500:** if the worker process itself dies (segfault from a bad C extension, e.g. NumPy/Pandas hitting a corrupted memory mapping, or a thread crash in the WS feed propagating SIGSEGV). A worker death in the middle of serving the request → connection dropped → Render proxy returns 502.
- **Why ranked last:** workers don't usually die from a config read. The lock-protected file I/O on `alerts_config.json` is well-tested elsewhere in the codebase. The scenario only fires if the file is genuinely corrupt or if a co-thread crashes natively.
- **Verification in Render logs:**
  - `grep -E "Worker .* exited|received signal|signal 11|SIGSEGV|JSONDecodeError|Traceback"` past 24 h.
  - Check the Render `Events` tab for any auto-restart events.

**Top-pick recommendation for the user:** Hypothesis 1 (RAM-during-scan OOM) is by far the most likely. The brief itself notes "we already had OOM cycle on Render Starter — Standard upgrade was the fix" — and `render.yaml:30` still says `plan: starter`. **Confirm the live tier on Render's dashboard first.** If still Starter, the OOM cycle is back; bump to Standard. If Standard, look at the memory chart for high-water marks during scan windows.

## Scheduler health

- **Single-flight lock:** `api.py:103-147` uses `fcntl.flock(LOCK_EX | LOCK_NB)` on `data/scheduler.lock` (POSIX path on Render). Falls back to `msvcrt.locking` on Windows, which is dev-only. On Render this is correct: only one worker per host can acquire the lock. With `--workers 1` (the default in `render.yaml:37`'s start command), there's only one process anyway, but the lock guards against accidental `--workers 2+` regressions. Code is correct.
- **Last completed scan:** `2026-05-05 22:23:55 UTC`; current audit time: `2026-05-05 23:02 UTC`. **39 min since last scan**. Default interval is 30 min (`scheduler.py:61` `DEFAULT_INTERVAL_MINUTES = 30`). Either the scheduler tick is overdue (mildly concerning), or the configured interval is now >30 min (operator change), or the next tick was suppressed by quiet hours. Worth confirming: tail the scheduler log for recent `SCAN STARTED` / `Skipped — quiet hours` lines.
- **Stuck "running" state:** No — `/scan/status` reports `running:false, progress:100.0`. Clean.
- **Feed status:** WS connected; 4 long-tail pairs (FLR/XDC/SHX/ZBCN) marked stale. These are pairs that probably aren't on the primary WS exchange feed; the staleness is expected per the chain. Cosmetic.

## Render log queries the user should run

Paste the to-do block below into Render → Service → Logs → Search:

- [ ] `Out of memory` past 24 h — confirms or rules out H1 (OOM during scan). If hit, Standard tier upgrade or scan-window memory profiling.
- [ ] `Memory cgroup out of memory` past 24 h — kernel-level OOM message; also rules in H1.
- [ ] `Worker .* exiting|Worker .* received signal|SIGKILL|SIGSEGV|signal 11` past 24 h — uvicorn worker death events; rules in H1 or H3.
- [ ] `\[Scheduler\] SCAN STARTED` past 24 h — confirms scheduler is actually running on schedule (last scan was 39 min ago, default is 30, so a tick is overdue).
- [ ] `\[Scheduler\] SCAN COMPLETE` past 24 h — paired with the above; gap = scan duration. If >60 s consistently, that's the GIL-contention window in H2.
- [ ] `Traceback` past 24 h, filtered to lines containing `execution|get_status|load_alerts` — direct hits on H3.
- [ ] `JSONDecodeError|json.decoder` past 24 h — corrupt `alerts_config.json` (H3 verification).
- [ ] `\[ALERTS\]|alerts_config` past 24 h — any config save races during `/execute/status` calls.
- [ ] `502|Bad Gateway|upstream` past 24 h in the **Render proxy logs** (separate tab from app logs) — the proxy-side view of the 502s; cross-correlate timestamps with scheduler ticks.
- [ ] `(uvicorn|Application startup)` past 24 h — counts how many times the worker has restarted; >2-3 in a day is suspicious and rules in H1/H3.
- [ ] `\[Scheduler\] Lock at .* held by another worker` — should be empty on `--workers 1`; if present, means render is silently spawning multiple workers and the single-flight lock is doing its job (and explains nothing about the 502).
- [ ] In the **Metrics** tab: memory utilization sawtooth pattern — peaks right after `SCAN STARTED` log lines? If yes → H1 confirmed.

## Recommended P0 fix order

1. **Confirm tier.** Render dashboard → Service Settings → Instance Type. Brief says Standard, `render.yaml:30` says Starter. If still Starter, **upgrade to Standard now** — that alone will likely close the 502 (and reconcile `render.yaml` to `plan: standard` in the same PR).
2. **Run the Render log query block above** (~5 minutes). Each query either rules a hypothesis in or out. Most likely smoking gun: an `Out of memory` line clustered around `[Scheduler] SCAN STARTED` lines.
3. **Auth-bearing curl matrix from the user's machine.** With `CRYPTO_SIGNAL_API_KEY=<actual-key>` set, run:
   ```bash
   for i in 1 2 3 4 5; do
     curl -sS -o /dev/null -w "call $i  %{http_code}  %{time_total}s\n" \
       -H "X-API-Key: $CRYPTO_SIGNAL_API_KEY" \
       https://crypto-signal-app-1fsi.onrender.com/execute/status
     sleep 1
   done
   # Also one during a known scan window:
   curl -sS -X POST -H "X-API-Key: $CRYPTO_SIGNAL_API_KEY" \
     https://crypto-signal-app-1fsi.onrender.com/scan/trigger
   # Then immediately:
   for i in 1 2 3 4 5 6 7 8 9 10; do
     curl -sS -o /dev/null -w "during-scan $i  %{http_code}  %{time_total}s\n" \
       -H "X-API-Key: $CRYPTO_SIGNAL_API_KEY" \
       https://crypto-signal-app-1fsi.onrender.com/execute/status
     sleep 5
   done
   ```
   If 502s only appear in the during-scan loop, **H1 confirmed** (RAM/GIL pressure during scan).
4. **Throttle topbar polling** as a quick mitigation regardless of root cause. Browser polls `/execute/status` every 5 s. If the problem is intermittent worker stalls during scans, increasing the polling interval to 30 s + adding exponential backoff on 502 will hide most of the user-visible breakage while the root cause is fixed. Frontend change only — no backend modification.
5. **Defer:** if H2 (GIL contention) is the residual cause after H1 is fixed, the cleanest medium-term fix is to peel the scheduler back into its own service (the originally-planned Outcome C, blocked by Render's single-disk-per-service constraint per `render.yaml:21-29`). Workaround: `aiosqlite` + a separate Render Worker tier with shared SQLite via a network filesystem — bigger redesign, not a quick fix.

## Audit gaps (acknowledged)

- No production API key in audit context, so the live 502 cannot be reproduced. The RCA above is a code-path analysis, not a confirmed-by-repro RCA.
- Render application logs and metrics dashboard are not accessible from this audit context. The user must paste the log queries above into the Render UI.
- The /execute/status response when authed-and-failing was not directly observable; the user's report ("persistent 502 every 5 s") is taken at face value.
