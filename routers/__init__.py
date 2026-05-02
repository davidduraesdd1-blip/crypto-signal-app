"""
routers/ — FastAPI router modules for the Phase D Next.js frontend.

Each module exposes an APIRouter that is mounted in api.py via
`app.include_router(...)`. Routers wrap the existing engine
(crypto_model_core, data_feeds, alerts, llm_analysis, database) and
expose page-level data shapes consumed by the Next.js + Tailwind +
shadcn/ui frontend deployed to Vercel.

Phase D plan: docs/redesign/2026-05-02_phase-d-streamlit-retirement.md
D1 audit:     docs/redesign/2026-05-02_d1-api-audit.md
"""
