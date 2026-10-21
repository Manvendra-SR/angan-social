# models/conversation_read.py
from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class ConversationRead(Base):
    """How far a user has read in a conversation.

    unread = messages in the conversation with id > last_read_message_id that
    were sent by the other person. A separate table (rather than columns on
    conversations) because create_all() can't add columns to existing tables.
    """
    __tablename__ = "conversation_reads"

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 0 = nothing read yet (not a FK; individual messages are never deleted)
    last_read_message_id: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
