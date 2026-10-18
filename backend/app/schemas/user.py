from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9_]{3,30}$"),
]
Bio = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class UserCreate(BaseModel):
    username: Username
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    is_private: bool = False


class UserUpdate(BaseModel):
    username: Username | None = None
    bio: Bio | None = None
    is_private: bool | None = None


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class UserOut(UserSummary):
    """The logged-in user's own account (includes email)."""
    email: EmailStr
    bio: str | None
    is_private: bool
    created_at: datetime


class UserProfile(UserSummary):
    """Another user's public profile (no email)."""
    bio: str | None
    is_private: bool
    created_at: datetime
    followers_count: int
    following_count: int
    posts_count: int
    # my relationship to this user: None, "pending" or "accepted"
    follow_status: Literal["pending", "accepted"] | None = None
    # can I see their posts?
    can_view_posts: bool = True
