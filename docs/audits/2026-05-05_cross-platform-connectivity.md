# Tier 8 — Cross-Platform Connectivity
**Date:** 2026-05-05
**Methodology:** Read-only audit of `render.yaml`, `web/.gitignore`, root `.env.example`, root `.gitignore`, `api.py` (CORS + auth boot), `database.py` (DB path), `alerts.py` (sensitive-env map + alerts_config path), `scheduler.py` (log path), `web/lib/api.ts` + `web/app/**` (frontend env refs), `web/capacitor.config.ts`, `docker-compose.yml`, `README.md`, and `docs/redesign/2026-05-03_d5-vercel-deploy-guide.md`. Cross-referenced every `os.environ.get` / `os.getenv` call in `*.py` and every `process.env.*` reference in `web/`. Tested the CORS regex against eight candidate origin strings.

## Summary

- Render env vars inventoried: **18** (in `render.yaml`)
- Vercel env vars inventoried: **2** (`NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_API_KEY`)
- Drift findings: **8** (3 name-drift, 2 declared-but-unused, 3 referenced-but-undeclared)
- Secrets exposure risks: **2 CRITICAL** (live API key value committed to two `docs/redesign/` markdown files; see "Secrets hygiene" below)
- CORS coverage gaps: **0** for the canonical Vercel URL, **1 watch-item** (regex admits any `*davidduraesdd1-blip*.vercel.app` subdomain — already broader than strictly needed; no exploitable gap)
- Persistent-disk misuse: **3** (`alerts_config.json`, `supergrok_audit.log`, `feedback_log.csv`/cwd-relative state files all write next to code, not under `data/`)
- Local-dev parity blocker: `web/.env.local.example` referenced by README but does not exist in repo

## Render env var inventory

Source: `render.yaml:48-131`. Every entry is `sync: false` (operator must paste in Render dashboard) **unless a value is shown** in the Value column — those are baked into the IaC blueprint.

| Var name | Purpose | Documented in | Value source |
|---|---|---|---|
| `CRYPTO_SIGNAL_ALLOW_UNAUTH` | Bypass `X-API-Key` requirement (local dev only). render.yaml pins `false` so a one-click recreate starts closed. Read in `api.py:64,291,881`, `routers/deps.py:69`. | render.yaml comment, README:70, `routers/deps.py` docstring | render.yaml value `"false"` |
| `CRYPTO_SIGNAL_API_KEY` | Production API key for `X-API-Key` auth. Read in `api.py:263`, `routers/deps.py:47`. Env-first, then `alerts_config.json` fallback. | render.yaml comment, README:69, deploy-guide §1, `routers/deps.py:32` | dashboard (`sync: false`) |
| `CRYPTO_SIGNAL_AUTOSTART_SCHEDULER` | When `"true"`, `api.py:103` spawns scheduler in a daemon thread inside uvicorn (D8 Path A). | render.yaml comment | render.yaml value `"true"` |
| `ANTHROPIC_ENABLED` | Soft-disable LLM features without removing the key. `config.py:34` reads it. | `.env.example:8` | render.yaml value `"false"` |
| `ANTHROPIC_API_KEY` | Claude API key. `config.py:8`, `agent.py:843`, `llm_analysis.py:103,316,511`, `news_sentiment.py:50`. | `.env.example:7`, README | dashboard |
| `DEMO_MODE` | render.yaml says "match conftest.py default" — but **no production code reads it**. Only `tests/conftest.py:34` and `tests/test_api_routers.py:30` reference `DEMO_MODE`; `app.py` uses `st.session_state["demo_mode"]` (lowercase, session-state, not env). **Dead env var on the production deploy.** | render.yaml only | render.yaml value `"true"` |
| `PYTHON_VERSION` | Pin Python 3.11 for Render's auto-detect. Mirrors `runtime.txt`. | render.yaml comment | render.yaml value `"3.11"` |
| `CRYPTOPANIC_API_KEY` | News sentiment. `config.py:9`. | `.env.example:37` (commented out — drift) | dashboard |
| `SUPERGROK_COINGECKO_API_KEY` | Demo CoinGecko key. `config.py:10`. | `.env.example:11` | dashboard |
| `COINMARKETCAP_API_KEY` | CMC global metrics. `config.py:22`, `data_feeds.py:6667,6771`. | `.env.example:12` | dashboard |
| `ETHERSCAN_API_KEY` | Wallet tx lookups. `config.py:23`. | `.env.example:24` | dashboard |
| `ZERION_API_KEY` | Wallet portfolio tab. `config.py:24`. | `.env.example:15` | dashboard |
| `SUPERGROK_SENTRY_DSN` | Sentry DSN. `config.py:21`, `app.py:55`. | `.env.example:27` | dashboard |
| `CRYPTORANK_API_KEY` | Token unlocks + VC fundraising. `data_feeds.py:7853`. | `.env.example:38` (commented out — drift) | dashboard |
| `OKX_API_KEY` | Live trading. `execution.py:208`, `alerts.py` env map. | `.env.example:18` | dashboard |
| `OKX_API_SECRET` | Live trading. `execution.py:209`, `alerts.py:133`. **`.env.example:19` calls it `OKX_SECRET` — mismatch.** | render.yaml comment + alerts.py | dashboard |
| `OKX_PASSPHRASE` | Live trading. `execution.py:212`. | `.env.example:20` | dashboard |
| (implicit) `PORT` | Bound by Render runtime; consumed in `startCommand: uvicorn ... --port $PORT`. | render.yaml | platform |

