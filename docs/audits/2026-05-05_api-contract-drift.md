# Tier 2 — API Contract Drift Sweep

**Date:** 2026-05-05
**OpenAPI fetched from:** https://crypto-signal-app-1fsi.onrender.com/openapi.json
**Methodology:**
1. Fetched live `/openapi.json` (38,092 bytes, 41 paths). FastAPI handlers do not declare `response_model=` so OpenAPI schemas are empty `{}` for every 200 — useless for shape comparison. Used Python source as canonical instead.
2. Enumerated every `apiFetch<T>(...)` in `web/lib/api.ts` and resolved each `T` from `web/lib/api-types.ts`.
3. For each endpoint, located the handler in `api.py` or `routers/*.py` and traced the actual return-statement shape (including the underlying DB function — `db.read_scan_results`, `db.get_backtest_df`, `model.fetch_onchain_metrics`, `exec_engine.get_status`, etc.).
4. Diffed the two shapes for missing fields, name mismatches, type mismatches, and nullability drift. Cross-checked actual UI consumers (`web/app/**/page.tsx`, `web/components/**`, `web/hooks/**`) to grade severity:
   - **P0** — visible on the home page, signals page, or topbar (the always-on surface)
   - **P1** — visible on a secondary page (Backtester, Alerts history, AI Assistant, Settings)
   - **P2** — extra/dead field, no user-facing impact

## Summary

- **Total endpoints inspected:** 27 (every `apiFetch<T>` in `lib/api.ts`)
- **Endpoints with drift:** 9
- **P0 drift (home / signals / topbar):** 4
- **P1 drift (Backtester, Alerts history, AI Assistant, etc.):** 4
- **P2 drift (cosmetic / dead fields):** 1

The single biggest cause of drift is the **scan-results dict** produced by `crypto_model_core.calculate_signal_confidence` (`crypto_model_core.py:4794-4838`). It emits `price_usd` and never sets `change_24h_pct` or top-level `price`. Multiple consumer routers (`/home/summary`, `/signals/{pair}`) read the missing fields back out and pass them through unchanged — so the drift fans out into three pages.

## Drift findings

### `/signals/{pair}` (GET) — P0

- **Frontend expects** (`web/lib/api-types.ts:62-85` `SignalRow`):

  ```ts
  interface SignalRow {
    pair: TradingPair;
    direction: DirectionLabel | string;
    confidence_avg_pct: number | null;
    regime?: RegimeLabel | null;
    regime_label?: RegimeLabel | null;
    high_conf?: boolean;
    price?: number | null;
    price_usd?: number | null;
    change_24h_pct?: number | null;
    mtf_alignment?: number | null;
    risk_mode?: string | null;
    entry?: number | null;
    stop_loss?: number | null;
    exit?: number | null;
    position_size_pct?: number | null;
    rsi?: number | null;
    adx?: number | null;
    macd?: number | null;
    [extra: string]: unknown;
  }
  ```

- **Backend returns** (`api.py:629-644` → `db.read_scan_results()` → row produced at `crypto_model_core.py:4794-4838`, optionally extended at `:4841-4856`):

  Emitted keys: `pair, price_usd, confidence_avg_pct, direction, strategy_bias, mtf_alignment, mtf_confirmed, higher_tf_direction, high_conf, fng_value, fng_category, entry, exit, timeframes, scan_sec, scan_timestamp, circuit_breaker, trending, altcoin_season, regime, sr_status, confluence_count, confluence_pct, dca_multiplier, blood_in_streets, macro_regime, macro_adj_pts, pi_cycle_signal, pi_cycle_active, pi_cycle_gap_pct, signal_flags, wyckoff_*` + (when `risk_info` present) `stop_loss, tp1, tp2, tp3, rr_ratios, leverage_rec, risk_pct, position_size_usd, position_size_pct, risk_mode, corr_with_btc, corr_adjusted_size_pct`.

