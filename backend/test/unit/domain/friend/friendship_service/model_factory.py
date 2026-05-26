from typing import List, Optional
from types import SimpleNamespace
from datetime import datetime, timezone

from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender


class UserFactory:
    """User + UserDetailInform 조합을 간단히 만드는 팩토리.

    SQLAlchemy 모델을 직접 쓰면 세션 의존성이 번거롭기에 SimpleNamespace로
    `user.user_id`, `user.detail.user_name`, `user.travel_styles[i].style`
    같은 속성 접근만 유사하게 제공한다.
    """

    _counter = 0

    @classmethod
    def create(
        cls,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        age: int = 20,
        gender: Gender = Gender.MALE,
        nationality: str = "KR",
        travel_styles: Optional[List[TravelStyle]] = None,
        detail: object = "default",
    ) -> SimpleNamespace:
        """detail=None 을 전달하면 2차 회원가입 미완료 케이스를 재현할 수 있다."""
        cls._counter += 1
        uid = user_id or f"USER_test_{cls._counter:04d}"
        uname = user_name or f"user{cls._counter}"

        if detail == "default":
            detail_obj = SimpleNamespace(
                user_id=uid,
                user_name=uname,
                age=age,
                gender=gender,
                nationality=nationality,
                profile_image_url=None,
            )
        else:
            detail_obj = detail  # None 또는 사용자 지정

        styles = [SimpleNamespace(style=s) for s in (travel_styles or [])]
        return SimpleNamespace(user_id=uid, detail=detail_obj, travel_styles=styles)


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class FriendshipFactory:
    """Friendship 모델 형태를 흉내내는 SimpleNamespace 생성.

    SQLAlchemy 인스트루멘테이션(backref 이벤트 등)을 우회해
    단위 테스트에서 어떤 세션 없이도 속성 접근/할당만 가능하게 한다.
    """

    _counter = 0

    @classmethod
    def create(
        cls,
        friendship_id: Optional[str] = None,
        requester_id: str = "USER_req",
        addressee_id: str = "USER_addr",
        status: FriendshipStatus = FriendshipStatus.PENDING,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        requester: Optional[SimpleNamespace] = None,
        addressee: Optional[SimpleNamespace] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        now = datetime(2026, 4, 20, tzinfo=timezone.utc)
        return SimpleNamespace(
            friendship_id=friendship_id or f"FS_test_{cls._counter:04d}",
            requester_id=requester_id,
            addressee_id=addressee_id,
            status=status,
            created_at=created_at or now,
            updated_at=updated_at or now,
            requester=requester,
            addressee=addressee,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class UserBlockFactory:
    """UserBlock 모델 형태를 흉내내는 SimpleNamespace 생성."""

    _counter = 0

    @classmethod
    def create(
        cls,
        block_id: Optional[str] = None,
        blocker_id: str = "USER_blocker",
        blocked_id: str = "USER_blocked",
        created_at: Optional[datetime] = None,
        blocked: Optional[SimpleNamespace] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        now = datetime(2026, 4, 20, tzinfo=timezone.utc)
        return SimpleNamespace(
            block_id=block_id or f"BLK_test_{cls._counter:04d}",
            blocker_id=blocker_id,
            blocked_id=blocked_id,
            created_at=created_at or now,
            blocked=blocked,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
