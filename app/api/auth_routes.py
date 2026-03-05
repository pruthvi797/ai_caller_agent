from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.schemas.user_schema import UserCreate, UserResponse, TokenRefresh, UserUpdate, ChangePasswordRequest
from app.services.auth_service import create_user, authenticate_user
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, get_current_user, hash_password, verify_password
)
from app.core.database import get_db
from app.models.user import User
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check duplicate email
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    result = create_user(db, user)
    new_user, error = result  # always unpack explicitly to avoid returning the tuple

    if error == "employee_id_taken":
        raise HTTPException(status_code=400, detail="Employee ID already taken")

    if new_user is None:
        raise HTTPException(status_code=500, detail="User creation failed")

    return new_user


@router.post("/login")
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    db_user = authenticate_user(db, username, password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if db_user.is_active is False:
        raise HTTPException(status_code=403, detail="Account is deactivated. Contact support.")

    # Update last login timestamp
    db_user.last_login_at = datetime.utcnow()  # type: ignore
    db.commit()

    access_token = create_access_token({"sub": str(db_user.user_id)})
    refresh_token = create_refresh_token({"sub": str(db_user.user_id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh")
def refresh_token(body: TokenRefresh):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload.get("sub")
    new_access = create_access_token({"sub": user_id})
    return {"access_token": new_access, "token_type": "bearer"}


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_profile(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, str(current_user.password_hash)):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = hash_password(body.new_password)  # type: ignore
    current_user.password_changed_at = datetime.utcnow()  # type: ignore
    current_user.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    return {"message": "Password changed successfully"}