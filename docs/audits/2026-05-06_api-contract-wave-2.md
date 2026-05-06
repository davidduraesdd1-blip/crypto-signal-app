# Tier 2 — API Contract Drift Sweep, Wave 2

**Date:** 2026-05-06
**Worktree:** `.claude/worktrees/exciting-lovelace-60ae5b`
**OpenAPI fetched from:** `https://crypto-signal-app-1fsi.onrender.com/openapi.json` (43 paths, 39,317 bytes — 2 new since Wave 1: `/diagnostics/feeds`, `/signals/history`)
**Mode:** read-only audit. No code changed.
**Methodology:**
1. Re-fetched live `/openapi.json`. Same finding as Wave 1: **zero** handlers declare `response_model=` (verified by `Grep "response_model" *.py` → no matches), so OpenAPI body schemas remain `{}`. Python source (`api.py`, `routers/*.py`, `database.py`, `crypto_model_core.py`, `execution.py`) is the canonical contract.
2. Re-validated the 9 Wave 1 findings against current main (`0e7ef9d` → HEAD).
3. Walked every consumer that drills into `/signals/{pair}` (the entire `web/app/signals/page.tsx` prop-passing chain) against the ground-truth response captured 2026-05-06 04:30 UTC.
4. Searched `web/` for every `.toFixed(`, `.toLocaleString(`, and arithmetic on API-derived values to enumerate the type-drift bug class that produced the daily_signals crash.
5. Searched `web/` for every `detail.X` field read where X is not a top-level engine emit (the new "nested-field drift" class).

## Wave 1 verification — 9-row table

| # | Wave 1 finding | Status now | Evidence |
|---|---|---|---|
| W1-1 | `/signals/{pair}` missing `change_24h_pct` + top-level `price` | **FIXED** | `crypto_model_core.py:4850-4854` now emits `price`, `price_usd`, `change_24h_pct`, `change_30d_pct`, `change_1y_pct`. Frontend `web/app/signals/page.tsx:241-243` reads them through. Confirmed in ground-truth `/signals/BTC-USDT` payload — all four present. |
| W1-2 | `/signals` list rows — same shape gap | **FIXED** (consequence of W1-1) | Same dict source per row. |
| W1-3 | `/home/summary` hero cards always-null `price` + `change_24h` | **FIXED upstream** | `routers/home.py:79-80` reads `r.get("price")` and `r.get("change_24h_pct")`; engine now emits both. Wave 1 hot-path neutralized. |
| W1-4 | `/execute/status` missing `agent_running` | **STILL PRESENT** | `execution.py:1150-1160` `get_status()` body unchanged. Topbar (`components/topbar.tsx:40`) still falls back to `live_trading`; AI Assistant page (`app/ai-assistant/page.tsx:114`) still receives `undefined`. **P0** — see new finding W2-N1 below. |
| W1-5 | `/backtest/trades` returns `total`, frontend reads `count` | **STILL PRESENT** | `api.py:737` returns `"total": total`. Frontend (`app/backtester/page.tsx:133`) `tradesQuery.data?.count` is always undefined → "last N of 0". **P1** — see W2-N2. |
| W1-6 | `/alerts/log` `sent_at`/`error_msg`/no `type` vs frontend `timestamp`/`message`/`type` | **STILL PRESENT** | `api.py:1083-1098` returns raw DB columns; `database.py:340-349` schema unchanged. Frontend (`app/alerts/history/page.tsx:81-87`) renders empty timestamps and identical `regime`-bucket badges for every row. **P1** — see W2-N3. |
| W1-7 | `/diagnostics/database` `wal_mode`/`auto_vacuum` hard-coded | **STILL PRESENT (P2)** | `routers/diagnostics.py:289-290` still `True` / `"nightly"`. Dormant — Dev Tools page doesn't render either field. |
| W1-8 | `/regimes/` per-row `regime: "Regime: Bull"` prefix vs summary keys `Bull` | **STILL PRESENT** | `crypto_model_core.py:4874` emits `'regime': f"Regime: {regime_1h}"`. `routers/regimes.py:72,77,79` passes through verbatim into both `summary` and per-row `regime`. Per-row prefix is preserved; summary buckets the prefixed string under `regime` key (line 76: `summary[state] = summary.get(state, 0) + 1`) — so summary now contains a `"Regime: Bull"` bucket that the seeded `Bull` bucket never receives. **REGRESSION risk:** the seeded `{Bull: 0, Bear: 0, …}` dict at routers/regimes.py:63-67 will all read 0; new bucket keys `"Regime: Bull"` etc. spawn dynamically. Frontend (`app/regimes/page.tsx:131-138`) calls `toRegimeState(row.regime)` which lowercases → `"regime: bull"` then `l.includes("bull")` returns true so the card shows correctly — but the regime-summary header card on the same page reads `regimesQuery.data.summary` which now contains `Regime: Bull: N` keys not in the v0 expected set. **P1** (cosmetic + summary card mis-bucket). |
| W1-9 | `/scan/status` shape — no drift | **CONFIRMED no drift** | `database.py:1618-1633` shape unchanged. |