## Vercel env var inventory

Source: `web/lib/api.ts:64,83`, `web/tests/api-contract.test.ts:34`, `web/app/settings/dev-tools/page.tsx:395`, deploy-guide tables.

| Var name | Purpose | NEXT_PUBLIC_? | Last known issue |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE` | FastAPI origin for browser fetches. Should equal `https://crypto-signal-app-1fsi.onrender.com` in production. | Yes (intentional — needs to be inlined into client bundle) | Earlier mismarked as "Sensitive" in Vercel UI, which prevented Next.js from inlining the value at build time. Recurring pitfall. `web/lib/api.ts:55-75` now hard-throws **in browser** when missing in production (1091ed7). |
| `NEXT_PUBLIC_API_KEY` | Sent as `X-API-Key` header on protected calls. Same value as Render's `CRYPTO_SIGNAL_API_KEY`. | Yes (deliberate D4-D8 trade-off; documented in `api.ts:11-13` as "real auth lands post-D8") | Earlier mismarked as "Sensitive" in Vercel; same inlining failure as above. `api.ts:83-95` warns in browser console when missing. |

**No non-public secrets are accidentally `NEXT_PUBLIC_` prefixed.** Only `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_API_KEY` exist, and both are intentionally exposed (the API key is acknowledged in code as a known limitation).

**No `web/.env.example` or `web/.env.local.example` exists**, even though `README.md:92` instructs `cp .env.local.example .env.local`. **Doc drift — local dev cannot follow the README literally.** The dev-tools page (`web/app/settings/dev-tools/page.tsx:394-396`) shows a `.env.local` snippet that uses `CRYPTO_SIGNAL_API_KEY` (server-side name) instead of `NEXT_PUBLIC_API_KEY` (the actual var that `lib/api.ts` reads) — second doc drift on the same surface.

## Recurring pitfall — Vercel "Sensitive" mismarking

Per the user's earlier report: when `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_API_KEY` were marked "Sensitive" in the Vercel UI, Next.js stopped inlining their values into the client bundle at build time, breaking every API call from the live frontend even though the dashboard "showed" the values were set. Sensitive vars are runtime-only on Vercel and not available to the browser. Fix is to flip them off Sensitive and re-deploy.

