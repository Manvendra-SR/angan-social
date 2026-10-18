# models/conversation.py
from sqlalchemy import ForeignKey, DateTime, func, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Conversation(Base):
    """A one-to-one conversation.

    The pair is stored in a canonical order (user_a_id < user_b_id) so the
    unique constraint guarantees at most one conversation per pair of users.
    """
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id"),
        CheckConstraint("user_a_id < user_b_id", name="ck_conversation_user_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_a_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_b_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # bumped on every new message; used to sort the conversation list
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user_a = relationship("User", foreign_keys=[user_a_id])
    user_b = relationship("User", foreign_keys=[user_b_id])
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    def has_participant(self, user_id: int) -> bool:
        return user_id in (self.user_a_id, self.user_b_id)

    def other_user(self, user_id: int):
        return self.user_b if user_id == self.user_a_id else self.user_a
