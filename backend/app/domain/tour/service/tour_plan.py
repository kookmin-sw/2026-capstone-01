from typing import Optional
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from collections import defaultdict

from app.domain.tour.repository.tour_plan import TourPlanRepository
from app.domain.tour.repository.tour_plan_item import TourPlanItemRepository
from app.domain.tour.repository.place import PlaceRepository
from app.domain.tour.model.tour_plan import TourPlan
from app.domain.tour.model.tour_plan_item import TourPlanItem
from app.domain.tour.service.exception import TourPlanNotFoundError, TourPlanItemNotFoundError
from app.domain.tour.dto.tour_plan import (
    TourPlanItemCreateInput,
    TourPlanItemData,
    TourPlanData,
    TourPlanSummaryData,
    TourPlanListData,
    ShareTokenData,
)
from app.database.session import UnitOfWork, transactional
from app.util.share_token import encode_share_token


# 카드 position 의 기본 간격. 큰 값일수록 같은 자리 반복 삽입 시 float 정밀도 여유 ↑
# (1.0 시작 대비 ~10번 더 절반 분할 가능)
_POSITION_SPACING = 1024.0

# UNIQUE(plan_id, day_number, position) 경합 시 최대 재시도 횟수.
# 솔로 편집 시 사실상 1번에 성공, 동시 편집 도입 시에도 2~3 회면 수렴.
_MAX_POSITION_RETRY = 3


