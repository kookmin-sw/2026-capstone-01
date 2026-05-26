"""Integration 테스트 공통 설정.

실제 PostgreSQL 을 대상으로 서비스 → 레포지토리 → DB 전체 흐름을 검증한다.

환경변수 ``POSTGRES_TEST_URL`` 이 설정돼 있어야 실행되며,
설정되지 않은 경우 모든 integration 테스트는 skip 된다.

예시::

    POSTGRES_TEST_URL="postgresql+asyncpg://cho:hyeonsang@localhost:5432/chohyeonsang_test"
"""

from typing import Callable
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
import pytest_asyncio
import pytest
import os

from app.domain.auth.model.user_detail_inform import Gender, UserDetailInform
from app.domain.auth.model.user import User, UserStatus
from app.database.session import Base, UnitOfWork
import app.database.model  # noqa: F401
from app.config.oauth import OAuthProvider


def _require_test_db_url() -> str:
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip(
            "POSTGRES_TEST_URL 환경변수가 설정되지 않아 integration 테스트를 건너뜁니다. "
            "예: POSTGRES_TEST_URL='postgresql+asyncpg://cho:hyeonsang@localhost:5432/chohyeonsang_test'",
            allow_module_level=False,
        )
    return url


@pytest_asyncio.fixture
async def engine():
    """매 테스트마다 새 엔진을 열고 테이블을 초기화.

    - asyncpg + pytest-asyncio 1.x 에서 session-scope async fixture 가
      event loop 격리 문제를 일으키는 것을 회피하기 위해 function-scope 로 둔다.
    - ``NullPool`` 로 연결 재사용을 끊어 동일 connection 경합을 방지한다.
    - 속도보다 신뢰성을 우선한 선택.
    """
    url = _require_test_db_url()
    engine = create_async_engine(url, echo=False, future=True, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def uow(session_factory) -> UnitOfWork:
    return UnitOfWork(session=session_factory)


@pytest_asyncio.fixture
async def seed_users(session_factory) -> Callable[..., "list[str]"]:
    """원하는 개수만큼 테스트용 유저를 생성하고 ID 리스트를 반환하는 팩토리.

    운영의 `User.user_id` 는 `default=generate_user_id` 로 INSERT 시점에 hash 가 부여되어
    중복이 자연 회피된다. 본 fixture 는 디버깅 용이성을 위해 명시적 `USER_IT_{idx:03d}` 를
    부여하므로, 같은 테스트 함수 안에서 여러 번 호출되어도 충돌하지 않도록 closure 카운터
    를 유지한다 (호출 간 idx 누적). fixture 자체는 함수 스코프라 테스트 간 자동 격리.
    """
    counter = {"value": 0}

    async def _seed(count: int = 3) -> list[str]:
        async with session_factory() as session:
            user_ids: list[str] = []
            for _ in range(count):
                idx = counter["value"]
                counter["value"] += 1
                uid = f"USER_IT_{idx:03d}"
                user_ids.append(uid)
                session.add(
                    User(
                        user_id=uid,
                        auth_provider=OAuthProvider.GOOGLE,
                        auth_provider_id=f"it_{uid}@example.com",
                        status=UserStatus.ACTIVE,
                    )
                )
                session.add(
                    UserDetailInform(
                        user_id=uid,
                        email=f"it_{uid}@example.com",
                        user_name=f"user{idx}",
                        age=20 + (idx % 60),
                        gender=Gender.MALE,
                        nationality="KR",
                    )
                )
            await session.commit()
        return user_ids

    return _seed
