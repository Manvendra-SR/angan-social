# models/message.py
from sqlalchemy import ForeignKey, String, Text, DateTime, func, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # serves "messages of conversation X ordered by id" (history + polling)
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        CheckConstraint("char_length(body) > 0", name="ck_message_body_not_empty"),
        # idempotent sends: a retried request with the same key can't create a
        # second message. NULL keys never conflict (each NULL is distinct).
        Index("uq_messages_sender_idempotency_key", "sender_id", "idempotency_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # client-generated key (Idempotency-Key header), unique per sender
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation = relationship("Conversation", back_populates="messages")
