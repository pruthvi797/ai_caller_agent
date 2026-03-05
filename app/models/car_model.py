import uuid
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, Boolean, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CarModel(Base):
    __tablename__ = "car_models"

    car_model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ─────────────────────────────────────────────────────────────
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )

    # ── Core identity ─────────────────────────────────────────────────────────
    brand = Column(String(100), nullable=False)               # e.g. Suzuki
    model_name = Column(String(150), nullable=False)          # e.g. Swift, Baleno
    variant = Column(String(100), nullable=False)             # e.g. ZXI+, VXI, LXI
    model_year = Column(Integer, nullable=False)              # e.g. 2024
    sku_code = Column(String(50), nullable=True, unique=True) # internal stock keeping code

    # ── Classification ────────────────────────────────────────────────────────
    # Hatchback | Sedan | SUV | MUV | Crossover | Coupe | Convertible | Pickup
    category = Column(String(50), nullable=False)
    # Petrol | Diesel | CNG | Electric | Hybrid | Petrol+CNG
    fuel_type = Column(String(30), nullable=False)
    # Manual | Automatic | AMT | CVT | DCT
    transmission = Column(String(30), nullable=False)
    # FWD | RWD | AWD | 4WD
    drive_type = Column(String(20), nullable=True)
    # 5-seater | 7-seater etc.
    seating_capacity = Column(Integer, nullable=True)
    # White | Red | Blue etc. (comma-separated available colors)
    available_colors = Column(Text, nullable=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    price_ex_showroom = Column(DECIMAL(12, 2), nullable=False)   # base ex-showroom price
    price_on_road = Column(DECIMAL(12, 2), nullable=True)        # on-road (incl. taxes)
    price_min = Column(DECIMAL(12, 2), nullable=True)            # range min (all variants)
    price_max = Column(DECIMAL(12, 2), nullable=True)            # range max (all variants)
    emi_starting_from = Column(DECIMAL(10, 2), nullable=True)    # indicative monthly EMI

    # ── Specifications ────────────────────────────────────────────────────────
    engine_cc = Column(Integer, nullable=True)                   # engine displacement in cc
    engine_description = Column(String(150), nullable=True)      # e.g. "1.2L K-Series Petrol"
    max_power_bhp = Column(DECIMAL(6, 2), nullable=True)
    max_torque_nm = Column(DECIMAL(6, 2), nullable=True)
    mileage_kmpl = Column(DECIMAL(5, 2), nullable=True)          # ARAI-certified mileage
    top_speed_kmph = Column(Integer, nullable=True)
    boot_space_litres = Column(Integer, nullable=True)
    ground_clearance_mm = Column(Integer, nullable=True)
    kerb_weight_kg = Column(Integer, nullable=True)
    length_mm = Column(Integer, nullable=True)
    width_mm = Column(Integer, nullable=True)
    height_mm = Column(Integer, nullable=True)
    wheelbase_mm = Column(Integer, nullable=True)
    fuel_tank_capacity_litres = Column(DECIMAL(5, 1), nullable=True)

    # ── Safety ────────────────────────────────────────────────────────────────
    ncap_rating = Column(String(10), nullable=True)              # e.g. "5-Star", "4-Star"
    airbags_count = Column(Integer, nullable=True)
    has_abs = Column(Boolean, nullable=True)
    has_esp = Column(Boolean, nullable=True)

    # ── Features ──────────────────────────────────────────────────────────────
    # JSON string list of key features for AI knowledge base
    key_features = Column(Text, nullable=True)
    # Detailed description for brochure/AI context
    description = Column(Text, nullable=True)
    # Comma-separated highlights for quick display
    highlights = Column(Text, nullable=True)

    # ── Media ─────────────────────────────────────────────────────────────────
    thumbnail_image = Column(Text, nullable=True)   # primary display image URL/path
    image_gallery = Column(Text, nullable=True)     # JSON array of image URLs

    # ── Offer / Promotion ─────────────────────────────────────────────────────
    current_offer = Column(Text, nullable=True)           # e.g. "₹50,000 cash discount"
    offer_valid_until = Column(TIMESTAMP, nullable=True)
    exchange_bonus = Column(DECIMAL(10, 2), nullable=True)
    corporate_discount = Column(DECIMAL(10, 2), nullable=True)

    # ── Inventory / Availability ──────────────────────────────────────────────
    stock_count = Column(Integer, nullable=False, default=0)
    # available | out_of_stock | discontinued | coming_soon | on_order
    availability_status = Column(String(30), nullable=False, default="available")
    delivery_weeks = Column(Integer, nullable=True)   # estimated delivery lead time

    # ── Status ────────────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)
    is_featured = Column(Boolean, nullable=False, default=False)  # show on top/homepage

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
    deleted_at = Column(TIMESTAMP, nullable=True)   # soft-delete