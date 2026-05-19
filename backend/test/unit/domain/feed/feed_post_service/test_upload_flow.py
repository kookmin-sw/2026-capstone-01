"""upload_post 흐름 회귀 테스트 — 정규화 통합 + 실패 시 cleanup.

happy path 전체 (실 Pillow + 실 S3 + 실 INSERT) 는 통합 테스트 영역. 본 파일은:
    - thumbnail 결과를 stub 으로 주입해 service 흐름만 검증
    - 빈/공백 caption 이 INSERT 까지 None 으로 흘러가는지 (정규화 통합)
    - S3 upload 실패 시 `delete_by_prefix` 가 호출되는지 (cleanup 보장)
    - INSERT 실패 시에도 cleanup 호출되는지 (S3 → DB 순서의 cleanup 단일 진입점)

`@transactional` 가 실제 commit 까지 호출하므로 mock_session 의 close/commit 도 정상 동작.
"""
import pytest

from app.domain.feed.dto.image import ProcessedFeedImage, ProcessedVariant
from app.domain.feed.model.feed_post import FeedVisibility


def _stub_processed() -> ProcessedFeedImage:
    """Pillow 처리 결과 stub — bytes 는 식별 가능한 sentinel 만 담음."""
    return ProcessedFeedImage(
        original=ProcessedVariant(b"orig-bytes", "image/jpeg", "jpg"),
        small=ProcessedVariant(b"small-bytes", "image/jpeg", "jpg"),
        medium=ProcessedVariant(b"medium-bytes", "image/jpeg", "jpg"),
    )


@pytest.fixture
def stub_thumbnail(monkeypatch):
    """thumbnail.process_feed_image 를 stub 으로 치환 — Pillow 디코딩 회피."""
    monkeypatch.setattr(
        "app.domain.feed.service.feed_post.process_feed_image",
        lambda _bytes: _stub_processed(),
    )


@pytest.mark.unit
class TestUploadCaptionNormalization:
    async def test_empty_caption_normalized_to_none_in_insert(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        """POST 진입점도 PATCH 와 동일 정규화 — 빈 문자열 → None 으로 INSERT."""
        storage_mock.upload_to_key.return_value = "https://x/url"

        result = await service.upload_post(
            user_id="USER_a",
            file_bytes=b"x",
            visibility=FeedVisibility.PUBLIC,
            caption="",
        )
        assert result.caption is None
        # repo.save 에 넘어간 FeedPost 의 caption 도 None 이어야 함
        saved_post = repo_mock.save.await_args.args[0]
        assert saved_post.caption is None

    async def test_whitespace_caption_normalized(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        storage_mock.upload_to_key.return_value = "https://x/url"
        result = await service.upload_post(
            user_id="USER_a", file_bytes=b"x",
            visibility=FeedVisibility.PUBLIC, caption="   \n  ",
        )
        assert result.caption is None

    async def test_non_blank_caption_passes_through(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        storage_mock.upload_to_key.return_value = "https://x/url"
        result = await service.upload_post(
            user_id="USER_a", file_bytes=b"x",
            visibility=FeedVisibility.PUBLIC, caption="안녕",
        )
        assert result.caption == "안녕"

    async def test_new_post_has_zero_counts(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        """신규 업로드 직후엔 좋아요/댓글 항상 0 — service 가 reload 없이 0 으로 합성."""
        storage_mock.upload_to_key.return_value = "https://x/url"
        result = await service.upload_post(
            user_id="USER_a", file_bytes=b"x",
            visibility=FeedVisibility.PUBLIC, caption="hi",
        )
        assert result.like_count == 0
        assert result.comment_count == 0

    async def test_new_post_is_liked_false(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        """신규 업로드 직후엔 본인이 자기 글에 아직 좋아요 안 눌렀으므로 항상 False —
        service 가 reload 없이 False 로 합성 (인스타 동치).
        """
        storage_mock.upload_to_key.return_value = "https://x/url"
        result = await service.upload_post(
            user_id="USER_a", file_bytes=b"x",
            visibility=FeedVisibility.PUBLIC, caption="hi",
        )
        assert result.is_liked is False


@pytest.mark.unit
class TestUploadCleanupOnFailure:
    async def test_s3_upload_failure_triggers_prefix_cleanup(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        """S3 가 부분/전부 실패해도 외부 try 가 prefix 통째 삭제로 정리."""
        storage_mock.upload_to_key.side_effect = RuntimeError("S3 down")

        with pytest.raises(RuntimeError, match="S3 down"):
            await service.upload_post(
                user_id="USER_a", file_bytes=b"x",
                visibility=FeedVisibility.PUBLIC, caption="hi",
            )
        # cleanup 이 정확히 한 번, prefix `{user_id}/feed/{post_id}` 형태로 호출
        storage_mock.delete_by_prefix.assert_awaited_once()
        called_prefix = storage_mock.delete_by_prefix.await_args.args[0]
        assert called_prefix.startswith("USER_a/feed/FDP_")
        # INSERT 는 호출되지 않아야 함 (S3 실패가 먼저)
        repo_mock.save.assert_not_called()

    async def test_insert_failure_triggers_cleanup(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        """S3 성공 + INSERT 실패 시에도 cleanup 단일 진입점 동작."""
        storage_mock.upload_to_key.return_value = "https://x/url"
        repo_mock.save.side_effect = RuntimeError("DB down")

        with pytest.raises(RuntimeError, match="DB down"):
            await service.upload_post(
                user_id="USER_a", file_bytes=b"x",
                visibility=FeedVisibility.PUBLIC, caption="hi",
            )
        storage_mock.delete_by_prefix.assert_awaited_once()

    async def test_cleanup_failure_does_not_mask_original_error(
        self, service, repo_mock, storage_mock, stub_thumbnail,
    ):
        """cleanup 자체가 실패해도 원 예외는 그대로 propagate (best-effort + log)."""
        storage_mock.upload_to_key.side_effect = RuntimeError("S3 down")
        storage_mock.delete_by_prefix.side_effect = RuntimeError("cleanup also down")

        with pytest.raises(RuntimeError, match="S3 down"):
            await service.upload_post(
                user_id="USER_a", file_bytes=b"x",
                visibility=FeedVisibility.PUBLIC, caption="hi",
            )
