from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.dependencies.database import get_db
from app.schemas.user import UserCreate, UserOut
from app.models.user import User
from app.core.db_errors import user_conflict
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # friendly early checks; the unique indexes on lower(...) are the real guard
    if db.scalar(select(User.id).where(func.lower(User.email) == user.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    if db.scalar(select(User.id).where(func.lower(User.username) == user.username.lower())):
        raise HTTPException(status_code=409, detail="Username already taken")

    new_user = User(
        username=user.username,
        email=user.email,  # lowercased by the schema
        password_hash=hash_password(user.password),
        is_private=user.is_private,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError as exc:
        # a concurrent registration took the name/email after our check
        db.rollback()
        raise user_conflict(exc)
    db.refresh(new_user)
    return new_user


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # OAuth2 form field is called "username" but we log in with the email
    user = db.scalar(select(User).where(User.email == form_data.username.strip().lower()))

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token(
        data={"sub": str(user.id)}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
