from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_routes import router as auth_router
from app.api.dealership_routes import router as dealership_router
from app.api.car_routes import router as car_router
from app.api.document_routes import router as document_router       # Day 3
from app.api.knowledge_base_routes import router as kb_router       # Day 3
from app.api.campaign_routes import router as campaign_router       # Day 4
from app.api.agent_routes import router as agent_router             # Day 5

try:
    from app.api.call_routes import router as call_router           # Day 6
    _has_calls = True
except ImportError:
    _has_calls = False

app = FastAPI(
    title="AI Caller Agent — Suzuki Dealership Platform",
    description=(
        "Backend API for managing dealerships, car inventory, "
        "documents, knowledge bases, campaigns, leads, and AI agent configuration."
    ),
    version="4.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Allows the React frontend (localhost:3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",   # Vite default fallback
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(dealership_router)
app.include_router(car_router)
app.include_router(document_router)     # /documents
app.include_router(kb_router)           # /kb
app.include_router(campaign_router)     # /campaigns  ← Day 4
app.include_router(agent_router)        # /agents     ← Day 5

if _has_calls:
    app.include_router(call_router)     # /calls      ← Day 6


@app.get("/")
def root():
    return {
        "app": "AI Caller Agent — Suzuki Dealership Platform",
        "version": "4.0.0",
        "docs": "/docs",
        "status": "running",
        "cors": "enabled for localhost:3000",
    }