# Infrastructure §4 Audit — 2026-05-03

**Trigger:** CLAUDE.md §4 — Phase D-1/D-ext sprint items completed,
fresh audit on a code surface the overnight audit under-covered.

**Files audited:** `scheduler.py`, `config.py`, `utils_format.py`,
`utils_audit_schema.py`, `utils_wallet_state.py`. (`utils_compute.py`
and `utils_dataframe.py` do not exist in this worktree.)

**Auditor:** focused subagent, returned 2026-05-03 afternoon.

**Branch baseline:** `phase-d/next-fastapi-cutover @ ff02657`.

---

## Executive summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH     | 3 |
| MEDIUM   | 8 |
| LOW      | 6 |
| **Total**| **17** |

Three biggest exposures:
1. **Scheduler reads its interval once at startup** — config edits to
   `autoscan_interval_minutes` never take effect until process restart.
   The Settings UI implies live config; the scheduler doesn't honor it.
   (S-1)
2. **`utils_wallet_state._LOCK` is a `threading.Lock`, not a file lock**
   — despite the docstring claiming "file lock serializes read-modify-
   write across multi-app hosts." Three sibling apps (DeFi / SuperGrok /
   RWA) running as separate Python processes can race the read-modify-
   write and double-allocate the same capital. (W-1)
3. **`_is_missing` swallows non-numeric strings** in `utils_format.py`
   — `format_usd("7,200")` silently renders as `—` instead of `$7,200`,
   masking upstream type bugs. (F-1)

---

## Findings by file

### `scheduler.py`

| ID | Sev | File:line | Issue |
|---|---|---|---|
| S-1 | HIGH | `scheduler.py:215, 227-232` | `_get_interval()` called once before `add_job`; config edits never picked up until process restart. |
| S-2 | HIGH | `scheduler.py:239-241` | `_t.join(timeout=1800)` is misleading — initial scan can run past 30 min holding `_scan_lock`; daemon thread is not actually terminated. |
| S-3 | MEDIUM | `scheduler.py:67-82` | Quiet-hours boundary bug on `start == end` (e.g. 00:00–00:00). Same-day path returns always-False; users configuring 24h quiet via 00:00–00:00 silently get scans. |
| S-4 | MEDIUM | `scheduler.py:106, 152` | Redundant `_alerts.load_alerts_config()` despite `# load once, reuse` comment on L150. |
| S-5 | LOW | `scheduler.py:81` | `logging.debug` (module-level) instead of `logger.debug` (named); inconsistent. |
| S-6 | LOW | `scheduler.py:139` | `{r["pair"]: ...}` raises KeyError if pair missing; `r.get("price_usd", 0)` filter drops legit `0.0` prices. |

### `config.py`

| ID | Sev | File:line | Issue |
|---|---|---|---|
| C-1 | MEDIUM | `config.py:123` | `coingecko_pro` flag double-counts the same env-var key, can flag pro mode on a free key → 401 on paid endpoints. |
| C-2 | MEDIUM | `config.py:19` | `ANTHROPIC_ENABLED` doesn't `.strip()` whitespace; `" false "` reads as enabled. |
| C-3 | LOW | `config.py:76-112` | TIER2 listings (`TIER2_PAIRS`, `TIER2_BINANCE_PAIRS`, `TIER2_COINGECKO_IDS`) drift risk; no import-time consistency assert. |
| C-4 | LOW | `config.py:188` | `BRAND_NAME` defaults to `"Family Office · Signal Intelligence"` — that's a real brand string, violates CLAUDE.md §6 placeholder rule. |

### `utils_format.py`

