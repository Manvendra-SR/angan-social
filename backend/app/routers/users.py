from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.schemas.user import UserOut, UserProfile, UserSummary, UserUpdate
from app.schemas.post import PostOut
from app.dependencies.database import get_db
from app.dependencies.pagination import Page, get_page
from app.dependencies.privacy import can_view_profile, is_blocked_between
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.post import Post
from app.models.follow import Follow
from app.routers.posts import with_liked_by_me

router = APIRouter(prefix="/users", tags=["Users"])


def get_visible_user(user_id: int, db: Session, current_user: User) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != current_user.id and is_blocked_between(db, current_user.id, user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.username is not None and data.username.lower() != current_user.username.lower():
        taken = db.scalar(
            select(User.id).where(func.lower(User.username) == data.username.lower())
        )
        if taken:
            raise HTTPException(status_code=409, detail="Username already taken")

    if data.username is not None:
        current_user.username = data.username
    if data.is_private is not None:
        current_user.is_private = data.is_private
    if "bio" in data.model_fields_set:
        current_user.bio = data.bio or None  # "" clears the bio

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")
    db.refresh(current_user)
    return current_user


@router.get("/search", response_model=list[UserSummary])
def search_users(
    q: str = Query(min_length=1, max_length=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(User)
        .where(func.lower(User.username).startswith(q.strip().lower(), autoescape=True))
        .order_by(User.username)
        .limit(20)
    )
    return db.scalars(stmt).all()


@router.get("/{user_id}", response_model=UserProfile)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = get_visible_user(user_id, db, current_user)

    follow_status = db.scalar(
        select(Follow.status).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user.id,
            Follow.status != "blocked",
        )
    )

    # private accounts still show their basic profile (so others can
    # send a follow request), but not their posts
    profile = UserProfile.model_validate(user)
    profile.follow_status = follow_status
    profile.can_view_posts = can_view_profile(user, current_user, db)
    return profile


@router.get("/{user_id}/posts", response_model=list[PostOut])
def get_user_posts(
    user_id: int,
    page: Page = Depends(get_page),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = get_visible_user(user_id, db, current_user)
    if not can_view_profile(user, current_user, db):
        raise HTTPException(status_code=403, detail="Private account")

    stmt = (
        select(Post)
        .options(selectinload(Post.user))
        .where(Post.user_id == user.id)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return with_liked_by_me(db, list(db.scalars(stmt).all()), current_user)
