"""SignupService 단위 테스트용 도메인 객체 팩토리.

`User` 는 `auth_provider` / `auth_provider_id` / `user_id` / `status` 가 핵심. SQLAlchemy
모델은 단위 테스트에서 backref 이벤트가 문제되는 경우가 있어 SimpleNamespace 로 attribute
만 흉내낸다 (chat / friend 도메인 컨벤션 일치).

`UserDetailInform` 도 본 service 에선 존재 여부만 확인하므로 minimal stub 로 충분.
"""
from typing import Optional
from types import SimpleNamespace

from app.domain.auth.model.user import UserStatus
from app.config.oauth import OAuthProvider


class UserFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        user_id: Optional[str] = None,
        auth_provider: OAuthProvider = OAuthProvider.GOOGLE,
        auth_provider_id: str = "test@example.com",
        status: UserStatus = UserStatus.ACTIVE,
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            user_id=user_id or f"USER_test_{cls._counter:04d}",
            auth_provider=auth_provider,
            auth_provider_id=auth_provider_id,
            status=status,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class UserDetailInformFactory:
    """UserDetailInform — signup 은 존재 여부만 검증해 attribute 최소만 채움."""

    _counter = 0

    @classmethod
    def create(cls, *, user_id: str = "USER_test") -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(user_id=user_id)


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
