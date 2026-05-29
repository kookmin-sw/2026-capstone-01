from typing import List
from pydantic import BaseModel, Field
from datetime import datetime


# ──────────────────── Response ────────────────────

class FriendSearchHistoryResponse(BaseModel):
    search_name: str = Field(..., description="검색어")
    created_at: datetime = Field(..., description="검색 시각")


class FriendSearchHistoryListResponse(BaseModel):
    histories: List[FriendSearchHistoryResponse] = Field(..., description="검색 기록 목록 (최신순)")
