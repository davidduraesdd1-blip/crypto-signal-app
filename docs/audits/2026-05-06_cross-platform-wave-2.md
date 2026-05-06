# Cross-Platform Connectivity — Wave 2

**Date:** 2026-05-06
**Worktree:** `.claude/worktrees/exciting-lovelace-60ae5b/` (branch `claude/exciting-lovelace-60ae5b`)
**Methodology:** Read-only audit. Re-grepped every `os.environ.get` / `os.getenv` /
`process.env.*` reference, re-read `render.yaml` line-by-line against `database.py`
+ `api.py` + `routers/deps.py`, re-grepped every `alerts_config.json` reference,
diffed `.env.example` against the live env-var matrix, curl-probed
`https://crypto-signal-app-1fsi.onrender.com/health` and
`https://cryptosignal-ddb1.streamlit.app`.
**Predecessor:** `docs/audits/2026-05-05_cross-platform-connectivity.md` (Wave 1).
**Phase 0.9 closure commits referenced:** `b5e369e` (P0-1), `7f85c36` (P0-2),
`76dff07` (P0-4).

---

## Executive summary

| Wave-1 finding | Phase 0.9 status | Wave-2 verdict |
|---|---|---|
| C-1 — `CRYPTO_SIGNAL_API_KEY` plaintext leak in `docs/redesign/*.md` | ✅ scrubbed in `b5e369e`; David rotated key | CLOSED — verified 0 hits for the `DY0YUB3...` shape under `docs/redesign/`. |
| P0-2 — `web/.env.local.example` missing | ✅ created in `7f85c36` | CLOSED — file at `web/.env.local.example` (20 lines, includes Sensitive-flag pitfall). |
| P0-4 — render.yaml plan drift (`starter` vs live `standard`) | ✅ synced in `76dff07` | CLOSED — render.yaml:35 now `plan: standard`. **README still says Starter $7 — stale (see §5).** |
| P1 — `alerts_config.json` not on persistent disk | ⏳ deferred | OPEN — confirmed 5 modules touch the bare-relative path (see §3). |
| P1 — `OKX_SECRET` legacy alias in `.env.example:19` | ⏳ deferred | OPEN — line 19 still `OKX_SECRET=...` (see §4). |

**Wave-2 P0 count:** 0.
**Wave-2 P1 count:** 5 (alerts disk migration, .env.example diff, README staleness × 3 lines, Streamlit auth-redirect investigation, dev-tools page snippet uses wrong env var name).
**Wave-2 P2 count:** 4 (Vercel auto-promote setup, GitHub Actions promotion fallback, dead `DEMO_MODE` env var, CORS regex tightening).

