"""WithdrawService 단위 테스트용 도메인 객체 팩토리.

`User` 는 `status` 필드가 핵심 — INACTIVE / ACTIVE / SUSPENDED 분기 검증에 사용. SQLAlchemy
모델을 직접 인스턴스화하지 않고 `SimpleNamespace` 로 attribute 흉내 (auth/profile_service
컨벤션 일치).
"""
from typing import Optional
from types import SimpleNamespace

from app.domain.auth.model.user import UserStatus


class UserFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        user_id: Optional[str] = None,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            user_id=user_id or f"USER_test_{cls._counter:04d}",
            status=status,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