**Net result:** 3 of 9 Wave 1 findings closed (W1-1, W1-2, W1-3). 5 still open and re-listed below with current line numbers. 1 confirmed clean (W1-9).

---

## New findings (Wave 2)

### W2-N1 — Nested-field drift class (NEW CLASS) — P0

The engine emits per-pair indicator fields under `timeframes['1h']`, `timeframes['4h']`, etc. The frontend reads them at the **top level** of the `/signals/{pair}` response. This was hidden during Wave 1 because every nested field was rendering as `—` (the data was effectively empty), but with Wave 1's data fixes landing, a future engine emit at the top level of `result` would *correctly* surface — and right now there's nothing.

#### Confirmed sites — `detail.X` reads where X is NOT a top-level engine emit

Ground-truth `/signals/BTC-USDT` (2026-05-06 04:30 UTC) shows: top-level keys are `pair, price_usd, price, change_*_pct, confidence_avg_pct, direction, strategy_bias, mtf_alignment, mtf_confirmed, higher_tf_direction, high_conf, fng_*, entry, exit, timeframes, scan_*, trending, altcoin_season, regime, sr_status, confluence_*, dca_multiplier, blood_in_streets, macro_*, pi_cycle_*, signal_flags, wyckoff_*, stop_loss, tp1, tp2, tp3, position_size_*, risk_mode, corr_*, tier`. **Notable absences at top level:** `rsi`, `macd`, `macd_hist`, `adx`, `stoch`, `vwap`, `ichimoku`, `fib_closest`, `supertrend`. All of those live under `timeframes['1h']` (and the other 4 TFs).

| File:line | Field read at wrong depth | Should be |
|---|---|---|
| `web/app/signals/page.tsx:327` | `detail.rsi` | `detail.timeframes?.['1h']?.rsi` |
| `web/app/signals/page.tsx:328` | `detail.macd` | `detail.timeframes?.['1h']?.macd_div` (engine emits `macd_div` string like `"Bearish (regular) (Strong)"`, not a numeric `macd`) |
| `web/app/signals/page.tsx:329` | `detail.adx` | `detail.timeframes?.['1h']?.adx` |
| `web/lib/api-types.ts:81-83` | `SignalRow.rsi`/`adx`/`macd` declared as top-level optional fields | Either move into a nested `timeframes` typed shape or declare as `never` in the SignalRow interface and only read via `detail.timeframes['1h']` |

**User-visible impact:** The Signals page Technical-Indicator tile strip ("RSI (14)", "MACD", "Supertrend", "ADX (14)") shows `—` for RSI, MACD, ADX on every pair. Subtext labels degrade to "unavailable" for all three (every variant matches `isMissing(rsi)`). Users see **three of four technical-tile cells permanently dashed** even when the engine has the values.

**Severity rationale:** P0 because Signals page is a top-3 surface and these cells are the canonical UI for "what's the technical state right now?" — every Beginner/Intermediate user looks here.

#### Spec-supplied indicator fields (engine confirmed non-existent at top level)

These types exist in `api-types.ts` but the engine does not now and never has emitted them at the top level. The catch-all `[extra: string]: unknown` permits the read without a TS error, so they look like a wired contract but aren't:

- `SignalRow.rsi` (api-types.ts:81)
- `SignalRow.adx` (api-types.ts:82)
- `SignalRow.macd` (api-types.ts:83)

Recommendation in §"P0 fixes" below.

---

### W2-N2 — Numeric-vs-string drift sites (NEW CLASS) — bug-class enumeration

The Wave 1 hotfix landed `_toFiniteNumber` and `_toCleanString` only inside `web/app/signals/page.tsx:125-136`. Outside that file, every `.toFixed(` / `.toLocaleString(` / `(numeric op)` on an API-derived value is a candidate. Below is every site.