- **Drift:**
  - **MISSING:** `change_24h_pct` — TS reads it at `web/app/signals/page.tsx:134`. Backend never produces it. Always undefined → "—" in the hero card forever.
  - **MISSING:** top-level `price` — TS reads `detail.price ?? detail.price_usd` (`web/app/signals/page.tsx:138-140`); the `??` fallback masks this, so `price_usd` is what actually gets used. Cosmetic.
  - **NAME DRIFT (cosmetic):** `regime` value is `f"Regime: {regime_1h}"` (literal `"Regime: "` prefix; e.g. `"Regime: Trending"`). `regimeToDisplay()` (`web/lib/format.ts:98`) just lowercases it, so the UI renders `"regime: trending"`. Visible everywhere `regime` is shown — Home hero cards, Signals hero, Regimes summary card.
  - **EXTRA (P2):** Backend emits ~30 keys (wyckoff_*, blood_in_streets, dca_multiplier, pi_cycle_*, macro_adj_pts, …) the TS catch-all `[extra: string]: unknown` accepts but no consumer reads. Wasted bytes on every `/signals` and `/signals/{pair}` response. ~3-5 KB / pair × ~100 pairs in the list response.
- **Severity:** P0 (visible on Home and Signals pages — most-trafficked surface).
- **Suggested fix:**
  1. Add `change_24h_pct` and a top-level `price` (mirror of `price_usd`) to the dict at `crypto_model_core.py:4794`. The 24h-change number already exists upstream — `data_feeds.fetch_24h_ticker` returns it for every pair; thread it through `calculate_signal_confidence` and store. Highest-leverage single fix in this audit.
  2. Strip the `"Regime: "` prefix at the source (`crypto_model_core.py:4816`, `:4854`) — it duplicates the column header on every row and breaks `regimeToDisplay`.

---

### `/signals` (GET, list) — P0

- Same payload as `/signals/{pair}` except wrapped: `{count, results}`. Same row shape, same drift. Consumer: `web/app/signals/page.tsx`, signals list panel.
- Wrapper shape matches TS `SignalsList { count, results }` exactly. **No wrapper drift.**
- Per-row drift identical to `/signals/{pair}` above. Same severity / fix.

---

### `/home/summary` (GET) — P0

- **Frontend expects** (`web/lib/api-types.ts:96-130`):

  ```ts
  interface HeroCard {
    pair: TradingPair;
    direction: DirectionLabel | string | null;
    confidence: number | null;
    regime: RegimeLabel | null;
    high_conf: boolean;
    price: number | null;
    change_24h: number | null;
  }
  ```

- **Backend returns** (`routers/home.py:73-81`):

  ```python
  hero_cards.append({
      "pair":        p,
      "direction":   r.get("direction"),
      "confidence":  r.get("confidence_avg_pct"),
      "regime":      r.get("regime") or r.get("regime_label"),
      "high_conf":   bool(r.get("high_conf", False)),
      "price":       r.get("price"),         # ← ALWAYS None (engine sets price_usd, not price)
      "change_24h":  r.get("change_24h_pct"), # ← ALWAYS None (never set by engine)
  })
  ```

- **Drift:**
  - **NULLABILITY (effectively MISSING):** `price` is read from `r.get("price")` but the engine never sets `"price"` — only `"price_usd"`. **Always `None` for every hero card.** Home hero cards display "—" for price forever.
  - **NULLABILITY (effectively MISSING):** `change_24h` is read from `r.get("change_24h_pct")` but the engine never sets that key. **Always `None`.** Home hero cards' 24h-change cell renders "—" forever.
  - **NAME DRIFT (cosmetic):** `regime` carries the same `"Regime: ..."` prefix as `/signals` — see above.
- **Severity:** P0 — visible on the landing page, in the most prominent UI element (hero cards).
- **Suggested fix:**
  1. Either fix the upstream (recommended — see `/signals` fix above) so `price` and `change_24h_pct` exist on every row, OR
  2. Patch `routers/home.py:73-81` to read `r.get("price_usd")` for `price` (one-line) — quick win that fixes price immediately, but leaves 24h-change broken until upstream fix lands.

---

### `/execute/status` (GET) — P0 (topbar)

- **Frontend expects** (`web/lib/api-types.ts:378-386`):

  ```ts
  interface ExecutionStatus {
    live_trading: boolean;
    keys_configured: boolean;
    agent_running?: boolean;
    paper_balance_usdt?: number;
    open_positions?: number;
    recent_orders?: number;
  }
  ```

