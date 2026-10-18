from datetime import datetime
from pydantic import BaseModel, ConfigDict


class FollowRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    follower_id: int
    follower_username: str
    created_at: datetime
