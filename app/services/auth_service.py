from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import hash_password, verify_password
from datetime import datetime
import uuid


def create_user(db: Session, user):
    # Check duplicate employee_id
    existing_employee = db.query(User).filter(
        User.employee_id == user.employee_id
    ).first()
    if existing_employee:
        return None, "employee_id_taken"

    new_user = User(
        user_id=uuid.uuid4(),
        email=user.email,
        password_hash=hash_password(user.password),
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        employee_id=user.employee_id,
        company_name=user.company_name,
        designation=getattr(user, "designation", None),
        department=getattr(user, "department", None),
        dealership_id=None,    # User creates dealership manually later
        role="admin",
        is_active=True,
        is_verified=False,
        failed_login_attempts=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user, None   # Always return a 2-tuple


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, str(user.password_hash)):
        return None
    return user