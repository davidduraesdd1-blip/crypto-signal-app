# Deferred Fixes — Numbered Proposals (2026-05-03)

**Source:** items deferred from the 2026-05-02 overnight audit + the
2026-05-03 fresh audit batches that need David's sign-off, a §22
regression diff, a design pass, or a dedicated test plan before
shipping.

**How to use:** read each proposal, reply with the numbers you
greenlight (e.g. "approve P1, P2, P5"). Anything not greenlit stays
deferred. Once approved, I execute the entire approved list
autonomously per CLAUDE.md §1.

**Format per proposal:**
- **What** — the change in plain English
- **Why now** — what it buys you, what it prevents
- **Risk** — what could go wrong
- **Effort** — rough wall-clock
- **What I need from you** — direction-level decisions before I start
- **Validation** — how we'll know it worked

---

## P1 — `routers/alerts.py` POST race condition

**Severity:** MEDIUM (data integrity)

**What:** introduce `update_alerts_config(updater_fn)` in `alerts.py`
that wraps the load → modify → save sequence in a module-level
`threading.RLock`. Refactor `routers/alerts.py` and
`routers/settings.py` to use it instead of calling
`load_alerts_config` + `save_alerts_config` separately. Closes the
read-modify-write race where two concurrent POSTs can lose one
caller's write.

**Why now:** the FastAPI `/alerts/configure` POST + the four
`/settings/*` PUTs all do unprotected read-modify-write. With
auto-deploy live and at least three concurrent processes hitting the
same `alerts_config.json` (FastAPI worker, agent loop, Streamlit during
the 30-day overlap), the window is real. The atomic-rename in
`save_alerts_config` only protects against crash-mid-write, not
against concurrent writers.

**Risk:**
- Adding a lock to a module that's currently lock-free can deadlock
  if `alerts_module.send_email` or another helper transitively calls
  `load_alerts_config` from inside the lock. Need to enumerate
  call-sites before wrapping.
- `RLock` chosen over `Lock` so re-entrant calls within the same
  thread don't self-deadlock.
- Streamlit and FastAPI run in separate processes, so an in-process
  `threading.Lock` doesn't help across them. A `filelock` (advisory
  fcntl/LockFileEx wrapper) would be needed for full cross-process
  safety. **Question for you:** in-process only (faster, smaller
  scope, fixes 80% of the risk) or cross-process via `filelock`
  (slower, +1 dependency, fixes the Streamlit-overlap window too)?

**Effort:** 2-3 hours including tests.

**What I need from you:**
- Pick: in-process `threading.RLock` only OR cross-process via the
  `filelock` package.

**Validation:**
- Existing tests stay green (no behavior change for sequential
  callers).
- New regression test fires N=20 concurrent threads each PUTting a
  unique key; assert all 20 land in the final config dict (currently
  fails by ~10-15% on a single CPU core).
- If cross-process chosen: spawn-subprocess test that two `python -c
  "alerts.update_alerts_config(...)"` calls don't lose writes either.

---

## P2 — `routers/diagnostics.py` gate 5 semantics

**Severity:** LOW (UX consistency)

**What:** decide one of:
- **(a)** Flip gate 5 (Trade-size cap) from `_ok` → `_unmeasured`,
  matching gates 4 and 6. Honest UI: "we cannot show real-time
  state of this gate at the status-read level, only the configured
  cap." `all_operational` becomes `false` until the agent pipeline
  logs cap-hit events to the DB.
- **(b)** Keep gate 5 `_ok`, but rewrite the detail string to make
  the distinction unambiguous: `"<X>% configured cap · enforced at
  order time, not measured here"`. `all_operational` stays `true`
  when the cap is configured.
- **(c)** Status quo (no change) — accept the inconsistency the
  overnight-audit doc glosses over.

**Why now:** the existing `test_diagnostics_circuit_breakers_smoke`
asserts `all_operational is False` and `has_unmeasured is True`
specifically because gate 4 is `_unmeasured`. So the test passes
today. But operators reading the Settings · Dev Tools card see a
green pill on gate 5 and infer "trade-size cap is currently being
enforced and nothing has tripped it" — when actually we're only
showing the configured value, no real-time state. Gate 4's `_unmeasured`
sets a precedent that reads honestly; gate 5 violates it.

**Risk:**
- (a) flips `all_operational` to false on the live deploy. The
  Settings · Dev Tools header pill goes from green to yellow.
  Existing test passes (it already expects false because of gate 4).
  No real-money path affected. This is the safest "honest UI" fix.
