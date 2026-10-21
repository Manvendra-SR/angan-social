# models/notification.py
from sqlalchemy import (
    ForeignKey, String, Boolean, DateTime, func, text, Index, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

NOTIFICATION_TYPES = ("follow_request", "follow", "follow_accepted", "like", "comment")
FOLLOW_TYPES = ("follow_request", "follow", "follow_accepted")


class Notification(Base):
    """Something another user did that the recipient should hear about.

    Direct messages deliberately do not create rows here; they have their
    own unread tracking (conversation_reads).
    """
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("actor_id <> recipient_id", name="ck_notification_not_self"),
        CheckConstraint(
            "type IN ('follow_request', 'follow', 'follow_accepted', 'like', 'comment')",
            name="ck_notification_type",
        ),
        # likes and comments point at a post; only comments point at a comment
        CheckConstraint("(type IN ('like', 'comment')) = (post_id IS NOT NULL)", name="ck_notification_post"),
        CheckConstraint("(type = 'comment') = (comment_id IS NOT NULL)", name="ck_notification_comment"),
        # list newest first for a recipient
        Index("ix_notifications_recipient_id_id", "recipient_id", "id"),
        # unread badge count
        Index("ix_notifications_unread", "recipient_id", postgresql_where=text("NOT is_read")),
        # dedupe: one like notification per (liker, post), one per follow event type
        Index(
            "uq_notifications_like", "recipient_id", "actor_id", "post_id",
            unique=True, postgresql_where=text("type = 'like'"),
        ),
        Index(
            "uq_notifications_follow", "recipient_id", "actor_id", "type",
            unique=True, postgresql_where=text("type IN ('follow_request', 'follow', 'follow_accepted')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=True
    )
    comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor = relationship("User", foreign_keys=[actor_id])
