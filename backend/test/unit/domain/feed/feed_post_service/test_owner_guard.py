"""`_load_owned_post` 권한/존재 분기 + 이를 통한 mutate 메서드 회귀 테스트.

`update_visibility` / `update_caption` / `delete_post` / `get_my_post` 가 모두
`_load_owned_post` 한 곳을 거치므로, 그 로직이 깨지면 4개 엔드포인트 권한이 동시에 깨진다.
이 파일이 단일 진입점의 보호 역할.

검증:
    - 미존재 post → FeedNotFoundError
    - 본인 아닌 post → PermissionError
    - 본인 post → 정상 반환 (mutate 메서드는 변경된 필드 + DTO 반환)
    - delete_post 가 DB row 삭제 후 S3 prefix 정리 (순서)
"""
from unittest.mock import MagicMock
from test.unit.domain.feed.mock_factory import make_feed_post_with_counts
import pytest
from datetime import datetime, timezone

from app.domain.feed.service.exception import FeedNotFoundError
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


def _mk_row(
    post_id="FDP_x",
    user_id="USER_owner",
    visibility=FeedVisibility.PUBLIC,
    caption="hi",
    *,
    like_count=0,
    comment_count=0,
):
    """`FeedPostWithCounts(post, like_count, comment_count)` 합성 — repo 의 단일 SELECT
    결과를 시뮬레이션. 테스트가 `row.post.x = ...` 로 mutate 검증할 수 있도록 frozen=True
    의 row 안에 mutable spec=FeedPost MagicMock 을 넣는다.
    """
    post = MagicMock(spec=FeedPost)
    post.post_id = post_id
    post.user_id = user_id
    post.visibility = visibility
    post.caption = caption
    post.original_url = "https://x/o.jpg"
    post.thumbnail_small_url = "https://x/s.jpg"
    post.thumbnail_medium_url = "https://x/m.jpg"
    post.created_at = datetime.now(timezone.utc)
    post.updated_at = datetime.now(timezone.utc)
    return make_feed_post_with_counts(
        post, like_count=like_count, comment_count=comment_count,
    )


# ──────────────────── 미존재 / 권한 거부 ────────────────────

