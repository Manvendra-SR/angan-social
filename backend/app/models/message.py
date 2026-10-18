# models/message.py
from sqlalchemy import ForeignKey, Text, DateTime, func, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # serves "messages of conversation X ordered by id" (history + polling)
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        CheckConstraint("char_length(body) > 0", name="ck_message_body_not_empty"),
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

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation = relationship("Conversation", back_populates="messages")
