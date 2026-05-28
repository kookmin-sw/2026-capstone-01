"""좋아요/댓글 schema 검증 회귀.

검증:
    - LikeResponse / LikedUsersResponse: 필수 필드 누락 → ValidationError
    - CreateCommentRequest: min_length=1 / max_length / 빈 문자열 거절
    - CommentResponse: 필수 필드 누락 → ValidationError
"""
import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from app.domain.feed.schema.feed_post_like import (
    LikedUserItem,
    LikedUsersResponse,
    LikeResponse,
)
from app.domain.feed.schema.feed_post_comment import (
    CommentListResponse,
    CommentResponse,
    CreateCommentRequest,
)
from app.domain.feed.model.feed_post_comment import COMMENT_MAX_LENGTH


@pytest.mark.unit
class TestLikeResponse:
    def test_validates(self):
        LikeResponse(post_id="FDP_x", like_count=42)


    def test_negative_count_allowed_by_pydantic_but_not_by_db(self):
        # Pydantic 자체는 음수 허용. like_count >= 0 은 service / DB 책임.
        # 본 테스트는 schema 가 음수에 ValidationError 던지지 않음을 확인 (문서화 목적).
        LikeResponse(post_id="FDP_x", like_count=-1)


    @pytest.mark.parametrize("missing", ["post_id", "like_count"])
    def test_missing_required_raises(self, missing):
        payload = {"post_id": "FDP_x", "like_count": 1}
        del payload[missing]
        with pytest.raises(ValidationError):
            LikeResponse(**payload)


@pytest.mark.unit
class TestLikedUserItem:
    def test_full_payload(self):
        LikedUserItem(
            user_id="USER_a", user_name="Alice",
            profile_image_url="https://x/a.jpg",
        )


    def test_profile_image_optional(self):
        LikedUserItem(user_id="USER_a", user_name="Alice")


    def test_user_name_required(self):
        with pytest.raises(ValidationError):
            LikedUserItem(user_id="USER_a")


@pytest.mark.unit
class TestLikedUsersResponse:
    def test_validates_empty_list(self):
        LikedUsersResponse(post_id="FDP_x", users=[])


    def test_validates_non_empty(self):
        LikedUsersResponse(
            post_id="FDP_x",
            users=[
                LikedUserItem(user_id="USER_a", user_name="Alice"),
                LikedUserItem(
                    user_id="USER_b", user_name="Bob",
                    profile_image_url="https://x/b.jpg",
                ),
            ],
        )


    def test_rejects_old_user_ids_field(self):
        """기존 `user_ids: list[str]` 형식 차단 — breaking change 명시."""
        with pytest.raises(ValidationError):
            LikedUsersResponse(post_id="FDP_x", user_ids=["USER_a"])


@pytest.mark.unit
class TestCreateCommentRequest:
    def test_accepts_one_char(self):
        CreateCommentRequest(content="a")


    def test_accepts_at_max_length(self):
        CreateCommentRequest(content="a" * COMMENT_MAX_LENGTH)


    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError):
            CreateCommentRequest(content="")


    def test_rejects_over_max_length(self):
        with pytest.raises(ValidationError):
            CreateCommentRequest(content="a" * (COMMENT_MAX_LENGTH + 1))


    def test_rejects_missing(self):
        with pytest.raises(ValidationError):
            CreateCommentRequest()


@pytest.mark.unit
class TestCommentResponse:
    def _payload(self, **overrides):
        base = {
            "comment_id": "FDC_x",
            "post_id": "FDP_x",
            "user_id": "USER_a",
            "user_name": "Alice",
            "profile_image_url": "https://x/a.jpg",
            "content": "hi",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        base.update(overrides)
        return base


    def test_full_payload_validates(self):
        CommentResponse(**self._payload())


    def test_profile_image_optional(self):
        CommentResponse(**self._payload(profile_image_url=None))


    def test_user_name_empty_string_allowed(self):
        """detail 결손 fallback — 빈 문자열도 통과."""
        CommentResponse(**self._payload(user_name=""))


    @pytest.mark.parametrize(
        "missing",
        ["comment_id", "post_id", "user_id", "user_name",
         "content", "created_at", "updated_at"],
    )
    def test_missing_required_raises(self, missing):
        payload = self._payload()
        del payload[missing]
        with pytest.raises(ValidationError):
            CommentResponse(**payload)


@pytest.mark.unit
class TestCommentListResponse:
    def test_empty_list_valid(self):
        CommentListResponse(comments=[], next_cursor=None)


    def test_with_items(self):
        CommentListResponse(
            comments=[
                CommentResponse(
                    comment_id="FDC_a", post_id="FDP_x", user_id="USER_a",
                    user_name="Alice", profile_image_url=None,
                    content="hi",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ),
            ],
            next_cursor="FDC_a",
        )
