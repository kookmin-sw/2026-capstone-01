"""popup schema 검증 회귀 테스트.

검증:
    - 필수 필드 누락 → ValidationError
    - profile_image_url Optional
    - nested feed.items 가 FeedPostResponse 형태
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.feed.model.feed_post import FeedVisibility
from app.domain.feed.schema.feed_popup import FeedPopupResponse, PopupFeedSection
from app.domain.feed.schema.feed_post import FeedPostResponse


def _mk_feed_item(post_id="FDP_x"):
    now = datetime.now(timezone.utc)
    return FeedPostResponse(
        post_id=post_id, user_id="USER_owner",
        visibility=FeedVisibility.PUBLIC, caption=None,
        original_url="https://x/o.jpg",
        thumbnail_small_url="https://x/s.jpg",
        thumbnail_medium_url="https://x/m.jpg",
        like_count=0, comment_count=0, is_liked=False,
        created_at=now, updated_at=now,
    )


@pytest.mark.unit
class TestFeedPopupResponse:
    def _payload(self, **overrides):
        base = {
            "user_id": "USER_owner",
            "user_name": "조현상",
            "nationality": "korea",
            "travel_styles": [TravelStyle.ACTIVITY],
            "profile_image_url": "https://x/p.jpg",
            "feed": PopupFeedSection(items=[]),
        }
        base.update(overrides)
        return base

    def test_full_payload_validates(self):
        FeedPopupResponse(**self._payload())

    def test_profile_image_optional(self):
        FeedPopupResponse(**self._payload(profile_image_url=None))

    def test_empty_feed_section_valid(self):
        resp = FeedPopupResponse(**self._payload(feed=PopupFeedSection(items=[])))
        assert resp.feed.items == []

    def test_feed_section_with_items(self):
        items = [_mk_feed_item(post_id=f"FDP_{i}") for i in range(9)]
        resp = FeedPopupResponse(
            **self._payload(feed=PopupFeedSection(items=items))
        )
        assert len(resp.feed.items) == 9
        assert resp.feed.items[0].post_id == "FDP_0"

    @pytest.mark.parametrize(
        "missing",
        ["user_id", "user_name", "nationality", "travel_styles", "feed"],
    )
    def test_missing_required_raises(self, missing):
        payload = self._payload()
        del payload[missing]
        with pytest.raises(ValidationError):
            FeedPopupResponse(**payload)


@pytest.mark.unit
class TestPopupFeedSection:
    def test_items_required(self):
        with pytest.raises(ValidationError):
            PopupFeedSection()

    def test_empty_items_allowed(self):
        PopupFeedSection(items=[])
