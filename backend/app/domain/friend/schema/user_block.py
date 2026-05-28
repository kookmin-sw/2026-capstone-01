from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

from app.domain.friend.schema.friendship import FriendPeerResponse


# ──────────────────── Request ────────────────────

class BlockUserBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_user_id": "USER_1700000000_abcdef12",
            }
        }
    )

    target_user_id: str = Field(..., description="차단할 유저 ID")


# ──────────────────── Response ────────────────────

class UserBlockResponse(BaseModel):
    block_id: str = Field(..., description="차단 고유 ID")
    blocked: FriendPeerResponse = Field(..., description="차단 대상 유저 프로필")
    created_at: datetime = Field(..., description="차단 시각")


class UserBlockListResponse(BaseModel):
    items: List[UserBlockResponse] = Field(..., description="차단 목록")
    next_cursor: Optional[str] = Field(None, description="다음 페이지 커서 (마지막 페이지면 null)")
