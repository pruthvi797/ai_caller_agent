import app.models

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_routes import router as auth_router
from app.api.dealership_routes import router as dealership_router
from app.api.car_routes import router as car_router
from app.api.document_routes import router as document_router
from app.api.knowledge_base_routes import router as kb_router
from app.api.campaign_routes import router as campaign_router

app = FastAPI(
    title="AI Caller Agent — Suzuki Dealership Platform",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(dealership_router)
app.include_router(car_router)
app.include_router(document_router)
app.include_router(kb_router)
app.include_router(campaign_router)   # /campaigns  ← Day 4


@app.get("/")
def root():
    return {
        "app": "AI Caller Agent — Suzuki Dealership Platform",
        "version": "2.0.0",
        "docs": "/docs",
        "status": "running",
        "modules": [
            "auth", "dealership", "cars",
            "documents", "knowledge_base",
            "campaigns", "leads"
        ]
    }