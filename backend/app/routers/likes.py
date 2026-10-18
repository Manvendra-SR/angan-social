from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.privacy import get_accessible_post
from app.models.like import Like
from app.models.post import Post
from app.models.user import User

router = APIRouter(prefix="/likes", tags=["Likes"])


@router.post("/{post_id}", status_code=status.HTTP_201_CREATED)
def like_post(
    post: Post = Depends(get_accessible_post),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.add(Like(post_id=post.id, user_id=current_user.id))
    try:
        db.commit()
    except IntegrityError:
        # the (post_id, user_id) primary key rejects a second like
        db.rollback()
        raise HTTPException(status_code=409, detail="Already liked")
    return {"message": "liked"}


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlike_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # idempotent: unliking a post you haven't liked is not an error
    db.execute(
        delete(Like).where(
            Like.post_id == post_id,
            Like.user_id == current_user.id,
        )
    )
    db.commit()
