from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.models.dealership import Dealership
from app.models.user import User
from app.schemas.dealership_schema import DealershipCreate, DealershipUpdate, DealershipResponse
from app.core.database import get_db
from app.core.security import get_current_user
from datetime import datetime
import shutil, os, uuid

router = APIRouter(prefix="/dealership", tags=["Dealership"])

UPLOAD_DIR = "uploads/logos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/create", response_model=DealershipResponse, status_code=201)
def create_dealership(
    body: DealershipCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text

    # Block if GST is already taken by a DIFFERENT user's active dealership
    if body.gst_number:
        gst_conflict = db.query(Dealership).filter(
            Dealership.gst_number == body.gst_number,
            Dealership.user_id != current_user.user_id,
            Dealership.status == "active"
        ).first()
        if gst_conflict:
            raise HTTPException(
                status_code=409,
                detail="GST number is already registered to another dealership"
            )

        # Clear GST from any closed dealership owned by THIS user so unique constraint doesn't block
        db.execute(
            text("UPDATE dealerships SET gst_number = NULL WHERE user_id = :uid AND gst_number = :gst AND status = 'closed'"),
            {"uid": str(current_user.user_id), "gst": body.gst_number}
        )
        db.commit()

    # Block if registration number is already taken by a DIFFERENT user's active dealership
    if body.registration_number:
        reg_conflict = db.query(Dealership).filter(
            Dealership.registration_number == body.registration_number,
            Dealership.user_id != current_user.user_id,
            Dealership.status == "active"
        ).first()
        if reg_conflict:
            raise HTTPException(
                status_code=409,
                detail="Registration number is already registered to another dealership"
            )

        # Clear reg number from any closed dealership owned by THIS user
        db.execute(
            text("UPDATE dealerships SET registration_number = NULL WHERE user_id = :uid AND registration_number = :reg AND status = 'closed'"),
            {"uid": str(current_user.user_id), "reg": body.registration_number}
        )
        db.commit()

    dealership = Dealership(
        dealership_id=uuid.uuid4(),
        user_id=current_user.user_id,
        # core identity
        name=body.name,
        brand=body.brand,
        registration_number=body.registration_number,
        gst_number=body.gst_number,
        # location
        location=body.location,
        showroom_address=body.showroom_address,
        city=body.city,
        state=body.state,
        country=body.country or "India",
        pincode=body.pincode,
        latitude=body.latitude,
        longitude=body.longitude,
        # contact
        contact_phone=body.contact_phone,
        alternate_phone=body.alternate_phone,
        contact_email=body.contact_email,
        website_url=body.website_url,
        # business details
        description=body.description,
        established_year=body.established_year,
        total_employees=body.total_employees,
        monthly_target_calls=body.monthly_target_calls,
        # status
        status="active",
        is_verified=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(dealership)

    # Link this dealership to the user
    current_user.dealership_id = dealership.dealership_id  # type: ignore
    current_user.updated_at = datetime.utcnow()  # type: ignore

    db.commit()
    db.refresh(dealership)
    return dealership


@router.post("/close", response_model=DealershipResponse)
def close_dealership(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.dealership_id is None:
        raise HTTPException(status_code=400, detail="You have no active dealership to close")

    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == current_user.dealership_id,
        Dealership.status == "active"
    ).first()

    if not dealership:
        raise HTTPException(status_code=404, detail="Active dealership not found")

    dealership.status = "closed"  # type: ignore
    dealership.closed_at = datetime.utcnow()  # type: ignore
    dealership.updated_at = datetime.utcnow()  # type: ignore

    # Unlink from user so they can create a new one
    current_user.dealership_id = None  # type: ignore
    current_user.updated_at = datetime.utcnow()  # type: ignore

    db.commit()
    db.refresh(dealership)
    return dealership


@router.get("/me", response_model=DealershipResponse)
def get_my_dealership(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.dealership_id is None:
        raise HTTPException(
            status_code=404,
            detail="You have no active dealership. Create one at POST /dealership/create"
        )
    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == current_user.dealership_id
    ).first()
    if not dealership:
        raise HTTPException(status_code=404, detail="Dealership not found")
    return dealership


@router.get("/history", response_model=List[DealershipResponse])
def get_dealership_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dealerships = db.query(Dealership).filter(
        Dealership.user_id == current_user.user_id
    ).order_by(Dealership.created_at.desc()).all()
    return dealerships


@router.put("/me", response_model=DealershipResponse)
def update_my_dealership(
    body: DealershipUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.dealership_id is None:
        raise HTTPException(status_code=400, detail="You have no active dealership")

    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == current_user.dealership_id,
        Dealership.status == "active"
    ).first()
    if not dealership:
        raise HTTPException(status_code=404, detail="Active dealership not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    for field, value in update_data.items():
        setattr(dealership, field, value)

    dealership.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(dealership)
    return dealership


@router.post("/me/logo", response_model=DealershipResponse)
def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.dealership_id is None:
        raise HTTPException(status_code=400, detail="You have no active dealership")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: jpeg, png, webp"
        )

    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == current_user.dealership_id
    ).first()
    if not dealership:
        raise HTTPException(status_code=404, detail="Dealership not found")

    ext = (file.filename or "file").split(".")[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    if dealership.logo is not None and os.path.exists(str(dealership.logo)):
        os.remove(str(dealership.logo))

    dealership.logo = filepath  # type: ignore
    dealership.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(dealership)
    return dealership