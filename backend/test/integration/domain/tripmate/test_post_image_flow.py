"""TripmateImageService — 이미지 업로드/삭제/고아 정리 e2e 통합 테스트.

Storage 만 mock — Mongo (TripmateImage / TripmatePostDraft) + RDB (TripmatePostImage) 는
실 인프라. 고아 이미지 정리의 합집합 (post 참조 ∪ draft 참조) 를 실 DB 로 검증.

검증 매트릭스:

    | 시나리오                              | 기대                                   |
    |---|---|
    | upload_image                         | Storage 호출 + Mongo metadata           |
    | delete_image 본인                    | Storage delete + Mongo row 삭제        |
    | delete_image 다른 유저               | PermissionError                         |
    | delete_image 미존재                  | ValueError                              |
    | cleanup 모두 참조됨                  | 0 반환, 외부 호출 X                     |
    | cleanup 일부 고아 (post + draft 외)  | Storage delete_many + Mongo bulk delete |
"""
from sqlalchemy import select
import pytest

from app.domain.tripmate.model.tripmate_post_image import TripmatePostImage
from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft
from app.domain.tripmate.model.tripmate_image import TripmateImage


pytestmark = pytest.mark.integration


# ──────────────────── upload_image ────────────────────

class TestUploadImage:
    async def test_uploads_to_storage_and_persists_metadata(
        self, tripmate_image_service, tripmate_image_storage_mock, seed_users,
    ):
        [user_id] = await seed_users(1)

        result = await tripmate_image_service.upload_image(
            user_id=user_id, file=b"img-bytes",
            file_name="test.jpg", content_type="image/jpeg",
        )

        # Storage 호출
        tripmate_image_storage_mock.upload_perm.assert_awaited_once()

        # Mongo metadata 적재
        coll = TripmateImage.get_motor_collection()
        doc = await coll.find_one({"image_id": result.image_id})
        assert doc is not None
        assert doc["user_id"] == user_id
        assert doc["image_url"] == result.image_url


# ──────────────────── delete_image ────────────────────

class TestDeleteImage:
    async def test_owner_can_delete_storage_and_metadata(
        self, tripmate_image_service, tripmate_image_storage_mock, seed_users,
    ):
        [user_id] = await seed_users(1)

        uploaded = await tripmate_image_service.upload_image(
            user_id=user_id, file=b"img", file_name="x.jpg", content_type="image/jpeg",
        )

        await tripmate_image_service.delete_image(
            user_id=user_id, image_id=uploaded.image_id,
        )

        # Storage delete 호출 (URL 인자)
        tripmate_image_storage_mock.delete.assert_awaited_once_with(uploaded.image_url)

        # Mongo metadata 사라짐
        coll = TripmateImage.get_motor_collection()
        assert await coll.count_documents({"image_id": uploaded.image_id}) == 0


    async def test_other_user_raises_permission_error(
        self, tripmate_image_service, seed_users,
    ):
        owner, other = await seed_users(2)

        uploaded = await tripmate_image_service.upload_image(
            user_id=owner, file=b"img", file_name="x.jpg", content_type="image/jpeg",
        )

        with pytest.raises(PermissionError):
            await tripmate_image_service.delete_image(
                user_id=other, image_id=uploaded.image_id,
            )


    async def test_missing_raises_value_error(
        self, tripmate_image_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        with pytest.raises(ValueError, match="존재하지 않는"):
            await tripmate_image_service.delete_image(
                user_id=user_id, image_id="IMG_ghost",
            )


# ──────────────────── cleanup_orphaned_images ────────────────────

class TestCleanupOrphanedImages:
    """고아 = (post 참조 ∪ draft 참조) 의 보집합. 실 RDB + 실 Mongo 합성 검증."""

    async def test_returns_zero_when_all_referenced(
        self, tripmate_image_service, tripmate_image_storage_mock,
        seed_users, seed_tripmate_post, session_factory,
    ):
        post_id, owner_id = await seed_tripmate_post()

        # 이미지 1: post 에서 참조 (RDB tripmate_post_image)
        post_referenced = await tripmate_image_service.upload_image(
            user_id=owner_id, file=b"a", file_name="a.jpg", content_type="image/jpeg",
        )
        async with session_factory() as session:
            session.add(TripmatePostImage(
                post_id=post_id, image_url=post_referenced.image_url, image_order=0,
            ))
            await session.commit()

        # 이미지 2: draft 에서 참조 (Mongo tripmate_post_draft)
        draft_referenced = await tripmate_image_service.upload_image(
            user_id=owner_id, file=b"b", file_name="b.jpg", content_type="image/jpeg",
        )
        await TripmatePostDraft(
            user_id=owner_id, image_urls=[draft_referenced.image_url],
        ).insert()

        deleted = await tripmate_image_service.cleanup_orphaned_images(user_id=owner_id)

        assert deleted == 0
        tripmate_image_storage_mock.delete_many.assert_not_awaited()


    async def test_deletes_only_orphans_from_union(
        self, tripmate_image_service, tripmate_image_storage_mock,
        seed_users, seed_tripmate_post, session_factory,
    ):
        post_id, owner_id = await seed_tripmate_post()

        # 4 이미지 시드 — post 참조 1, draft 참조 1, 고아 2
        post_ref = await tripmate_image_service.upload_image(
            user_id=owner_id, file=b"p", file_name="post.jpg", content_type="image/jpeg",
        )
        draft_ref = await tripmate_image_service.upload_image(
            user_id=owner_id, file=b"d", file_name="draft.jpg", content_type="image/jpeg",
        )
        orphan1 = await tripmate_image_service.upload_image(
            user_id=owner_id, file=b"o1", file_name="o1.jpg", content_type="image/jpeg",
        )
        orphan2 = await tripmate_image_service.upload_image(
            user_id=owner_id, file=b"o2", file_name="o2.jpg", content_type="image/jpeg",
        )

        # post 참조
        async with session_factory() as session:
            session.add(TripmatePostImage(
                post_id=post_id, image_url=post_ref.image_url, image_order=0,
            ))
            await session.commit()

        # draft 참조
        await TripmatePostDraft(
            user_id=owner_id, image_urls=[draft_ref.image_url],
        ).insert()

        deleted = await tripmate_image_service.cleanup_orphaned_images(user_id=owner_id)

        assert deleted == 2
        # Storage 에 고아 2건만
        deleted_urls = tripmate_image_storage_mock.delete_many.await_args.args[0]
        assert set(deleted_urls) == {orphan1.image_url, orphan2.image_url}

        # Mongo 에서 고아 2건 사라짐, 참조된 2건 보존
        coll = TripmateImage.get_motor_collection()
        remaining_ids = {
            doc["image_id"] async for doc in coll.find({"user_id": owner_id})
        }
        assert remaining_ids == {post_ref.image_id, draft_ref.image_id}


    async def test_no_images_returns_zero(
        self, tripmate_image_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        deleted = await tripmate_image_service.cleanup_orphaned_images(user_id=user_id)

        assert deleted == 0
