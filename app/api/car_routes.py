from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.car_model import CarModel
from app.models.user import User
from app.schemas.car_schema import (
    CarModelCreate, CarModelUpdate, CarModelResponse, StockUpdate
)
from app.core.database import get_db
from app.core.security import get_current_user
from datetime import datetime
import uuid, shutil, os

router = APIRouter(prefix="/cars", tags=["Car Models"])

IMAGE_DIR = "uploads/car_images"
os.makedirs(IMAGE_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_MB = 5


# ── Helpers ───────────────────────────────────────────────────────────────────
def generate_sku(model: str, variant: str, year: int, transmission: str, tone: str | None = None):
    model_code = model[:3].upper()
    variant_code = variant.replace(" ", "").upper()
    year_code = str(year)

    sku = f"{model_code}-{variant_code}-{year_code}-{transmission.upper()}"

    if tone:
        sku += f"-{tone.upper()}"

    return sku

def _get_car_or_404(car_model_id: str, dealership_id, db: Session) -> CarModel:
    """Fetch a car that belongs to the current user's dealership, or raise 404."""
    car = db.query(CarModel).filter(
        CarModel.car_model_id == car_model_id,
        CarModel.dealership_id == dealership_id,
        CarModel.deleted_at.is_(None)
    ).first()
    if not car:
        raise HTTPException(status_code=404, detail="Car model not found")
    return car


def _require_dealership(current_user: User):
    """Raise 400 if the user has no linked dealership yet."""
    if current_user.dealership_id is None:
        raise HTTPException(
            status_code=400,
            detail="You must create a dealership first (POST /dealership/create)"
        )


# ── CREATE ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=CarModelResponse, status_code=201)
def create_car(
    body: CarModelCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new car model to your dealership inventory."""
    _require_dealership(current_user)

    # Prevent duplicate variant per dealership
    existing = db.query(CarModel).filter(
        CarModel.dealership_id == current_user.dealership_id,
        CarModel.brand == body.brand,
        CarModel.model_name == body.model_name,
        CarModel.variant == body.variant,
        CarModel.model_year == body.model_year,
        CarModel.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"{body.brand} {body.model_name} {body.variant} ({body.model_year}) already exists in your inventory"
        )

    data = body.model_dump(exclude_unset=False)

    data["sku_code"] = generate_sku(
        data["model_name"],
        data["variant"],
        data["model_year"],
        data["transmission"],
        data.get("tone")
    )

    car = CarModel(
        car_model_id=uuid.uuid4(),
        dealership_id=current_user.dealership_id,
        **data,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(car)
    db.commit()
    db.refresh(car)
    return car


# ── LIST with filters ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[CarModelResponse])
def list_cars(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # Filters
    category: Optional[str] = Query(None, description="Hatchback | Sedan | SUV | ..."),
    fuel_type: Optional[str] = Query(None, description="Petrol | Diesel | Electric | ..."),
    transmission: Optional[str] = Query(None, description="Manual | Automatic | AMT | ..."),
    availability_status: Optional[str] = Query(None, description="available | out_of_stock | ..."),
    is_featured: Optional[bool] = Query(None, description="Filter featured cars only"),
    is_active: Optional[bool] = Query(True, description="Filter active/inactive cars"),
    min_price: Optional[float] = Query(None, description="Minimum ex-showroom price"),
    max_price: Optional[float] = Query(None, description="Maximum ex-showroom price"),
    model_year: Optional[int] = Query(None, description="Filter by model year"),
    search: Optional[str] = Query(None, description="Search by model name or variant"),
    # Pagination
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
):
    """List all car models in your dealership with optional filters and pagination."""
    _require_dealership(current_user)

    q = db.query(CarModel).filter(
        CarModel.dealership_id == current_user.dealership_id,
        CarModel.deleted_at.is_(None)
    )

    if category:
        q = q.filter(CarModel.category == category)
    if fuel_type:
        q = q.filter(CarModel.fuel_type == fuel_type)
    if transmission:
        q = q.filter(CarModel.transmission == transmission)
    if availability_status:
        q = q.filter(CarModel.availability_status == availability_status)
    if is_featured is not None:
        q = q.filter(CarModel.is_featured == is_featured)
    if is_active is not None:
        q = q.filter(CarModel.is_active == is_active)
    if min_price is not None:
        q = q.filter(CarModel.price_ex_showroom >= min_price)
    if max_price is not None:
        q = q.filter(CarModel.price_ex_showroom <= max_price)
    if model_year is not None:
        q = q.filter(CarModel.model_year == model_year)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            (CarModel.model_name.ilike(term)) |
            (CarModel.variant.ilike(term)) |
            (CarModel.brand.ilike(term))
        )

    return q.order_by(CarModel.is_featured.desc(), CarModel.created_at.desc()).offset(skip).limit(limit).all()


# ── GET single ────────────────────────────────────────────────────────────────

@router.get("/{car_model_id}", response_model=CarModelResponse)
def get_car(
    car_model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full details of a single car model."""
    _require_dealership(current_user)
    return _get_car_or_404(car_model_id, current_user.dealership_id, db)


# ── UPDATE ────────────────────────────────────────────────────────────────────

from sqlalchemy.exc import IntegrityError

@router.put("/{car_model_id}", response_model=CarModelResponse)
def update_car(
    car_model_id: str,
    body: CarModelUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _require_dealership(current_user)
    car = _get_car_or_404(car_model_id, current_user.dealership_id, db)

    update_data = body.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    # apply updates
    for field, value in update_data.items():
        setattr(car, field, value)

    # regenerate SKU if important fields changed
    if any(k in update_data for k in ["model_name", "variant", "model_year", "transmission", "tone"]):
        car.sku_code = generate_sku(# type: ignore
            car.model_name,# type: ignore
            car.variant,# type: ignore
            car.model_year,# type: ignore
            car.transmission,# type: ignore
            getattr(car, "tone", None)
        )# type: ignore

        # check duplicate
        existing = db.query(CarModel).filter(
            CarModel.sku_code == car.sku_code,
            CarModel.car_model_id != car.car_model_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Another car variant already uses this SKU"
            )

    car.updated_at = datetime.utcnow()  # type: ignore

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="SKU already exists"
        )

    db.refresh(car)
    return car


# ── STOCK UPDATE (dedicated endpoint) ────────────────────────────────────────

@router.patch("/{car_model_id}/stock", response_model=CarModelResponse)
def update_stock(
    car_model_id: str,
    body: StockUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update stock count and availability status without touching other car details."""
    _require_dealership(current_user)
    car = _get_car_or_404(car_model_id, current_user.dealership_id, db)

    car.stock_count = body.stock_count  # type: ignore

    # Auto-derive availability if not explicitly provided
    if body.availability_status:
        car.availability_status = body.availability_status  # type: ignore
    else:
        car.availability_status = "available" if body.stock_count > 0 else "out_of_stock"  # type: ignore

    if body.delivery_weeks is not None:
        car.delivery_weeks = body.delivery_weeks  # type: ignore

    car.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(car)
    return car


# ── TOGGLE FEATURED ───────────────────────────────────────────────────────────

@router.patch("/{car_model_id}/feature", response_model=CarModelResponse)
def toggle_featured(
    car_model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle the featured flag on a car model (show/hide on top of listings)."""
    _require_dealership(current_user)
    car = _get_car_or_404(car_model_id, current_user.dealership_id, db)

    car.is_featured = not car.is_featured  # type: ignore
    car.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(car)
    return car


# ── TOGGLE ACTIVE / DEACTIVATE ────────────────────────────────────────────────

@router.patch("/{car_model_id}/toggle-active", response_model=CarModelResponse)
def toggle_active(
    car_model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Activate or deactivate a car model without deleting it."""
    _require_dealership(current_user)
    car = _get_car_or_404(car_model_id, current_user.dealership_id, db)

    car.is_active = not car.is_active  # type: ignore
    car.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(car)
    return car


# ── UPLOAD THUMBNAIL ──────────────────────────────────────────────────────────

@router.post("/{car_model_id}/thumbnail", response_model=CarModelResponse)
def upload_thumbnail(
    car_model_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload or replace the thumbnail image for a car model."""
    _require_dealership(current_user)
    car = _get_car_or_404(car_model_id, current_user.dealership_id, db)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: jpeg, png, webp"
        )

    ext = (file.filename or "image").split(".")[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(IMAGE_DIR, filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Delete old thumbnail file if it exists on disk
    if car.thumbnail_image is not None and os.path.exists(str(car.thumbnail_image)):
        os.remove(str(car.thumbnail_image))

    car.thumbnail_image = filepath  # type: ignore
    car.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(car)
    return car


# ── SOFT DELETE ───────────────────────────────────────────────────────────────

@router.delete("/{car_model_id}", status_code=200)
def delete_car(
    car_model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft-delete a car model (sets deleted_at, keeps the record).
    Data is preserved for call logs and campaign history.
    """
    _require_dealership(current_user)
    car = _get_car_or_404(car_model_id, current_user.dealership_id, db)

    car.deleted_at = datetime.utcnow()  # type: ignore
    car.is_active = False  # type: ignore
    car.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    return {"message": f"Car model '{car.model_name} {car.variant}' has been deleted"}


# ── SUMMARY / STATS ───────────────────────────────────────────────────────────

@router.get("/stats/summary", response_model=dict)
def car_inventory_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a quick inventory summary for the dealership dashboard:
    total active cars, out-of-stock count, featured count, breakdown by category and fuel type.
    """
    _require_dealership(current_user)

    base_q = db.query(CarModel).filter(
        CarModel.dealership_id == current_user.dealership_id,
        CarModel.deleted_at.is_(None)
    )

    total = base_q.count()
    active = base_q.filter(CarModel.is_active == True).count()
    out_of_stock = base_q.filter(CarModel.availability_status == "out_of_stock").count()
    featured = base_q.filter(CarModel.is_featured == True).count()
    coming_soon = base_q.filter(CarModel.availability_status == "coming_soon").count()

    # Group by category
    from sqlalchemy import func
    category_counts = {
        row[0]: row[1]
        for row in db.query(CarModel.category, func.count(CarModel.car_model_id))
        .filter(CarModel.dealership_id == current_user.dealership_id, CarModel.deleted_at.is_(None))
        .group_by(CarModel.category)
        .all()
    }

    # Group by fuel type
    fuel_counts = {
        row[0]: row[1]
        for row in db.query(CarModel.fuel_type, func.count(CarModel.car_model_id))
        .filter(CarModel.dealership_id == current_user.dealership_id, CarModel.deleted_at.is_(None))
        .group_by(CarModel.fuel_type)
        .all()
    }

    return {
        "total": total,
        "active": active,
        "inactive": total - active,
        "out_of_stock": out_of_stock,
        "featured": featured,
        "coming_soon": coming_soon,
        "by_category": category_counts,
        "by_fuel_type": fuel_counts,
    }