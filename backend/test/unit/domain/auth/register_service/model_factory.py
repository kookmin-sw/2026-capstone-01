"""RegisterService 단위 테스트용 도메인 객체 팩토리.

`User` 는 존재 여부 검증에 사용 (find_by_id), `UserDetailInform` 은 중복 검증에만 사용.
SimpleNamespace 로 attribute 만 채우는 minimal stub.
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


class UserDetailInformFactory:
    """register 의 중복 가입 가드 검증 — 존재 여부만 의미. user_id 만 채움."""

    _counter = 0

    @classmethod
    def create(cls, *, user_id: str = "USER_test") -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(user_id=user_id)


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
