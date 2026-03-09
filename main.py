from fastapi import FastAPI
from app.api.auth_routes import router as auth_router
from app.api.dealership_routes import router as dealership_router
from app.api.car_routes import router as car_router
from app.api.document_routes import router as document_router       # Day 3
from app.api.knowledge_base_routes import router as kb_router       # Day 3
from app.api.campaign_routes import router as campaign_router       # Day 4
from app.api.agent_routes import router as agent_router             # Day 5

app = FastAPI(
    title="AI Caller Agent — Suzuki Dealership Platform",
    description=(
        "Backend API for managing dealerships, car inventory, "
        "documents, knowledge bases, campaigns, leads, and AI agent configuration."
    ),
    version="3.0.0",
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(dealership_router)
app.include_router(car_router)
app.include_router(document_router)     # /documents
app.include_router(kb_router)           # /kb
app.include_router(campaign_router)     # /campaigns  ← Day 4
app.include_router(agent_router)        # /agents     ← Day 5


@app.get("/")
def root():
    return {
        "app": "AI Caller Agent — Suzuki Dealership Platform",
        "version": "3.0.0",
        "docs": "/docs",
        "status": "running",
        "modules": [
            "auth", "dealership", "cars",
            "documents", "knowledge_base",
            "campaigns", "leads",
            "agent_configuration",          # Day 5 ← NEW
        ],
        "elevenlabs_integration": "Day 5 — Agent config, prompt engineering, KB sync",
        "call_engine": "Day 6 — Coming next",
    }
