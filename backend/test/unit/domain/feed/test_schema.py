"""feed 도메인 schema (Pydantic) 검증 회귀 테스트.

API 계약을 변경하면 곧바로 테스트가 깨져 알아채도록:
    - UpdateCaptionRequest: max_length, Optional, 빈/null 허용
    - UpdateVisibilityRequest: enum 강제
    - FeedPostResponse: 필수 필드 누락 시 ValidationError
"""
import pytest
from pydantic import ValidationError

from app.domain.feed.schema.feed_post import (
    FeedPostResponse,
    UpdateCaptionRequest,
    UpdateVisibilityRequest,
)
from app.domain.feed.model.feed_post import CAPTION_MAX_LENGTH, FeedVisibility


@pytest.mark.unit
class TestUpdateCaptionRequest:
    def test_accepts_none(self):
        req = UpdateCaptionRequest(caption=None)
        assert req.caption is None


    def test_accepts_default_omitted(self):
        req = UpdateCaptionRequest()
        assert req.caption is None


    def test_accepts_at_max_length(self):
        req = UpdateCaptionRequest(caption="a" * CAPTION_MAX_LENGTH)
        assert len(req.caption) == CAPTION_MAX_LENGTH


    def test_rejects_over_max_length(self):
        with pytest.raises(ValidationError):
            UpdateCaptionRequest(caption="a" * (CAPTION_MAX_LENGTH + 1))


@pytest.mark.unit
class TestUpdateVisibilityRequest:
    @pytest.mark.parametrize("v", ["private", "friends", "public"])
    def test_accepts_each_enum_value_string(self, v):
        req = UpdateVisibilityRequest(visibility=v)
        assert req.visibility == FeedVisibility(v)


    def test_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            UpdateVisibilityRequest(visibility="everyone")


    def test_rejects_missing(self):
        with pytest.raises(ValidationError):
            UpdateVisibilityRequest()


@pytest.mark.unit
class TestFeedPostResponse:
    def _payload(self, **overrides):
        from datetime import datetime, timezone
        base = {
            "post_id": "FDP_x",
            "user_id": "USER_x",
            "visibility": FeedVisibility.PUBLIC,
            "caption": None,
            "original_url": "https://x/o.jpg",
            "thumbnail_small_url": "https://x/s.jpg",
            "thumbnail_medium_url": "https://x/m.jpg",
            "like_count": 0,
            "comment_count": 0,
            "is_liked": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        base.update(overrides)
        return base


    def test_full_payload_validates(self):
        FeedPostResponse(**self._payload())


    def test_counts_are_serialized(self):
        """카운트 필드가 응답에 정확히 노출되는지 — 새 필드 회귀 가드."""
        resp = FeedPostResponse(**self._payload(like_count=42, comment_count=7))
        assert resp.like_count == 42
        assert resp.comment_count == 7


    def test_is_liked_is_serialized(self):
        """viewer 좋아요 여부가 응답에 정확히 노출되는지 — 새 필드 회귀 가드."""
        resp = FeedPostResponse(**self._payload(is_liked=True))
        assert resp.is_liked is True


    @pytest.mark.parametrize(
        "missing_field",
        ["post_id", "user_id", "visibility",
         "original_url", "thumbnail_small_url", "thumbnail_medium_url",
         "like_count", "comment_count", "is_liked",
         "created_at", "updated_at"],
    )
    def test_missing_required_field_raises(self, missing_field):
        payload = self._payload()
        del payload[missing_field]
        with pytest.raises(ValidationError):
            FeedPostResponse(**payload)


    def test_caption_is_optional(self):
        payload = self._payload(caption=None)
        FeedPostResponse(**payload)
