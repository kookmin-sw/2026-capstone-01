"""Router 계층 HTTP 계약 테스트.

Service 를 Mock 으로 대체하고 FastAPI TestClient 로 라우터가:
- 성공 시 적절한 status code + JSON shape
- ValueError → 400, PermissionError → 403 매핑
- 요청 body 검증 실패 시 422
를 반환하는지 검증한다. 실 DB 가 필요 없어 POSTGRES_TEST_URL 없이도 실행된다.
"""

from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from dependency_injector import providers
from datetime import datetime, timezone

from app.domain.friend.service.friend_detail import UserNotFoundError
from app.domain.friend.router import friend_router
from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.friend.dto.user_block import UserBlockData
from app.domain.friend.dto.search import FriendSearchData, FriendSearchListData
from app.domain.friend.dto.friendship import (
    FriendPeerData,
    FriendshipData,
    FriendshipListData,
)
from app.domain.friend.dto.friend_detail import FriendDetailData
from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender
import app.database.model  # noqa: F401 — 매퍼 선 등록 (dto 가 enum 타입 참조)
from app.container import Container


pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────
# 공통 fixture
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def http():
    """Service 를 mock 으로 주입한 최소 FastAPI 앱 + TestClient."""
    container = Container()

    friendship_mock = AsyncMock()
    block_mock = AsyncMock()
    detail_mock = AsyncMock()

    container.friendship_service.override(providers.Object(friendship_mock))
    container.user_block_service.override(providers.Object(block_mock))
    container.friend_detail_service.override(providers.Object(detail_mock))

    app = FastAPI()
    app.container = container

    @app.middleware("http")
    async def inject_user(request, call_next):
        user_id = request.headers.get("X-User-Id")
        if user_id:
            request.state.user_id = user_id
        return await call_next(request)

    app.include_router(friend_router, prefix="/api")

    container.wire(modules=[
        "app.domain.friend.router.friendship",
        "app.domain.friend.router.user_block",
        "app.domain.friend.router.detail",
    ])

    try:
        with TestClient(app) as client:
            yield client, friendship_mock, block_mock, detail_mock
    finally:
        container.unwire()


