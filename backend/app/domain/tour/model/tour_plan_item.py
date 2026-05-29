from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index, UniqueConstraint, CheckConstraint

from app.util.id_generator import generate_tour_plan_item_id
from app.database.session import Base


class TourPlanItem(Base):
    """여행 플랜의 카드(여행지) 1건 (RDB)

    - day_number: 1-indexed 여행 일차
    - position: 같은 day 내 정렬 키. 추가/이동 시 (앞.position + 뒤.position)/2 로 한 행만 갱신
    - place_id: MongoDB Place 컬렉션의 Google Places ID 참조 (FK 제약 없음)
    - display_name / address: Place 가 사라져도 카드가 깨지지 않도록 스냅샷 보관 (rating 은 라이브 조회)
    """

    __tablename__ = "tour_plan_item"
    # `eager_defaults=True` — server-eval `updated_at` 을 RETURNING 으로 즉시 ORM 반영.
    # async 환경에서 lazy-load (MissingGreenlet) 회피 표준 패턴.
    __mapper_args__ = {"eager_defaults": True}

    item_id = Column(String(50), primary_key=True, default=generate_tour_plan_item_id)  # 카드 고유 ID
    plan_id = Column(String(50), ForeignKey("tour_plan.plan_id", ondelete="CASCADE"), nullable=False)  # 소속 플랜 ID
    day_number = Column(Integer, nullable=False)  # 여행 일차 (1-indexed)
    position = Column(Float, nullable=False)  # 같은 day 내 정렬 순서 (드래그 앤 드롭용)

    place_id = Column(String(255), nullable=False)  # MongoDB Place 참조 (FK 없음 주의해야 함)
    display_name = Column(String(255), nullable=False)  # 장소 이름 스냅샷
    address = Column(String(500), nullable=False)  # 주소 스냅샷

    visit_time = Column(String(5), nullable=True)  # 방문 시각 'HH:MM' (미정 가능)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    plan = relationship("TourPlan", back_populates="items")

    __table_args__ = (
        # (plan_id, day_number, position) 복합 UNIQUE — 동시 INSERT race 차단.
        # Unique index 가 자동 생성되므로 (plan_id, day_number, position) 정렬/조회용 일반 인덱스는 별도 불필요.
        UniqueConstraint("plan_id", "day_number", "position", name="uq_tour_plan_item_position"),
        Index("ix_tour_plan_item_place_id", "place_id"),
        CheckConstraint("day_number >= 1", name="ck_tour_plan_item_day_min"),
    )

    def __repr__(self):
        return f"<TourPlanItem(item_id={self.item_id}, plan_id={self.plan_id}, day={self.day_number}, pos={self.position})>"
