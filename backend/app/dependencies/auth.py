from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.dependencies.database import get_db
from app.core.security import decode_access_token
from app.models.user import User


def get_current_user(
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
