from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, delete, or_, case
from sqlalchemy.exc import IntegrityError
from app.core import media
from app.core.db_errors import user_conflict
from app.core.realtime import manager
from app.core.notifications import (
    delete_follow_request_notification, get_counts, notify, push_counts, push_notification,
)
from app.schemas.notification import Counts
from app.schemas.user import UserOut, UserProfile, UserSummary, UserUpdate
from app.schemas.post import PostOut
from app.dependencies.database import get_db
from app.dependencies.pagination import CursorPage, get_cursor_page
from app.dependencies.privacy import can_view_profile, is_blocked_between
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.post import Post
from app.models.follow import Follow
from app.models.conversation import Conversation
from app.models.notification import Notification
from app.routers.posts import newest_first, with_liked_by_me

router = APIRouter(prefix="/users", tags=["Users"])


def blocked_me(db: Session, me: int, other: int) -> bool:
    """Did `other` block me? (stored as follower=me, following=other, blocked)"""
    return db.scalar(
        select(Follow.id).where(
            Follow.follower_id == me, Follow.following_id == other, Follow.status == "blocked"
        )
    ) is not None


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


@router.get("/me/counts", response_model=Counts)
def get_my_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Both navigation badges in one request."""
    return get_counts(db, current_user.id)


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.username is not None and data.username.lower() != current_user.username.lower():
        taken = db.scalar(
            select(User.id).where(func.lower(User.username) == data.username.lower())
        )
        if taken:
            raise HTTPException(status_code=409, detail="Username already taken")

    became_public = data.is_private is False and current_user.is_private
    if data.username is not None:
        current_user.username = data.username
    if data.is_private is not None:
        current_user.is_private = data.is_private
    if "bio" in data.model_fields_set:
        current_user.bio = data.bio or None  # "" clears the bio

    # a public account has no approval step: accept everyone who was waiting
    accepted_notifications = []
    if became_public:
        pending = db.scalars(
            select(Follow).where(Follow.following_id == current_user.id, Follow.status == "pending")
        ).all()
        for follow in pending:
            follow.status = "accepted"
            delete_follow_request_notification(db, owner_id=current_user.id, requester_id=follow.follower_id)
            accepted_notifications.append(notify(
                db, recipient_id=follow.follower_id, actor_id=current_user.id, type="follow_accepted"
            ))

    try:
        db.commit()
    except IntegrityError as exc:
        # someone took the username between our check and the commit
        db.rollback()
        raise user_conflict(exc)
    db.refresh(current_user)

    for notification in accepted_notifications:
        push_notification(background_tasks, db, notification)
    if became_public:
        push_counts(background_tasks, db, current_user.id)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete the logged-in account (identified only by the token).

    One DELETE on users; PostgreSQL's ON DELETE CASCADE removes everything that
    belongs to or points at the account in the same transaction: posts (and
    their likes, comments, notifications), the user's own likes/comments/
    follows/blocks/requests, notifications sent or received, read markers, and
    the user's one-to-one conversations with all their messages (a
    conversation can't exist without both participants).

    External clean-up only happens after the commit succeeds, so a failed
    delete never removes Cloudinary images of a still-existing account.
    """
    user_id = current_user.id

    # gather what the database can't clean up / needs to tell others about
    image_ids = db.scalars(
        select(Post.image_public_id).where(Post.user_id == user_id, Post.image_public_id.is_not(None))
    ).all()
    partners = db.scalars(
        select(case((Conversation.user_a_id == user_id, Conversation.user_b_id), else_=Conversation.user_a_id))
        .where(or_(Conversation.user_a_id == user_id, Conversation.user_b_id == user_id))
    ).all()
    notified = db.scalars(
        select(Notification.recipient_id).where(Notification.actor_id == user_id).distinct()
    ).all()

    db.execute(delete(User).where(User.id == user_id))
    db.commit()  # on failure nothing was deleted anywhere (no images, no sockets)

    # after the response: images (only this account's, by stored public_id),
    # live sockets of the deleted account, and badges of affected users
    for public_id in image_ids:
        background_tasks.add_task(media.delete_image, public_id)
    background_tasks.add_task(manager.close_user, user_id, 4401)
    for other_id in set(partners) | set(notified):
        push_counts(background_tasks, db, other_id)


@router.get("/search", response_model=list[UserSummary])
def search_users(
    q: str = Query(min_length=1, max_length=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # people who blocked me don't show up (their profile would be a 403 anyway)
    blocked_me_subq = select(Follow.following_id).where(
        Follow.follower_id == current_user.id, Follow.status == "blocked"
    )
    stmt = (
        select(User)
        .where(
            func.lower(User.username).startswith(q.strip().lower(), autoescape=True),
            User.id.not_in(blocked_me_subq),
        )
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
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != current_user.id and blocked_me(db, current_user.id, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # someone I blocked: a minimal profile so I can find the Unblock button
    blocked_by_me = user.id != current_user.id and is_blocked_between(db, current_user.id, user.id)

    follow_status = None if blocked_by_me else db.scalar(
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
    profile.blocked_by_me = blocked_by_me
    profile.can_view_posts = not blocked_by_me and can_view_profile(user, current_user, db)
    return profile


@router.get("/{user_id}/posts", response_model=list[PostOut])
def get_user_posts(
    user_id: int,
    page: CursorPage = Depends(get_cursor_page),
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
    )
    return with_liked_by_me(db, list(db.scalars(newest_first(stmt, page)).all()), current_user)