| File:line | Call | Coercion present? | Drift risk |
|---|---|---|---|
| `web/components/composite-score.tsx:23` | `score.toFixed(1)` on prop | parent (`signals/page.tsx:309`) coerces via `_toFiniteNumber ?? 0`. Safe **only** through that consumer. **HIGH risk** if any future caller passes the raw API value. |
| `web/components/decisions-table.tsx:62` | `total.toLocaleString()` | `app/ai-assistant/page.tsx:123` does `decisionsQuery.data?.count ?? decisions.length`. `count` comes straight from the API response (`api.py:124` → `len(df)`, always int). **Safe** — but only because the backend never drifts. No defensive coercion. |
| `web/components/agent-config-card.tsx:40` | `value.toLocaleString()` on `SliderField` value prop | Visual-only (no API source). Safe. |
| `web/components/regime-weights.tsx:61,65,69,73` | `(col.weights.tech * 100).toFixed(0)` | Hardcoded mock weights in `app/regimes/page.tsx:98-119`. Safe today, but if the page wires to a future `/weights` API the structure can drift. **MEDIUM** when wired. |
| `web/app/settings/execution/page.tsx:42` | `value.toLocaleString()` on local `useState<number>` | Local state only. Safe. |
| `web/app/settings/execution/page.tsx:340` | `testResult.balance_usdt.toLocaleString(...)` | **NOT GUARDED.** TS type `ExchangeTestConnection.balance_usdt: number` (api-types.ts:331); `routers/exchange.py:64` does have a fallback `"balance_usdt": 0.0` but if `exec_engine.test_connection()` returns `None`/string for `balance_usdt` (e.g. on partial CCXT failure), `.toLocaleString` crashes the page. **MEDIUM** — happens only on a degraded backend. |
| `web/app/settings/signal-risk/page.tsx:45` | `value.toLocaleString()` on local `useState<number>` | Local state only. Safe. |
| `web/app/ai-assistant/page.tsx:35` | `Math.round(r.confidence_avg_pct ?? 0)` | Coerces null but **not strings**. `r.confidence_avg_pct` typed `number \| null` from `AiDecision`, but the upstream is `pd.read_sql_query` (database.py:1284), which can deliver a string if `daily_signals.confidence_avg_pct` was written as text by an older engine. `Math.round("85.2")` returns `NaN`; the `confidence: NaN` then prints `NaN%` in the table cell. **LOW** — defensive coercion absent. |
| `web/app/ai-assistant/page.tsx:69` | `d.toLocaleString("en-US", {...})` on `Date` instance | Not API-derived. Safe. |
| `web/app/signals/page.tsx:104,176,272,312` | All inside `_toFiniteNumber`-guarded paths | Safe (Wave 1 hotfix). |
| `web/lib/format.ts:44,63` | `Number(value).toLocaleString(...)`, `v.toFixed(d)` | `formatNumber` and `formatPct` both call `isMissing(v)` at line 42/60 first which catches `null`, `undefined`, `NaN`, and string-flavors of those. **Safe.** Wave 1 H4 fix verified. |
| `web/components/ui/chart.tsx:237` | `item.value.toLocaleString()` | Inside Recharts internals — depends on chart data source. The chart isn't wired to live API data on any page (verified). Safe today. |
| `web/components/ui/calendar.tsx:40` | `date.toLocaleString('default', ...)` on Date instance | Not API-derived. Safe. |

**Bug-class summary:**
- **One genuine drift hazard found:** `web/app/settings/execution/page.tsx:340` calls `.toLocaleString` on `testResult.balance_usdt` without `isMissing` / `_toFiniteNumber` coercion. Guard is needed if backend returns null/undefined under partial-CCXT-failure conditions.
- **One latent hazard:** `decisions-table.tsx:62` is safe today but not defensively coerced — any future change to upstream `count` shape could crash the table.
- **One incomplete coercion:** `app/ai-assistant/page.tsx:35` Math.round-on-null but not string.

The Wave 1 `_toFiniteNumber` / `_toCleanString` helpers should be **promoted to `web/lib/format.ts`** (currently duplicated only inside signals/page.tsx) so every page can adopt the same defensive pattern.

---

### W2-N3 — `SignalRow` TS type carries fields the engine never emits at top level (response-shape stability) — P1

`web/lib/api-types.ts:62-87` declares optional `rsi`, `adx`, `macd` on `SignalRow`. Since Wave 1, the engine *does* now emit `change_30d_pct` / `change_1y_pct` / `price` at top level (P0-3 fix). The TS type acknowledges those (api-types.ts:72-73 + comment). Good.

But the type does **not** currently declare:
- `timeframes` — the actual nested indicator container (used at signals/page.tsx:284)
- `wyckoff_phase, wyckoff_conf, wyckoff_desc, wyckoff_plain, wyckoff_spring, wyckoff_upthrust` (engine emits all six)
- `pi_cycle_signal, pi_cycle_active, pi_cycle_gap_pct` (engine emits)
- `confluence_count, confluence_pct, dca_multiplier, blood_in_streets` (engine emits)
- `macro_regime, macro_adj_pts` (engine emits)
- `tp1, tp2, tp3, rr_ratios, leverage_rec, risk_pct, position_size_usd, corr_with_btc, corr_adjusted_size_pct, tier` (engine emits in `risk_info` branch)
- `strategy_bias, mtf_confirmed, higher_tf_direction, fng_value, fng_category, scan_sec, scan_timestamp, sr_status, signal_flags, trending, altcoin_season, circuit_breaker` (engine emits)

All of these flow through the catch-all `[extra: string]: unknown` (api-types.ts:86), so reads compile. But a future page that wants to render Wyckoff phase or macro adjustment loses IDE autocomplete and gets `unknown` typed values requiring a cast at every site. **The catch-all is masking the real shape from the consumer.**

Severity P1 because no current page consumes them — but the prompt explicitly asked: "any TS types that should be expanded to acknowledge the new fields."

