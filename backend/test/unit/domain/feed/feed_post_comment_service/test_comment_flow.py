"""댓글 작성/목록/삭제 비즈니스 로직 회귀.

검증:
    - create_comment: 정상 (작성자 프로필 포함 응답) / 빈 본문 / 공백만 본문 / detail 결손 fallback
    - list_comments: 페이지네이션 next_cursor 약속 / 작성자 프로필 매핑
    - delete_comment: 작성자 권한 / 미존재 / post 매칭 실패
    - 캡션 정책과 차이: 빈 댓글 = 400 (캡션은 None 정규화)
    - 단일 JOIN 쿼리: repo (`find_by_id` / `find_by_post`) 가 user.detail 까지 한 번에 로드,
      service 의 `_to_dto` 가 닉네임/프로필 이미지를 정확 매핑 + detail 결손 fallback (chat
      / like 도메인 컨벤션 일치).
"""
from test.unit.domain.feed.mock_factory import make_feed_post_comment_mock
import pytest

from app.domain.feed.service.exception import FeedPostCommentNotFoundError


# ──────────────────── create ────────────────────

@pytest.mark.unit
class TestCreateComment:
    async def test_success_returns_dto_with_author_profile(
        self, service, comment_repo_mock,
    ):
        """INSERT 후 reload (`find_by_id`) 결과의 user.detail 이 응답에 매핑."""
        comment_repo_mock.find_by_id.return_value = make_feed_post_comment_mock(
            content="hello", user_id="USER_v",
            user_name="Alice", profile_image_url="https://x/a.jpg",
        )
        result = await service.create_comment(
            user_id="USER_v", post_id="FDP_x", content="hello",
        )
        assert result.content == "hello"
        assert result.post_id == "FDP_x"
        assert result.user_id == "USER_v"
        assert result.user_name == "Alice"
        assert result.profile_image_url == "https://x/a.jpg"
        comment_repo_mock.save.assert_awaited_once()
        comment_repo_mock.find_by_id.assert_awaited_once()  # reload 호출 검증


    async def test_strips_leading_trailing_whitespace(self, service, comment_repo_mock):
        """비-빈 댓글의 양끝 공백은 제거 (캡션과 다른 정책)."""
        comment_repo_mock.find_by_id.return_value = make_feed_post_comment_mock(
            content="hello",
        )
        result = await service.create_comment(
            user_id="USER_v", post_id="FDP_x", content="  hello  ",
        )
        # service 가 strip 후 INSERT — repo.save 의 인자 검증
        saved_arg = comment_repo_mock.save.await_args.args[0]
        assert saved_arg.content == "hello"


    async def test_missing_detail_falls_back_to_empty(
        self, service, comment_repo_mock,
    ):
        """detail 결손 (회원가입 미완료) → user_name='' / profile_image_url=None.

        chat / like 도메인의 동일 fallback — 응답 형태 일관성.
        """
        comment_repo_mock.find_by_id.return_value = make_feed_post_comment_mock(
            content="hello", user_id="USER_v", detail_present=False,
        )
        result = await service.create_comment(
            user_id="USER_v", post_id="FDP_x", content="hello",
        )
        assert result.user_id == "USER_v"
        assert result.user_name == ""
        assert result.profile_image_url is None


    @pytest.mark.parametrize("content", ["", "   ", "\n\t", "  \n  "])
    async def test_blank_content_raises_value_error(
        self, service, comment_repo_mock, content,
    ):
        # schema 의 min_length=1 이 1차로 빈 문자열 차단하지만, service 도 strip 후 검증
        # (공백만은 schema 통과 → service 에서 잡음).
        with pytest.raises(ValueError, match="댓글 내용이 비어"):
            await service.create_comment(
                user_id="USER_v", post_id="FDP_x", content=content,
            )
        comment_repo_mock.save.assert_not_called()


# ──────────────────── list ────────────────────