- **Backend returns** (`api.py:991-1002` → `execution.py:1150-1160`):

  ```python
  return {
      "ccxt_available":     _CCXT_AVAILABLE,
      "live_trading":       cfg["live_trading"],
      "auto_execute":       cfg["auto_execute"],
      "auto_min_conf":      cfg["auto_min_conf"],
      "keys_configured":    cfg["keys_configured"],
      "default_order_type": cfg["default_order_type"],
  }
  ```

- **Drift:**
  - **MISSING:** `agent_running` — read at `web/components/topbar.tsx:71` (`execQuery.data?.agent_running ?? execQuery.data?.live_trading`) and `web/app/ai-assistant/page.tsx:113`. The topbar masks the gap with `?? live_trading`, so the topbar AGENT pill shows "ON" whenever live-trading is enabled, "OFF" otherwise — independent of whether the scheduler thread is actually alive. The AI Assistant page has no fallback so `apiAgentRunning` is always `false`.
  - **MISSING:** `paper_balance_usdt`, `open_positions`, `recent_orders`. None are consumed today (the catch-all `[extra: string]: unknown` swallows them) but the type comment claims they "drive the AGENT pill in topbar" — misleading.
  - **EXTRA (P2):** `ccxt_available, auto_execute, auto_min_conf, default_order_type` returned but not in the type. Catch-all swallows them.
- **Severity:** P0 for `agent_running` (topbar pill mis-reports agent-thread health), P1 otherwise.
- **Suggested fix:**
  1. In `execution.get_status()`, add `agent_running` (consult `agent.is_running()` or the scheduler thread liveness) and `paper_balance_usdt` (call `get_balance()` cheaply or read paper-mode running balance).
  2. Either drop the unused fields from the TS type or wire them up in the topbar.

---

### `/backtest/trades` (GET) — P1

- **Frontend expects** (`web/lib/api-types.ts:449-452`):

  ```ts
  interface BacktestTradesList {
    count: number;
    trades: BacktestTrade[];
  }
  ```

- **Backend returns** (`api.py:736-741`):

  ```python
  return {
      "total":  total,        # ← TS reads this as `count`, missing
      "offset": offset,
      "limit":  limit,
      "trades": _serialize(page.to_dict(orient="records")),
  }
  ```

- **Drift:**
  - **NAME DRIFT:** Backend says `total`, TS reads `count` (`web/app/backtester/page.tsx:133`). `tradesQuery.data?.count` is **always undefined → 0**. The Backtester page's "n trades" subtitle in every KPI card always shows `n = 0 trades` regardless of actual count.
  - **EXTRA (P2):** `offset`, `limit` — pagination metadata not declared in the TS type. Catch-all accepts them but unused.
- **Severity:** P1 (Backtester page).
- **Suggested fix:** Rename `total` → `count` in `api.py:738` for consistency with every other list endpoint (`/backtest/runs`, `/signals`, `/regimes/`, `/alerts/log`, `/alerts/configure`). One-character diff. No UI dependency on `total` — only `data?.count` is read.

---

### `/alerts/log` (GET) — P1

- **Frontend expects** (`web/lib/api-types.ts:251-266`):

  ```ts
  interface AlertLogRow {
    id?: string | number;
    timestamp?: IsoTimestamp;
    pair?: TradingPair;
    type?: string;
    message?: string;
    channel?: string;
    status?: string;
  }
  interface AlertLog { count: number; alerts: AlertLogRow[]; }
  ```

- **Backend returns** (`api.py:1083-1098` → `db.get_alerts_log_df()` → `alerts_log` table):

  Columns from `database.py:340-349`:
  `sent_at, channel, pair, direction, confidence, status, error_msg`

- **Drift:**
  - **NAME DRIFT (P1):** TS reads `row.timestamp` (`web/app/alerts/history/page.tsx:81`) — backend column is `sent_at`. **Always undefined → every row's timestamp cell shows "—".**
  - **MISSING (P1):** `type` — TS uses it to bucket alerts into colored badges (`web/app/alerts/history/page.tsx:45-71`). Backend has no `type` column; the closest signal is `channel` (e.g. `"email_signal"`, `"tradingview_webhook"`) or `direction` (BUY/SELL). With `type` always undefined, the bucketing logic falls through to the default `"regime"` (neutral teal) for every row. **Every alert badge looks the same.**
  - **NAME DRIFT (P1):** TS reads `row.message` — backend column is `error_msg`. The Alerts history table's free-text `message` column is empty for every successful alert (`error_msg` is only populated on failure).