**Suggested type expansion** (api-types.ts:62-87):
```ts
export interface TimeframeFrame {
  confidence: number | null;
  direction: string | null;
  volume_passed?: boolean;
  rsi?: number | null;
  stoch?: string | null;
  adx?: number | null;
  vwap?: number | null;
  ichimoku?: string | null;
  fib_closest?: string | null;
  macd_div?: string | null;
  supertrend?: string | null;
  sr_status?: string | null;
  [extra: string]: unknown;
}

export interface SignalRow {
  // ... existing fields ...
  timeframes?: Partial<Record<"1h"|"4h"|"1d"|"1w"|"1M", TimeframeFrame>>;
  // explicit acknowledgment of engine-emitted top-level fields:
  strategy_bias?: string;
  mtf_confirmed?: boolean;
  higher_tf_direction?: string | null;
  fng_value?: number | null;
  fng_category?: string;
  scan_sec?: number;
  scan_timestamp?: string;
  trending?: boolean;
  altcoin_season?: string;
  sr_status?: string;
  confluence_count?: number;
  confluence_pct?: number;
  dca_multiplier?: number;
  blood_in_streets?: string;
  macro_regime?: string;
  macro_adj_pts?: number;
  pi_cycle_signal?: string;
  pi_cycle_active?: boolean;
  pi_cycle_gap_pct?: number;
  signal_flags?: string[];
  wyckoff_phase?: string;
  wyckoff_conf?: number;
  wyckoff_desc?: string;
  wyckoff_plain?: string;
  wyckoff_spring?: boolean;
  wyckoff_upthrust?: boolean;
  tp1?: number | null;
  tp2?: number | null;
  tp3?: number | null;
  rr_ratios?: unknown;
  leverage_rec?: unknown;
  risk_pct?: number;
  position_size_usd?: number;
  corr_with_btc?: number | null;
  corr_adjusted_size_pct?: number;
  tier?: number;
  // remove these (they are NOT top-level — see W2-N1):
  // rsi, adx, macd
}
```

---

### W2-N4 — `/ai/decisions` — `rationale` field never emitted by backend — P1

**Backend** (`routers/ai_assistant.py:112-124`): returns rows from `db.get_signals_df()` which queries the `daily_signals` table. Schema (`database.py:227-253`) has columns `scan_timestamp, pair, price_usd, confidence_avg_pct, direction, strategy_bias, mtf_alignment, high_conf, fng_value, fng_category, entry, exit, stop_loss, risk_pct, position_size_usd, position_size_pct, risk_mode, corr_with_btc, corr_adjusted_size_pct, regime, sr_status, circuit_breaker_*, scan_sec`. **No `rationale` column.**

**Frontend** (`web/app/ai-assistant/page.tsx:42`): `if (typeof r.rationale === "string") rationale = r.rationale;`. The check guards against a missing field, so no crash — but the conditional **never fires**. The user always sees the auto-derived `Direction: BUY, confidence 78%` placeholder, never the actual Claude rationale.

The actual `claude_rationale` lives in the `agent_log` table (`database.py:371-382`, populated by `agent.py:971`). The `/ai/decisions` endpoint reads the wrong table.

**Severity P1.** AI Assistant page becomes accurate: same content, no false promise.

**Fix:** either (a) change `routers/ai_assistant.py:112` to read `agent_log` instead, JOINing on pair + nearby timestamp; or (b) join the two tables; or (c) remove `rationale` from the auto-fallback message and the `AiDecision.rationale?` field on the TS side, plus the no-op `typeof === "string"` check.

---

### W2-N5 — `/regimes/` summary buckets mis-keyed when engine prefixes `"Regime: "` — P1

**Backend** (`routers/regimes.py:72-76`):
```python
state = _extract_regime(r) or "Unknown"
summary[state] = summary.get(state, 0) + 1
```
With the engine emitting `"Regime: Trending"` (crypto_model_core.py:4874), `state` is `"Regime: Trending"` not `"Trending"`. The seeded summary dict (`{Bull: 0, Bear: 0, Sideways: 0, Transition: 0, Trending: 0, Ranging: 0, Neutral: 0, Unknown: 0}`) gets a *new* dynamic key `"Regime: Trending"` while the seeded `Trending` stays at 0 forever.

**Frontend** (`web/app/regimes/page.tsx:140`): `regimesQuery.data?.count` works, but no consumer iterates `summary`. The summary card is dead-mock for now (lines 36-119 are hardcoded). When wired, the v0 expected keys (`Bull, Accumulation, Distribution, Bear`) won't match either the seeded keys OR the prefix-keyed buckets. Latent bug.

Also impacted: the row-level `regime` value in every `RegimeRow` carries the prefix — `routers/regimes.py:79` — so `regimeToDisplay()` produces `"regime: bull"` lower-cased, which renders verbatim in `app/regimes/page.tsx`'s eventual summary header text and on Home hero cards / Signals hero per Wave 1 finding W1-8.

**Suggested single-edit fix:** strip the prefix at engine source:
```python
# crypto_model_core.py:4874
'regime': regime_1h,  # was: f"Regime: {regime_1h}"
```
Closes Wave 1 W1-8 + Wave 2 W2-N5 in one line.

---

### W2-N6 — `/execute/status` still missing `agent_running` — P0 (re-statement)

`execution.py:1150-1160` `get_status()` returns 6 keys, none of them `agent_running`. The Topbar (`components/topbar.tsx:40`) and AI Assistant (`app/ai-assistant/page.tsx:114`) both read it. **Topbar has a `?? live_trading` fallback so the pill is wrong-but-non-crashing.** AI Assistant has no fallback so `apiAgentRunning` is permanently `false` and the local `setRunning(apiAgentRunning)` effect (lines 116-118) keeps the local toggle in sync at `false`.