def _friendship_dto(
    friendship_id: str = "FS_1",
    status: FriendshipStatus = FriendshipStatus.PENDING,
    peer_id: str = "USER_b",
) -> FriendshipData:
    return FriendshipData(
        friendship_id=friendship_id,
        status=status,
        peer=FriendPeerData(
            user_id=peer_id,
            user_name="피어",
            age=25,
            gender=Gender.MALE,
            nationality="KR",
        ),
        is_requester=True,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


# ──────────────────────────────────────────────────────────────────
# POST /api/friend/requests — 친구 요청
# ──────────────────────────────────────────────────────────────────

class TestSendFriendRequestEndpoint:
    def test_returns_201_with_payload_on_success(self, http):
        client, friendship_mock, _, _ = http
        friendship_mock.send_request.return_value = _friendship_dto()

        resp = client.post(
            "/api/friend/friendships/requests",
            json={"addressee_id": "USER_b"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["friendship_id"] == "FS_1"
        assert body["status"] == "pending"
        assert body["peer"]["user_id"] == "USER_b"
        assert body["is_requester"] is True


    def test_returns_400_on_value_error(self, http):
        client, friendship_mock, _, _ = http
        friendship_mock.send_request.side_effect = ValueError("이미 친구 요청을 보낸 상대입니다.")

        resp = client.post(
            "/api/friend/friendships/requests",
            json={"addressee_id": "USER_b"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "이미 친구 요청을 보낸 상대입니다."


    def test_returns_422_on_missing_body(self, http):
        client, _, _, _ = http

        resp = client.post(
            "/api/friend/friendships/requests",
            json={},  # addressee_id 누락
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────
# PATCH /api/friend/requests/{id}/accept — 수락
# ──────────────────────────────────────────────────────────────────

class TestAcceptEndpoint:
    def test_returns_200_with_message(self, http):
        client, friendship_mock, _, _ = http
        friendship_mock.accept_request.return_value = None

        resp = client.patch(
            "/api/friend/friendships/requests/FS_x/accept",
            headers={"X-User-Id": "USER_b"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"message": "친구 요청을 수락했습니다."}


    def test_maps_value_error_to_400(self, http):
        client, friendship_mock, _, _ = http
        friendship_mock.accept_request.side_effect = ValueError("존재하지 않는 친구 요청입니다.")

        resp = client.patch(
            "/api/friend/friendships/requests/FS_x/accept",
            headers={"X-User-Id": "USER_b"},
        )

        assert resp.status_code == 400
        assert "존재하지 않는" in resp.json()["detail"]


    def test_maps_permission_error_to_403(self, http):
        client, friendship_mock, _, _ = http
        friendship_mock.accept_request.side_effect = PermissionError("요청 수락 권한이 없습니다.")

        resp = client.patch(
            "/api/friend/friendships/requests/FS_x/accept",
            headers={"X-User-Id": "USER_c"},
        )

        assert resp.status_code == 403


# ──────────────────────────────────────────────────────────────────
# GET /api/friend — 친구 목록
# ──────────────────────────────────────────────────────────────────

class TestGetFriendsEndpoint:
    def test_returns_list_with_cursor(self, http):
        client, friendship_mock, _, _ = http
        friendship_mock.get_friends.return_value = FriendshipListData(
            items=[_friendship_dto(status=FriendshipStatus.ACCEPTED)],
            next_cursor="FS_cursor",
        )

        resp = client.get("/api/friend/friendships", headers={"X-User-Id": "USER_a"})

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["next_cursor"] == "FS_cursor"


# ──────────────────────────────────────────────────────────────────
# POST /api/friend/blocks — 차단
# ──────────────────────────────────────────────────────────────────

class TestBlockEndpoint:
    def test_returns_201_on_success(self, http):
        client, _, block_mock, _ = http
        block_mock.block_user.return_value = UserBlockData(
            block_id="BLK_1",
            blocked=FriendPeerData(
                user_id="USER_b",
                user_name="타겟",
                age=25,
                gender=Gender.MALE,
                nationality="KR",
            ),
            created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        )

        resp = client.post(
            "/api/friend/blocks",
            json={"target_user_id": "USER_b"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 201
        assert resp.json()["block_id"] == "BLK_1"
        assert resp.json()["blocked"]["user_id"] == "USER_b"


    def test_returns_400_on_value_error(self, http):
        client, _, block_mock, _ = http
        block_mock.block_user.side_effect = ValueError("이미 차단한 유저입니다.")

        resp = client.post(
            "/api/friend/blocks",
            json={"target_user_id": "USER_b"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 400


# ──────────────────────────────────────────────────────────────────
# GET /api/friend/detail/{user_id} — 친구 상세 조회
# ──────────────────────────────────────────────────────────────────

def _friend_detail_dto(user_id: str = "USER_b") -> FriendDetailData:
    return FriendDetailData(
        user_id=user_id,
        user_name="피어",
        age=25,
        gender=Gender.MALE,
        nationality="KR",
        travel_styles=[TravelStyle.FOOD_TOUR],
        friendship_id=None,
        friendship_status=None,
        is_requester=None,
        i_blocked_peer=False,
    )


class TestDetailEndpoint:
    def test_returns_200_with_public_profile(self, http):
        client, _, _, detail_mock = http
        detail_mock.get_friend_detail.return_value = _friend_detail_dto()

        resp = client.get(
            "/api/friend/detail/USER_b",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "USER_b"
        assert body["user_name"] == "피어"
        assert body["travel_styles"] == ["food_tour"]
        # 민감 정보는 응답에 없어야 함
        assert "email" not in body
        assert "phone_number" not in body
        assert "auth_provider" not in body


    def test_returns_404_on_user_not_found(self, http):
        client, _, _, detail_mock = http
        detail_mock.get_friend_detail.side_effect = UserNotFoundError("존재하지 않는 유저입니다.")

        resp = client.get(
            "/api/friend/detail/USER_ghost",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "존재하지 않는 유저입니다."


    def test_returns_400_on_incomplete_profile(self, http):
        client, _, _, detail_mock = http
        detail_mock.get_friend_detail.side_effect = ValueError("2차 회원가입이 완료되지 않은 유저입니다.")

        resp = client.get(
            "/api/friend/detail/USER_b",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 400
        assert "2차 회원가입" in resp.json()["detail"]


# ──────────────────────────────────────────────────────────────────
# /search + /search/history fixture
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def http_search():
    """search / search_history service mock 만 override.

    기존 ``http`` fixture 와 별도로 둬 시그니처(언팩 순서)를 분리한다.
    """
    container = Container()

    search_mock = AsyncMock()
    search_history_mock = AsyncMock()

    container.friend_search_service.override(providers.Object(search_mock))
    container.friend_search_history_service.override(providers.Object(search_history_mock))

    app = FastAPI()
    app.container = container

    @app.middleware("http")
    async def inject_user(request, call_next):
        user_id = request.headers.get("X-User-Id")
        if user_id:
            request.state.user_id = user_id
        return await call_next(request)

    app.include_router(friend_router, prefix="/api")

    container.wire(modules=[
        "app.domain.friend.router.search",
        "app.domain.friend.router.search_history",
    ])

    try:
        with TestClient(app) as client:
            yield client, search_mock, search_history_mock
    finally:
        container.unwire()


def _search_item_dto(
    user_id: str = "USER_b",
    user_name: str = "영희",
    friendship_status=None,
    is_requester=None,
) -> FriendSearchData:
    return FriendSearchData(
        user_id=user_id,
        user_name=user_name,
        nationality="KR",
        travel_styles=[TravelStyle.FOOD_TOUR],
        friendship_status=friendship_status,
        is_requester=is_requester,
        i_blocked_peer=False,
        profile_image_url=None,
    )


# ──────────────────────────────────────────────────────────────────
# GET /api/friend/search — 친구 추가 후보 검색
# ──────────────────────────────────────────────────────────────────

class TestSearchEndpoint:
    def test_returns_200_with_items_and_cursor(self, http_search):
        client, search_mock, _ = http_search
        search_mock.search.return_value = FriendSearchListData(
            items=[_search_item_dto()],
            next_cursor="USER_cursor",
        )

        resp = client.get(
            "/api/friend/search",
            params={"keyword": "영"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["next_cursor"] == "USER_cursor"
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["user_id"] == "USER_b"
        assert item["user_name"] == "영희"
        assert item["nationality"] == "KR"
        assert item["travel_styles"] == ["food_tour"]
        assert item["friendship_status"] is None
        assert item["is_requester"] is None
        assert item["i_blocked_peer"] is False


    def test_returns_pending_with_is_requester_payload(self, http_search):
        client, search_mock, _ = http_search
        search_mock.search.return_value = FriendSearchListData(
            items=[
                _search_item_dto(
                    friendship_status=FriendshipStatus.PENDING,
                    is_requester=True,
                ),
            ],
            next_cursor=None,
        )

        resp = client.get(
            "/api/friend/search",
            params={"keyword": "영"},
            headers={"X-User-Id": "USER_a"},
        )

        body = resp.json()
        assert body["items"][0]["friendship_status"] == "pending"
        assert body["items"][0]["is_requester"] is True


    def test_returns_400_on_whitespace_only_keyword(self, http_search):
        """router 단에서 strip + 빈 문자열 검증 — service 호출 자체가 일어나지 않음."""
        client, search_mock, _ = http_search

        resp = client.get(
            "/api/friend/search",
            params={"keyword": "   "},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 400
        assert "검색어" in resp.json()["detail"]
        search_mock.search.assert_not_called()


    def test_returns_422_on_missing_keyword(self, http_search):
        client, _, _ = http_search

        resp = client.get(
            "/api/friend/search",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 422


    def test_returns_400_when_service_raises_value_error(self, http_search):
        """service 가 정상 입력에서도 ValueError 를 던지면 400 으로 매핑."""
        client, search_mock, _ = http_search
        search_mock.search.side_effect = ValueError("검색어를 입력해주세요.")

        resp = client.get(
            "/api/friend/search",
            params={"keyword": "x"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 400


    def test_strips_keyword_before_passing_to_service(self, http_search):
        client, search_mock, _ = http_search
        search_mock.search.return_value = FriendSearchListData(items=[], next_cursor=None)

        client.get(
            "/api/friend/search",
            params={"keyword": "  영희  "},
            headers={"X-User-Id": "USER_a"},
        )

        # service 에는 normalized 키워드가 전달
        _, kwargs = search_mock.search.call_args
        assert kwargs["keyword"] == "영희"

    # ──────────────────── save_search 통합 ────────────────────

    def test_history_saved_on_first_page(self, http_search):
        client, search_mock, search_history_mock = http_search
        search_mock.search.return_value = FriendSearchListData(items=[], next_cursor=None)

        client.get(
            "/api/friend/search",
            params={"keyword": "영희"},
            headers={"X-User-Id": "USER_a"},
        )

        search_history_mock.save_search.assert_awaited_once_with(
            user_id="USER_a", search_name="영희",
        )


    def test_history_not_saved_on_paginated_call(self, http_search):
        """cursor 가 있는 페이지네이션 호출에선 save_search 미호출 — 동일 키워드 중복 갱신 차단."""
        client, search_mock, search_history_mock = http_search
        search_mock.search.return_value = FriendSearchListData(items=[], next_cursor=None)

        client.get(
            "/api/friend/search",
            params={"keyword": "영희", "cursor": "USER_xyz"},
            headers={"X-User-Id": "USER_a"},
        )

        search_history_mock.save_search.assert_not_called()


    def test_history_failure_does_not_block_search(self, http_search):
        """save_search best-effort — Mongo 장애 시에도 200 으로 검색 결과 반환."""
        client, search_mock, search_history_mock = http_search
        search_history_mock.save_search.side_effect = Exception("Mongo down")
        search_mock.search.return_value = FriendSearchListData(items=[], next_cursor=None)

        resp = client.get(
            "/api/friend/search",
            params={"keyword": "영희"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        # 검색은 정상 수행
        search_mock.search.assert_awaited_once()


    def test_history_save_uses_stripped_keyword(self, http_search):
        """history 에 저장되는 키워드도 normalized — `" 영희 "` → `"영희"`."""
        client, search_mock, search_history_mock = http_search
        search_mock.search.return_value = FriendSearchListData(items=[], next_cursor=None)

        client.get(
            "/api/friend/search",
            params={"keyword": "  영희  "},
            headers={"X-User-Id": "USER_a"},
        )

        search_history_mock.save_search.assert_awaited_once_with(
            user_id="USER_a", search_name="영희",
        )


# ──────────────────────────────────────────────────────────────────
# /search/history — 검색 기록 CRUD
# ──────────────────────────────────────────────────────────────────

from types import SimpleNamespace  # noqa: E402 — fixture/test 분리 후 사용


class TestSearchHistoryEndpoints:
    def test_get_returns_list_in_repo_order(self, http_search):
        client, _, search_history_mock = http_search
        search_history_mock.get_search_histories.return_value = [
            SimpleNamespace(
                search_name="조현상",
                created_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                search_name="민수",
                created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            ),
        ]

        resp = client.get(
            "/api/friend/search/history",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["histories"]) == 2
        assert body["histories"][0]["search_name"] == "조현상"
        assert body["histories"][1]["search_name"] == "민수"


    def test_get_returns_empty_list_when_no_history(self, http_search):
        client, _, search_history_mock = http_search
        search_history_mock.get_search_histories.return_value = []

        resp = client.get(
            "/api/friend/search/history",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"histories": []}


    def test_delete_one_returns_message(self, http_search):
        client, _, search_history_mock = http_search
        search_history_mock.delete_search.return_value = None

        resp = client.delete(
            "/api/friend/search/history/one",
            params={"search_name": "조현상"},
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        assert "삭제" in resp.json()["message"]
        search_history_mock.delete_search.assert_awaited_once_with(
            user_id="USER_a", search_name="조현상",
        )


    def test_delete_one_returns_422_on_missing_search_name(self, http_search):
        client, _, _ = http_search

        resp = client.delete(
            "/api/friend/search/history/one",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 422


    def test_delete_all_returns_message(self, http_search):
        client, _, search_history_mock = http_search
        search_history_mock.delete_all_searches.return_value = None

        resp = client.delete(
            "/api/friend/search/history",
            headers={"X-User-Id": "USER_a"},
        )

        assert resp.status_code == 200
        body = resp.json()
        # 전체 / 모두 둘 중 하나는 포함
        assert "전체" in body["message"] or "모두" in body["message"]
        search_history_mock.delete_all_searches.assert_awaited_once_with("USER_a")
