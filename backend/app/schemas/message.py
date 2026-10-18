from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, StringConstraints
from app.schemas.user import UserSummary

MessageBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class ConversationCreate(BaseModel):
    user_id: int


class MessageCreate(BaseModel):
    # no sender_id field: the sender is always the authenticated user
    body: MessageBody


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
    updated_at: datetime