@pytest.mark.unit
class TestListComments:
    async def test_next_cursor_when_full_page(
        self, service, comment_repo_mock, monkeypatch,
    ):
        monkeypatch.setattr(
            "app.domain.feed.service.feed_post_comment.PAGE_SIZE", 2,
        )
        comment_repo_mock.find_by_post.return_value = [
            make_feed_post_comment_mock(comment_id="FDC_0"),
            make_feed_post_comment_mock(comment_id="FDC_1"),
        ]
        result = await service.list_comments(viewer_id="USER_v", post_id="FDP_x")
        assert result.next_cursor == "FDC_1"


    async def test_next_cursor_none_when_partial_page(
        self, service, comment_repo_mock, monkeypatch,
    ):
        monkeypatch.setattr(
            "app.domain.feed.service.feed_post_comment.PAGE_SIZE", 5,
        )
        comment_repo_mock.find_by_post.return_value = [
            make_feed_post_comment_mock(comment_id=f"FDC_{i}") for i in range(3)
        ]
        result = await service.list_comments(viewer_id="USER_v", post_id="FDP_x")
        assert result.next_cursor is None


    async def test_cursor_passes_through_to_repo(
        self, service, comment_repo_mock,
    ):
        comment_repo_mock.find_by_post.return_value = []
        await service.list_comments(
            viewer_id="USER_v", post_id="FDP_x", cursor="FDC_seed",
        )
        assert comment_repo_mock.find_by_post.await_args.kwargs["cursor"] == "FDC_seed"


    async def test_maps_author_profile_per_comment(self, service, comment_repo_mock):
        """find_by_post 의 단일 JOIN 결과가 작성자 프로필까지 정확 매핑 + 결손 fallback."""
        comment_repo_mock.find_by_post.return_value = [
            make_feed_post_comment_mock(
                comment_id="FDC_a", user_id="USER_a",
                user_name="Alice", profile_image_url="https://x/a.jpg",
            ),
            make_feed_post_comment_mock(
                comment_id="FDC_b", user_id="USER_b",
                detail_present=False,  # 회원가입 미완료 fallback 케이스
            ),
        ]
        result = await service.list_comments(viewer_id="USER_v", post_id="FDP_x")
        assert result.comments[0].user_name == "Alice"
        assert result.comments[0].profile_image_url == "https://x/a.jpg"
        assert result.comments[1].user_name == ""
        assert result.comments[1].profile_image_url is None


# ──────────────────── delete ────────────────────

@pytest.mark.unit
class TestDeleteComment:
    async def test_author_can_delete_own_comment(
        self, service, comment_repo_mock,
    ):
        comment = make_feed_post_comment_mock(comment_id="FDC_x", post_id="FDP_x", user_id="USER_author")
        comment_repo_mock.find_by_id.return_value = comment

        await service.delete_comment(
            user_id="USER_author", post_id="FDP_x", comment_id="FDC_x",
        )
        comment_repo_mock.delete.assert_awaited_once_with(comment)


    async def test_non_author_cannot_delete(
        self, service, comment_repo_mock,
    ):
        comment = make_feed_post_comment_mock(user_id="USER_author")
        comment_repo_mock.find_by_id.return_value = comment

        with pytest.raises(PermissionError):
            await service.delete_comment(
                user_id="USER_intruder", post_id="FDP_x", comment_id="FDC_x",
            )
        comment_repo_mock.delete.assert_not_called()


    async def test_post_owner_cannot_delete_others_comment(
        self, service, comment_repo_mock,
    ):
        """게시물 owner 도 댓글 작성자 외엔 삭제 불가 — MVP 정책 (작성자만)."""
        comment = make_feed_post_comment_mock(post_id="FDP_x", user_id="USER_author")
        comment_repo_mock.find_by_id.return_value = comment

        with pytest.raises(PermissionError):
            await service.delete_comment(
                user_id="USER_owner_of_post", post_id="FDP_x", comment_id="FDC_x",
            )


    async def test_missing_comment_raises_not_found(
        self, service, comment_repo_mock,
    ):
        comment_repo_mock.find_by_id.return_value = None
        with pytest.raises(FeedPostCommentNotFoundError):
            await service.delete_comment(
                user_id="USER_v", post_id="FDP_x", comment_id="FDC_missing",
            )


    async def test_post_id_mismatch_treated_as_not_found(
        self, service, comment_repo_mock,
    ):
        """다른 post 의 comment_id 가 path 에 들어오면 not-found 로 일원화 (정보 누출 회피)."""
        comment = make_feed_post_comment_mock(post_id="FDP_other", user_id="USER_v")
        comment_repo_mock.find_by_id.return_value = comment
        with pytest.raises(FeedPostCommentNotFoundError):
            await service.delete_comment(
                user_id="USER_v", post_id="FDP_x", comment_id="FDC_x",
            )
