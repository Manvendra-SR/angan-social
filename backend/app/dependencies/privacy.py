from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.models.follow import Follow
from app.models.post import Post
from app.models.user import User

# A block of B is stored as Follow(follower_id=B, following_id=A, status="blocked")


def is_blocked_between(db: Session, user_id: int, other_id: int) -> bool:
    """True if either user has blocked the other."""
    return db.scalar(
        select(Follow.id).where(
            Follow.status == "blocked",
            or_(
                and_(Follow.follower_id == user_id, Follow.following_id == other_id),
                and_(Follow.follower_id == other_id, Follow.following_id == user_id),
            ),
        )
    ) is not None


def can_view_profile(
    target: User,
    current_user: User,
    db: Session,
):
    """Can current_user see target's posts and comments? (ignores blocks)"""
    if not target.is_private:
        return True

    if target.id == current_user.id:
        return True

    follow = db.scalar(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == target.id,
            Follow.status == "accepted",
        )
    )

    return bool(follow)


def get_accessible_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Post:
    """Load a post the current user is allowed to see, or raise 404/403.

    Shared by the post, comment and like endpoints.
    """
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # owner can always see
    if post.user_id == current_user.id:
        return post

    if is_blocked_between(db, current_user.id, post.user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if not can_view_profile(post.user, current_user, db):
        raise HTTPException(status_code=403, detail="Private account")

    return post