**User-visible:** Topbar AGENT pill mirrors live_trading state instead of scheduler-thread liveness. AI Assistant AGENT card always shows "Stopped" on first load.

**Fix:** In `execution.get_status()` add:
```python
"agent_running": exec_engine._agent_thread is not None and exec_engine._agent_thread.is_alive(),
"paper_balance_usdt": _PAPER_BALANCE_USDT_RUNNING,  # if available
```
Roughly 4 lines.

---

### W2-N7 — `/backtest/trades` `total` vs `count` (re-statement) — P1

Wave 1 finding still present at `api.py:737`. One-character fix: `"total": total` → `"count": total`. Frontend reads `tradesQuery.data?.count` (`app/backtester/page.tsx:133`), so changing the backend key restores the "last N of M" subtitle.

---

### W2-N8 — `/alerts/log` field-name drift (re-statement) — P1

Wave 1 finding still present. `api.py:1083-1098` returns the raw `alerts_log` columns (`sent_at, channel, pair, direction, confidence, status, error_msg`). Frontend (`app/alerts/history/page.tsx:80-87`) reads `row.timestamp` (always undefined → "—" rendered), `row.type` (always undefined → bucketed as `"regime"` neutral teal for every row), `row.message` (reads `error_msg`, empty for non-failed alerts).

**Fix in `api.py:1095-1097`:** map columns at the API boundary:
```python
def _map_alert_row(r: dict) -> dict:
    direction = (r.get("direction") or "").upper()
    return {
        "timestamp": r.get("sent_at"),
        "pair":      r.get("pair"),
        "channel":   r.get("channel"),
        "status":    r.get("status"),
        "direction": direction,
        "type":      "buy" if "BUY" in direction else "sell" if "SELL" in direction else "regime",
        "message":   r.get("error_msg") or f"{direction or 'Alert'} signal sent via {r.get('channel') or 'email'}",
    }
return {"count": len(df), "alerts": [_map_alert_row(r) for r in df.tail(limit).to_dict(orient="records")]}
```

---

### W2-N9 — `/diagnostics/feeds` (NEW endpoint) — wired backend, NO frontend consumer — P2

`routers/diagnostics.py:294-413` — fully implemented (probes 8 feeds: Kraken, Gate.io, Bybit, MEXC, OKX-geo-blocked, CoinGecko, alternative.me, FRED). Cached 60s. Returns `{generated_at, cached, render_region, feeds: [...], summary: {ok, warn, unreachable, total}}`.

**Frontend:** zero references. `Grep "diagnostics/feeds|getFeeds"` in `web/` — only matches are this audit + the existing `data-feed-liveness` audit doc + a comment in `signals/page.tsx`. The Dev Tools page (`app/settings/dev-tools/page.tsx`) is the natural home. The endpoint is dead-wired today.

**Suggested:** add `GET /diagnostics/feeds` to `lib/api.ts`, type the response, and render a per-feed status strip in `app/settings/dev-tools/page.tsx` below the "Database health" card. ~30 lines of TS.

---

### W2-N10 — `Watchlist` component (Home page) is 100% mock — P1 (latent / not "drift" but worth noting)

`web/app/page.tsx:51-99` and `web/components/watchlist.tsx` — sparkline points + prices + tickers all hardcoded. `useHomeSummary` carries the right pairs (top 5 by scan order) but the 6-row Watchlist card is detached. When this gets wired, the `price`, `change`, `sparklinePoints` props will need to be derived from `/signals` or a new `/signals/{pair}/sparkline` endpoint — flag for the type-check pass when that lands.

---

## Bug-class summary

### A. Nested-field reads (CRITICAL — 3 confirmed sites, all in `web/app/signals/page.tsx`)

The frontend reads engine indicator fields at the wrong depth (`detail.rsi/adx/macd` instead of `detail.timeframes['1h'].rsi/adx/macd_div`). Result: three of the four Technical-Indicator tiles permanently dashed.

**Locations:**
- `web/app/signals/page.tsx:327` — `detail.rsi`
- `web/app/signals/page.tsx:328` — `detail.macd`
- `web/app/signals/page.tsx:329` — `detail.adx`

The Wave 1 type declaration (`api-types.ts:81-83`) suggested these fields existed at the top level, masking the bug from TypeScript. **Recommend removing those three fields from `SignalRow` and adding the `timeframes` typed shape (W2-N3).**

### B. Numeric-vs-string call sites missing defensive coercion (1 confirmed hazard, 1 latent)

`web/app/settings/execution/page.tsx:340` is the only outside-Wave-1 site with material risk: `testResult.balance_usdt.toLocaleString(...)` runs without `isMissing` / `_toFiniteNumber`. If the upstream returns null/undefined on degraded CCXT, the page crashes.

`web/components/decisions-table.tsx:62` is safe through the current consumer but defensively un-coerced.

`web/lib/format.ts:formatNumber` / `formatPct` are correctly guarded — Wave 1 H4 holds. **Recommend promoting `_toFiniteNumber` and `_toCleanString` from signals/page.tsx into `lib/format.ts`** so every consumer can opt in.

