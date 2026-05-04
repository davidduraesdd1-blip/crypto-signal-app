# Crypto Signal App

Composite signal engine + Next.js dashboard for crypto + DeFi signals.
Layered indicator stack (technical + macro + sentiment + on-chain) feeding
a single BUY / HOLD / SELL output per pair.

**Status (2026-05-04):** Phase D **CLOSED** — Streamlit retired to 30-day
fallback, Next.js + FastAPI is the primary stack, production lives on `main`.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Next.js 16 (web/)                          Streamlit (app.py)           │
│  ─────────────────                          ──────────────────           │
│  app router + shadcn/ui                     legacy UI — retiring D8      │
│  TanStack Query v5                          stays live 30 days post-D8   │
│  deploys → Vercel                           deploys → Streamlit Cloud    │
│                  │                                  │                    │
│                  ▼   X-API-Key                      ▼                    │
│  ─────────────────────────────────────────────────────                   │
│  FastAPI (api.py + routers/)                                             │
│  ─────────────────────────                                               │
│  ~30 endpoints across 6 routers                                          │
│  /home /signals /regimes /onchain /alerts /ai /settings                  │
│  /diagnostics /exchange /execute                                         │
│  deploys → Render                                                        │
│                  │                                                       │
│                  ▼                                                       │
│  ─────────────────────────────────────────────────────                   │
│  Engine (composite_signal.py + crypto_model_core.py)                     │
│  ────────────────────────────────────────────────                        │
│  4 layers: Technical · Macro · Sentiment · On-chain                      │
│  HMM regime detection · Optuna-tuned weights                             │
│  agent.py (LangGraph) drives autonomous trading via execution.py         │
│  database.py (SQLite WAL) for signal history + paper trades              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Live deploys

| Surface | URL | Auth |
|---|---|---|
| FastAPI (production) | https://crypto-signal-app-1fsi.onrender.com | `X-API-Key` header required on protected routes |
| FastAPI `/health` | https://crypto-signal-app-1fsi.onrender.com/health | public |
| Streamlit (legacy) | https://cryptosignal-ddb1.streamlit.app | session-state |
| Next.js (Vercel — **primary**) | https://v0-davidduraesdd1-blip-crypto-signa.vercel.app | `NEXT_PUBLIC_API_KEY` env var → forwarded as `X-API-Key` |

---

## Quick start — local dev

### Python side (FastAPI + engine)

```bash
# Clone + install
git clone https://github.com/davidduraesdd1-blip/crypto-signal-app
cd crypto-signal-app
pip install -r requirements.txt

# Configure secrets (copy + edit)
cp .env.example .env
# At minimum, set:
#   ANTHROPIC_API_KEY=...   (optional — disables AI features if absent)
#   CRYPTO_SIGNAL_API_KEY=  (any 32+ char string for local; production has a real one)
#   CRYPTO_SIGNAL_ALLOW_UNAUTH=true   (local-only — disables auth)

# Run FastAPI
python -m uvicorn api:app --reload --port 8000
# → Swagger UI: http://localhost:8000/docs

# Run Streamlit (legacy UI — same engine, different presentation)
streamlit run app.py

# Run scheduler (autonomous scan loop — separate process)
python scheduler.py

# Run tests
python -m pytest -x
# → 428 passed, 1 skipped (as of 2026-05-03)
```

### Next.js side (web/)

```bash
cd web
pnpm install            # uses pnpm-lock.yaml; npm install also works
cp .env.local.example .env.local
# Edit .env.local:
#   NEXT_PUBLIC_API_BASE=http://localhost:8000
#   NEXT_PUBLIC_API_KEY=<same value as CRYPTO_SIGNAL_API_KEY in .env above>

pnpm dev                # → http://localhost:3000
pnpm build              # → production build
pnpm test               # → vitest (api-contract drift-guard against live API)
pnpm test:contract      # → contract test only
```

---

## Repository layout

