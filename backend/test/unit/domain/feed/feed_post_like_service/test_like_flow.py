"""좋아요 add/remove/list 비즈니스 로직 회귀.

검증:
    - add: 정상 → save 호출 + 새 count 반환
    - add: 이미 누른 상태 → ValueError (중복 방지)
    - add: race (find 통과 후 INSERT IntegrityError) → ValueError 로 변환 (400)
    - remove: 정상 → delete 호출 + 새 count 반환
    - remove: 안 누른 상태 → ValueError
    - list: 단일 JOIN 쿼리 결과 → DTO (user_id / user_name / profile_image_url) 정확 매핑
    - list: detail 결손 → user_name="" / profile_image_url=None fallback (chat 컨벤션)
    - 모든 진입점이 `load_viewable_post` 를 호출 (가시성 transitive 적용)
    - 가시성 raise 는 catch 안 함 (그대로 propagate → router 가 매핑)
"""
from unittest.mock import AsyncMock
from test.unit.domain.feed.mock_factory import make_feed_post_like_mock
from sqlalchemy.exc import IntegrityError
import pytest

from app.domain.feed.service.exception import FeedNotFoundError


# ──────────────────── add ────────────────────

@pytest.mark.unit
class TestAddLike:
    async def test_success_returns_new_count(self, service, like_repo_mock):
        like_repo_mock.find_by_user_and_post.return_value = None
        like_repo_mock.count_by_post.return_value = 5

        count = await service.add_like(user_id="USER_v", post_id="FDP_x")
        assert count == 5
        like_repo_mock.save.assert_awaited_once()
        # save 의 첫 인자가 FeedPostLike(user_id, post_id)
        saved = like_repo_mock.save.await_args.args[0]
        assert saved.user_id == "USER_v"
        assert saved.post_id == "FDP_x"


    async def test_duplicate_raises_value_error(self, service, like_repo_mock):
        like_repo_mock.find_by_user_and_post.return_value = object()  # 이미 누름
        with pytest.raises(ValueError, match="이미 좋아요"):
            await service.add_like(user_id="USER_v", post_id="FDP_x")
        like_repo_mock.save.assert_not_called()


    async def test_race_integrity_error_treated_as_duplicate(
        self, service, like_repo_mock,
    ):
        """find 통과 직후 INSERT 에서 composite PK 충돌 (동시 두 번 클릭) →
        일반 중복 케이스와 동일한 ValueError 로 일원화 (라우터에서 400)."""
        like_repo_mock.find_by_user_and_post.return_value = None  # find 분기 통과
        like_repo_mock.save.side_effect = IntegrityError(
            statement="INSERT", params=None, orig=Exception("duplicate key"),
        )
        with pytest.raises(ValueError, match="이미 좋아요"):
            await service.add_like(user_id="USER_v", post_id="FDP_x")
        # IntegrityError 후엔 같은 session 으로 추가 쿼리 안 함 (PendingRollbackError 회피)
        like_repo_mock.count_by_post.assert_not_called()


# ──────────────────── remove ────────────────────

@pytest.mark.unit
class TestRemoveLike:
    async def test_success_returns_new_count(self, service, like_repo_mock):
        like_repo_mock.find_by_user_and_post.return_value = object()
        like_repo_mock.count_by_post.return_value = 4

        count = await service.remove_like(user_id="USER_v", post_id="FDP_x")
        assert count == 4
        like_repo_mock.delete_by_user_and_post.assert_awaited_once_with("USER_v", "FDP_x")


    async def test_not_liked_raises_value_error(self, service, like_repo_mock):
        like_repo_mock.find_by_user_and_post.return_value = None
        with pytest.raises(ValueError, match="좋아요를 누르지 않은"):
            await service.remove_like(user_id="USER_v", post_id="FDP_x")
        like_repo_mock.delete_by_user_and_post.assert_not_called()


# ──────────────────── list ────────────────────

@pytest.mark.unit
class TestGetLikedUsers:
    """단일 JOIN 쿼리 결과 (`find_with_user_by_post`) 가 LikedUserData 로 정확히 매핑되는지."""

    async def test_maps_user_profile_fields(self, service, like_repo_mock):
        like_repo_mock.find_with_user_by_post.return_value = [
            make_feed_post_like_mock(
                user_id="USER_a", user_name="Alice", profile_image_url="https://x/a.jpg",
            ),
            make_feed_post_like_mock(
                user_id="USER_b", user_name="Bob", profile_image_url=None,
            ),
        ]
        result = await service.get_liked_users(viewer_id="USER_v", post_id="FDP_x")

        assert len(result) == 2
        assert result[0].user_id == "USER_a"
        assert result[0].user_name == "Alice"
        assert result[0].profile_image_url == "https://x/a.jpg"
        assert result[1].user_id == "USER_b"
        assert result[1].user_name == "Bob"
        assert result[1].profile_image_url is None


    async def test_missing_detail_falls_back_to_empty(self, service, like_repo_mock):
        """detail 결손 (회원가입 미완료) → user_name='' / profile_image_url=None.

        chat 도메인 `_user_to_member_dto` 와 동일 fallback — 응답 형태 일관성 유지.
        """
        like_repo_mock.find_with_user_by_post.return_value = [
            make_feed_post_like_mock(user_id="USER_x", detail_present=False),
        ]
        result = await service.get_liked_users(viewer_id="USER_v", post_id="FDP_x")
        assert result[0].user_id == "USER_x"
        assert result[0].user_name == ""
        assert result[0].profile_image_url is None


    async def test_empty_list_when_no_likes(self, service, like_repo_mock):
        like_repo_mock.find_with_user_by_post.return_value = []
        result = await service.get_liked_users(viewer_id="USER_v", post_id="FDP_x")
        assert result == []


    async def test_repo_call_uses_resolved_post_id(self, service, like_repo_mock):
        """service 가 viewable post 의 post_id 로 repo 호출 (path post_id 그대로 X)."""
        like_repo_mock.find_with_user_by_post.return_value = []
        await service.get_liked_users(viewer_id="USER_v", post_id="FDP_x")
        like_repo_mock.find_with_user_by_post.assert_awaited_once_with("FDP_x")


# ──────────────────── 가시성 propagate ────────────────────

@pytest.mark.unit
class TestVisibilityPropagation:
    """`load_viewable_post` 가 raise 하면 service 가 catch 하지 않고 그대로 올린다."""

    async def test_add_propagates_not_found(self, monkeypatch, service, like_repo_mock):
        async def _raise(*a, **kw):
            raise FeedNotFoundError("존재하지 않는 게시물입니다.")
        monkeypatch.setattr(
            "app.domain.feed.service.feed_post_like.load_viewable_post", _raise,
        )
        with pytest.raises(FeedNotFoundError):
            await service.add_like(user_id="USER_v", post_id="FDP_missing")
        # 가시성 실패 시 좋아요 INSERT 자체 안 일어남
        like_repo_mock.save.assert_not_called()


    async def test_remove_propagates_not_found(
        self, monkeypatch, service, like_repo_mock,
    ):
        async def _raise(*a, **kw):
            raise FeedNotFoundError("...")
        monkeypatch.setattr(
            "app.domain.feed.service.feed_post_like.load_viewable_post", _raise,
        )
        with pytest.raises(FeedNotFoundError):
            await service.remove_like(user_id="USER_v", post_id="FDP_missing")