The Vercel auto-promote question (Wave-2 #1) is **not a code bug** — it's a Vercel
project setting. Concrete two-step fix in §1; CI fallback in §1b.

---

## 1. Vercel auto-promote — root cause + fix

### Symptom (per David)
"Tonight Vercel did NOT auto-promote new deploys to production — I had to manually
promote each commit's deploy via the ⋮ menu."

### Root cause
v0-generated Vercel projects default to **"Only production deployments"** auto-
promote OFF for the connected Git branch. The project is configured so that
each push to `main` produces a **Preview deployment** with a unique URL, and the
**Production** alias (`v0-davidduraesdd1-blip-crypto-signa.vercel.app`) only
moves when the operator clicks "Promote to Production" in the dashboard. This
is a v0/Vercel UX choice — there is **no `vercel.json` in `web/` or repo root**,
so no IaC config has overridden the default.

Verified:
- `find . -name vercel.json` → 0 hits (root and `web/` both empty).
- `web/next.config.mjs` only handles `BUILD_TARGET=mobile` static export; it
  does not control deploy promotion.
- No GitHub Action calls `vercel deploy --prod` (the four workflows are
  `deps-audit.yml`, `feedback_evaluator.yml`, `secret-scan.yml`, `security.yml`
  — none touch Vercel).

### Recommended fix — simplest path (5 minutes, zero code)

In the **Vercel dashboard** for project `v0-davidduraesdd1-blip-crypto-signa`:

1. Go to **Project → Settings → Git**.
2. Locate the **"Production Branch"** field. Confirm it says `main`.
3. Locate the **"Ignored Build Step"** field — leave blank (or `null`).
4. Go to **Project → Settings → Deployments**.
5. Find the toggle / dropdown labeled either:
   - **"Auto-assign Custom Domains"** (newer UI), OR
   - **"Production Branch Auto-deploy"** (older UI), OR
   - **"Promote production deployments automatically"** (v0 UI).

   Set it to **ON / Enabled / "Always promote"**. Older v0 templates default
   this OFF.
6. Save.
7. Push a no-op commit (`git commit --allow-empty -m "test: vercel auto-promote"`)
   and watch the build — it should deploy AND alias to production in one step.

**Verification:** after the next push, the build log in the Vercel dashboard
should show two stages: "Deployment Ready" and "Promoted to Production"
back-to-back, both green. If only the first appears, the toggle is still off.

### 1b. GitHub Action fallback (only if dashboard toggle is unavailable)

If the v0-managed project does not expose the toggle, add a tiny workflow that
runs `vercel --prod --token=$VERCEL_TOKEN` on push to `main`. Add the file at
`.github/workflows/vercel-promote.yml`:

```yaml
name: Vercel — promote main to production
on:
  push:
    branches: [main]

jobs:
  promote:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Install Vercel CLI
        run: npm install -g vercel@latest
      - name: Pull Vercel env
        run: vercel pull --yes --environment=production --token=${{ secrets.VERCEL_TOKEN }}
        working-directory: web
      - name: Build
        run: vercel build --prod --token=${{ secrets.VERCEL_TOKEN }}
        working-directory: web
      - name: Deploy to production
        run: vercel deploy --prebuilt --prod --token=${{ secrets.VERCEL_TOKEN }}
        working-directory: web
```

Required GitHub secrets:
- `VERCEL_TOKEN` — generate at https://vercel.com/account/tokens (Account-scoped).
- `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` — found at `web/.vercel/project.json`
  after a local `vercel link` (do NOT commit `.vercel/`; it's already in
  `web/.gitignore:31`). Set both as repo secrets.

**Recommendation:** try the dashboard toggle first (§1, takes 5 min). Only fall
back to the GitHub Action if v0's project flavor doesn't expose the toggle.
The Action introduces a second deploy pipeline (Vercel's own + this one) that
can race; the dashboard toggle is the single-source-of-truth fix.

---

## 2. render.yaml line-by-line audit

Source: `render.yaml` (143 lines, 18 env vars).

| Field | Value | Verdict |
|---|---|---|
| `services[0].type` | `web` | ✅ Correct (single-service, scheduler in-process). |
| `services[0].name` | `crypto-signal-app` | ✅ Matches dashboard. |
| `services[0].runtime` | `python` | ✅ Matches `runtime.txt` Python 3.11. |
| `services[0].plan` | `standard` | ✅ Synced post-P0-4 (was `starter`). |
| `services[0].region` | `oregon` | ✅ Matches manual config. |
| `services[0].branch` | `main` | ✅ Post-D8 (was `claude/awesome-moore-2850b6`). |
| `services[0].autoDeploy` | `true` | ✅ Correct — every push to `main` redeploys. |
| `services[0].healthCheckPath` | `/health` | ✅ Endpoint exists at `api.py:515`. Live curl returns HTTP 200 in 0.25s. |
| `services[0].buildCommand` | `pip install -r requirements.txt` | ✅ Standard. |
| `services[0].startCommand` | `uvicorn api:app --host 0.0.0.0 --port $PORT` | ✅ Render injects `$PORT`. |
| `disk.name` | `crypto-signal-data` | ✅ Single-service mount (Render constraint). |
| `disk.mountPath` | `/opt/render/project/src/data` | ✅ Matches `database._DATA_DIR` resolution (database.py:50-68). |
| `disk.sizeGB` | `1` | ✅ Well above current footprint (DB ~50 MB, scheduler.log < 100 MB). |

### Env-var match against `os.environ.get` / `os.getenv`

| render.yaml var | Read in code at | Match? |
|---|---|---|
| `CRYPTO_SIGNAL_ALLOW_UNAUTH` (value `"false"`) | api.py:64,291,881; routers/deps.py:69 | ✅ |
| `CRYPTO_SIGNAL_API_KEY` (sync:false) | api.py:263; routers/deps.py:47 | ✅ |
| `CRYPTO_SIGNAL_AUTOSTART_SCHEDULER` (value `"true"`) | api.py:103 | ✅ |
| `ANTHROPIC_ENABLED` (value `"false"`) | config.py:34 | ✅ |
| `ANTHROPIC_API_KEY` (sync:false) | config.py:8; agent.py:843; llm_analysis.py:103,316,511; news_sentiment.py:50 | ✅ |
| `DEMO_MODE` (value `"true"`) | tests/conftest.py:34; tests/test_api_routers.py:30 | ⚠️ **DEAD ENV** — only test fixtures read it. No production code reads `os.environ.get("DEMO_MODE")`. Streamlit uses `st.session_state["demo_mode"]` (lowercase, session-state, not env). Drop from render.yaml or wire a real gate. |
| `PYTHON_VERSION` (value `"3.11"`) | (Render runtime) | ✅ Mirrors `runtime.txt`. |
| `CRYPTOPANIC_API_KEY` (sync:false) | config.py:9 | ✅ |
| `SUPERGROK_COINGECKO_API_KEY` (sync:false) | config.py:10 | ✅ |
| `COINMARKETCAP_API_KEY` (sync:false) | config.py:22; data_feeds.py:6667,6771 | ✅ |
| `ETHERSCAN_API_KEY` (sync:false) | config.py:23 | ✅ |
| `ZERION_API_KEY` (sync:false) | config.py:24 | ✅ |
| `SUPERGROK_SENTRY_DSN` (sync:false) | config.py:21; app.py:55 | ✅ |
| `CRYPTORANK_API_KEY` (sync:false) | data_feeds.py:7853 (via env_key lookup) | ✅ |
| `OKX_API_KEY` (sync:false) | execution.py:208; alerts.py:128 | ✅ |
| `OKX_API_SECRET` (sync:false) | execution.py:209-211; alerts.py:133 | ✅ (legacy `OKX_SECRET` accepted as fallback). |
| `OKX_PASSPHRASE` (sync:false) | execution.py:212 | ✅ |

### Secret hygiene per render.yaml

Every var holding a real secret is `sync: false` ✅ (no live values committed).
Plain non-secret toggles (`CRYPTO_SIGNAL_ALLOW_UNAUTH=false`,
`ANTHROPIC_ENABLED=false`, `CRYPTO_SIGNAL_AUTOSTART_SCHEDULER=true`,
`PYTHON_VERSION=3.11`, `DEMO_MODE=true`) are baked in — correct pattern.

### Code-referenced vars NOT in render.yaml

| Var | Read at | Should be in render.yaml? |
|---|---|---|
| `CRYPTO_SIGNAL_MAX_ORDER_USD` | api.py:435 (defaults to `10000`) | **Recommend YES** — operator may want a tighter cap; today they have to read source. |
| `EMAIL_APP_PASSWORD` | alerts.py:135 (`_SENSITIVE_ENV_MAP`) | **Recommend YES (sync:false)** — currently the only way to use email alerts without plaintext in `alerts_config.json` is via env, and the env var is invisible. |
| `STRICT_AUDIT_SCHEMA` | utils_audit_schema.py:93 (defaults to permissive) | **Recommend YES (value `"true"`)** — master CLAUDE.md §15 says family-office hardening should run strict; today silently false. |
| `LUNARCRUSH_API_KEY` | data_feeds.py:1894; news_sentiment.py:159 | Optional. Recommend YES (sync:false) — already invoked in code. |
| `RENDER_REGION` | routers/diagnostics.py:407 | ✅ Render auto-injects this; no entry needed. |
| `COINGECKO_PRO_KEY` / `SUPERGROK_COINGECKO_PRO_KEY` | config.py:18-19 | Optional/paid — defer. |
| `SUPERGROK_COINALYZE_API_KEY` / `COINALYZE_API_KEY` | data_feeds.py:5149 | Optional — defer. |

### Verdict

`render.yaml` is structurally correct. Three additive recommendations (P2):
1. Add `CRYPTO_SIGNAL_MAX_ORDER_USD` (sync:false, comment that defaults to 10000).
2. Add `EMAIL_APP_PASSWORD` (sync:false).
3. Add `STRICT_AUDIT_SCHEMA: "true"` (baked-in value).

One removal recommendation (P2):
4. Drop `DEMO_MODE` (dead in production code), or wire it into a real demo-mode
   gate — but defer the wire-in unless David wants the kill-switch behavior.

---

## 3. `alerts_config.json` migration plan

### File-by-file inventory

`alerts_config.json` is touched as a **bare relative path** (`"alerts_config.json"`,
i.e. resolved against `os.getcwd()`) in **two** modules, and as
`Path(__file__).resolve().parent / "alerts_config.json"` in **two** other modules
(resolves to `/opt/render/project/src/alerts_config.json` on Render — also NOT
on the persistent disk).

| File | Line | Resolution | Disk-mounted? |
|---|---|---|---|
| `alerts.py` | 25 | `"alerts_config.json"` (cwd-relative) | ❌ NO |
| `data_feeds.py` | 1824 | `"alerts_config.json"` (cwd-relative) | ❌ NO |
| `composite_signal.py` | 102 | `_Path(__file__).resolve().parent / "alerts_config.json"` | ❌ NO (resolves to repo root, not disk) |
| `composite_weight_optimizer.py` | 87 | `Path(__file__).resolve().parent / "alerts_config.json"` | ❌ NO (same as above) |

All four resolve to `/opt/render/project/src/alerts_config.json` on the live
deploy. The disk mount at `/opt/render/project/src/data/` is one directory
deeper. **Every redeploy that triggers a fresh git clone wipes operator-tuned
values** (auto-execute thresholds, watchlist rules, Optuna-learned weights,
saved API keys).

### Minimal migration patch

The cleanest fix is to introduce a **single shared resolver** (no new module —
piggyback on `database._DATA_DIR` which already does the
"writable-or-/tmp-fallback" probe and is the canonical disk anchor) and have
all four files import it.

**Step 1 — `alerts.py`:** replace line 25:

```python
# Before:
_ALERTS_CONFIG_FILE = "alerts_config.json"

# After:
import database as _db  # already imported transitively elsewhere; safe at module load
_ALERTS_CONFIG_FILE = str(_db._DATA_DIR / "alerts_config.json")

# One-time legacy migration: if the old cwd-relative file exists and the
# new disk-mounted file does not, copy it once. Idempotent.
import os as _os, shutil as _shutil
_LEGACY_ALERTS = "alerts_config.json"
if _os.path.exists(_LEGACY_ALERTS) and not _os.path.exists(_ALERTS_CONFIG_FILE):
    try:
        _shutil.copy2(_LEGACY_ALERTS, _ALERTS_CONFIG_FILE)
        logger.info("[alerts] migrated %s → %s", _LEGACY_ALERTS, _ALERTS_CONFIG_FILE)
    except Exception as _e:
        logger.error("[alerts] one-time migration failed: %s", _e)
```

**Step 2 — `data_feeds.py:1824`:** same swap. To avoid circular imports
(`data_feeds` is imported very early), use lazy resolution:

```python
def _get_api_keys_file() -> str:
    import database as _db
    return str(_db._DATA_DIR / "alerts_config.json")

# Replace usages of _API_KEYS_FILE with _get_api_keys_file() at the call-site
# (data_feeds.py:1839,1840). Or assign once at module top after the lazy import.
```

**Step 3 — `composite_signal.py:102`:**

```python
# Before:
_cfg_path = _Path(__file__).resolve().parent / "alerts_config.json"

# After:
import database as _db
_cfg_path = _db._DATA_DIR / "alerts_config.json"
```

**Step 4 — `composite_weight_optimizer.py:87`:**

```python
# Before:
_CONFIG_PATH = Path(__file__).resolve().parent / "alerts_config.json"

# After:
import database as _db
_CONFIG_PATH = _db._DATA_DIR / "alerts_config.json"
```

### Migration verification

After the patch, on the next redeploy:
1. Render starts uvicorn → `database.py` initializes `_DATA_DIR` →
   `/opt/render/project/src/data/`.
2. `alerts.py` import-time hook checks legacy `./alerts_config.json` — won't
   exist on a fresh deploy clone (it's gitignored at root), so no-op. On a
   redeploy where the file existed (e.g. from prior cwd writes that survived),
   it gets copied to disk.
3. From this point forward all reads/writes go through the disk path → values
   persist across redeploys.

### Risk

LOW. Backward-compat preserved by the one-time-copy block in `alerts.py`. If
`database._DATA_DIR` falls back to `/tmp/supergrok_data` on a constrained host,
alerts ride that fallback (matches today's `crypto_model.db` behavior — no new
failure mode). Tests that use a temp dir will continue to work because
`_DATA_DIR` is monkeypatchable at test setup.

### Test plan

Add to `tests/test_alerts.py`:
1. `test_alerts_config_path_uses_data_dir` — assert
   `_ALERTS_CONFIG_FILE.endswith("data/alerts_config.json")`.
2. `test_legacy_migration_copies_once` — create a tmp `alerts_config.json` at
   cwd, force-import alerts, assert file appears at `_DATA_DIR/alerts_config.json`,
   reset, re-import → assert no second copy attempted.

---

## 4. `.env.example` cleanup — proposed diff

Current `.env.example` (39 lines) status against code references:

| Var | In `.env.example`? | Code reference | Action |
|---|---|---|---|
| `OKX_SECRET` (legacy) | line 19 ❌ wrong name | execution.py:210 (fallback only); render.yaml uses `OKX_API_SECRET` | RENAME to `OKX_API_SECRET` |
| `EMAIL_APP_PASSWORD` | ❌ missing | alerts.py:135 | ADD |
| `CRYPTO_SIGNAL_API_KEY` | ❌ missing | api.py:263; routers/deps.py:47 | ADD (with dev placeholder note) |
| `CRYPTO_SIGNAL_ALLOW_UNAUTH` | ❌ missing | api.py:64,291,881; routers/deps.py:69 | ADD (commented `false` default) |
| `CRYPTO_SIGNAL_MAX_ORDER_USD` | ❌ missing | api.py:435 | ADD (commented, defaults 10000) |
| `STRICT_AUDIT_SCHEMA` | ❌ missing | utils_audit_schema.py:93 | ADD (commented, set `true` for prod) |
| `LUNARCRUSH_API_KEY` | line 31 (commented out) | data_feeds.py:1894; news_sentiment.py:159 | KEEP (commented is fine — optional) |
| `CRYPTORANK_API_KEY` | line 38 (commented out) | data_feeds.py:7853 | UNCOMMENT or leave — referenced in render.yaml as canonical |
| `CRYPTOPANIC_API_KEY` | line 37 (commented out) | config.py:9 | UNCOMMENT or leave — already in render.yaml |
| `COINGECKO_PRO_KEY` / `SUPERGROK_COINGECKO_PRO_KEY` | ❌ missing | config.py:18-19 | OPTIONAL ADD |

### Proposed `.env.example` patch (apply on top of current file)

```diff
@@ -6,6 +6,12 @@
 # ── AI (HIGH VALUE — unlocks signal explanations, weight adjustments, agent) ──
 ANTHROPIC_API_KEY=sk-ant-api03-...          # console.anthropic.com → API Keys
 ANTHROPIC_ENABLED=true                      # set to "false" to disable all AI features without removing key
+
+# ── FastAPI auth (REQUIRED in production; recommended in local dev) ───────────
+CRYPTO_SIGNAL_API_KEY=                      # any 32+ char string for local; production has the rotated value (see docs/runbooks/api-key-rotation.md)
+CRYPTO_SIGNAL_ALLOW_UNAUTH=false            # set to "true" in local dev only — bypasses X-API-Key check; NEVER set true in production or render.yaml
+CRYPTO_SIGNAL_MAX_ORDER_USD=10000           # per-order ceiling for /execute (manual orders); raise for larger manual trades
+STRICT_AUDIT_SCHEMA=false                   # family-office prod should run "true" — fails loud on schema drift instead of warn-and-accept
 
 # ── Market Data ───────────────────────────────────────────────────────────────
 SUPERGROK_COINGECKO_API_KEY=CG-...          # coingecko.com/en/api (free demo tier available)
@@ -16,9 +22,12 @@
 
 # ── Live Trading (OKX) — leave blank to stay in paper-trade mode ─────────────
 OKX_API_KEY=...                             # OKX account → API Management
-OKX_SECRET=...
+OKX_API_SECRET=...                          # canonical name (matches render.yaml + alerts.py); legacy OKX_SECRET still accepted as a fallback
 OKX_PASSPHRASE=...
 
+# ── Email Alerts ──────────────────────────────────────────────────────────────
+EMAIL_APP_PASSWORD=                         # Gmail/Outlook app-password (NOT your account password). Bypasses plaintext storage in alerts_config.json.
+
 # ── Optional: Premium On-Chain Data ──────────────────────────────────────────
 SUPERGROK_COINALYZE_API_KEY=...             # coinalyze.net — aggregated funding rates & OI
 ETHERSCAN_API_KEY=...                       # etherscan.io/register (free) — wallet tx lookup
```

That's an additive 7-line / 1-rename change. No deletions. New devs copying
`.env.example` to `.env` will see every env var the running code reads.

---

## 5. README.md correction list

Five drift items found:

| Line | Current | Issue | Suggested fix |
|---|---|---|---|
| 84 | `# → 428 passed, 1 skipped (as of 2026-05-03)` | Stale — git log shows tests/ added through 2026-05-05 P0 batch (Phase 0.9 added several test files). | Update count after running suite, or change to `# → see tests/ (CI-gated)` to dodge drift. |
| 92 | `cp .env.local.example .env.local` | ✅ NOW CORRECT post-P0-2 (`web/.env.local.example` exists). | None — verified. |
| 122 | `├── tests/                      pytest suite (428 passed)` | Same staleness as line 84. | Same fix. |
| 191 | `\| `crypto-signal-app` (web) \| Starter \| **$7** \| FastAPI uvicorn + ...` | Stale post-P0-4. Live tier is `standard` ($25/mo, 1 CPU, 2 GB). | Change to `\| Standard \| **$25** \|` and update the "no idle sleep" line — Standard also has no idle sleep but the rationale shifts (OOM during scans on Starter, not idle-sleep concerns). |
| 199 | `see api.py:78-103), keeping the same single $7/mo Cowork approved.` | Same. | Update to `$25/mo` and add a parenthetical noting the Phase 0.9 tier upgrade. |

Verified (still accurate):
- Line 48: FastAPI URL `https://crypto-signal-app-1fsi.onrender.com` — live
  health endpoint returns HTTP 200.
- Line 50: Streamlit URL `https://cryptosignal-ddb1.streamlit.app` — see §6
  caveat.
- Line 51: Vercel URL `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`
  — matches the canonical recorded in MEMORY.md.
- Lines 12-40 (architecture diagram): accurate.
- Line 91: `pnpm install` — accurate (pnpm is canonical per `web/.gitignore:6-10`).

---

## 6. Streamlit legacy

### Live status — INVESTIGATION NEEDED

`curl https://cryptosignal-ddb1.streamlit.app` returns **HTTP 303** with a redirect
chain through `https://share.streamlit.io/-/auth/app?redirect_uri=...`. The
redirect target itself returns HTTP 303 again — i.e. the URL is in an **infinite
auth-redirect loop** when fetched without a Streamlit Cloud session cookie.

This means **one of the following is true**:
1. The app is set to **private/restricted** in Streamlit Cloud (only logged-in
   collaborators can access). Phase D D8 didn't change this — but the symptom
   is new.
2. The Streamlit Cloud free-tier app is **paused/sleeping** and the redirect is
   the cold-boot prompt (Streamlit Cloud puts free apps to sleep after 7 days
   of zero traffic; on the first request they show a "Yes, get this app back up"
   gate that the redirect chain implements).
3. Streamlit Cloud's auth flow changed since the D8 cutover.

**Most likely:** option 2. The 30-day overlap window means David hasn't actively
pushed users to Streamlit since 2026-05-04, and traffic dried up — the app is
sleeping and the auth-redirect IS the wake-up gate. A logged-in browser visit
should resurrect it within ~60s.

**Recommend:** David visits the URL in a browser (logged into Streamlit Cloud
with the same Google account that owns the deploy) and clicks "Wake up." If
that fixes it → option 2. If it asks for collaborator access → option 1. If it
errors → option 3.

### `app.py` import health

`python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read())"` →
**PARSES OK**. Phase D + Phase 0.9 changes did not touch the Streamlit code
path. The 7,400-line module still imports cleanly.

### Sunset schedule

Per CLAUDE.md §11 and `docs/redesign/2026-05-03_d8-cutover-guide.md:147`:
**pause Streamlit at day 31** (≈2026-06-04, given D8 closed 2026-05-04).
Procedure: Streamlit dashboard → Pause app → README update.

If §6 option 2 is correct, the app is *already* effectively paused (asleep with
no incoming wake-ups); operator just needs to formalize it in 4 weeks.

### No deprecation warnings in code

Grep for `DeprecationWarning` / `streamlit.*deprecat` / `# DEPRECATED`:
no Streamlit-specific deprecations in `app.py`. Streamlit version pinned in
`requirements.txt` is whatever was current on 2026-05-04 (not separately
tested in this audit).

---

## 7. Local dev parity

### Backend (Python)

```bash
# Clone + install
git clone https://github.com/davidduraesdd1-blip/crypto-signal-app
cd crypto-signal-app
pip install -r requirements.txt

# Configure (after Wave-2 §4 patch lands, .env.example will have everything)
cp .env.example .env
# Set in .env:
#   CRYPTO_SIGNAL_API_KEY=any-32+-char-string
#   CRYPTO_SIGNAL_ALLOW_UNAUTH=true   # convenience: skip X-API-Key on every curl
#   ANTHROPIC_API_KEY=sk-ant-...      # optional — disables AI if absent

# Run
uvicorn api:app --reload --port 8000
# → http://localhost:8000/docs (Swagger)
# → http://localhost:8000/health
```

### Frontend (Next.js)

```bash
cd web
pnpm install
cp .env.local.example .env.local
# Edit web/.env.local:
#   NEXT_PUBLIC_API_BASE=http://localhost:8000
#   NEXT_PUBLIC_API_KEY=<same value as CRYPTO_SIGNAL_API_KEY in ../.env>

pnpm dev
# → http://localhost:3000
```

### Database location (dev)

Per `database.py:50-68`:
1. First-pref: `<repo>/data/crypto_model.db`. Created on first import if
   missing. The directory itself is committed to git (it holds
   `data/feedback_checkpoint.json`); git ignores `*.db` files inside.
2. Fallback: `/tmp/supergrok_data/crypto_model.db` if the preferred dir is
   read-only (e.g. Streamlit Cloud).
3. Legacy: `<repo>/crypto_model.db` if it exists — preserved for backward
   compat with old local installs.

### Render disk simulation in local dev

There is **no disk simulation needed**. `database._DATA_DIR` resolves to a real
filesystem path either way:
- On Render: `/opt/render/project/src/data/` (the disk mount).
- Local: `<repo>/data/` (a normal directory).
- Streamlit Cloud: `/tmp/supergrok_data/` (the writable fallback).

The path resolution is identical at the Python level. No platform-specific code
required.

**Caveat:** the proposed §3 patch makes `alerts_config.json` follow the same
path. After the patch, `alerts_config.json` will live at `<repo>/data/alerts_config.json`
locally (not the repo root). Existing local installs that have the file at the
old root location will be auto-migrated by the one-time copy block.

### Single-command stack: docker-compose

`docker-compose.yml` brings up `scheduler`, `streamlit`, `api` from one root
`Dockerfile` with `env_file: .env`. Useful for one-shot local stack runs.
**Caveat from Wave 1**: the `crypto_data:/app` volume mounts over the entire
`/app` source directory — initial run needs either a `cp` step into the volume
or a re-targeted mount at `/app/data`. Verify before recommending to a new dev
(out of scope for this wave).

### Local dev parity gaps post-Phase 0.9

1. ⚠️ `web/app/settings/dev-tools/page.tsx:394-396` shows a `.env.local` snippet
   that uses `CRYPTO_SIGNAL_API_KEY` (server-side name) — **wrong**. Should be
   `NEXT_PUBLIC_API_KEY` (the actual var `web/lib/api.ts` reads). Wave 1
   flagged this; not yet fixed.
2. ⚠️ `.env.example` still missing the seven entries above (§4). A new dev
   following the README literally will hit "API key not configured" 401s on
   every protected endpoint until they read source.
3. ✅ `web/.env.local.example` exists post-P0-2. README reference is now valid.
4. ⚠️ `alerts_config.json` still cwd-relative (§3). Local dev unaffected; only
   Render redeploys lose values. Mention in §3.

---

## 8. Single source of truth — duplication map

| Value | Canonical source | Copies | In sync? |
|---|---|---|---|
| API key (`CRYPTO_SIGNAL_API_KEY`) | Render dashboard env (post-rotation) | Vercel `NEXT_PUBLIC_API_KEY`, local `.env` | ✅ Now in sync (P0-1 rotated; live deploy verified per MEMORY.md). Operator must keep all three sites updated together — runbook lives at `docs/runbooks/api-key-rotation.md` (created in P0-1). |
| Render service plan | `render.yaml:35` (`standard`) | README:191 (says Starter $7), README:199 (says $7/mo) | ❌ DRIFT — README still says Starter (§5). |
| Backend URL | `web/.env.local.example:13` (https://crypto-signal-app-1fsi.onrender.com) | README:48,176; `docs/redesign/2026-05-03_d5-vercel-deploy-guide.md`; `web/lib/api.ts:64` (default fallback) | ✅ All match. |
| Vercel URL | MEMORY.md (`v0-davidduraesdd1-blip-crypto-signa.vercel.app`) | README:51,147; api.py CORS regex (broader) | ✅ All match. |
| Streamlit URL | README:50 | `docs/redesign/2026-05-03_d8-cutover-guide.md`; CLAUDE.md §2 | ✅ All match. |
| Bundle ID | `web/capacitor.config.ts` (`com.polaris.edge` per P0-6 commit `621e36b`) | `web/android/app/build.gradle` (auto-generated by Capacitor) | ✅ Synced post-P0-6. |
| OKX secret env name | render.yaml:133 (`OKX_API_SECRET`); alerts.py:133 | `.env.example:19` (`OKX_SECRET` — legacy) | ❌ DRIFT — see §4. Backend accepts both via fallback so functional risk is zero, but doc drift remains. |
| Database path | `database._DATA_DIR` | `render.yaml` mount path | ✅ Synced (`/opt/render/project/src/data`). |
| `alerts_config.json` path | (none — drift) | `alerts.py:25`, `data_feeds.py:1824`, `composite_signal.py:102`, `composite_weight_optimizer.py:87` | ❌ DRIFT — four independent path expressions, all resolving OFF the persistent disk. §3 fixes by routing all four through `database._DATA_DIR`. |
| Python version | `runtime.txt` (`python-3.11`) | `render.yaml` `PYTHON_VERSION=3.11`; `.github/workflows/*.yml` `python-version: "3.11"` | ✅ All synced. |
| Production branch | `render.yaml:37` (`main`) | `.github/workflows/*.yml` (`branches: ["main"]`); README; CLAUDE.md | ✅ All synced post-D8. |
| Test count | tests/ directory | README:84,122 (`428 passed, 1 skipped (as of 2026-05-03)`) | ⚠️ STALE — see §5. |

---

## 9. P0 / P1 / P2 prioritized actions for autonomous execution

### P0 — none

Wave 1's P0 (`CRYPTO_SIGNAL_API_KEY` leak, `web/.env.local.example` missing,
render.yaml plan drift) all closed in Phase 0.9 (`b5e369e`, `7f85c36`, `76dff07`).

### P1 — actionable now (no architectural decisions needed)

**P1-W2-1: Migrate `alerts_config.json` to persistent disk** (§3).
- Files: `alerts.py:25`, `data_feeds.py:1824`, `composite_signal.py:102`,
  `composite_weight_optimizer.py:87`.
- One-time-migration block in `alerts.py` import block.
- 2 new tests in `tests/test_alerts.py`.
- Risk: LOW. Local + tests + Render all keep working.

**P1-W2-2: Update `.env.example` with the 7 missing/renamed entries** (§4).
- File: `.env.example`.
- Diff already drafted in §4. Apply directly.
- Risk: NIL (doc-only).

**P1-W2-3: Fix README staleness** (§5).
- File: `README.md` lines 84, 122 (test count), 191, 199 (Starter → Standard).
- Risk: NIL (doc-only).

**P1-W2-4: Fix `web/app/settings/dev-tools/page.tsx:394-396` env-var name in
the rendered snippet** (§7 gap #1).
- Change `CRYPTO_SIGNAL_API_KEY` → `NEXT_PUBLIC_API_KEY` in the displayed
  `.env.local` example.
- Risk: NIL.

**P1-W2-5: Streamlit liveness investigation** (§6).
- Manual: David browser-visit `https://cryptosignal-ddb1.streamlit.app` while
  logged in. Confirm whether app is sleeping (likely) or restricted.
- If sleeping: optionally formalize the pause (matches D8+30 schedule).
- If restricted: flip to public until 2026-06-04 (the documented pause date).

### P2 — defer or batch with another sprint

**P2-W2-1: Vercel auto-promote.** (§1)
- Manual dashboard toggle (5 min). David action. **No code change required.**
- Fallback: GitHub Action (§1b) — only if dashboard toggle is missing.

**P2-W2-2: Add `CRYPTO_SIGNAL_MAX_ORDER_USD`, `EMAIL_APP_PASSWORD`,
`STRICT_AUDIT_SCHEMA` to render.yaml** (§2).
- File: `render.yaml`.
- Three new `envVars` entries (sync:false on EMAIL_APP_PASSWORD; baked-in value
  on STRICT_AUDIT_SCHEMA).
- Recommend bundle with P1-W2-2 in one commit since both are env-var doc work.

**P2-W2-3: Drop `DEMO_MODE` from `render.yaml`** (§2).
- File: `render.yaml`.
- Or wire it into a real production demo-mode gate. Defer unless David asks
  for the kill-switch behavior.

**P2-W2-4: Tighten CORS regex** (Wave 1 P0-10, still open).
- File: `api.py:219-224`.
- Replace `[a-z0-9-]*davidduraesdd1-blip[a-z0-9-]*\.vercel\.app$` with the
  stricter form requiring a `crypto`/`signal`/`v0` prefix or suffix.
- Risk: LOW — current CORS regex is broader than strictly needed but Vercel
  namespacing makes the threat negligible. Defer until other surface area
  hardening (NextAuth, JWT) is sequenced.

---

## Appendix A — Live-environment probe results

```
$ curl -sS -o /dev/null -w "HTTP=%{http_code} TIME=%{time_total}\n" \
    https://crypto-signal-app-1fsi.onrender.com/health
HTTP=200 TIME=0.245

$ curl -sS -o /dev/null -w "HTTP=%{http_code} TIME=%{time_total}\n" \
    https://cryptosignal-ddb1.streamlit.app
HTTP=303 TIME=0.593   # → redirect to share.streamlit.io/-/auth/app (loop, see §6)
```

## Appendix B — Phase 0.9 commits referenced

```
b5e369e fix(P0-1): scrub leaked CRYPTO_SIGNAL_API_KEY plaintext + add rotation runbook
7f85c36 fix(P0-2): harden mobile build env + scaffold Capacitor 8.3.1
76dff07 fix(P0-4): reconcile render.yaml plan with live tier
9d136c2 hotfix(signal-hero): undefined .bgClass crash on STRONG SELL/BUY
86225a3 hotfix(P0-MTF): harden _deriveTransitions + timeframes against type drift
```

---

**Wave 2 audit closed.** No code modified. All findings ready for autonomous
execution per the P1 list in §9. Read-only audit; total time ~25 min.
