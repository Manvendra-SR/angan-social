# models/like.py
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Like(Base):
    __tablename__ = "likes"

    # composite primary key (post_id, user_id) prevents duplicate likes
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")