- (b) requires only a string change — zero risk. But preserves the
  semantic ambiguity.
- (c) ships nothing.

**Recommendation:** (a). The "honest empty states" memory
(`feedback_empty_states.md`) leans this direction.

**Effort:** 30 min including test update.

**What I need from you:** pick (a), (b), or (c).

**Validation:**
- (a): update `test_diagnostics_circuit_breakers_smoke` to also assert
  gate 5's `status == "unmeasured"` (regression-guard against future
  reverts).
- (b): update the assert on `gate5["detail"]` to contain
  `"not measured here"`.

---

## P3 — `api.py:place_order` `OrderRequest` validation

**Severity:** HIGH (financial / order placement)

**What:** add Pydantic constraints to `OrderRequest` in `api.py:315-321`:

  - `direction`: enum {`BUY`, `SELL`, `STRONG BUY`, `STRONG SELL`}
    (exclude `NEUTRAL` — can't place a neutral order)
  - `order_type`: enum {`market`, `limit`, `MARKET`, `LIMIT`}
  - `size_usd`: keep `gt=0`, add `le=10_000` (cap from `_DEFAULTS.agent_max_trade_size_usd`,
    can be raised via env var if you want larger)
  - `limit_price`: when `order_type` is `limit`, require `limit_price > 0`
    via a `model_validator(mode="after")`
  - `pair`: bound length 3-32 (already done in routers)

**Why now:** without these, a frontend bug (or a malicious caller
with the API key) can place a $10M order, an order with a negative
limit price, or send `direction="moonshot"` and crash the engine on
the `direction.upper()` interpolation. With C-1 closed, the API key
is now the only auth boundary — any caller through it gets full
order placement.

**Risk:**
- This intersects the deferred CRITICAL **C-3** (allowlist + size
  cap + SL/TP validation). C-3 needs sign-off because it touches the
  order-placement contract end-to-end (allowlist of pairs, etc.).
  This proposal P3 is the **subset** of C-3 that's input-validation
  only — not the architectural part. It's safe in isolation but
  there's a question: **do you want me to do P3 alone now, or hold
  it until you sign off on the full C-3 batch?**
- A frontend that sends `direction: "buy"` (lowercase) currently
  works because of the `.upper()` call. Pydantic enum match is
  case-sensitive, so adding the enum without tolerance would break
  lowercase callers. Mitigation: use a `field_validator(mode="before")`
  that uppercases before matching.

**Effort:** 1-2 hours including tests.

**What I need from you:** approve P3 standalone, or hold for full
C-3 batch (which needs additional sign-off on the allowlist semantics).

**Validation:**
- New regression tests: bad direction → 422, negative size → 422,
  limit order without limit_price → 422, $10M order → 422.
- Existing `place_order` smoke test (if any) keeps passing.
- Live curl on Render against a paper-trade order: still works.

---

## P4 — C-3/C-4/C-5/C-6 execution-layer architectural CRITICALs

**Severity:** CRITICAL × 4 (financial)

**What:** the four execution-layer findings the overnight audit
flagged but deferred:
- **C-3:** `place_order` lacks pair allowlist + size cap + SL/TP
  validation (architectural — touches every order path)
- **C-4:** `place_order` not idempotent (no `clientOrderId`); a 504
  retry or double-click places duplicate live orders
- **C-5:** circuit breaker is not actually called from `place_order`
  (the comment claiming it is, is wrong); also two parallel
  implementations to consolidate (`execution.check_circuit_breaker`
  vs `circuit_breakers.check_all`)
- **C-6:** short-side slippage + fee math is directionally wrong;
  `effective = size * (1 + slippage)` should sign on `side`

**Why now:** CLAUDE.md §10 explicitly requires allowlist + cap +
validation before live submission. Live trading is currently OFF on
Render (`live_trading_enabled=false`), so today this is a latent risk.
The moment you flip live trading on, all four findings activate.

**Risk:**
- Each of the four touches the execution contract. C-6 needs paired
  §22 backtester regression diff to quantify P&L impact (compounded
  over 12,000+ historical trades the backtester samples).
- C-4 (`clientOrderId`) requires ccxt OKX integration testing in
  paper mode — the OKX API contract for `clOrdId` has subtle quirks
  around length and character set.
- C-5 consolidation breaks anything that currently calls the orphan
  `circuit_breakers.check_all` path. Need to grep + rewrite.

**Effort:** 1-2 days end-to-end including all four + their tests +
the §22 regression diff for C-6.

**What I need from you:**
- Sign off on the order-placement contract changes (allowlist
  source: alerts_config.trading_pairs, default = top-30 by mcap?
  Strict-deny on miss = yes/no?)
- Sign off on `MAX_ORDER_SIZE_USD` cap value (currently
  `agent_max_trade_size_usd=$1000` — keep that as the absolute
  ceiling? Different cap for live vs paper?)
- Confirm we run §22 regression diff before merging C-6 (yes per
  CLAUDE.md §22 — just confirming).

**Validation:**
- All 4 findings closed in audit doc.
- New tests: pair-not-in-allowlist → 422, oversize → 422, idempotent
  retry returns same order ID, circuit breaker actually trips on
  oversize portfolio loss, short-side P&L matches expected.
- `docs/signal-regression/2026-05-XX-c6-slippage.md` quantifies
  before/after P&L on the canonical fixture set.

---

## P5 — LA-1/LA-2/LA-3/LA-4 look-ahead-bias math CRITICALs

**Severity:** CRITICAL × 4 (math correctness)

**What:** four look-ahead bugs the overnight audit deferred behind
the §22 regression-diff gate:
- **LA-1:** `top_bottom_detector._pivot_lows/_pivot_highs` use
  centered rolling — every divergence detection peeks `n` bars into
  the future
- **LA-2:** squeeze momentum reads `delta.iloc[-1]` while delta is
  built from current (unclosed) bar
- **LA-3:** `crypto_model_core.detect_macd_divergence_improved` peaks
  defined via `macd.shift(-1)` — same future-peek class
- **LA-4:** anchored VWAP anchor uses centered-pivot output, inherits
  future-peek

**Why now:** every BUY/HOLD/SELL signal touches at least two of these
modules. Backtest results reported up to today are **systematically
optimistic** because the engine sees future bars during signal
generation. The longer this stays unfixed, the harder it is to
reconcile reported alpha vs live alpha.

**Risk:**
- Fixing look-ahead bias **lowers backtest performance**. Stakeholders
  who saw the optimistic numbers will see a step-down. We need a
  clear before/after report so the regression isn't mistaken for a
  new bug.
- `cycle_indicators.py` and `composite_signal.py` are the gold
  references per CLAUDE.md §22 — every change requires a backtest
  diff against the 2023-2026 universe committed to
  `docs/signal-regression/`.
- Some signals may flip BUY ↔ SELL after the fix because the late
  pivot detection produces a different state. We need a trade-by-trade
  diff, not just aggregate metrics.

**Effort:** 2-3 days. Most of it is the regression diff +
reconciliation, not the code fix itself.

**What I need from you:**
- Confirm you want me to ship the fix even though backtest numbers
  will drop (correctness > optics).
- Sign off on the regression-diff format (`docs/signal-regression/2026-05-XX-look-ahead.md`,
  trade-level CSV side-by-side, signed P&L delta per pair, summary
  table of "signals that flipped BUY→SELL").

**Validation:**
- All 4 look-ahead findings closed.
- §22 regression diff committed showing the magnitude of the change
  per pair + per timeframe.
- New unit tests: `pivot_lows(closed_only=True)` returns identical
  output to the closed-bar subset of the centered-rolling output
  (regression-guard against re-introducing the bias).

---

## P6 — LLM-1/LLM-2/LLM-3 trust-boundary CRITICALs

**Severity:** CRITICAL × 3 (security / LLM safety)

**What:** three deferred LLM trust-boundary findings:
- **LLM-1:** `agent.py._sanitize` is a 7-phrase substring wall —
  bypassed by Unicode look-alikes, paraphrase, base64. Replace with
  strict per-field whitelist + XML-tagged untrusted blocks.
- **LLM-2:** three prompt builders in `llm_analysis.py` interpolate
  raw `pair`/`regime`/`funding` strings with no sanitization.
  (This batch's `routers/ai_assistant.py` Pydantic constraint — fix #15
  — is a partial mitigation; the source bug is still in the prompt
  builders.)
- **LLM-3:** emergency-stop checked only in `_check_pre_risk` —
  TOCTOU window during ~45s Claude round-trip lets a kill-switched
  cycle still execute.

**Why now:** the agent has authority to place real-money orders. A
prompt-injection bypass that gets the LLM to recommend BUY on a
manipulated pair, combined with C-3's missing allowlist, combined
with C-5's missing circuit-breaker call inside `place_order`, is a
fully-loaded chain.

**Risk:**
- The replacement sanitizer is a design decision. Strict per-field
  whitelist (e.g., `pair must match ^[A-Z]{2,10}/[A-Z]{2,10}$`)
  works for structured fields but the model also sees free-text
  fields (`question`, `note`, news headlines).
- XML-tagged untrusted blocks are the current best-practice (cf.
  Anthropic's prompt-injection-resistance guidance) — but they
  require restructuring all three prompt builders.
- LLM-3 (TOCTOU) needs `is_emergency_stop()` checks at multiple
  enforcement points: pre-risk, mid-roundtrip (cancellation flag in
  `asyncio.Event`), and post-decision. Non-trivial.

**Effort:** 2-3 days for the design pass + implementation + tests.

**What I need from you:**
- Sign off on the design direction: strict-whitelist + XML-tagged
  blocks (recommended) vs alternative (e.g., LLM-as-classifier
  pre-pass)
- Confirm priority: do this before live trading is enabled (yes,
  recommended) or accept the risk under a manual-approval flow
  short-term

**Validation:**
- 50-attack red-team battery: substring bypasses, Unicode
  look-alikes, base64, paraphrase. All return refusal or sanitized
  output.
- TOCTOU regression test: emergency-stop flip during a Claude call
  results in cycle abort before order placement (currently fails).

---

## P7 — DB-1/DB-2/DB-3/DB-4 database concurrency CRITICALs

**Severity:** CRITICAL × 4 (data integrity)

**What:** four database concurrency findings:
- **DB-1:** default `isolation_level=""` + per-thread connection
  pool + manual `BEGIN/COMMIT` in some helpers but not others =
  sporadic "transaction within a transaction" + silent rollbacks
  via `_NoCloseConn.close()`
- **DB-2:** no `PRAGMA busy_timeout`; SQLITE_BUSY retries not
  implemented despite three concurrent writers (FastAPI + agent +
  Streamlit)
- **DB-3:** f-string interpolation of column name into `ALTER TABLE`
  (currently safe — literals only — but bypasses `_add_col` whitelist
  guard, one careless edit becomes injection)
- **DB-4:** `save_positions` uses raw `BEGIN` outside the auto-tx
  model — risk of "transaction within transaction" in pooled paths

**Why now:** silent rollbacks are corrupting historical data we'll
later use as backtest fixtures. SQLITE_BUSY without retry is the
"random rare 500" we sometimes see on the live deploy.

**Risk:**
- DB rewrites are scary. Need a dedicated test plan covering:
  concurrent reads + writes from all three writer processes,
  long-running transactions, crash-mid-transaction recovery.
- Migrating from `isolation_level=""` to `"DEFERRED"` (the canonical
  SQLite mode) might surface latent bugs in code that relies on the
  current weird-mode behavior.
- `PRAGMA busy_timeout` is cheap (just set it to 5000ms in the
  connection factory) but exposing it requires testing all the
  long-running queries to ensure none exceed the timeout.

**Effort:** 3-4 days including the test plan.

**What I need from you:**
- Sign off on the test plan (I'll write it as a doc first; you
  approve before I start the rewrites)
- Confirm we can take a brief Streamlit downtime during the migration
  (probably ~30 min, schedule for an off-hours window)

**Validation:**
- New concurrency test suite: 3-process simulation (FastAPI worker
  + agent + simulated Streamlit), 100 concurrent transactions,
  zero data loss + zero deadlocks.
- All existing 360 tests still pass.
- Live deploy soak test: 24 hours of normal traffic, no SQLITE_BUSY
  errors in logs.

---

## Recommended order if you approve everything

If you greenlight all of P1-P7, the dependency-aware order is:

1. **P3** (input-validation slice of C-3) — fast, no deps. Closes
   the worst input vectors before the bigger fixes land.
2. **P1** (alerts.py race) — independent, defends data integrity
   under the auto-deploy + agent + Streamlit triple-writer load.
3. **P2** (gate 5 semantics) — 30 min, tiny risk.
4. **P5** (look-ahead math) — large but independent. Backtest diff
   gates everything else math-related.
5. **P4** (full C-3/4/5/6 execution layer) — unblocks live trading.
   Build on P3.
6. **P7** (DB concurrency) — large; do after P5 so the look-ahead
   fixes don't have to also handle DB schema changes.
7. **P6** (LLM trust boundary) — last because it's the deepest
   redesign. Should land before live-trading-with-agent is enabled.

If you only have appetite for one this week: **P3 + P2 + P1** in
that order (~half a day total) closes 80% of the realistic risk
without touching the math or LLM stack.
