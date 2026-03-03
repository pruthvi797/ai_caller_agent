from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import hash_password, verify_password


def create_user(db: Session, user):
    new_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
        phone=user.phone,
        dealership_id=user.dealership_id
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


def authenticate_user(db: Session, email, password):
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    if not verify_password(password, str(user.password_hash)):
        return None

    return user