```
.
├── api.py                      FastAPI app + legacy /signals /scan /execute routes
├── app.py                      Streamlit UI (retiring at D8 + 30-day overlap)
├── scheduler.py                Autonomous scan loop (apscheduler)
├── agent.py                    LangGraph agent state machine
├── composite_signal.py         §22 gold reference for signal aggregation
├── crypto_model_core.py        Technical indicators + scan orchestrator
├── cycle_indicators.py         Cycle / trend math (LA-1 closed-bar pivots in top_bottom_detector.py)
├── execution.py                Paper + live order execution (OKX via ccxt)
├── database.py                 SQLite WAL connection pool + schema
├── alerts.py                   Email alerts + alerts_config persistence + RLock
├── data_feeds.py               OHLCV + macro + on-chain fetchers (CCXT, Glassnode, etc.)
├── llm_analysis.py             Claude prompt builders (XML-tagged untrusted blocks)
├── routers/                    Phase D-1 FastAPI routers (home/signals/regimes/...)
├── tests/                      pytest suite (428 passed)
├── web/                        Next.js 16 frontend (Phase D-3+ via v0)
│   ├── app/                    App-router pages (15 routes)
│   ├── components/             v0-generated UI + shadcn primitives
│   ├── hooks/                  TanStack Query hooks (one per page section)
│   ├── lib/                    api.ts (typed client) + format.ts + query-client.ts
│   ├── providers/              QueryProvider + AppProviders (theme + level)
│   └── tests/                  vitest config + api-contract drift-guard
├── docs/
│   ├── redesign/               Phase D plans + handoff briefings
│   ├── audits/                 §4 audit reports + deferred-fix proposals
│   └── signal-regression/      §22 backtest diff baselines
└── shared-docs/                Cross-app deployment checklists
```

---

## Phase D status

| Stage | Status | Deliverable |
|---|---|---|
| D1 — FastAPI scaffold | ✅ closed | 6 routers + tests |
| D2 — Render deploy | ✅ closed | Live API + auth verified |
| D3 — v0 mockups exported | ✅ closed | `web/` directory + 15 routes |
| D4 — Wire frontend to FastAPI | ✅ closed | TanStack hooks + 3 form mutations + contract test |
| D5 — Vercel deploy | ✅ closed | https://v0-davidduraesdd1-blip-crypto-signa.vercel.app |
| D6 — Security + perf pass | ✅ closed | All routes Lighthouse a11y 100; `docs/redesign/2026-05-04_d6-security-perf-results.md` |
| D7 — §22 regression diff | ✅ compliance reviewed | `docs/signal-regression/2026-05-03-d7-section22-compliance-review.md` |
| D8 — Cutover | ✅ closed 2026-05-04 | merge `be4afb3` → main; render.yaml flipped to `main`; 30-day Streamlit overlap active |

Master plan: `docs/redesign/2026-05-02_phase-d-streamlit-retirement.md`

---

## Key docs

- **CLAUDE.md** (root) — agent rules, sprint protocol, audit standards
- **docs/redesign/2026-05-02_phase-d-streamlit-retirement.md** — master plan
- **docs/redesign/2026-05-02_d1-api-audit.md** — endpoint inventory
- **docs/redesign/2026-05-02_phase-d-d4-code-wire-plan.md** — D4 binding map
- **docs/redesign/2026-05-03_d5-vercel-deploy-guide.md** — your D5 paste-ready
- **docs/redesign/2026-05-03_d6-security-perf-checklist.md** — D6 fire-when-D5-lands
- **docs/audits/** — every §4 audit report (8 today)
- **docs/signal-regression/** — §22 backtest baselines

---

## Deploy URLs cheat sheet

```bash
# FastAPI health
curl https://crypto-signal-app-1fsi.onrender.com/health

# FastAPI signals (auth-required)
curl -H "X-API-Key: $CRYPTO_SIGNAL_API_KEY" https://crypto-signal-app-1fsi.onrender.com/signals

# Streamlit (legacy)
open https://cryptosignal-ddb1.streamlit.app

# Vercel (after D5)
# Set in Vercel dashboard env vars:
#   NEXT_PUBLIC_API_BASE = https://crypto-signal-app-1fsi.onrender.com
#   NEXT_PUBLIC_API_KEY  = <same as CRYPTO_SIGNAL_API_KEY in Render env>
```

## Render services + costs

| Service | Plan | Cost/mo | Purpose |
|---|---|---|---|
| `crypto-signal-api` (web) | Free | $0 | FastAPI uvicorn — sleeps after 15min idle |
| `crypto-signal-scheduler` (worker) | Starter | **$7** | Long-lived `python scheduler.py` — runs the full autoscan pipeline (run_scan + append_to_master + feedback loop + position updates + alerts). |
| Persistent disk `crypto-signal-data` | 1 GB | included | Mounted at `/opt/render/project/src/data` on **both** services — covers `crypto_model.db` and `data/scheduler.log`. |

The worker tier closes Cowork's 2026-05-04 Outcome C decision — see
`docs/audits/2026-05-04_scheduler-inventory.md` for the rationale.
Cross-process SQLite contention is handled via WAL mode +
`PRAGMA busy_timeout=5000` in `database.py:81-93`; no app-level retry
needed.

---

## License + ownership

Private repository. Family-office-internal — not for redistribution.
Operator: David Duraes.
