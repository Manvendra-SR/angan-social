from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from app.schemas.user import UserSummary

PostContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class PostUpdate(BaseModel):
    content: PostContent | None = None


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    author: UserSummary = Field(validation_alias="user")
    content: str | None
    image_url: str | None
    created_at: datetime
    likes_count: int
    comments_count: int
    liked_by_me: bool = False