@pytest.mark.unit
class TestLoadOwnedPostMissingOrForbidden:
    async def test_get_my_post_missing_raises_not_found(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = None
        with pytest.raises(FeedNotFoundError):
            await service.get_my_post(user_id="USER_a", post_id="FDP_missing")


    async def test_get_my_post_other_owner_raises_permission(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        with pytest.raises(PermissionError):
            await service.get_my_post(user_id="USER_intruder", post_id="FDP_x")


    async def test_update_visibility_missing_raises_not_found(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = None
        with pytest.raises(FeedNotFoundError):
            await service.update_visibility(
                user_id="USER_a", post_id="FDP_missing", visibility=FeedVisibility.PRIVATE,
            )


    async def test_update_visibility_other_owner_raises_permission(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        with pytest.raises(PermissionError):
            await service.update_visibility(
                user_id="USER_intruder", post_id="FDP_x", visibility=FeedVisibility.PRIVATE,
            )


    async def test_update_caption_other_owner_raises_permission(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        with pytest.raises(PermissionError):
            await service.update_caption(
                user_id="USER_intruder", post_id="FDP_x", caption="nope",
            )


    async def test_delete_post_other_owner_raises_permission(self, service, repo_mock, storage_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        with pytest.raises(PermissionError):
            await service.delete_post(user_id="USER_intruder", post_id="FDP_x")
        # 권한 거부면 storage 호출도 일어나면 안 됨 — 인가 검증 회귀 가드.
        storage_mock.delete_by_prefix.assert_not_called()


# ──────────────────── 정상 mutate 경로 ────────────────────

@pytest.mark.unit
class TestUpdateVisibilitySuccess:
    async def test_owner_can_change_visibility(self, service, repo_mock):
        row = _mk_row(user_id="USER_owner", visibility=FeedVisibility.PUBLIC)
        repo_mock.find_by_post_id.return_value = row

        result = await service.update_visibility(
            user_id="USER_owner", post_id="FDP_x", visibility=FeedVisibility.FRIENDS,
        )
        assert result.visibility == FeedVisibility.FRIENDS
        # row.post 객체에도 mutate 적용 (다음 조회/캐시 일관성)
        assert row.post.visibility == FeedVisibility.FRIENDS


    async def test_visibility_change_preserves_counts(self, service, repo_mock):
        """visibility 수정은 좋아요/댓글 수에 무관 — row 의 카운트 그대로 응답."""
        row = _mk_row(user_id="USER_owner", like_count=7, comment_count=3)
        repo_mock.find_by_post_id.return_value = row

        result = await service.update_visibility(
            user_id="USER_owner", post_id="FDP_x", visibility=FeedVisibility.PRIVATE,
        )
        assert result.like_count == 7
        assert result.comment_count == 3


@pytest.mark.unit
class TestUpdateCaptionSuccess:
    async def test_owner_can_set_non_empty_caption(self, service, repo_mock):
        row = _mk_row(user_id="USER_owner", caption=None)
        repo_mock.find_by_post_id.return_value = row

        result = await service.update_caption(
            user_id="USER_owner", post_id="FDP_x", caption="새 캡션",
        )
        assert result.caption == "새 캡션"
        assert row.post.caption == "새 캡션"


    async def test_owner_can_clear_with_empty_string(self, service, repo_mock):
        """빈 문자열 → 정규화 → None 으로 저장 (PATCH 와 POST 동일 규칙)."""
        row = _mk_row(user_id="USER_owner", caption="이전 캡션")
        repo_mock.find_by_post_id.return_value = row

        result = await service.update_caption(
            user_id="USER_owner", post_id="FDP_x", caption="",
        )
        assert result.caption is None
        assert row.post.caption is None


    async def test_owner_can_clear_with_whitespace(self, service, repo_mock):
        row = _mk_row(user_id="USER_owner", caption="이전")
        repo_mock.find_by_post_id.return_value = row

        result = await service.update_caption(
            user_id="USER_owner", post_id="FDP_x", caption="   \n\t  ",
        )
        assert result.caption is None


# ──────────────────── delete_post 흐름 ────────────────────

@pytest.mark.unit
class TestDeletePost:
    async def test_owner_delete_calls_db_then_storage(self, service, repo_mock, storage_mock):
        """auth/profile 패턴: DB row 삭제 후 S3 prefix 정리 (best-effort)."""
        row = _mk_row(user_id="USER_owner", post_id="FDP_x")
        repo_mock.find_by_post_id.return_value = row

        await service.delete_post(user_id="USER_owner", post_id="FDP_x")

        repo_mock.delete.assert_awaited_once_with(row.post)
        # prefix 는 `{user_id}/feed/{post_id}` 형식
        storage_mock.delete_by_prefix.assert_awaited_once_with("USER_owner/feed/FDP_x")


    async def test_storage_failure_is_swallowed(self, service, repo_mock, storage_mock):
        """S3 삭제 실패해도 사용자 작업은 성공 (orphan 만 남음). best-effort 보장 회귀."""
        row = _mk_row(user_id="USER_owner", post_id="FDP_x")
        repo_mock.find_by_post_id.return_value = row
        storage_mock.delete_by_prefix.side_effect = RuntimeError("S3 down")

        # raise 되지 않아야 함
        await service.delete_post(user_id="USER_owner", post_id="FDP_x")
        repo_mock.delete.assert_awaited_once()


    async def test_missing_post_raises_not_found_without_storage_call(
        self, service, repo_mock, storage_mock,
    ):
        repo_mock.find_by_post_id.return_value = None
        with pytest.raises(FeedNotFoundError):
            await service.delete_post(user_id="USER_owner", post_id="FDP_missing")
        storage_mock.delete_by_prefix.assert_not_called()


# ──────────────────── get_my_feed pagination ────────────────────

@pytest.mark.unit
class TestGetMyFeed:
    async def test_passes_all_visibilities_for_self(self, service, repo_mock):
        repo_mock.find_by_owner.return_value = []
        await service.get_my_feed(user_id="USER_a", cursor=None)

        call_kwargs = repo_mock.find_by_owner.await_args.kwargs
        assert call_kwargs["owner_id"] == "USER_a"
        assert set(call_kwargs["visibilities"]) == set(FeedVisibility)
        assert call_kwargs["cursor"] is None


    async def test_passes_self_as_viewer_id(self, service, repo_mock):
        """get_my_feed 는 본인이 viewer 라 viewer_id=user_id 전달 — 본인이 자기 글에
        누른 좋아요(인스타 동치)가 is_liked=True 로 합성되도록 보장.
        """
        repo_mock.find_by_owner.return_value = []
        await service.get_my_feed(user_id="USER_a", cursor=None)

        assert repo_mock.find_by_owner.await_args.kwargs["viewer_id"] == "USER_a"


    async def test_next_cursor_is_last_post_id_when_full_page(
        self, service, repo_mock, monkeypatch,
    ):
        """PAGE_SIZE 만큼 차면 next_cursor = 마지막 row.post.post_id."""
        # PAGE_SIZE 를 작게 패치해 fixture 로 가짜 row N개로 충족.
        monkeypatch.setattr("app.domain.feed.service.feed_post.PAGE_SIZE", 2)
        rows = [_mk_row(post_id=f"FDP_{i}", user_id="USER_a") for i in range(2)]
        repo_mock.find_by_owner.return_value = rows

        result = await service.get_my_feed(user_id="USER_a", cursor=None)
        assert result.next_cursor == "FDP_1"


    async def test_next_cursor_is_none_when_partial_page(
        self, service, repo_mock, monkeypatch,
    ):
        monkeypatch.setattr("app.domain.feed.service.feed_post.PAGE_SIZE", 5)
        rows = [_mk_row(post_id=f"FDP_{i}", user_id="USER_a") for i in range(3)]
        repo_mock.find_by_owner.return_value = rows

        result = await service.get_my_feed(user_id="USER_a", cursor=None)
        assert result.next_cursor is None


    async def test_response_includes_like_and_comment_counts(self, service, repo_mock):
        """list 응답의 각 DTO 가 row 의 카운트를 정확 매핑."""
        repo_mock.find_by_owner.return_value = [
            _mk_row(post_id="FDP_a", like_count=10, comment_count=2),
            _mk_row(post_id="FDP_b", like_count=0, comment_count=5),
        ]
        result = await service.get_my_feed(user_id="USER_a")
        assert result.posts[0].like_count == 10
        assert result.posts[0].comment_count == 2
        assert result.posts[1].like_count == 0
        assert result.posts[1].comment_count == 5


    async def test_response_propagates_is_liked_from_row(self, service, repo_mock):
        """row.is_liked 가 응답 DTO 까지 정확히 흘러가는지 — _to_dto 누락 회귀 가드."""
        repo_mock.find_by_owner.return_value = [
            make_feed_post_with_counts(
                _mk_row(post_id="FDP_a", user_id="USER_a").post, is_liked=True,
            ),
            make_feed_post_with_counts(
                _mk_row(post_id="FDP_b", user_id="USER_a").post, is_liked=False,
            ),
        ]
        result = await service.get_my_feed(user_id="USER_a")
        assert result.posts[0].is_liked is True
        assert result.posts[1].is_liked is False


# ──────────────────── _load_owned_post 가 viewer_id=user_id 전달 ────────────────────

@pytest.mark.unit
class TestLoadOwnedPostViewerForwarding:
    """`_load_owned_post` 가 `find_by_post_id` 호출 시 viewer_id 를 본인으로 박아 보내야
    본인의 좋아요 여부가 응답에 정확히 반영된다 (get_my_post / update_visibility /
    update_caption 응답 모두 이 경로 통과).
    """
    async def test_get_my_post_forwards_viewer_id(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        await service.get_my_post(user_id="USER_owner", post_id="FDP_x")
        assert repo_mock.find_by_post_id.await_args.kwargs["viewer_id"] == "USER_owner"


    async def test_update_visibility_forwards_viewer_id(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        await service.update_visibility(
            user_id="USER_owner", post_id="FDP_x", visibility=FeedVisibility.FRIENDS,
        )
        assert repo_mock.find_by_post_id.await_args.kwargs["viewer_id"] == "USER_owner"


    async def test_update_caption_forwards_viewer_id(self, service, repo_mock):
        repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        await service.update_caption(
            user_id="USER_owner", post_id="FDP_x", caption="새 캡션",
        )
        assert repo_mock.find_by_post_id.await_args.kwargs["viewer_id"] == "USER_owner"


    async def test_response_includes_is_liked_for_mutation_endpoints(
        self, service, repo_mock,
    ):
        """mutate 응답 (update_visibility/caption) 에도 is_liked 가 row 기준으로 정확 노출."""
        row = make_feed_post_with_counts(
            _mk_row(user_id="USER_owner", visibility=FeedVisibility.PUBLIC).post,
            is_liked=True,
        )
        repo_mock.find_by_post_id.return_value = row

        result = await service.update_caption(
            user_id="USER_owner", post_id="FDP_x", caption="hi",
        )
        assert result.is_liked is True
