import re
from pydantic import BaseModel, field_validator, model_validator
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import datetime


# ── Enums (validated as strings for simplicity) ───────────────────────────────

VALID_FUEL_TYPES = {"Petrol", "Diesel", "CNG", "Electric", "Hybrid", "Petrol+CNG"}
VALID_CATEGORIES = {"Hatchback", "Sedan", "SUV", "MUV", "Crossover", "Coupe", "Convertible", "Pickup"}
VALID_TRANSMISSIONS = {"Manual", "Automatic", "AMT", "CVT", "DCT"}
VALID_DRIVE_TYPES = {"FWD", "RWD", "AWD", "4WD"}
VALID_AVAILABILITY = {"available", "out_of_stock", "discontinued", "coming_soon", "on_order"}

CURRENT_YEAR = datetime.now().year


# ── Create ────────────────────────────────────────────────────────────────────

class CarModelCreate(BaseModel):
    # Required
    brand: str
    model_name: str
    variant: str
    model_year: int
    category: str
    fuel_type: str
    transmission: str
    price_ex_showroom: Decimal

    # Optional — specs
    drive_type: Optional[str] = None
    seating_capacity: Optional[int] = None
    available_colors: Optional[str] = None
    sku_code: Optional[str] = None

    # Optional — pricing
    price_on_road: Optional[Decimal] = None
    price_min: Optional[Decimal] = None
    price_max: Optional[Decimal] = None
    emi_starting_from: Optional[Decimal] = None

    # Optional — engine & performance
    engine_cc: Optional[int] = None
    engine_description: Optional[str] = None
    max_power_bhp: Optional[Decimal] = None
    max_torque_nm: Optional[Decimal] = None
    mileage_kmpl: Optional[Decimal] = None
    top_speed_kmph: Optional[int] = None
    boot_space_litres: Optional[int] = None
    ground_clearance_mm: Optional[int] = None
    kerb_weight_kg: Optional[int] = None
    length_mm: Optional[int] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    wheelbase_mm: Optional[int] = None
    fuel_tank_capacity_litres: Optional[Decimal] = None

    # Optional — safety
    ncap_rating: Optional[str] = None
    airbags_count: Optional[int] = None
    has_abs: Optional[bool] = None
    has_esp: Optional[bool] = None

    # Optional — content
    key_features: Optional[str] = None
    description: Optional[str] = None
    highlights: Optional[str] = None
    thumbnail_image: Optional[str] = None
    image_gallery: Optional[str] = None

    # Optional — offers
    current_offer: Optional[str] = None
    offer_valid_until: Optional[datetime] = None
    exchange_bonus: Optional[Decimal] = None
    corporate_discount: Optional[Decimal] = None

    # Optional — inventory
    stock_count: Optional[int] = 0
    availability_status: Optional[str] = "available"
    delivery_weeks: Optional[int] = None
    is_featured: Optional[bool] = False

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("brand", "model_name", "variant")
    @classmethod
    def string_not_blank(cls, v: str, info) -> str:
        v = v.strip()
        if not v:
            raise ValueError(f"{info.field_name} cannot be blank")
        if len(v) < 2:
            raise ValueError(f"{info.field_name} must be at least 2 characters")
        return v

    @field_validator("model_year")
    @classmethod
    def valid_model_year(cls, v: int) -> int:
        if v < 1980 or v > CURRENT_YEAR + 2:
            raise ValueError(f"model_year must be between 1980 and {CURRENT_YEAR + 2}")
        return v

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
        return v

    @field_validator("fuel_type")
    @classmethod
    def valid_fuel_type(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_FUEL_TYPES:
            raise ValueError(f"fuel_type must be one of: {', '.join(sorted(VALID_FUEL_TYPES))}")
        return v

    @field_validator("transmission")
    @classmethod
    def valid_transmission(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_TRANSMISSIONS:
            raise ValueError(f"transmission must be one of: {', '.join(sorted(VALID_TRANSMISSIONS))}")
        return v

    @field_validator("drive_type")
    @classmethod
    def valid_drive_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v not in VALID_DRIVE_TYPES:
                raise ValueError(f"drive_type must be one of: {', '.join(sorted(VALID_DRIVE_TYPES))}")
        return v

    @field_validator("price_ex_showroom")
    @classmethod
    def price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price_ex_showroom must be greater than 0")
        return v

    @field_validator("price_on_road", "price_min", "price_max", "emi_starting_from",
                     "exchange_bonus", "corporate_discount")
    @classmethod
    def optional_price_positive(cls, v: Optional[Decimal], info) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError(f"{info.field_name} cannot be negative")
        return v

    @field_validator("seating_capacity")
    @classmethod
    def valid_seating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 12):
            raise ValueError("seating_capacity must be between 1 and 12")
        return v

    @field_validator("airbags_count")
    @classmethod
    def valid_airbags(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 0 or v > 12):
            raise ValueError("airbags_count must be between 0 and 12")
        return v

    @field_validator("mileage_kmpl")
    @classmethod
    def valid_mileage(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and (v <= 0 or v > 200):
            raise ValueError("mileage_kmpl must be between 0 and 200")
        return v

    @field_validator("stock_count")
    @classmethod
    def stock_not_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("stock_count cannot be negative")
        return v

    @field_validator("availability_status")
    @classmethod
    def valid_availability(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_AVAILABILITY:
            raise ValueError(f"availability_status must be one of: {', '.join(sorted(VALID_AVAILABILITY))}")
        return v

    @model_validator(mode="after")
    def price_range_check(self) -> "CarModelCreate":
        if self.price_min is not None and self.price_max is not None:
            if self.price_min > self.price_max:
                raise ValueError("price_min cannot be greater than price_max")
        return self


# ── Update ────────────────────────────────────────────────────────────────────

class CarModelUpdate(BaseModel):
    brand: Optional[str] = None
    model_name: Optional[str] = None
    variant: Optional[str] = None
    model_year: Optional[int] = None
    category: Optional[str] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    drive_type: Optional[str] = None
    seating_capacity: Optional[int] = None
    available_colors: Optional[str] = None
    sku_code: Optional[str] = None
    price_ex_showroom: Optional[Decimal] = None
    price_on_road: Optional[Decimal] = None
    price_min: Optional[Decimal] = None
    price_max: Optional[Decimal] = None
    emi_starting_from: Optional[Decimal] = None
    engine_cc: Optional[int] = None
    engine_description: Optional[str] = None
    max_power_bhp: Optional[Decimal] = None
    max_torque_nm: Optional[Decimal] = None
    mileage_kmpl: Optional[Decimal] = None
    top_speed_kmph: Optional[int] = None
    boot_space_litres: Optional[int] = None
    ground_clearance_mm: Optional[int] = None
    kerb_weight_kg: Optional[int] = None
    fuel_tank_capacity_litres: Optional[Decimal] = None
    ncap_rating: Optional[str] = None
    airbags_count: Optional[int] = None
    has_abs: Optional[bool] = None
    has_esp: Optional[bool] = None
    key_features: Optional[str] = None
    description: Optional[str] = None
    highlights: Optional[str] = None
    thumbnail_image: Optional[str] = None
    image_gallery: Optional[str] = None
    current_offer: Optional[str] = None
    offer_valid_until: Optional[datetime] = None
    exchange_bonus: Optional[Decimal] = None
    corporate_discount: Optional[Decimal] = None
    stock_count: Optional[int] = None
    availability_status: Optional[str] = None
    delivery_weeks: Optional[int] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("model_name", "variant", "brand")
    @classmethod
    def string_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError(f"{info.field_name} cannot be set to blank")
        return v

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
        return v

    @field_validator("fuel_type")
    @classmethod
    def valid_fuel_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_FUEL_TYPES:
            raise ValueError(f"fuel_type must be one of: {', '.join(sorted(VALID_FUEL_TYPES))}")
        return v

    @field_validator("transmission")
    @classmethod
    def valid_transmission(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_TRANSMISSIONS:
            raise ValueError(f"transmission must be one of: {', '.join(sorted(VALID_TRANSMISSIONS))}")
        return v

    @field_validator("availability_status")
    @classmethod
    def valid_availability(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_AVAILABILITY:
            raise ValueError(f"availability_status must be one of: {', '.join(sorted(VALID_AVAILABILITY))}")
        return v

    @field_validator("price_ex_showroom")
    @classmethod
    def price_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("price_ex_showroom must be greater than 0")
        return v

    @field_validator("stock_count")
    @classmethod
    def stock_not_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("stock_count cannot be negative")
        return v

    @model_validator(mode="after")
    def price_range_check(self) -> "CarModelUpdate":
        if self.price_min is not None and self.price_max is not None:
            if self.price_min > self.price_max:
                raise ValueError("price_min cannot be greater than price_max")
        return self


# ── Inventory update (dedicated endpoint) ────────────────────────────────────

class StockUpdate(BaseModel):
    stock_count: int
    availability_status: Optional[str] = None
    delivery_weeks: Optional[int] = None

    @field_validator("stock_count")
    @classmethod
    def stock_not_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("stock_count cannot be negative")
        return v

    @field_validator("availability_status")
    @classmethod
    def valid_availability(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_AVAILABILITY:
            raise ValueError(f"availability_status must be one of: {', '.join(sorted(VALID_AVAILABILITY))}")
        return v


# ── Response ──────────────────────────────────────────────────────────────────

class CarModelResponse(BaseModel):
    car_model_id: UUID
    dealership_id: UUID
    brand: str
    model_name: str
    variant: str
    model_year: int
    sku_code: Optional[str]
    category: str
    fuel_type: str
    transmission: str
    drive_type: Optional[str]
    seating_capacity: Optional[int]
    available_colors: Optional[str]
    price_ex_showroom: Decimal
    price_on_road: Optional[Decimal]
    price_min: Optional[Decimal]
    price_max: Optional[Decimal]
    emi_starting_from: Optional[Decimal]
    engine_cc: Optional[int]
    engine_description: Optional[str]
    max_power_bhp: Optional[Decimal]
    max_torque_nm: Optional[Decimal]
    mileage_kmpl: Optional[Decimal]
    top_speed_kmph: Optional[int]
    boot_space_litres: Optional[int]
    ground_clearance_mm: Optional[int]
    kerb_weight_kg: Optional[int]
    length_mm: Optional[int]
    width_mm: Optional[int]
    height_mm: Optional[int]
    wheelbase_mm: Optional[int]
    fuel_tank_capacity_litres: Optional[Decimal]
    ncap_rating: Optional[str]
    airbags_count: Optional[int]
    has_abs: Optional[bool]
    has_esp: Optional[bool]
    key_features: Optional[str]
    description: Optional[str]
    highlights: Optional[str]
    thumbnail_image: Optional[str]
    image_gallery: Optional[str]
    current_offer: Optional[str]
    offer_valid_until: Optional[datetime]
    exchange_bonus: Optional[Decimal]
    corporate_discount: Optional[Decimal]
    stock_count: int
    availability_status: str
    delivery_weeks: Optional[int]
    is_active: bool
    is_featured: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}