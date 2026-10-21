from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from app.schemas.user import UserSummary

MessageBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class ConversationCreate(BaseModel):
    user_id: int


class MessageCreate(BaseModel):
    # no sender_id field: the sender is always the authenticated user
    body: MessageBody


class MarkRead(BaseModel):
    # the newest message the client has actually displayed
    last_read_message_id: int = Field(ge=1)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender_id: int
    body: str
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    other_user: UserSummary
    last_message: MessageOut | None
    unread_count: int = 0
    updated_at: datetime
