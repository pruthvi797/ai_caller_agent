from fastapi import FastAPI
from app.core.database import Base, engine

from app.models import (
    dealership,
    user,
    car_model,
    campaign,
    lead,
    document,
    call,
    agent_config,
    campaign_documents,
    document_chunk
)
from app.api import auth_routes, dealership_routes, car_routes



app = FastAPI()

@app.get("/")
def root():
    return {"message": "AI Caller Agent Backend Running"}

app.include_router(auth_routes.router)
app.include_router(dealership_routes.router)
app.include_router(car_routes.router)
Base.metadata.create_all(bind=engine)