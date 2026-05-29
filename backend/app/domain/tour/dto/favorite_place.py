from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.tour.dto.place import PlaceDetailData


@dataclass
class FavoritePlaceData:
    """즐겨찾기 단건 DTO"""
    favorite_id: str
    created_at: datetime
    place: PlaceDetailData


@dataclass
class FavoritePlaceListData:
    """즐겨찾기 목록 DTO"""
    favorites: List[FavoritePlaceData]
    total_count: int