This recurs because Vercel's UI nudges toward Sensitive for anything that "looks like a key." Add to deploy checklist (`shared-docs/deployment-checklists/crypto-signal-app.md`) if not already there.

## Env var name drift

| Concept | Render / code canonical | `.env.example` | Notes |
|---|---|---|---|
| OKX trading secret | `OKX_API_SECRET` (render.yaml:128, alerts.py:133, execution.py:209) | `OKX_SECRET` (line 19) | B2 fix in commit `02ffaf6` made the backend accept both via `_SENSITIVE_ENV_FALLBACKS` (alerts.py:141-143). `.env.example` still shows the legacy name — should be updated to canonical. |
| CoinGecko Pro | `COINGECKO_PRO_KEY` or legacy `SUPERGROK_COINGECKO_PRO_KEY` (config.py:18-19) | not declared | Both names referenced in code; neither in `.env.example` or render.yaml. Optional/paid tier — low priority. |
| Coinalyze | `SUPERGROK_COINALYZE_API_KEY` or `COINALYZE_API_KEY` (data_feeds.py:5149) | `SUPERGROK_COINALYZE_API_KEY` (line 23) | Code accepts both; render.yaml lists neither. Falls through to free tier silently if absent. |

**Vars referenced in code but never declared in render.yaml or `.env.example`:**

