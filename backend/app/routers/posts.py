from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, or_
from app.schemas.post import PostOut, PostUpdate
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.pagination import CursorPage, get_cursor_page
from app.dependencies.privacy import get_accessible_post
from app.models.post import Post
from app.models.user import User
from app.models.like import Like
from app.models.follow import Follow
from app.core import media
from app.core.notifications import push_counts

router = APIRouter(prefix="/posts", tags=["Posts"])


def with_liked_by_me(db: Session, posts: list[Post], current_user: User) -> list[Post]:
    """Set post.liked_by_me with one query for the whole page of posts."""
    ids = [p.id for p in posts]
    liked = set(
        db.scalars(
            select(Like.post_id).where(Like.user_id == current_user.id, Like.post_id.in_(ids))
        )
    ) if ids else set()
    for p in posts:
        p.liked_by_me = p.id in liked
    return posts


def get_own_post(post_id: int, db: Session, current_user: User) -> Post:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only modify your own posts")
    return post


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(
    content: str | None = Form(None, max_length=2000),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = content.strip() if content else None
    if not content and not image:
        raise HTTPException(status_code=400, detail="Post cannot be empty")

    # validate fully before uploading anything
    data = media.read_image(image) if image else None
    uploaded = media.upload_image(data, current_user.id) if data else None

    new_post = Post(
        user_id=current_user.id,
        content=content,
        image_url=uploaded.url if uploaded else None,
        image_public_id=uploaded.public_id if uploaded else None,
    )
    db.add(new_post)
    try:
        db.commit()
    except Exception:
        # don't leave an orphaned image in Cloudinary
        db.rollback()
        media.delete_image(uploaded.public_id if uploaded else None)
        raise
    db.refresh(new_post)
    return with_liked_by_me(db, [new_post], current_user)[0]


def newest_first(stmt, page: CursorPage):
    """Apply the descending-id cursor: ids only grow, so posts created after
    the first page can never shift later pages (no repeats, no skips)."""
    if page.before_id is not None:
        stmt = stmt.where(Post.id < page.before_id)
    return stmt.order_by(Post.id.desc()).limit(page.limit)


@router.get("/feed", response_model=list[PostOut])
def get_feed(
    page: CursorPage = Depends(get_cursor_page),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chronological feed: my posts, every public account's posts (discovery)
    and private accounts I'm an accepted follower of, minus blocks both ways.

    The conditions are OR-ed in one WHERE over posts (joined 1:1 to the author),
    not UNION-ed, so a post that qualifies twice is still one row.
    """
    following_subq = (
        select(Follow.following_id)
        .where(
            Follow.follower_id == current_user.id,
            Follow.status == "accepted",
        )
    )

    # users I blocked (stored as follower=them, following=me)
    blocked_by_me_subq = (
        select(Follow.follower_id)
        .where(
            Follow.following_id == current_user.id,
            Follow.status == "blocked",
        )
    )

    # users who blocked me
    blocked_me_subq = (
        select(Follow.following_id)
        .where(
            Follow.follower_id == current_user.id,
            Follow.status == "blocked",
        )
    )

    stmt = (
        select(Post)
        .join(User, User.id == Post.user_id)
        .options(selectinload(Post.user))
        .where(
            or_(
                Post.user_id == current_user.id,
                User.is_private == False,
                Post.user_id.in_(following_subq),
            ),
            Post.user_id.not_in(blocked_by_me_subq),
            Post.user_id.not_in(blocked_me_subq),
        )
    )

    return with_liked_by_me(db, list(db.scalars(newest_first(stmt, page)).all()), current_user)


@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post: Post = Depends(get_accessible_post),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return with_liked_by_me(db, [post], current_user)[0]


@router.patch("/{post_id}", response_model=PostOut)
def update_post(
    post_id: int,
    data: PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = get_own_post(post_id, db, current_user)

    if "content" in data.model_fields_set:
        if data.content is None and not post.image_url:
            raise HTTPException(status_code=400, detail="Post cannot be empty")
        post.content = data.content

    db.commit()
    db.refresh(post)
    return with_liked_by_me(db, [post], current_user)[0]


@router.put("/{post_id}/image", response_model=PostOut)
def replace_post_image(
    post_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = get_own_post(post_id, db, current_user)

    uploaded = media.upload_image(media.read_image(image), current_user.id)
    old_public_id = post.image_public_id

    post.image_url = uploaded.url
    post.image_public_id = uploaded.public_id
    try:
        db.commit()
    except Exception:
        db.rollback()
        media.delete_image(uploaded.public_id)
        raise

    # only remove the old image once the new one is saved
    media.delete_image(old_public_id)
    db.refresh(post)
    return with_liked_by_me(db, [post], current_user)[0]


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = get_own_post(post_id, db, current_user)
    public_id = post.image_public_id

    db.delete(post)  # comments, likes and their notifications go via ON DELETE CASCADE
    db.commit()

    media.delete_image(public_id)
    push_counts(background_tasks, db, current_user.id)
