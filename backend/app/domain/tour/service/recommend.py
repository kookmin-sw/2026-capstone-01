from google.api_core.exceptions import (
    GoogleAPICallError,
    PermissionDenied,
    ResourceExhausted,
    Unauthenticated,
)

from app.domain.tour.service.exception import (
    TourRecommendCredentialExpiredError,
    TourRecommendQuotaExceededError,
    TourRecommendVendorError,
)
from app.domain.tour.schema.recommend import (
    TourBudgetItemResponse,
    TourDayResponse,
    TourMovementHopResponse,
    TourPlaceDetailResponse,
    TourPlaceLocationResponse,
    TourRecommendRequest,
    TourRecommendResponse,
    TourTimelineSlotResponse,
)
from app.core.ai.tour_planner.v2.data_state import (
    TourDayInput as PlannerTourDayInput,
    TourPlanResult,
)
from app.core.ai.tour_planner.load import TourPlanner


class RecommendService:
    """여행 추천 서비스

    - 라우터에서 받은 요청(Pydantic Request)을 Tour Planner 입력으로 정규화해 호출
    - Tour Planner 결과(TourPlanResult)를 응답 스키마(TourRecommendResponse)로 변환

    Tour Planner 자체는 무상태 싱글톤이라 UoW를 받지 않는다 (MenuOcrService와 동일 패턴).
    """

    def __init__(self) -> None:
        self._planner = TourPlanner()


    # ──────────────────── 진입점 ────────────────────


    async def recommend(self, body: TourRecommendRequest) -> TourRecommendResponse:
        """여행 코스 추천."""
        planner_days = self._to_planner_input(body)

        try:
            result = await self._planner.invoke(
                travel_days=body.travel_days,
                food_preference=body.food_preference,
                days=planner_days,
            )
        except (Unauthenticated, PermissionDenied) as e:
            raise TourRecommendCredentialExpiredError(str(e)) from e
        except ResourceExhausted as e:
            raise TourRecommendQuotaExceededError(str(e)) from e
        except GoogleAPICallError as e:
            raise TourRecommendVendorError(str(e)) from e

        return self._to_response(result)


    # ──────────────────── Request → Planner 입력 ────────────────────


    @staticmethod
    def _to_planner_input(body: TourRecommendRequest) -> list[PlannerTourDayInput]:
        """Request 일자별 입력을 Tour Planner의 TourDayInput으로 변환."""
        return [
            PlannerTourDayInput(
                departure_cluster=d.departure_cluster,
                arrival_cluster=d.arrival_cluster,
                additional_place_id=d.additional_place_id,
                transport=d.transport,
                start_time=d.start_time,
                end_time=d.end_time,
                companion=d.companion,
                budget_per_person_krw=d.budget_per_person_krw,
                styles=list(d.styles),
                schedule_density=d.schedule_density,
            )
            for d in body.days
        ]


    # ──────────────────── Planner 결과 → Response ────────────────────


    @staticmethod
    def _to_response(result: TourPlanResult) -> TourRecommendResponse:
        """TourPlanResult → TourRecommendResponse 매핑."""
        return TourRecommendResponse(
            tour_plan=[
                TourDayResponse(
                    day=day.day,
                    timeline=[
                        TourTimelineSlotResponse(
                            time=slot.time,
                            place_id=slot.place_id,
                            title=slot.title,
                        )
                        for slot in day.timeline
                    ],
                    places=[
                        TourPlaceDetailResponse(
                            place_id=p.place_id,
                            display_name=p.display_name,
                            category=p.category,
                            address=p.address,
                            location=TourPlaceLocationResponse(
                                lat=p.location.lat, lng=p.location.lng
                            ),
                            rating=p.rating,
                            reason=p.reason,
                            estimated_cost_krw=p.estimated_cost_krw,
                            stay_minutes=p.stay_minutes,
                            photos=p.photos,
                        )
                        for p in day.places
                    ],
                    movements=[
                        TourMovementHopResponse(
                            from_place=m.from_place,
                            to_place=m.to_place,
                            method=m.method,
                        )
                        for m in day.movements
                    ],
                    budget_breakdown=[
                        TourBudgetItemResponse(label=b.label, amount_krw=b.amount_krw)
                        for b in day.budget_breakdown
                    ],
                    budget_total_krw=day.budget_total_krw,
                    summary=day.summary,
                )
                for day in result.tour_plan
            ],
        )
