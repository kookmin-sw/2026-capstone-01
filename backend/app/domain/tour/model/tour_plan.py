from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, CheckConstraint

from app.util.id_generator import generate_tour_plan_id
from app.database.session import Base


class TourPlan(Base):
    """저장된 여행 플랜 (RDB)

    - AI가 생성한 일정을 사용자가 저장 후 직접 편집 가능
    - 카드(여행지) 목록은 TourPlanItem 으로 분리되어 day/position 으로 정렬됨

    day_number 의미 (remove_day 도입 후):
    - travel_days 는 "부여된 적 있는 day_number 의 최댓값" — monotonic, 감소 안 함
    - add_day → travel_days += 1 (gap 재사용 X, 새 ID 부여)
    - remove_day(N) → 해당 day 의 카드만 일괄 제거 (travel_days 그대로, gap 생성)
    - gap day 는 valid 슬롯 — add_item / move_item 으로 재채움 가능 (의도된 동작)
    - "active day" 추론은 frontend 가 items 의 day_number 분포로 처리
    """

    __tablename__ = "tour_plan"
    # `eager_defaults=True` — server-eval `updated_at` 을 RETURNING 으로 즉시 ORM 반영.
    # async 환경에서 lazy-load (MissingGreenlet) 회피 표준 패턴.
    __mapper_args__ = {"eager_defaults": True}

    plan_id = Column(String(50), primary_key=True, default=generate_tour_plan_id)  # 플랜 고유 ID
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 작성자 ID
    title = Column(String(100), nullable=True)  # 사용자 지정 플랜 이름 (선택)
    travel_days = Column(Integer, nullable=False)  # 부여된 day_number 의 최댓값 (monotonic, remove 후에도 감소 X)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # 저장 시각
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())  # 마지막 편집 시각

    items = relationship(
        "TourPlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_tour_plan_user_id", "user_id"),
        CheckConstraint("travel_days >= 1", name="ck_tour_plan_travel_days_min"),
    )

    def __repr__(self):
        return f"<TourPlan(plan_id={self.plan_id}, user_id={self.user_id}, days={self.travel_days})>"
