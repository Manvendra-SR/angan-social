from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from app.schemas.user import UserSummary

CommentContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class CommentCreate(BaseModel):
    content: CommentContent


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    user_id: int
    author: UserSummary = Field(validation_alias="user")
    content: str
    created_at: datetime
