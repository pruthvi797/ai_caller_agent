from fastapi import FastAPI
from app.api.auth_routes import router as auth_router
from app.api.dealership_routes import router as dealership_router
from app.api.car_routes import router as car_router
from app.api.document_routes import router as document_router       # Day 3
from app.api.knowledge_base_routes import router as kb_router       # Day 3

app = FastAPI(
    title="AI Caller Agent — Suzuki Dealership Platform",
    description="Backend API for managing dealerships, car inventory, documents, and AI knowledge bases.",
    version="1.0.0",
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(dealership_router)
app.include_router(car_router)
app.include_router(document_router)   # /documents
app.include_router(kb_router)         # /kb


@app.get("/")
def root():
    return {
        "app": "AI Caller Agent — Suzuki Dealership Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }