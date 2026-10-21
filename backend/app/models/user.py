# models/user.py
from sqlalchemy import String, Boolean, DateTime, Index, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, column_property
from .base import Base
from .follow import Follow
from .post import Post

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(nullable=False)
    bio: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    posts = relationship(
        "Post", back_populates="user", cascade="all, delete-orphan"
    )
    comments = relationship(
        "Comment", back_populates="user", cascade="all, delete-orphan"
    )
    likes = relationship(
        "Like", back_populates="user", cascade="all, delete-orphan"
    )

    followers = relationship(
        "Follow",
        foreign_keys="[Follow.following_id]",
        cascade="all, delete-orphan",
    )
    following = relationship(
        "Follow",
        foreign_keys="[Follow.follower_id]",
        cascade="all, delete-orphan",
    )

    # only accepted follows count; pending requests and blocks (also stored in
    # the follows table) must not inflate the numbers
    followers_count = column_property(
        select(func.count(Follow.follower_id))
        .where(Follow.following_id == id, Follow.status == "accepted")
        .correlate_except(Follow)
        .scalar_subquery()
    )

    following_count = column_property(
        select(func.count(Follow.following_id))
        .where(Follow.follower_id == id, Follow.status == "accepted")
        .correlate_except(Follow)
        .scalar_subquery()
    )

    posts_count = column_property(
        select(func.count(Post.id))
        .where(Post.user_id == id)
        .correlate_except(Post)
        .scalar_subquery()
    )


# Case-insensitive uniqueness, enforced by the database even when two requests
# race past the Python pre-check. Usernames keep their display casing; emails
# are stored lowercase (see schemas/user.py). Existing databases get these via
# `python -m app.migrate`.
USERNAME_LOWER_INDEX = Index("uq_users_username_lower", func.lower(User.username), unique=True)
EMAIL_LOWER_INDEX = Index("uq_users_email_lower", func.lower(User.email), unique=True)
