from typing import List
import time

from app.core.instrumentation import ai_inference, ai_model_load_duration_set
from app.core.ai.tour_planner.v2.graph_orchestrator import (
    TourPlannerGraphOrchestrator,
    get_tour_planner_graph,
)
from app.core.ai.tour_planner.v2.data_state import (
    FoodPreference,
    TourDayInput,
    TourPlanResult,
)


class TourPlanner:
    """Tour Planner — 사용자 맞춤 서울 여행 코스를 생성합니다."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance


    async def load(self) -> None:
        """서버 시작 시 한 번 호출된다."""
        if self._initialized:
            return
        started = time.perf_counter()
        self._orchestrator: TourPlannerGraphOrchestrator = get_tour_planner_graph()
        await self._orchestrator.initialize()
        ai_model_load_duration_set("tour_planner", time.perf_counter() - started)
        self._initialized = True


    async def invoke(
        self,
        travel_days: int,
        food_preference: FoodPreference,
        days: List[TourDayInput],
    ) -> TourPlanResult:
        """추론 요청의 단일 진입점.

        Args:
            travel_days: 여행 일수 (1~3)
            food_preference: 음식 옵션 (halal / vegetarian / any)
            days: 일자별 입력 (TourDayInput, 길이 == travel_days)

        Returns:
            TourPlanResult: tour_plan(list[TourDayPlan]) 형태의 최종 플랜
        """
        if not self._initialized:
            raise RuntimeError("모델이 로드되지 않았습니다.")

        async with ai_inference("tour_planner"):
            return await self._orchestrator.ainvoke(
                travel_days=travel_days,
                food_preference=food_preference,
                days=days,
            )