### C. Missing `response_model=` on every FastAPI route (CONFIRMED 0 declarations)

`Grep response_model *.py` matches **nothing**. OpenAPI 200 schemas all `{}`. This is the root cause of every drift in this audit — there is no contract surface for CI to enforce.

**Mapping of every endpoint to the TS type it should resolve to:**

| Endpoint | File:line of handler | Suggested `response_model=` | Maps to TS type |
|---|---|---|---|
| `GET /` | api.py:505 | `RootInfo` (new) | (none — minor) |
| `GET /health` | api.py:515 | `HealthResponse` (mirror api-types.ts:496) | `HealthResponse` |
| `GET /signals` | api.py:563 | `SignalsList` | `SignalsList` |
| `GET /signals/history` | api.py:597 | `SignalHistoryResponse` (mirror api.ts:298) | `SignalHistoryResponse` |
| `GET /signals/{pair}` | api.py:623 | `SignalRow` | `SignalRow` |
| `GET /positions` | api.py:649 | `PositionsList` (new) | (none today) |
| `GET /paper-trades` | api.py:661 | `PaperTradesList` (new) | (none today) |
| `GET /backtest` | api.py:687 | `BacktestLegacyResponse` (new) | (none today) |
| `GET /backtest/trades` | api.py:718 | `BacktestTradesList` (after `total`→`count` rename) | `BacktestTradesList` |
| `GET /backtest/runs` | api.py:744 | `BacktestRunsList` | `BacktestRunsList` |
| `GET /weights` | api.py:760 | `WeightsResponse` (new) | (none today) |
| `GET /weights/history` | api.py:772 | `WeightsHistory` (new) | (none today) |
| `GET /scan/status` | api.py:788 | `ScanStatus` | `ScanStatus` |
| `POST /scan/trigger` | api.py:797 | `ScanTriggerResponse` | `ScanTriggerResponse` |
| `POST /webhook/tradingview` | api.py:829 | (any) | (none — webhook only) |
| `GET /prices/live` | api.py:937 | `LivePricesAll` (new) | (none today) |
| `GET /prices/live/{pair}` | api.py:964 | `LivePrice` (new) | (none today) |
| `GET /execute/status` | api.py:991 | `ExecutionStatus` (after adding `agent_running`) | `ExecutionStatus` |
| `GET /execute/balance` | api.py:1005 | `ExchangeBalance` (new) | (none today) |
| `POST /execute/order` | api.py:1026 | `PlaceOrderResponse` | `PlaceOrderResponse` |
| `GET /execute/log` | api.py:1063 | `ExecutionLog` (new) | (none today) |
| `GET /alerts/log` | api.py:1083 | `AlertLog` (after column-rename mapper) | `AlertLog` |
| `GET /home/summary` | routers/home.py:29 | `HomeSummary` | `HomeSummary` |
| `GET /regimes/` | routers/regimes.py:31 | `RegimesList` | `RegimesList` |
| `GET /regimes/{pair}/history` | routers/regimes.py:87 | `RegimeHistory` | `RegimeHistory` |
| `GET /regimes/transitions` | routers/regimes.py:117 | `RegimeTransitions` | `RegimeTransitions` |
| `GET /onchain/dashboard` | routers/onchain.py:56 | `OnchainDashboard` | `OnchainDashboard` |
| `GET /onchain/{metric}` | routers/onchain.py:74 | `OnchainMetric` | `OnchainMetric` |
| `GET /alerts/configure` | routers/alerts.py:80 | `AlertRulesList` | `AlertRulesList` |
| `POST /alerts/configure` | routers/alerts.py:90 | `AlertRuleCreated` | `AlertRuleCreated` |
| `DELETE /alerts/configure/{rule_id}` | routers/alerts.py:132 | `AlertRuleDeleted` | `AlertRuleDeleted` |
| `POST /ai/ask` | routers/ai_assistant.py:48 | `AskAiResponse` | `AskAiResponse` |
| `GET /ai/decisions` | routers/ai_assistant.py:100 | `AiDecisionsList` | `AiDecisionsList` |
| `GET /settings/` | routers/settings.py:281 | `SettingsSnapshot` | `SettingsSnapshot` |
| `PUT /settings/trading` | routers/settings.py:323 | `SettingsPutResponse` | `SettingsPutResponse` |
| `PUT /settings/signal-risk` | routers/settings.py:333 | `SettingsPutResponse` | `SettingsPutResponse` |
| `PUT /settings/dev-tools` | routers/settings.py:343 | `SettingsPutResponse` | `SettingsPutResponse` |
| `PUT /settings/execution` | routers/settings.py:353 | `SettingsPutResponse` | `SettingsPutResponse` |
| `POST /exchange/test-connection` | routers/exchange.py:28 | `ExchangeTestConnection` | `ExchangeTestConnection` |
| `GET /diagnostics/circuit-breakers` | routers/diagnostics.py:212 | `CircuitBreakersResponse` | `CircuitBreakersResponse` |
| `GET /diagnostics/database` | routers/diagnostics.py:246 | `DatabaseHealth` | `DatabaseHealth` |
| `GET /diagnostics/feeds` | routers/diagnostics.py:371 | `FeedsHealthResponse` (new) | (need to add to api-types.ts) |
| `GET /backtest/summary` | routers/backtest.py:100 | `BacktestSummary` | `BacktestSummary` |
| `GET /backtest/arbitrage` | routers/backtest.py:114 | `ArbitrageList` | `ArbitrageList` |

