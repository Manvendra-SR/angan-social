# models/post.py
from sqlalchemy import ForeignKey, Text, DateTime, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, column_property
from .base import Base
from .like import Like
from .comment import Comment

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # image bytes live in Cloudinary; we keep the URL and the public_id
    # (needed to delete the asset later)
    image_url: Mapped[str | None] = mapped_column(nullable=True)
    image_public_id: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="posts")
    comments = relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    likes = relationship(
        "Like", back_populates="post", cascade="all, delete-orphan"
    )

    likes_count = column_property(
        select(func.count(Like.post_id))
        .where(Like.post_id == id)
        .correlate_except(Like)
        .scalar_subquery()
    )

    comments_count = column_property(
        select(func.count(Comment.post_id))
        .where(Comment.post_id == id)
        .correlate_except(Comment)
        .scalar_subquery()
    )

