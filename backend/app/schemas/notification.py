from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserSummary


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal["follow_request", "follow", "follow_accepted", "like", "comment"]
    actor: UserSummary
    post_id: int | None
    comment_id: int | None
    is_read: bool
    created_at: datetime


class Counts(BaseModel):
    """Absolute badge values (never increments, so they can't drift)."""
    unread_notifications: int
    unread_messages: int
