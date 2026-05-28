"""TripmateImageService — 이미지 업로드/조회/삭제 + 고아 정리 단위 테스트.

검증 대상:
    - `upload_image`: Storage 업로드 → Mongo metadata save (URL 매핑)
    - `upload_images`: bulk — 각 file 별 upload_image 호출
    - `get_images`: repo thin wrapper
    - `delete_image`: 권한 + Storage delete + Mongo delete
    - `cleanup_orphaned_images`: post 참조 + draft 참조 합집합 → 고아만 정리. 5가지 분기:
        - 빈 all_images → 0
        - 모두 참조됨 → 0
        - draft 미존재 → draft set 빈
        - 일부 고아 → storage / mongo bulk delete
"""
from types import SimpleNamespace
from test.unit.domain.tripmate.tripmate_image_service.model_factory import (
    TripmateImageFactory,
)
import pytest


# ──────────────────────────────────────────────────────────────────
# upload_image
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUploadImage:
    """Tests for TripmateImageService.upload_image."""

    async def test_uploads_to_storage_and_saves_metadata(
        self, service, storage_mock, image_repo_mock,
    ):
        """Storage URL 을 받아 metadata row 의 image_url 에 매핑 후 저장."""
        storage_mock.upload_perm.return_value = "https://img/uploaded.jpg"

        result = await service.upload_image(
            user_id="USER_a",
            file=b"binary",
            file_name="test.jpg",
            content_type="image/jpeg",
        )

        storage_mock.upload_perm.assert_awaited_once()
        image_repo_mock.save.assert_awaited_once()
        saved = image_repo_mock.save.await_args.args[0]
        assert saved.user_id == "USER_a"
        assert saved.image_url == "https://img/uploaded.jpg"
        assert result.image_url == "https://img/uploaded.jpg"


# ──────────────────────────────────────────────────────────────────
# upload_images — bulk
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUploadImages:
    """Tests for TripmateImageService.upload_images."""

    async def test_uploads_each_file(self, service, storage_mock, image_repo_mock):
        """N 개 파일 → upload_perm N 회 + save N 회."""
        storage_mock.upload_perm.side_effect = [
            "https://img/1.jpg", "https://img/2.jpg", "https://img/3.jpg",
        ]

        results = await service.upload_images(
            user_id="USER_a",
            files=[
                (b"f1", "1.jpg", "image/jpeg"),
                (b"f2", "2.jpg", "image/jpeg"),
                (b"f3", "3.jpg", "image/jpeg"),
            ],
        )

        assert len(results) == 3
        assert storage_mock.upload_perm.await_count == 3
        assert image_repo_mock.save.await_count == 3


    async def test_empty_files_returns_empty_list(self, service, storage_mock):
        result = await service.upload_images(user_id="USER_a", files=[])

        assert result == []
        storage_mock.upload_perm.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# get_images
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetImages:
    """Tests for TripmateImageService.get_images."""

    async def test_returns_repo_result(self, service, image_repo_mock):
        images = [TripmateImageFactory.create(), TripmateImageFactory.create()]
        image_repo_mock.find_by_user_id.return_value = images

        result = await service.get_images(user_id="USER_a")

        assert result == images
        image_repo_mock.find_by_user_id.assert_awaited_once_with("USER_a")


# ──────────────────────────────────────────────────────────────────
# delete_image — 권한 + Storage + Mongo
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestDeleteImage:
    """Tests for TripmateImageService.delete_image."""

    async def test_raises_when_image_not_found(
        self, service, image_repo_mock, storage_mock,
    ):
        image_repo_mock.find_by_image_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는 이미지"):
            await service.delete_image(user_id="USER_a", image_id="IMG_x")

        storage_mock.delete.assert_not_awaited()
        image_repo_mock.delete_by_image_id.assert_not_awaited()


    async def test_raises_when_not_owner(
        self, service, image_repo_mock, storage_mock,
    ):
        image_repo_mock.find_by_image_id.return_value = TripmateImageFactory.create(
            user_id="USER_owner",
        )

        with pytest.raises(PermissionError, match="권한"):
            await service.delete_image(user_id="USER_other", image_id="IMG_x")

        storage_mock.delete.assert_not_awaited()
        image_repo_mock.delete_by_image_id.assert_not_awaited()


    async def test_deletes_storage_and_metadata_in_order(
        self, service, image_repo_mock, storage_mock,
    ):
        """Storage 먼저 → Mongo metadata. broken URL 노출 회피 패턴."""
        image = TripmateImageFactory.create(
            image_id="IMG_x", user_id="USER_a", image_url="https://img/x.jpg",
        )
        image_repo_mock.find_by_image_id.return_value = image

        await service.delete_image(user_id="USER_a", image_id="IMG_x")

        storage_mock.delete.assert_awaited_once_with("https://img/x.jpg")
        image_repo_mock.delete_by_image_id.assert_awaited_once_with("IMG_x")