- **Severity:** P1 (Alerts history page broken at the row level).
- **Suggested fix:**
  - Either rename DB columns (high cost — migration + every other consumer), or
  - Map at the API layer in `api.py:1083-1098`: alias `sent_at → timestamp`, derive `type` from `channel + direction` (e.g. `"buy_signal"` from `direction="BUY"` + `channel="email_signal"`), alias `error_msg → message` (populate with a positive description on success: `"BUY signal sent via email"`).

---

### `/diagnostics/database` (GET) — P1

- **Frontend expects** (`web/lib/api-types.ts:357-373`):

  ```ts
  interface DatabaseHealth {
    tables: { feedback_log, signal_history, backtest_trades, paper_trades,
              positions, agent_log, alerts_log, execution_log };
    backtest_unique_runs: number;
    db_size_kb: number;
    db_size_mb: number;
    wal_mode: boolean;
    auto_vacuum: string;
  }
  ```

- **Backend returns** (`routers/diagnostics.py:269-285`): exact match.

- **Drift:** None on the `tables` map keys / shape.
  - **EXTRA (P2):** `wal_mode` is hard-coded `True` and `auto_vacuum` hard-coded `"nightly"`. Not measured. The Dev-Tools page has no consumer for these today, so the falseness is dormant. Worth flagging for honesty (per the `feedback_empty_states` memory: "truthful empty states") — change to `"unmeasured"` until real PRAGMA reads are wired.

- **Severity:** P2.

---

### `/regimes/` (GET) — Cosmetic regime label drift only

- **Frontend expects** (`web/lib/api-types.ts:135-147`): `RegimesList { count, summary, results: RegimeRow[] }` — exact wrapper match.
- **Backend returns** (`routers/regimes.py:36-84`): matching wrapper.
- **Drift:** Per-row `regime` field carries `"Regime: <label>"` prefix (engine-side, see `/signals`). Summary keys have the literal label without prefix (`Bull, Bear, Sideways, Transition, ...`) because the router seeds them at `:63-67`. Visible mismatch: summary card pill says `Bull` but the row pill below it says `Regime: Bull`.
- **Severity:** P1 (Regimes page header vs row labels visually inconsistent).

---

### `/scan/status` (GET) — Nullability nit

- **Frontend expects** (`web/lib/api-types.ts:510-516`):

  ```ts
  interface ScanStatus { running: boolean; timestamp: IsoTimestamp | null;
    error: string | null; progress: number; pair: string; }
  ```

- **Backend returns** (`api.py:788-794` → `db.read_scan_status` → `database.py:1618-1633`): exact shape; `pair` is `""` when never run, `progress` is `0`, `timestamp` and `error` are `None`. No drift.

- **Drift:** **None.** Listed for completeness.

---

### Endpoints with no drift (verified)

These were inspected and found to match TS types within the catch-all and `??` fallbacks:

