from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.car_model import CarModel
from app.core.database import get_db

router = APIRouter(prefix="/cars", tags=["Cars"])


@router.post("/")
def create_car(model_name: str, db: Session = Depends(get_db)):

    car = CarModel(model_name=model_name)

    db.add(car)
    db.commit()
    db.refresh(car)

    return car


@router.get("/")
def get_cars(db: Session = Depends(get_db)):
    return db.query(CarModel).all()