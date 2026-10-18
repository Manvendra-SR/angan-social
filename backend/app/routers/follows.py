from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.models.follow import Follow
from app.models.user import User
from app.schemas.follow import FollowRequestOut

router = APIRouter(prefix="/follows", tags=["Follows"])


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
def follow_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    target = db.scalar(select(User).where(User.id == user_id))
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    blocked_by_target = db.scalar(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
            Follow.status == "blocked",
        )
    )
    if blocked_by_target:
        raise HTTPException(status_code=403, detail="You are blocked")

    blocked_by_me = db.scalar(
        select(Follow).where(
            Follow.follower_id == user_id,
            Follow.following_id == current_user.id,
            Follow.status == "blocked",
        )
    )
    if blocked_by_me:
        raise HTTPException(
            status_code=400,
            detail="Unblock user before sending follow request",
        )

    existing = db.scalar(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Already {existing.status}",
        )

    status_value = "accepted" if not target.is_private else "pending"

    follow = Follow(
        follower_id=current_user.id,
        following_id=user_id,
        status=status_value,
    )
    db.add(follow)
    try:
        db.commit()
    except IntegrityError:
        # concurrent duplicate request hit the unique constraint
        db.rollback()
        raise HTTPException(status_code=409, detail="Follow already exists")

    return {"status": status_value}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        delete(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
            Follow.status == "accepted",
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="You are not following this user",
        )

    db.commit()


@router.delete("/{user_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_follow_request(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        delete(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
            Follow.status == "pending",
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="No pending request found",
        )

    db.commit()


@router.get("/requests", response_model=list[FollowRequestOut])
def get_follow_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(
            Follow.follower_id,
            User.username.label("follower_username"),
            Follow.created_at,
        )
        .join(User, User.id == Follow.follower_id)
        .where(
            Follow.following_id == current_user.id,
            Follow.status == "pending",
        )
        .order_by(Follow.created_at.desc())
    )

    return db.execute(stmt).all()


@router.post("/{follower_id}/accept")
def accept_follow(
    follower_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    follow = db.scalar(
        select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.following_id == current_user.id,
            Follow.status == "pending",
        )
    )

    if not follow:
        raise HTTPException(status_code=404, detail="Request not found")

    follow.status = "accepted"
    db.commit()

    return {"message": "follow request accepted"}


@router.delete("/{follower_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_follow(
    follower_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        delete(Follow).where(
            Follow.follower_id == follower_id,
            Follow.following_id == current_user.id,
            Follow.status == "pending",
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Request not found")

    db.commit()


@router.post("/{user_id}/block")
def block_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    # a block is stored as Follow(follower=blocked user, following=me, "blocked"),
    # replacing their follow / follow request if there was one
    follow = db.scalar(
        select(Follow).where(
            Follow.follower_id == user_id,
            Follow.following_id == current_user.id,
        )
    )

    if follow:
        follow.status = "blocked"
    else:
        follow = Follow(
            follower_id=user_id,
            following_id=current_user.id,
            status="blocked",
        )
        db.add(follow)

    # I also stop following them (unless that row is their block of me)
    db.execute(
        delete(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
            Follow.status != "blocked",
        )
    )

    db.commit()
    return {"message": "user blocked"}


@router.delete("/{user_id}/unblock", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    blocked = db.scalar(
        select(Follow).where(
            Follow.follower_id == user_id,
            Follow.following_id == current_user.id,
            Follow.status == "blocked",
        )
    )

    if not blocked:
        raise HTTPException(status_code=404, detail="User not blocked")

    db.delete(blocked)
    db.commit()
