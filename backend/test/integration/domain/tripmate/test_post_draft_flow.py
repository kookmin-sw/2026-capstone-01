"""TripmatePostDraftService — Mongo 임시저장 e2e 통합 테스트.

`save_draft` 가 beanie `replace_one(upsert=True)` 패턴으로 동작하는지, 같은 user_id 의
unique 인덱스가 실 mongo 에 적용되어 idempotent 갱신 흐름이 보장되는지 검증.

검증 매트릭스:

    | 시나리오                       | Mongo 효과                          |
    |---|---|
    | 첫 save_draft                  | INSERT (unique index 부여)           |
    | 두 번째 save_draft (같은 user) | UPDATE (덮어쓰기 — 누적 X)            |
    | get_draft 정상                 | 단건 반환                            |
    | get_draft 미존재               | None                                 |
    | delete_draft                   | row 사라짐                           |
"""
import pytest
from datetime import date

from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft


pytestmark = pytest.mark.integration


# ──────────────────── save_draft (upsert) ────────────────────

class TestSaveDraft:
    async def test_first_save_inserts_new_row(
        self, tripmate_post_draft_service,
    ):
        await tripmate_post_draft_service.save_draft(
            user_id="USER_a",
            title="여행",
            content="content",
            image_urls=["https://img/1"],
        )

        coll = TripmatePostDraft.get_motor_collection()
        doc = await coll.find_one({"user_id": "USER_a"})
        assert doc is not None
        assert doc["title"] == "여행"
        assert doc["image_urls"] == ["https://img/1"]


    async def test_second_save_overwrites_same_user(
        self, tripmate_post_draft_service,
    ):
        """같은 user_id 두 번 save → INSERT 가 아니라 UPDATE (덮어쓰기). unique index 가
        실 mongo 에 적용되어야 보장됨."""
        await tripmate_post_draft_service.save_draft(
            user_id="USER_a", title="첫번째", content="first",
        )
        await tripmate_post_draft_service.save_draft(
            user_id="USER_a", title="수정됨", content="second",
        )

        coll = TripmatePostDraft.get_motor_collection()
        # 단 1건만 — unique 인덱스 보장
        assert await coll.count_documents({"user_id": "USER_a"}) == 1
        doc = await coll.find_one({"user_id": "USER_a"})
        assert doc["title"] == "수정됨"
        assert doc["content"] == "second"


    async def test_image_urls_none_normalized_to_empty_list(
        self, tripmate_post_draft_service,
    ):
        await tripmate_post_draft_service.save_draft(
            user_id="USER_a", title="t", image_urls=None,
        )

        coll = TripmatePostDraft.get_motor_collection()
        doc = await coll.find_one({"user_id": "USER_a"})
        assert doc["image_urls"] == []


# ──────────────────── get_draft ────────────────────

class TestGetDraft:
    async def test_returns_draft_when_exists(
        self, tripmate_post_draft_service,
    ):
        await tripmate_post_draft_service.save_draft(
            user_id="USER_a",
            title="여행",
            preferred_age_min=20,
            travel_start_date=date(2026, 6, 1),
        )

        result = await tripmate_post_draft_service.get_draft(user_id="USER_a")

        assert result is not None
        assert result.title == "여행"
        assert result.preferred_age_min == 20
        assert result.travel_start_date == date(2026, 6, 1)


    async def test_returns_none_when_no_draft(
        self, tripmate_post_draft_service,
    ):
        result = await tripmate_post_draft_service.get_draft(user_id="USER_ghost")

        assert result is None


# ──────────────────── delete_draft ────────────────────

class TestDeleteDraft:
    async def test_deletes_existing(self, tripmate_post_draft_service):
        await tripmate_post_draft_service.save_draft(user_id="USER_a", title="t")

        await tripmate_post_draft_service.delete_draft(user_id="USER_a")

        coll = TripmatePostDraft.get_motor_collection()
        assert await coll.count_documents({"user_id": "USER_a"}) == 0


    async def test_idempotent_when_no_draft(self, tripmate_post_draft_service):
        """draft 없는 상태에서 delete → 에러 없이 정상 종료."""
        await tripmate_post_draft_service.delete_draft(user_id="USER_ghost")