**Total endpoints needing `response_model=`:** 43.
**Already-typed on the TS side:** 28 endpoints map directly to existing api-types.ts interfaces.
**Need new TS types:** 15 (the never-consumed endpoints — `/positions`, `/paper-trades`, `/weights`, `/weights/history`, `/execute/balance`, `/execute/log`, `/prices/live`, `/prices/live/{pair}`, `/backtest` legacy, `/diagnostics/feeds`, `/`, etc.).

**Highest-leverage subset to add `response_model=` on first** (already-typed, drives the entire visible UI): `/health`, `/signals`, `/signals/{pair}`, `/signals/history`, `/scan/status`, `/scan/trigger`, `/home/summary`, `/regimes/`, `/regimes/{pair}/history`, `/regimes/transitions`, `/onchain/dashboard`, `/onchain/{metric}`, `/alerts/configure`, `/alerts/log`, `/ai/ask`, `/ai/decisions`, `/settings/`, `/settings/{group}` (×4), `/exchange/test-connection`, `/diagnostics/*`, `/backtest/*`, `/execute/status`, `/execute/order`. **27 endpoints. ~1 line each + minor Pydantic model definition.**

---

## `/signals/{pair}` deep dive — every prop drilled into a child component

Tracing every consumer in `web/app/signals/page.tsx` against the ground-truth response.

### Hero card (`<SignalHero {...heroData} />` at line 448)

`heroData` built at lines 221-275. Each field:

| heroData prop | Source field on `detail` | In ground-truth response? | Issue |
|---|---|---|---|
| `ticker` | `detail.pair` | ✓ `"BTC/USDT"` | none |
| `name` | `detail.pair.split("/")[0]` | ✓ | none |
| `price` | `detail.price ?? detail.price_usd` | ✓ both `81463.5` | none (Wave 1 fixed) |
| `change24h` | `detail.change_24h_pct` | ✓ `0.68` | none (Wave 1 fixed) |
| `change30d` | `detail.change_30d_pct` (cast) | ✓ `18.24` | none (P0-3 fixed) |
| `change1y` | `detail.change_1y_pct` (cast) | ✓ `null` (truthful — short history) | none |
| `signal` | `directionToSignalType(detail.direction)` | ✓ `"HOLD"` | none |
| `signalStrength` | `detail.high_conf` | ✓ `false` | none |
| `timeframe` | `"1d"` literal | n/a | none |
| `regime` | `detail.regime ?? detail.regime_label` | ✓ `"Regime: Trending"` (PREFIX BUG W2-N5/W1-8) | renders `"regime: trending"` |
| `confidence` | `detail.confidence_avg_pct` | ✓ `44.7` | none |
| `regimeAge` | `"—"` literal | n/a | TODO(D-ext) honest |

### Beginner gloss (lines 460-477)

Reads `detail.direction`, `detail.confidence_avg_pct`, `detail.pair`. All present. Safe.

### Multi-timeframe strip (`<TimeframeStrip timeframes={timeframes} />` at line 491)

`timeframes` built at lines 282-302. Iterates `_ENGINE_TFS = ["1h", "4h", "1d", "1w", "1M"]` and reads `detail.timeframes[tf].direction` and `detail.timeframes[tf].confidence`.

| Field | Path | In ground-truth? | Issue |
|---|---|---|---|
| `direction` | `detail.timeframes['1h'].direction` | ✓ `"LOW VOL"` (truthful empty) | none |
| `confidence` | `detail.timeframes['1h'].confidence` | ✓ `19.8` | none |

`_toCleanString` and `_toFiniteNumber` defensively coerce. Wave 1 hotfix covers this.

### Composite score card (`<CompositeScore {...compositeFallback} />` at line 508)

Reads `detail.confidence_avg_pct`. Present (`44.7`). Coerced via `_toFiniteNumber`. Safe.

### Technical indicator tiles (lines 318-380)

| Tile | Reads | Engine emits at this path? | Bug |
|---|---|---|---|
| RSI (14) | `detail.rsi` | **NO** — engine emits `detail.timeframes['1h'].rsi` (`58.5` in ground truth) | **W2-N1 — always "—"** |
| MACD | `detail.macd` | **NO** — engine emits `detail.timeframes['1h'].macd_div` (string `"Bearish (regular) (Strong)"`) | **W2-N1 — always "—"** |
| Supertrend | `directionToSignalType(detail.direction)` + `regimeToDisplay(detail.regime)` | ✓ both | renders correctly (regime prefix bug aside) |
| ADX (14) | `detail.adx` | **NO** — engine emits `detail.timeframes['1h'].adx` (`26.3` in ground truth) | **W2-N1 — always "—"** |

**3 of 4 tiles permanently broken on every pair.**

### Signal history (`<SignalHistory entries={signalHistoryEntries} />` at line 551)