- `CRYPTO_SIGNAL_API_KEY` — declared in render.yaml ✅ but **missing from `.env.example`** (README mentions it; first-time devs copying `.env.example` will not see it).
- `CRYPTO_SIGNAL_ALLOW_UNAUTH` — declared in render.yaml ✅ but missing from `.env.example`. README mentions it.
- `CRYPTO_SIGNAL_AUTOSTART_SCHEDULER` — declared in render.yaml ✅, missing from `.env.example` (probably intentional — dev shouldn't run scheduler from web import).
- `CRYPTO_SIGNAL_MAX_ORDER_USD` — referenced `api.py:435`, **not** in `.env.example` or render.yaml (defaults to `10000`). Operator who wants a tighter cap has no clue this knob exists.
- `EMAIL_APP_PASSWORD` — referenced `alerts.py:135`, **not in `.env.example` or render.yaml**. Email alerts will silently fall back to alerts_config.json plaintext (the very thing the env-var override was added to avoid).
- `STRICT_AUDIT_SCHEMA` — referenced `utils_audit_schema.py:93`, not in `.env.example` or render.yaml. Defaults to permissive ("warn-and-accept"). Family-office hardening guidance in the comment says it should be `true` — should be in `render.yaml`.
- `LUNARCRUSH_API_KEY` — referenced `data_feeds.py:1894,7841`, only in `.env.example` as a comment (line 31).

**Vars declared but never referenced (dead env on production):**

- `DEMO_MODE` (render.yaml:91) — production code does not read this env var; only test fixtures do.

## Persistent disk

`render.yaml:43-46` declares:
```
disk:
  name: crypto-signal-data
  mountPath: /opt/render/project/src/data
  sizeGB: 1
```

Render's working directory at runtime is `/opt/render/project/src/`, so `data/` resolves to the disk mount.

| File | Code reference | Path resolution on Render | On disk? |
|---|---|---|---|
| `crypto_model.db` | `database.py:50-68` (`_BASE_DIR / "data" / "crypto_model.db"`) | `/opt/render/project/src/data/crypto_model.db` | ✅ Yes |
| `scheduler.log` | `scheduler.py:43-45` (`Path(__file__).parent / "data" / "scheduler.log"`) | `/opt/render/project/src/data/scheduler.log` | ✅ Yes |
| `scheduler.lock` | `api.py:111` (`Path(_db.DB_FILE).parent / "scheduler.lock"`) | `/opt/render/project/src/data/scheduler.lock` | ✅ Yes (single-flight guard depends on this) |
| `feedback_checkpoint.json` | tracked in git at `data/feedback_checkpoint.json` | `/opt/render/project/src/data/feedback_checkpoint.json` (file in repo, but the `data/` directory is mounted over by the disk on Render — **the in-repo file is shadowed at runtime**) | ⚠️ Subtle: at first boot the disk mount is empty, so the in-repo file disappears. App must re-create it. |
| `alerts_config.json` | `alerts.py:25` (`_ALERTS_CONFIG_FILE = "alerts_config.json"` — bare relative path) | `/opt/render/project/src/alerts_config.json` (cwd, **not** `data/`) | ❌ **Not on persistent disk.** Survives only because Render's filesystem is preserved between deploys; a fresh deploy restores from git (no committed file → empty on first boot). Any UI-side edits to alerts (recipients, thresholds) are lost on redeploy. |
| `supergrok_audit.log` | `app.py:87` (`os.path.join(os.path.dirname(__file__), "supergrok_audit.log")`) | `/opt/render/project/src/supergrok_audit.log` | ❌ Not on disk. Wiped on every redeploy. (Streamlit-only — moot once Streamlit is paused on day 31.) |
| Various JSON state files (`scan_status.json`, `positions.json`, `pending_multisig.json`, `circuit_state.json`, `wallet_reservations.json`, `cross_app_positions.json`, `dynamic_weights.json`, `feedback_log.csv`, `daily_signals_master.csv`, `weights_log.csv`, `paper_trades_log.csv`, `scan_results_cache.json`) | listed in root `.gitignore:23-35` (so they're cwd-resident) | `/opt/render/project/src/<filename>` | ❌ Not on disk — wiped on redeploy. |

`data/` is **not** itself listed in the root `.gitignore` (line 14-19 catches `*.db` and `*.sqlite` only). The directory itself is committed (it holds `feedback_checkpoint.json`); only the database files inside are ignored. That's the right setup, but worth a single explicit comment in `.gitignore` so a future contributor doesn't add a blanket `data/` rule and lose the checkpoint file.

## Secrets hygiene

| Secret | Documented? | Rotation procedure documented? | Exposed in client bundle? |
|---|---|---|---|
| `CRYPTO_SIGNAL_API_KEY` | Yes — README:69, render.yaml:66, deploy guide. **CRITICAL: live value `DY0YUB3Z0qTClL5p59I49Lv-gb1zUw1r2FWzoJYFKhg` is committed in plaintext at `docs/redesign/2026-05-03_d5-vercel-deploy-guide.md:58` and `docs/redesign/2026-05-04_full-handoff-brief.md:63-64`.** Anyone with read access to the repo can call every protected endpoint until rotated. | No rotation procedure documented anywhere. | **Yes, deliberately** — `NEXT_PUBLIC_API_KEY` is inlined into the JS bundle (acknowledged trade-off in `web/lib/api.ts:11-13` and deploy-guide §70-72). |
| `OKX_API_KEY` | Yes — `.env.example:18`, render.yaml:122, alerts.py:128. | No. | No (`Grep "OKX_API_KEY"` in `web/` returns 0 hits — verified). |
| `OKX_API_SECRET` | Yes (under canonical name) in render.yaml:128, alerts.py:133. **Drift:** `.env.example:19` calls it `OKX_SECRET`. | No. | No (0 hits in `web/`). |
| `OKX_PASSPHRASE` | Yes — `.env.example:20`, render.yaml:130. | No. | No. |
| `EMAIL_APP_PASSWORD` | **No** — referenced in `alerts.py:135` but absent from `.env.example`, `render.yaml`, and `README.md`. Operator who wants email alerts has to read source. | No. | No. |
| `ANTHROPIC_API_KEY` | Yes — `.env.example:7`, render.yaml:85, README. | No. | No (verified — only referenced server-side in `agent.py`, `llm_analysis.py`, `news_sentiment.py`, `config.py`). |
| `SUPERGROK_SENTRY_DSN` | Yes — `.env.example:27`. | No. | No. |
| Other API keys (Cryptopanic, CMC, Etherscan, Zerion, CoinGecko, Cryptorank, Lunarcrush) | Mixed — see drift section. | No. | No (server-side only). |

**No backend secret leaks into `web/`** — verified by searching `web/` for `OKX`, `ANTHROPIC`, `EMAIL_APP`, `CRYPTO_SIGNAL_API_KEY` (server-side name): 0 hits in code, only documentation comments.

**`gitleaks.toml` exists at repo root** but did not catch the API-key leak in `docs/redesign/*.md` — worth a follow-up to add a rule for the `DY0YUB3...` shape or `CRYPTO_SIGNAL_API_KEY = ` literal.

## CORS regex coverage

`api.py:219-224`:
```
^https://
(crypto-signal-app(-[a-z0-9-]+-davidduraesdd1-blip)?
|[a-z0-9-]*davidduraesdd1-blip[a-z0-9-]*)
\.vercel\.app$
```
Plus explicit allow-list `api.py:193-197`:
```
http://localhost:8501, http://127.0.0.1:8501,
http://localhost:3000, http://127.0.0.1:3000
```

**Tested origins (regex match results):**

| Origin | Matches? | Verdict |
|---|---|---|
| `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app` (canonical Vercel prod) | ✅ | Correct |
| `https://crypto-signal-app.vercel.app` (legacy/expected name) | ✅ | Correct |
| `https://crypto-signal-app-abc123-davidduraesdd1-blip.vercel.app` (preview-deploy shape #1) | ✅ | Correct |
| `https://v0-davidduraesdd1-blip-crypto-signal-abc123.vercel.app` (per-deploy hash variant) | ✅ | Correct |
| `https://v0-davidduraesdd1-blip-git-abc123-davidduraesdd1-projects.vercel.app` (git-branch preview) | ✅ | Correct |
| `https://attacker.vercel.app` | ❌ NO match | Correct (rejects) |
| `https://crypto-signal-attacker.vercel.app` (squatting check) | ❌ NO match | Correct |
| `https://davidduraesdd1-blip.vercel.app` (worst-case bare-owner subdomain) | ✅ | **Watch-item** — if Vercel ever lets a different account claim a project named exactly `davidduraesdd1-blip`, the regex would admit it. The owner-handle uniqueness on Vercel makes this collision unlikely, but the check leans on Vercel's namespacing rather than repo-name. |
| `http://localhost:3000` (Next.js dev) | n/a — handled by explicit `allow_origins` ✅ | Correct |
| `http://localhost:8501` (Streamlit dev) | n/a — handled by explicit `allow_origins` ✅ | Correct |
| `https://cryptosignal-ddb1.streamlit.app` | ❌ Neither regex nor allow-list | **Not needed** — Streamlit Cloud calls the Python engine in-process; it does not cross-origin fetch the FastAPI on Render. Browser tabs at the Streamlit URL talk only to the Streamlit Cloud runtime. **Confirmed correct (no change needed).** |

`allow_methods=["GET","POST","PUT","DELETE"]`, `allow_headers=["X-API-Key","Content-Type"]`, `allow_credentials=False` — all explicit and minimal. Looks good.

## Streamlit overlap

- **Backend**: yes, both UIs read the same Render-backed FastAPI / SQLite. Streamlit (`app.py`) uses Python imports directly into `crypto_model_core`, `database`, etc. Vercel (Next.js `web/`) goes through `https://crypto-signal-app-1fsi.onrender.com` as documented in `docs/redesign/2026-05-03_d8-cutover-guide.md:135-141`.
- **Database**: Streamlit Cloud has its own filesystem (cannot mount Render's disk); `app.py` calls `database.py` which probes `data/` for write access and falls back to `/tmp/supergrok_data` (database.py:52-60). **Streamlit and Render therefore have separate SQLite databases as of D8.** During the 30-day overlap, signals shown in Streamlit are computed from the Streamlit-side ephemeral DB — not from the Render-side authoritative DB that the Vercel UI reads. This is documented behavior (each platform runs its own engine), but worth flagging: a user comparing signals across the two URLs should expect drift driven by independent scan schedules, not a bug.
- **`app.py` functional?** Imports unchanged in this branch (`grep streamlit app.py | head -3` shows the standard `import streamlit as st` setup); Phase D didn't break it. Streamlit Cloud cold-start still goes through `app.py`'s 472 KB main module.
- **User landing**: there is **no automatic redirect** between the two URLs. Per `docs/redesign/2026-05-03_d8-cutover-guide.md:147`, the README simply lists Vercel as primary and Streamlit as fallback. A user with a bookmark on Streamlit will keep landing there.
- **Overlap end date**: per CLAUDE.md and the cutover guide §159 — pause Streamlit at day 31 (~2026-06-04, given D8 closed 2026-05-04). Procedure: Streamlit dashboard → Pause app → README update.

## Local dev parity

**Backend (Python):**
```bash
cp .env.example .env
# Add to .env (NOT in .env.example yet — drift):
#   CRYPTO_SIGNAL_API_KEY=any-32+-char-string
#   CRYPTO_SIGNAL_ALLOW_UNAUTH=true   # convenience: skip X-API-Key on every curl
pip install -r requirements.txt
python -m uvicorn api:app --reload --port 8000
# Streamlit (legacy):
streamlit run app.py
```

**Frontend (Next.js):**
```bash
cd web
pnpm install
# README says `cp .env.local.example .env.local` — file does not exist.
# Create web/.env.local manually with:
#   NEXT_PUBLIC_API_BASE=http://localhost:8000
#   NEXT_PUBLIC_API_KEY=<same value as CRYPTO_SIGNAL_API_KEY in ../.env>
pnpm dev   # → http://localhost:3000
```

**`docker-compose.yml`** exists at repo root and brings up three services (`scheduler`, `streamlit`, `api`) all built from the root `Dockerfile`, sharing a named volume `crypto_data:/app`. `env_file: .env` means a single `.env` at repo root drives all three. Useful for one-command local stack:
```bash
docker-compose up
# → Streamlit on :8501, FastAPI on :8000, scheduler in background
```

**Note**: docker-compose mounts `crypto_data:/app` over the entire `/app` directory, which is also where the source lives — initial run will need to either copy code into the volume or change the mount target to `/app/data`. Worth verifying before recommending to a new dev.

**Capacitor (mobile shell)** at `web/capacitor.config.ts` wraps the Next.js static export in `web/out/` for iOS/Android. Bundle ID `com.polaris-edge.app`. Uses `npm run build:mobile` then `npx cap add android` / `cap add ios`. Out of scope for this audit, listed for completeness.

## Recommended P0 fix order

1. **CRITICAL — Rotate `CRYPTO_SIGNAL_API_KEY` and scrub the leaked value from git history.** The current value `DY0YUB3Z0qTClL5p59I49Lv-gb1zUw1r2FWzoJYFKhg` is committed in `docs/redesign/2026-05-03_d5-vercel-deploy-guide.md:58` and `docs/redesign/2026-05-04_full-handoff-brief.md:63-64`. Anyone with repo read access can call every protected endpoint. Steps: (a) generate a new key, (b) update Render `CRYPTO_SIGNAL_API_KEY` and Vercel `NEXT_PUBLIC_API_KEY` together, (c) replace the committed values with `<paste-from-render-dashboard>` placeholders, (d) commit, (e) decide whether to BFG-rewrite history or accept that the rotated key + scrubbed HEAD is sufficient (the leaked key is now invalid).
2. **HIGH — Add `gitleaks` rule for the API-key shape.** The 43-char URL-safe base64 token shape evaded the existing `gitleaks.toml`. Add a custom regex `[A-Za-z0-9_-]{40,}` plus a content match on `CRYPTO_SIGNAL_API_KEY *= *[A-Za-z0-9]` and re-run pre-commit hook.
3. **HIGH — Move `alerts_config.json` to the persistent disk path.** Change `alerts.py:25` from `_ALERTS_CONFIG_FILE = "alerts_config.json"` to `os.path.join(database._DATA_DIR, "alerts_config.json")` (or equivalent). Today, alert recipients/thresholds set via the UI are silently wiped on every Render redeploy.
4. **HIGH — Fix `OKX_API_SECRET` / `OKX_SECRET` drift in `.env.example`.** Update line 19 to `OKX_API_SECRET=...` (canonical) with a comment noting the legacy alias. Backend already accepts both per B2 fix in `02ffaf6`.
5. **HIGH — Create `web/.env.local.example`.** README:92 instructs `cp .env.local.example .env.local`. Add the file with `NEXT_PUBLIC_API_BASE=http://localhost:8000` and `NEXT_PUBLIC_API_KEY=` (blank, with comment). Also fix the snippet in `web/app/settings/dev-tools/page.tsx:394-396` to use `NEXT_PUBLIC_API_KEY`, not `CRYPTO_SIGNAL_API_KEY`.
6. **MEDIUM — Document `EMAIL_APP_PASSWORD`, `STRICT_AUDIT_SCHEMA`, `CRYPTO_SIGNAL_MAX_ORDER_USD` in `.env.example` and (where prod-relevant) `render.yaml`.** Section §15 of master CLAUDE.md says family-office should run `STRICT_AUDIT_SCHEMA=true`; today it's silently `false`.
7. **MEDIUM — Drop `DEMO_MODE` from `render.yaml`** (it's not read by production code) or wire it into a real demo-mode gate in `api.py` if a hard kill-switch was the original intent. Today the env is dead and confuses operators.
8. **MEDIUM — Add Vercel "Sensitive flag" pitfall to `shared-docs/deployment-checklists/crypto-signal-app.md`** with the exact symptom ("every API call fails with NEXT_PUBLIC_API_BASE undefined in DevTools") and the fix ("uncheck Sensitive, redeploy"). Ship a 1-line CI/preview check that fetches `${NEXT_PUBLIC_API_BASE}/health` from a deployed page and fails the build if the response is not 200.
9. **MEDIUM — Document API key rotation procedure** in `README.md` or `docs/redesign/2026-05-03_d6-security-perf-checklist.md`. Steps should cover: generate new key → set in Render → set in Vercel → wait for Vercel deploy → verify 4-test curl matrix → revoke old key.
10. **LOW — Tighten the CORS regex** so the bare-owner subdomain `https://davidduraesdd1-blip.vercel.app` does not match. Replace `[a-z0-9-]*davidduraesdd1-blip[a-z0-9-]*\.vercel\.app$` with a stricter form requiring `crypto`/`signal`/`v0` prefix or owner suffix, e.g.:
    ```
    ^https://(crypto-signal-app(-[a-z0-9-]+)?|v0-davidduraesdd1-blip[a-z0-9-]*)\.vercel\.app$
    ```
    Negligible exploitable risk today (Vercel namespace would have to collide), but it tightens the security boundary at no cost.
11. **LOW — Add `data/` directory note to root `.gitignore`** explaining why `data/` itself isn't blanket-ignored (the in-repo `feedback_checkpoint.json` is intentionally tracked; only `*.db` files inside are ignored).

---

**Audit closed 2026-05-05.** No code modified. Findings ready for owner sign-off; recommended sprint: P0 fixes 1-5 in a single commit, P0 fixes 6-9 in a follow-up batch, P0 10-11 deferred unless prioritized.