| Endpoint | Notes |
|---|---|
| `GET /health` | TS `HealthResponse` has `[extra: string]: unknown` so the wide backend payload (`db, scan, feeds`) is fine. `feed_health.status` is `"OK"|"DEGRADED"|"ERROR"` but TS doesn't constrain it. |
| `POST /scan/trigger` | `{status: "started", message: ...}` matches `ScanTriggerResponse`. |
| `GET /regimes/{pair}/history` | Exact match. |
| `GET /regimes/transitions` | Exact match. |
| `GET /onchain/dashboard` | Exact match (nullable per-metric values). |
| `GET /onchain/{metric}` | Exact match. |
| `GET /alerts/configure` | `{count, rules}` matches. |
| `POST /alerts/configure` | `{status: "created", rule}` matches. |
| `DELETE /alerts/configure/{id}` | `{status: "deleted", id, remaining}` matches. |
| `POST /ai/ask` | `{pair, signal, text, source}` matches; `source: "unavailable"` documented in TS comment. |
| `GET /ai/decisions` | `{count, decisions}` matches. |
| `GET /settings/` | `{trading, signal_risk, dev_tools, execution, all}` matches snake_case. |
| `PUT /settings/{group}` | `{status, applied, rejected, current}` matches. |
| `POST /exchange/test-connection` | `{ok, balance_usdt, error}` matches. |
| `GET /diagnostics/circuit-breakers` | `{all_operational, has_unmeasured, gate_count, gates, last_check}` matches. |
| `POST /execute/order` | All fields match including `client_order_id`, `idempotent_replay`, `slippage_pct`, `fee_usd`, `effective_usd`. TS allows `mode: "dry_run"|"aborted_emergency_stop"` which Python never emits — over-broad, harmless. |
| `GET /backtest/summary` | Exact match. |
| `GET /backtest/runs` | `{count, runs}` matches (note: contrasts with `/backtest/trades` `total`). |
| `GET /backtest/arbitrage` | `{count, opportunities}` matches; row columns from `arb_opportunities` table line up with `ArbitrageOpportunity`. |

---

### Endpoints exposed by backend but never called by frontend

These appear in `/openapi.json` but no `apiFetch<T>` references them. Listed for completeness — not drift:

`/`, `/positions`, `/paper-trades`, `/weights`, `/weights/history`, `/execute/balance`, `/execute/log`, `/signals/history`, `/prices/live`, `/prices/live/{pair}`, `/webhook/tradingview`, `/backtest` (legacy unwrapped — `/backtest/summary` is what the frontend uses).

If a future page wires these, audit their shape before consuming.

---

## Recommended P0 fix order

1. **`crypto_model_core.py:4794`** — add `change_24h_pct` and a top-level `price` to the per-pair scan result dict. Highest leverage: fixes Home hero cards' price + 24h, fixes Signals hero card's 24h, fixes Signals list table's price/change columns, eliminates the always-`None` reads in `routers/home.py:80`.
2. **`crypto_model_core.py:4816, 4854`** — strip the `"Regime: "` prefix from the `regime` value (or have `routers/regimes.py` and `routers/home.py` strip it on read). Fixes the lowercase `"regime: trending"` rendered on Home, Signals, Regimes pages.
3. **`execution.py:1150-1160`** (`get_status`) — add `agent_running` (scheduler-thread liveness) and ideally `paper_balance_usdt`. Topbar AGENT pill becomes truthful instead of mirroring `live_trading`.
4. **`api.py:738`** — rename `total` → `count` on `/backtest/trades`. One-line diff. Fixes Backtester page subtitles "n = 0 trades" forever.
5. **`api.py:1083-1098`** — alias `sent_at → timestamp`, `error_msg → message`, derive `type` from `channel + direction` for `/alerts/log` rows. Fixes Alerts history page rendering.
6. **`routers/regimes.py:84`** — strip `"Regime: "` prefix on read so summary keys and row labels agree (depends on #2 — if #2 fixes the source, this is unnecessary).

P0 fixes #1-3 are the only ones visible on the always-on home/signals/topbar surface. P1 fixes #4-6 are the secondary-page polish.

## Closing the test gap

The current `web/tests/api-contract.test.ts` only verifies endpoint paths exist. To close the shape-level gap that produced this audit:

- **Option A (cheap):** Extend the existing test with a per-endpoint smoke fetch that checks a hand-picked subset of required fields exists on the live response (e.g. `GET /home/summary` must return `hero_cards: array, info_strip.scan_progress: number`). Catches name drift (`total` vs `count`) but won't catch always-null values.
- **Option B (better):** Add `response_model=` Pydantic models to every FastAPI handler (`api.py` + every router) so OpenAPI emits real schemas. Then auto-generate TS types from `/openapi.json` (e.g. `openapi-typescript`) into a separate file and have CI fail when the generated file disagrees with the hand-written `api-types.ts`. One-time migration, eliminates this whole audit category.
- **Option C (expensive but bulletproof):** Replace hand-written `api-types.ts` entirely with the auto-generated file from B; ban hand-edits via lint.

B is the recommended path — existing handlers are mostly free of side effects in the response shape, and Pydantic models would make `_serialize()` redundant.