Drives via `useSignalHistory(activePair, 50)` → `SignalHistoryRow` rows. `_deriveTransitions` at lines 148-191 reads `row.direction`, `row.price_usd`, `row.regime`, `row.confidence_avg_pct`, `row.mtf_alignment`, `row.scan_timestamp` — all defensively coerced. Wave 1 hotfix covers. Safe.

### Other tiles (on-chain + sentiment + price)

All hardcoded `—` values with honest "not in V1" / "backfill pending" subtext per AUDIT-2026-05-05 (P0-8). Truthful empty states. No drift.

---

## P0 fixes for autonomous execution — ranked by user-visible impact

1. **`crypto_model_core.py:4848` — copy `timeframes['1h']` indicator fields up to top level OR pivot the consumer to read nested.** The fewest-line fix is two new lines after the `result` dict is built:
   ```python
   _tf1h = tf_data.get('1h') or {}
   result.update({
       'rsi':  _tf1h.get('rsi'),
       'adx':  _tf1h.get('adx'),
       'macd_div': _tf1h.get('macd_div'),  # also expose macd if numeric available
   })
   ```
   **Closes W2-N1.** Restores 3 Technical-Indicator tiles on every Signals page, every pair. Backwards-compatible — existing consumers of `timeframes['1h']` still see the nested copy.

2. **`crypto_model_core.py:4874` — strip `"Regime: "` prefix at source.** Single-character edit:
   ```python
   'regime': regime_1h,  # was: f"Regime: {regime_1h}"
   ```
   **Closes Wave 1 W1-8 + Wave 2 W2-N5 + the cosmetic `regime: trending` rendering on Home/Signals/Regimes.** No downstream breakage — `_extract_regime` in routers/regimes.py:27-28 and `regimeToDisplay` in lib/format.ts both already handle bare label strings.

3. **`execution.py:1153` — add `agent_running` to `get_status()` return dict.** Roughly 4 lines (peek at scheduler thread, peek at paper-balance counter). **Closes W2-N6 + Wave 1 W1-4.** Restores Topbar AGENT pill truthfulness + AI Assistant page initial state.

4. **`api.py:737` — rename `total` → `count` on `/backtest/trades`.** One-character fix. **Closes Wave 1 W1-5 + W2-N7.** Backtester page subtitle ("last 8 of N") starts working.

5. **`api.py:1095-1097` — alias `sent_at→timestamp`, `error_msg→message`, derive `type` from direction at the API boundary on `/alerts/log`.** ~10 lines (see W2-N8 patch). **Closes Wave 1 W1-6 + W2-N8.** Alerts history page rows render correctly.

6. **`routers/ai_assistant.py:112` — read from `agent_log` instead of `daily_signals` for `/ai/decisions`.** ~5 lines. **Closes W2-N4.** AI Assistant Recent Decisions table shows the actual Claude rationale.

### P1 follow-ups (lower visible impact)

7. **`web/app/settings/execution/page.tsx:340` — guard `testResult.balance_usdt.toLocaleString` with `isMissing()`.** 1 line. Defensive — only fires on degraded CCXT.

8. **Add `/diagnostics/feeds` to `lib/api.ts` and render in Dev Tools page.** ~30 lines. **Closes W2-N9.** Operator finally sees Render-side feed reachability without log archaeology.

9. **`web/lib/api-types.ts:62-87` — expand `SignalRow` to declare `timeframes`, drop top-level `rsi/adx/macd`, acknowledge wyckoff/pi_cycle/macro/risk_info fields.** ~40 lines. **Closes W2-N3.** No runtime impact — purely type hygiene + IDE autocomplete.

10. **`web/lib/format.ts` — promote `_toFiniteNumber` and `_toCleanString` from signals/page.tsx so every page can use the same defensive coercions.** ~10 lines.

### P2 follow-ups (cosmetic / type-only)

11. **Add `response_model=` to the 27 already-typed endpoints.** ~1 line each + Pydantic model defs (most map directly to existing TS interfaces; convert the TS shape to Pydantic). Enables auto-generated openapi.json schemas for CI drift-checking. Single biggest preventive win against future Wave-3 audits.

12. **`routers/diagnostics.py:289-290` — change `wal_mode: True` and `auto_vacuum: "nightly"` to actual PRAGMA reads or `"unmeasured"` strings.** Already documented in Wave 1 (W1-7).

---

## Closing

Wave 1 closed 3 of 9 findings (the high-impact P0-3 engine emit). Wave 2 finds:
- **1 new high-impact P0 bug class** (nested-field reads — 3 broken indicator tiles on every pair).
- **1 new P1** (`/ai/decisions` reads wrong DB table → rationale never surfaces).
- **1 new P1** (`testResult.balance_usdt.toLocaleString` un-guarded coercion).
- **1 new dead-wired P2** (`/diagnostics/feeds` shipped backend-only).
- Reaffirms 5 still-open Wave 1 findings (W1-4 thru W1-8).

**Total open after Wave 2: 11 findings (3 P0, 5 P1, 3 P2).** All have line-number-precise fixes documented above.

**Single biggest preventive lift:** add `response_model=` to the 27 already-typed endpoints. Closes the OpenAPI drift category once and for all.