# ──────────────────────────────────────────────────────────────────
# cleanup_orphaned_images — post / draft 참조 합집합으로 고아 식별
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCleanupOrphanedImages:
    """Tests for TripmateImageService.cleanup_orphaned_images."""

    async def test_returns_zero_when_no_images(
        self, service, image_repo_mock, storage_mock, post_image_repo_mock,
    ):
        """업로드 이미지 자체가 없음 → 정리 대상 없음, 외부 호출 skip."""
        image_repo_mock.find_by_user_id.return_value = []

        result = await service.cleanup_orphaned_images(user_id="USER_a")

        assert result == 0
        # post / draft 조회 자체 skip
        post_image_repo_mock.find_urls_by_user_id.assert_not_awaited()
        storage_mock.delete_many.assert_not_awaited()
        image_repo_mock.delete_by_image_ids.assert_not_awaited()


    async def test_returns_zero_when_all_referenced(
        self, service, image_repo_mock, storage_mock,
        post_image_repo_mock, draft_find_one_mock,
    ):
        """모든 이미지가 post 또는 draft 에서 참조 중 → 고아 0건."""
        image_repo_mock.find_by_user_id.return_value = [
            TripmateImageFactory.create(image_url="https://img/a.jpg"),
            TripmateImageFactory.create(image_url="https://img/b.jpg"),
        ]
        post_image_repo_mock.find_urls_by_user_id.return_value = ["https://img/a.jpg"]
        draft_find_one_mock.return_value = SimpleNamespace(
            image_urls=["https://img/b.jpg"],
        )

        result = await service.cleanup_orphaned_images(user_id="USER_a")

        assert result == 0
        storage_mock.delete_many.assert_not_awaited()
        image_repo_mock.delete_by_image_ids.assert_not_awaited()


    async def test_handles_no_draft(
        self, service, image_repo_mock, storage_mock,
        post_image_repo_mock, draft_find_one_mock,
    ):
        """draft 미존재 → draft 참조 set 은 빈. post 참조만 적용."""
        image_repo_mock.find_by_user_id.return_value = [
            TripmateImageFactory.create(image_id="IMG_a", image_url="https://img/a.jpg"),
            TripmateImageFactory.create(image_id="IMG_b", image_url="https://img/b.jpg"),
        ]
        post_image_repo_mock.find_urls_by_user_id.return_value = ["https://img/a.jpg"]
        draft_find_one_mock.return_value = None  # draft 없음

        result = await service.cleanup_orphaned_images(user_id="USER_a")

        # IMG_a 는 post 참조됨, IMG_b 는 어디에서도 참조 안 됨 → 고아
        assert result == 1
        storage_mock.delete_many.assert_awaited_once_with(["https://img/b.jpg"])
        image_repo_mock.delete_by_image_ids.assert_awaited_once_with(["IMG_b"])


    async def test_deletes_only_orphans_from_union(
        self, service, image_repo_mock, storage_mock,
        post_image_repo_mock, draft_find_one_mock,
    ):
        """고아 식별 = (post 참조 ∪ draft 참조) 의 보집합 — 둘 중 하나라도 참조되면 보존."""
        image_repo_mock.find_by_user_id.return_value = [
            TripmateImageFactory.create(image_id="IMG_post", image_url="https://img/post.jpg"),
            TripmateImageFactory.create(image_id="IMG_draft", image_url="https://img/draft.jpg"),
            TripmateImageFactory.create(image_id="IMG_both", image_url="https://img/both.jpg"),
            TripmateImageFactory.create(image_id="IMG_orphan1", image_url="https://img/o1.jpg"),
            TripmateImageFactory.create(image_id="IMG_orphan2", image_url="https://img/o2.jpg"),
        ]
        post_image_repo_mock.find_urls_by_user_id.return_value = [
            "https://img/post.jpg", "https://img/both.jpg",
        ]
        draft_find_one_mock.return_value = SimpleNamespace(
            image_urls=["https://img/draft.jpg", "https://img/both.jpg"],
        )

        result = await service.cleanup_orphaned_images(user_id="USER_a")

        assert result == 2
        # 고아 2건만 정리 — 참조 중인 건 보존
        deleted_urls = storage_mock.delete_many.await_args.args[0]
        assert set(deleted_urls) == {"https://img/o1.jpg", "https://img/o2.jpg"}
        deleted_ids = image_repo_mock.delete_by_image_ids.await_args.args[0]
        assert set(deleted_ids) == {"IMG_orphan1", "IMG_orphan2"}
