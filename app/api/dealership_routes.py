from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.dealership import Dealership
from app.core.database import get_db

router = APIRouter(prefix="/dealership", tags=["Dealership"])


@router.get("/{dealership_id}")
def get_dealership(dealership_id: str, db: Session = Depends(get_db)):
    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == dealership_id
    ).first()

    return dealership


@router.put("/{dealership_id}")
def update_dealership(dealership_id: str, name: str, db: Session = Depends(get_db)):

    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == dealership_id
    ).first()

    if not dealership:
        raise HTTPException(status_code=404, detail="Dealership not found")

    setattr(dealership, "name", name)

    db.commit()
    db.refresh(dealership)

    return dealership