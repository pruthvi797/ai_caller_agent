from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import Base, engine
from app.models import (
    dealership, user, car_model, campaign, lead,
    document, call, agent_config, campaign_documents, document_chunk
)
from app.api import auth_routes, dealership_routes, car_routes

app = FastAPI(
    title="AI Caller Agent",
    description="AI-powered automobile dealership calling platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(auth_routes.router)
app.include_router(dealership_routes.router)
app.include_router(car_routes.router)


@app.get("/")
def root():
    return {"message": "AI Caller Agent Backend Running", "docs": "/docs"}