| ID | Sev | File:line | Issue |
|---|---|---|---|
| F-1 | HIGH | `utils_format.py:23-35, 55` | `_is_missing` swallows `ValueError` from `float(non_numeric_string)`; `format_usd("7,200")` → `—` silently masks upstream type bugs. |
| F-2 | MEDIUM | `utils_format.py:94, 143` | `if abs(v) <= 1.5: v = v * 100` heuristic — legitimate `1.2%` (passed as `1.2`) gets multiplied to `120%`. Some callers pass `0.012` for 1.2%, others pass `1.2`. No way to disambiguate. |
| F-3 | MEDIUM | `utils_format.py:60` | `decimals = max(0, min(6, int(decimals)))` silent-clamps without warning; masks bugs where `decimals` comes from user input. |
| F-4 | LOW | `utils_format.py:68-69` | `950K → "$0.95M"` rounding inconsistency: adjacent rows show "$940.00K" + "$0.95M" — visually inconsistent. |
| F-5 | LOW | `utils_format.py:292` | `import time as _time` inside function body; trivial. |

### `utils_audit_schema.py`

| ID | Sev | File:line | Issue |
|---|---|---|---|
| A-1 | MEDIUM | `utils_audit_schema.py:83-85` | Unknown app/event_type silently accepted; typo (`"superGrok"` vs `"supergrok"`) bifurcates the audit ledger. |
| A-2 | LOW | `utils_audit_schema.py:120-127` | `serialize_event` fallback on serialize failure produces silent JSON without app/timestamp/event_type — downstream tooling can't reconcile. |

### `utils_wallet_state.py`

| ID | Sev | File:line | Issue |
|---|---|---|---|
| W-1 | HIGH | `utils_wallet_state.py:39, 53-76` | `_LOCK = threading.Lock()` is intra-process; docstring claims file-lock cross-process. Multi-app double-allocation possible. |
| W-2 | MEDIUM | `utils_wallet_state.py:144` | `reservation_id` uses 24-bit hash; collision possible within same second; release() can delete wrong reservation. |
| W-3 | MEDIUM | `utils_wallet_state.py:142, 210` | `amount_usd <= 0` allows NaN/Inf through (`float("nan") <= 0` is False); poisons all downstream sums. |
| W-4 | MEDIUM | `utils_wallet_state.py` | `_load_state + _prune_expired + _save_state` on every read mutates state without saving — expired entries persist on disk until next reserve/release. |
| W-5 | LOW | `utils_wallet_state.py:214-217` | Hard-coded `{:,.0f}` USD format; bypasses `format_usd` so unit consistency drifts. |

---

## Recommended next batch — autonomously shippable (12)

These are bug fixes / cleanups not requiring sign-off, regression diff,
design pass, or test plan:

1. **S-1** — Scheduler interval re-read on each tick (HIGH)
2. **S-4** — Scheduler dedupe `load_alerts_config()` call (MEDIUM)
3. **S-5** — `logging.debug` → `logger.debug` (LOW)
4. **S-6** — Scheduler `r.get("pair")` defensive (LOW)
5. **C-2** — `ANTHROPIC_ENABLED` strip whitespace (MEDIUM)
6. **C-3** — TIER2 dict-consistency assert at import (LOW)
7. **F-1** — `_is_missing` strip commas/whitespace (HIGH, narrow fix)
8. **F-3** — `format_usd` log on decimals clamp (MEDIUM)
9. **A-2** — `serialize_event` fallback sentinel (LOW)
10. **W-2** — `reservation_id` use uuid suffix (MEDIUM)
11. **W-3** — `reserve()` reject NaN/Inf amounts (MEDIUM)
12. **W-5** — `has_capacity` use `format_usd` (LOW)

## Holding for explicit sign-off

- **S-2** scheduler initial-scan join semantics — logging-only safe;
  the actual root cause (2× concurrent runs on `--now`) needs UX call.
- **S-3** quiet-hours equal-start/end semantics (UX scheduling change)
- **C-1** coingecko_pro flag (external API contract)
- **C-4** `BRAND_NAME` default (branding/UX)
- **F-2** percent/fraction split (math semantics, broad blast radius)
- **F-4** USD compact rounding threshold (UX/display)
- **A-1** strict app/event_type enforcement (audit ledger contract)

## Holding for dedicated test plan (concurrency)

- **W-1** wallet-state file lock — multi-process safety; needs
  cross-app reproduction test before shipping. Same category as
  `routers/alerts.py` race (P1 in 2026-05-03 deferred-fixes-proposals)
  and DB-1/2/3/4 from the overnight audit.
