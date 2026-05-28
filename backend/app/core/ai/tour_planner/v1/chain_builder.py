from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from functools import lru_cache

from app.core.llm_manager import ModelName, get_llm_manager
from app.core.ai.tour_planner.v1.prompt_manager import get_tour_planner_prompt_manager


class PlaceRecommendation(BaseModel):
    """추천 여행지 정보"""
    name: str = Field(description="여행지 이름")
    latitude: float = Field(description="위도")
    longitude: float = Field(description="경도")
    reason: str = Field(description="추천 이유 (1문장)")


class DayRecommendation(BaseModel):
    """일자별 여행 추천"""
    day: int = Field(description="여행 일차")
    cluster_name: str = Field(description="권역 이름")
    places: List[PlaceRecommendation] = Field(description="추천 여행지 목록 (1~3개)")


class TourRecommendationResult(BaseModel):
    """여행 추천 결과"""
    recommendations: List[DayRecommendation] = Field(description="일자별 여행 추천 목록")


class TourPlanLocation(BaseModel):
    """여행 플랜 장소 좌표"""
    lat: float = Field(description="위도")
    lng: float = Field(description="경도")


class TourPlanPlace(BaseModel):
    """여행 플랜 장소 정보"""
    place_id: str = Field(description="Google Places 고유 ID")
    display_name: str = Field(description="장소 이름")
    category: str = Field(description="카테고리")
    address: str = Field(description="주소")
    location: TourPlanLocation = Field(description="좌표")
    rating: Optional[float] = Field(None, description="평균 별점")
    description: str = Field(description="추천 이유와 특징 (2~3문장)")
    tip: str = Field(description="방문 팁 (1문장)")


class TourPlanDay(BaseModel):
    """일자별 여행 플랜"""
    day: int = Field(description="여행 일차")
    cluster_name: str = Field(description="권역 이름")
    places: List[TourPlanPlace] = Field(description="여행 장소 목록 (1~3개)")


class TourPlanResult(BaseModel):
    """최종 여행 플랜 결과"""
    tour_plan: List[TourPlanDay] = Field(description="일자별 여행 플랜 목록")


class TourPlannerChainManager:
    """Tour Planner 체인을 구성하는 클래스"""

    def __init__(self):
        self._prompt_manager = get_tour_planner_prompt_manager()
        self._llm_manager = get_llm_manager()
        self._chains: Dict[str, Any] = {}


    def build_recommend_destinations_chain(self) -> Any:
        """여행지 추천 체인을 생성합니다."""
        if 'recommend_destinations' not in self._chains:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._prompt_manager.get_prompt('recommend_destinations')),
                ("human", "여행 계획을 추천해주세요."),
            ])
            model = self._llm_manager.get_model(ModelName.GEMINI_2_5_FLASH)
            self._chains['recommend_destinations'] = prompt | model.with_structured_output(TourRecommendationResult)

        return self._chains['recommend_destinations']


    def build_tour_plan_chain(self) -> Any:
        """실제 장소 데이터 기반 여행 플랜 생성 체인을 생성합니다."""
        if 'build_tour_plan' not in self._chains:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._prompt_manager.get_prompt('build_tour_plan')),
                ("human", "여행 플랜을 만들어주세요."),
            ])
            model = self._llm_manager.get_model(ModelName.GEMINI_2_5_FLASH)
            self._chains['build_tour_plan'] = prompt | model.with_structured_output(TourPlanResult)

        return self._chains['build_tour_plan']


    def get_chain(self, chain_name: str) -> Optional[Any]:
        """특정 체인을 반환합니다."""
        return self._chains.get(chain_name)


    def build_all_chains(self) -> None:
        """모든 체인을 생성합니다."""
        self.build_recommend_destinations_chain()
        self.build_tour_plan_chain()


@lru_cache(maxsize=1)
def get_tour_planner_chain_builder() -> TourPlannerChainManager:
    """TourPlannerChainManager 싱글톤 인스턴스를 반환합니다."""
    return TourPlannerChainManager()