class TourPlanService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.place_repo = PlaceRepository()


    # ──────────────────── 플랜 생성 ────────────────────

    @transactional
    async def create_plan(
        self,
        user_id: str,
        title: Optional[str],
        travel_days: int,
        items: list[TourPlanItemCreateInput],
    ) -> TourPlanData:
        """플랜 + 카드 일괄 저장

        1. 입력 검증 (travel_days, day_number 범위)
        2. MongoDB Place 배치 조회 → display_name / address 스냅샷
        3. day 별 position 을 _POSITION_SPACING 간격으로 부여 (1024.0, 2048.0, ...)
        4. plan.items.append + plan_repo.save → relationship cascade 로 한 번에 INSERT
        5. 응답 DTO 빌드 (rating 라이브)

        같은 plan/day 안의 position 은 시퀀셜이라 race 무관 — UNIQUE 재시도는 add_item / move_item 에서.
        """
        if travel_days < 1:
            raise ValueError("travel_days 는 1 이상이어야 합니다.")
        if not items:
            raise ValueError("카드가 1개 이상 필요합니다.")
        for it in items:
            if not (1 <= it.day_number <= travel_days):
                raise ValueError(f"day_number 가 범위를 벗어났습니다: {it.day_number}")

        # MongoDB 배치 조회 → place_id 스냅샷
        place_ids = list({it.place_id for it in items})
        raw_places = await self.place_repo.find_by_place_ids(place_ids)
        place_map = {p["place_id"]: p for p in raw_places}

        missing = [pid for pid in place_ids if pid not in place_map]
        if missing:
            raise ValueError(f"존재하지 않는 장소가 있습니다: {missing}")

        # plan + items 그래프 구성 (FK 는 cascade 가 채움)
        plan = TourPlan(user_id=user_id, title=title, travel_days=travel_days)

        day_positions: dict[int, float] = defaultdict(float)
        for it in items:
            day_positions[it.day_number] += _POSITION_SPACING
            raw = place_map[it.place_id]
            plan.items.append(TourPlanItem(
                day_number=it.day_number,
                position=day_positions[it.day_number],
                place_id=it.place_id,
                display_name=raw["display_name"],
                address=raw["address"],
                visit_time=it.visit_time,
            ))

        plan_repo = TourPlanRepository(self._session)
        await plan_repo.save(plan)

        sorted_items = sorted(plan.items, key=lambda i: (i.day_number, i.position))
        return self._to_plan_dto(plan, sorted_items, place_map)


    # ──────────────────── 플랜 단건 조회 ────────────────────

    @transactional
    async def get_plan(self, plan_id: str, user_id: str) -> TourPlanData:
        """플랜 단건 조회 (카드 포함, 별점 라이브)"""
        plan_repo = TourPlanRepository(self._session)

        plan = await plan_repo.find_by_id_with_items(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 조회 권한이 없습니다.")

        items = sorted(plan.items, key=lambda i: (i.day_number, i.position))
        place_ids = list({i.place_id for i in items})
        raw_places = await self.place_repo.find_by_place_ids(place_ids)
        place_map = {p["place_id"]: p for p in raw_places}

        return self._to_plan_dto(plan, items, place_map)


    # ──────────────────── 플랜 목록 조회 ────────────────────

    @transactional
    async def get_plans(self, user_id: str) -> TourPlanListData:
        """유저의 플랜 목록 (최신순, 메타만)"""
        plan_repo = TourPlanRepository(self._session)
        plans = await plan_repo.find_all_by_user_id(user_id)
        return TourPlanListData(plans=[self._to_summary_dto(p) for p in plans])


    # ──────────────────── 플랜 메타 수정 ────────────────────

    @transactional
    async def update_plan_title(
        self,
        plan_id: str,
        user_id: str,
        title: Optional[str],
    ) -> TourPlanSummaryData:
        """플랜 title 수정 — null 이면 제목 제거.

        updated_at 은 명시적 Python touch — server-side onupdate 에 위임하면
        flush 후 attribute 가 expire 되어 _to_summary_dto 에서 lazy refresh 가
        트리거되며 async 컨텍스트에서 MissingGreenlet 위험. add_item 등 다른
        메서드와 동일 패턴으로 통일.
        """
        plan_repo = TourPlanRepository(self._session)

        plan = await plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 수정 권한이 없습니다.")

        plan.title = title
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)

        return self._to_summary_dto(plan)


    # ──────────────────── 플랜 공유 토큰 발급 ────────────────────

    @transactional
    async def generate_share_token(self, plan_id: str, user_id: str) -> ShareTokenData:
        """플랜 공유 토큰 발급 — JWT 로 plan_id 서명.

        - 본인 소유 플랜만 발급 가능
        - 토큰은 settings.SHARE_JWT_EXPIRATION_DAYS 일 후 만료
        - 동일 plan 에 여러 번 호출 가능 (각각 다른 토큰, 모두 유효)
        - 개별 revoke 미지원 (필요 시 SHARE_JWT_SECRET_KEY 회전으로 일괄 무효화)
        """
        plan_repo = TourPlanRepository(self._session)

        plan = await plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 공유 권한이 없습니다.")

        token, expires_at = encode_share_token(plan_id)
        return ShareTokenData(share_token=token, expires_at=expires_at)


    # ──────────────────── 플랜 일차 추가 ────────────────────

    @transactional
    async def add_day(self, plan_id: str, user_id: str) -> TourPlanSummaryData:
        """플랜에 빈 일차 추가 — travel_days += 1 (monotonic 증가).

        - travel_days 는 "max_day_number" 의미 (단조 증가). 새 day = 기존 max + 1.
        - remove_day 로 생긴 gap 은 재사용하지 않음 — day_number 의 단조성 보장.
        - 새 일차는 카드 0개 상태로 시작.
        - updated_at 은 명시적 Python touch (lazy refresh 회피, update_plan_title 와 동일 이유).
        - 중간 삽입은 미지원 (append only).
        """
        plan_repo = TourPlanRepository(self._session)

        plan = await plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 수정 권한이 없습니다.")

        plan.travel_days += 1
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)

        return self._to_summary_dto(plan)


    # ──────────────────── 플랜 일차 삭제 ────────────────────

    @transactional
    async def remove_day(self, plan_id: str, user_id: str, day_number: int) -> None:
        """플랜의 특정 일차 삭제 — 해당 day 의 모든 카드를 일괄 제거.

        설계 철학: **gap 보존 + 단조 증가 day_number (단순 monotonic 모델)**
        - travel_days 는 그대로 유지 (max_day_number 의미)
          → 삭제된 day_number 자리에 gap 생김 (예: {1,2,3,4,5} → remove(3) → {1,2,4,5}).
        - 뒷 일차의 day_number 를 당기지 않음 (cascading UPDATE 회피, day_number 가
          외부 참조에 안전한 monotonic ID 처럼 동작).
        - 이후 add_day 는 max+1 로 새 day_number 부여 (gap 재사용 X — 단조 증가).
        - gap day 는 valid 슬롯 — 같은 day_number 로 add_item / move_item 호출하면
          정상적으로 재채워짐 (의도된 동작; deleted_days 별도 추적 안 함).
          UX 상 "삭제된 day" 표시는 frontend 가 items 의 day_number 분포로 추론.

        구현:
        - bulk DELETE 1 번으로 해당 day 의 모든 카드 제거 (빈 day 도 idempotent).
        - plan row 미변경 → onupdate 가 안 터져서 명시적 plan.updated_at touch.
        """
        plan_repo = TourPlanRepository(self._session)
        item_repo = TourPlanItemRepository(self._session)

        plan = await plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 수정 권한이 없습니다.")
        if not (1 <= day_number <= plan.travel_days):
            raise ValueError(f"day_number 가 범위를 벗어났습니다: {day_number}")

        await item_repo.delete_by_plan_and_day(plan_id, day_number)

        # 카드 변경은 plan row 를 안 건드리므로 onupdate 가 안 터짐 → 명시적 touch
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)


    # ──────────────────── 플랜 삭제 ────────────────────

    @transactional
    async def delete_plan(self, plan_id: str, user_id: str) -> None:
        """플랜 삭제 (cascade 로 카드 자동 삭제)"""
        plan_repo = TourPlanRepository(self._session)

        plan = await plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 삭제 권한이 없습니다.")

        await plan_repo.delete(plan)


    # ──────────────────── 카드 추가 ────────────────────

    @transactional
    async def add_item(
        self,
        plan_id: str,
        user_id: str,
        day_number: int,
        place_id: str,
        visit_time: Optional[str] = None,
    ) -> TourPlanItemData:
        """카드 추가 — 해당 day 의 맨 끝에 삽입"""
        plan_repo = TourPlanRepository(self._session)
        item_repo = TourPlanItemRepository(self._session)

        plan = await plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")
        if plan.user_id != user_id:
            raise PermissionError("플랜 수정 권한이 없습니다.")
        if not (1 <= day_number <= plan.travel_days):
            raise ValueError(f"day_number 가 범위를 벗어났습니다: {day_number}")

        # MongoDB Place 조회 (스냅샷 + 별점)
        raw = await self.place_repo.find_by_place_id(place_id)
        if raw is None:
            raise ValueError("존재하지 않는 장소입니다.")

        item = await self._insert_item_at_day_end(
            item_repo=item_repo,
            plan_id=plan_id,
            day_number=day_number,
            place_id=place_id,
            display_name=raw["display_name"],
            address=raw["address"],
            visit_time=visit_time,
        )

        # 카드 변경은 plan row 를 안 건드리므로 onupdate 가 안 터짐 → 명시적 touch
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)

        return self._to_item_dto(item, raw.get("rating"), raw.get("photos") or [])


    # ──────────────────── 카드 교체 (PUT) ────────────────────

    @transactional
    async def update_item(
        self,
        item_id: str,
        user_id: str,
        place_id: str,
        visit_time: Optional[str],
        expected_plan_id: Optional[str] = None,
    ) -> TourPlanItemData:
        """카드 교체 — place_id + visit_time 일괄 갱신.

        - place_id 변경 시 display_name / address 스냅샷도 새 Place 기준으로 다시 채움
          (같은 place_id 라도 무조건 MongoDB 재조회 → 최신 스냅샷 부수효과)
        - day_number / position 은 변경 안 함 (이동은 move_item 사용)
        - expected_plan_id: URL 계층 검증용. item.plan_id 와 다르면 404 통일 처리.
        """
        plan_repo = TourPlanRepository(self._session)
        item_repo = TourPlanItemRepository(self._session)

        item = await item_repo.find_by_id(item_id)
        if item is None or (expected_plan_id is not None and item.plan_id != expected_plan_id):
            raise TourPlanItemNotFoundError("존재하지 않는 카드입니다.")

        plan = await plan_repo.find_by_id(item.plan_id)
        if plan is None:
            raise TourPlanItemNotFoundError("존재하지 않는 카드입니다.")
        if plan.user_id != user_id:
            raise PermissionError("카드 수정 권한이 없습니다.")

        # MongoDB Place 조회 (새 place_id 기준 스냅샷 + rating)
        raw = await self.place_repo.find_by_place_id(place_id)
        if raw is None:
            raise ValueError("존재하지 않는 장소입니다.")

        item.place_id = place_id
        item.display_name = raw["display_name"]
        item.address = raw["address"]
        item.visit_time = visit_time
        await item_repo.update(item)

        # 카드 변경은 plan row 를 안 건드리므로 onupdate 가 안 터짐 → 명시적 touch
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)

        return self._to_item_dto(item, raw.get("rating"), raw.get("photos") or [])


    # ──────────────────── 카드 이동 ────────────────────

    @transactional
    async def move_item(
        self,
        item_id: str,
        user_id: str,
        target_day_number: int,
        after_item_id: Optional[str],
        expected_plan_id: Optional[str] = None,
    ) -> None:
        """카드 이동 — target_day 의 after_item_id 다음 자리 (None 이면 맨 앞).

        expected_plan_id: URL 계층 검증용. item.plan_id 와 다르면 404 통일 처리.
        """
        plan_repo = TourPlanRepository(self._session)
        item_repo = TourPlanItemRepository(self._session)

        item = await item_repo.find_by_id(item_id)
        if item is None or (expected_plan_id is not None and item.plan_id != expected_plan_id):
            raise TourPlanItemNotFoundError("존재하지 않는 카드입니다.")

        plan = await plan_repo.find_by_id(item.plan_id)
        if plan is None:
            raise TourPlanItemNotFoundError("존재하지 않는 카드입니다.")
        if plan.user_id != user_id:
            raise PermissionError("카드 수정 권한이 없습니다.")
        if not (1 <= target_day_number <= plan.travel_days):
            raise ValueError(f"day_number 가 범위를 벗어났습니다: {target_day_number}")

        await self._update_item_position(
            item_repo=item_repo,
            item=item,
            target_day_number=target_day_number,
            after_item_id=after_item_id,
        )

        # 카드 변경은 plan row 를 안 건드리므로 onupdate 가 안 터짐 → 명시적 touch
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)


    # ──────────────────── 카드 삭제 ────────────────────

    @transactional
    async def remove_item(
        self,
        item_id: str,
        user_id: str,
        expected_plan_id: Optional[str] = None,
    ) -> None:
        """카드 단건 삭제.

        expected_plan_id: URL 계층 검증용. item.plan_id 와 다르면 404 통일 처리.
        """
        plan_repo = TourPlanRepository(self._session)
        item_repo = TourPlanItemRepository(self._session)

        item = await item_repo.find_by_id(item_id)
        if item is None or (expected_plan_id is not None and item.plan_id != expected_plan_id):
            raise TourPlanItemNotFoundError("존재하지 않는 카드입니다.")

        plan = await plan_repo.find_by_id(item.plan_id)
        if plan is None:
            raise TourPlanItemNotFoundError("존재하지 않는 카드입니다.")
        if plan.user_id != user_id:
            raise PermissionError("카드 삭제 권한이 없습니다.")

        await item_repo.delete(item)

        # 카드 변경은 plan row 를 안 건드리므로 onupdate 가 안 터짐 → 명시적 touch
        plan.updated_at = datetime.now(timezone.utc)
        await plan_repo.update(plan)


    # ──────────────────── position 계산 / 동시성 헬퍼 ────────────────────

    @staticmethod
    def _compute_position(day_items: list[TourPlanItem], after_item_id: Optional[str]) -> float:
        """day_items (position ASC) 중 after_item_id 다음 자리의 position 계산.

        - 빈 day: _POSITION_SPACING
        - after_item_id is None: 맨 앞 (first.position / 2)
        - after_item_id 가 마지막 카드: last.position + _POSITION_SPACING
        - 그 외: (after.position + next.position) / 2
        """
        if not day_items:
            return _POSITION_SPACING
        if after_item_id is None:
            return day_items[0].position / 2

        for idx, it in enumerate(day_items):
            if it.item_id == after_item_id:
                if idx == len(day_items) - 1:
                    return it.position + _POSITION_SPACING
                return (it.position + day_items[idx + 1].position) / 2

        raise ValueError(f"after_item_id 가 해당 day 에 없습니다: {after_item_id}")


    async def _insert_item_at_day_end(
        self,
        *,
        item_repo: TourPlanItemRepository,
        plan_id: str,
        day_number: int,
        place_id: str,
        display_name: str,
        address: str,
        visit_time: Optional[str],
    ) -> TourPlanItem:
        """day 의 맨 끝에 카드 INSERT — UNIQUE(plan_id, day_number, position) 경합 시 재시도.

        매 시도마다 max position 을 다시 읽어 다른 TX 가 같은 자리에 INSERT 한 row 를 반영.
        SAVEPOINT 로 INSERT 만 감싸서 외부 트랜잭션은 유지한 채 실패한 시도만 롤백.
        """
        for attempt in range(_MAX_POSITION_RETRY):
            all_items = await item_repo.find_by_plan_id(plan_id)
            day_items = [i for i in all_items if i.day_number == day_number]
            new_position = (day_items[-1].position + _POSITION_SPACING) if day_items else _POSITION_SPACING

            item = TourPlanItem(
                plan_id=plan_id,
                day_number=day_number,
                position=new_position,
                place_id=place_id,
                display_name=display_name,
                address=address,
                visit_time=visit_time,
            )
            try:
                async with self._session.begin_nested():
                    await item_repo.save(item)
                return item
            except IntegrityError:
                if attempt == _MAX_POSITION_RETRY - 1:
                    raise ValueError("카드 추가 경합으로 저장에 실패했습니다. 잠시 후 다시 시도해주세요.")
                # SAVEPOINT 롤백 → 다음 iteration 에서 max position 재조회


    async def _update_item_position(
        self,
        *,
        item_repo: TourPlanItemRepository,
        item: TourPlanItem,
        target_day_number: int,
        after_item_id: Optional[str],
    ) -> None:
        """카드 이동 — UNIQUE(plan_id, day_number, position) 경합 시 position 재계산 후 재시도.

        - 매 시도마다 day_items 를 다시 읽음 (자기 자신 제외)
        - SAVEPOINT 롤백 후 재시도하면 SQLAlchemy 가 객체 상태를 expire — 재할당으로 정상 UPDATE
        """
        for attempt in range(_MAX_POSITION_RETRY):
            all_items = await item_repo.find_by_plan_id(item.plan_id)
            day_items = [i for i in all_items if i.day_number == target_day_number and i.item_id != item.item_id]
            new_position = self._compute_position(day_items, after_item_id)

            item.day_number = target_day_number
            item.position = new_position
            try:
                async with self._session.begin_nested():
                    await item_repo.update(item)
                return
            except IntegrityError:
                if attempt == _MAX_POSITION_RETRY - 1:
                    raise ValueError("카드 이동 경합으로 저장에 실패했습니다. 잠시 후 다시 시도해주세요.")
                # SAVEPOINT 롤백 → 다음 iteration 에서 day_items 재조회


    # ──────────────────── 내부 변환 유틸 ────────────────────


    @staticmethod
    def _to_item_dto(item: TourPlanItem, rating: Optional[float], photos: list[str]) -> TourPlanItemData:
        return TourPlanItemData(
            item_id=item.item_id,
            day_number=item.day_number,
            position=item.position,
            place_id=item.place_id,
            display_name=item.display_name,
            address=item.address,
            visit_time=item.visit_time,
            rating=rating,
            photos=photos,
        )


    def _to_plan_dto(
        self,
        plan: TourPlan,
        items: list[TourPlanItem],
        place_map: dict[str, dict],
    ) -> TourPlanData:
        item_dtos = []
        for i in items:
            raw = place_map.get(i.place_id)
            rating = raw.get("rating") if raw else None
            photos = (raw.get("photos") or []) if raw else []
            item_dtos.append(self._to_item_dto(i, rating, photos))

        return TourPlanData(
            plan_id=plan.plan_id,
            user_id=plan.user_id,
            title=plan.title,
            travel_days=plan.travel_days,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            items=item_dtos,
        )


    @staticmethod
    def _to_summary_dto(plan: TourPlan) -> TourPlanSummaryData:
        return TourPlanSummaryData(
            plan_id=plan.plan_id,
            title=plan.title,
            travel_days=plan.travel_days,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
