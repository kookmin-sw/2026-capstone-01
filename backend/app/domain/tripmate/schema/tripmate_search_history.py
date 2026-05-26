from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

# ──────────────────── Response ────────────────────

class SearchHistoryResponse(BaseModel):
    search_name: str = Field(..., description="검색어")
    created_at: datetime = Field(..., description="검색 시각")


class SearchHistoryListResponse(BaseModel):
    histories: List[SearchHistoryResponse] = Field(..., description="검색 기록 목록 (최신순)")


