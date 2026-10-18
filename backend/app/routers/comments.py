from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from app.schemas.comment import CommentCreate, CommentOut
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.pagination import Page, get_page
from app.dependencies.privacy import get_accessible_post
from app.models.comment import Comment
from app.models.user import User
from app.models.post import Post

router = APIRouter(prefix="/comments", tags=["Comments"])


def get_own_comment(comment_id: int, db: Session, current_user: User) -> Comment:
    comment = db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only modify your own comments")
    return comment


@router.post("/posts/{post_id}", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    comment: CommentCreate,
    post: Post = Depends(get_accessible_post),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_comment = Comment(
        post_id=post.id,
        user_id=current_user.id,
        content=comment.content,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment


@router.get("/posts/{post_id}", response_model=list[CommentOut])
def get_comments(
    post: Post = Depends(get_accessible_post),
    page: Page = Depends(get_page),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Comment)
        .options(selectinload(Comment.user))
        .where(Comment.post_id == post.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return db.scalars(stmt).all()


@router.patch("/{comment_id}", response_model=CommentOut)
def update_comment(
    comment_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = get_own_comment(comment_id, db, current_user)
    comment.content = data.content
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = get_own_comment(comment_id, db, current_user)
    db.delete(comment)
    db.commit()
