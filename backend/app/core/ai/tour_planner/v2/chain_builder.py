from typing import Any, Dict, Optional
from langchain_core.prompts import ChatPromptTemplate
from functools import lru_cache

from app.core.llm_manager import ModelName, get_llm_manager
from app.core.ai.tour_planner.v2.prompt_manager import get_tour_planner_prompt_manager
from app.core.ai.tour_planner.v2.data_state import TourDayPlan


class TourPlannerChainManager:
    """Tour Planner v2 체인 매니저

    데이터 모델은 모두 ``data_state.py``에 정의되어 있다.
    """

    def __init__(self):
        self._prompt_manager = get_tour_planner_prompt_manager()
        self._llm_manager = get_llm_manager()
        self._chains: Dict[str, Any] = {}


    def build_day_plan_chain(self) -> Any:
        """일자별 상세 플랜 체인 (일자별로 1회씩 호출)"""
        if 'build_day_plan' not in self._chains:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._prompt_manager.get_prompt('build_day_plan')),
                ("human", "Please build the travel plan for this day."),
            ])
            model = self._llm_manager.get_model(ModelName.GEMINI_2_5_FLASH)
            self._chains['build_day_plan'] = prompt | model.with_structured_output(TourDayPlan)

        return self._chains['build_day_plan']


    def get_chain(self, chain_name: str) -> Optional[Any]:
        return self._chains.get(chain_name)


    def build_all_chains(self) -> None:
        self.build_day_plan_chain()


@lru_cache(maxsize=1)
def get_tour_planner_chain_builder() -> TourPlannerChainManager:
    """TourPlannerChainManager 싱글톤"""
    return TourPlannerChainManager()
