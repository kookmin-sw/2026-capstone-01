"""TripmatePostService — 게시글 CRUD 단위 테스트.

검증 대상 (메서드별 핵심 분기 위주):
    - `create_post`: INSERT + image attach + draft 정리 (best-effort) + detail snapshot
    - `get_post`: 단건 조회 + 미존재 가드
    - `get_posts` / `search_posts`: 페이지네이션 + next_cursor 합성
    - `update_post`: 권한 + 이미지 차집합 cleanup (best-effort)
    - `delete_post`: 권한 + 이미지 cleanup (best-effort) + 알림 cascade 안 함
    - `toggle_display`: 권한 + 토글
"""
from test.unit.domain.tripmate.tripmate_post_service.model_factory import (
    TripmatePostFactory,
    make_post_image,
)
import pytest
from datetime import date

from app.domain.tripmate.repository.tripmate_post import PAGE_SIZE
from app.domain.tripmate.model.tripmate_post import CompanionType, PreferredGender


# ──────────────────────────────────────────────────────────────────
# create_post
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCreatePost:
    """Tests for TripmatePostService.create_post."""

    async def test_saves_post_and_returns_dto(
        self, service, post_repo_mock, image_repo_mock, detail_repo_mock,
    ):
        """기본 INSERT — post / image_repo 호출 + DTO 반환."""
        from types import SimpleNamespace
        detail_repo_mock.find_by_user_id.return_value = SimpleNamespace(
            profile_image_url="https://img/p.jpg",
        )

        result = await service.create_post(
            user_id="USER_a",
            title="제주 동행",
            content="6/1 ~ 6/5",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender=PreferredGender.ANY,
            region="제주",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type=CompanionType.FRIEND,
            image_urls=None,
        )

        post_repo_mock.save.assert_awaited_once()
        image_repo_mock.save_all.assert_not_awaited()  # 이미지 없음
        assert result.title == "제주 동행"
        assert result.image_urls == []
        assert result.profile_image_url == "https://img/p.jpg"


    async def test_attaches_images_when_provided(
        self, service, image_repo_mock,
    ):
        """이미지 URL 리스트 → 순서 보존하여 image_repo.save_all 호출."""
        await service.create_post(
            user_id="USER_a",
            title="t",
            content="c",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender=PreferredGender.ANY,
            region="r",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type=CompanionType.FRIEND,
            image_urls=["https://img/1", "https://img/2"],
        )

        image_repo_mock.save_all.assert_awaited_once()
        saved = image_repo_mock.save_all.await_args.args[0]
        assert [img.image_order for img in saved] == [0, 1]
        assert [img.image_url for img in saved] == ["https://img/1", "https://img/2"]


    async def test_draft_delete_failure_is_swallowed(
        self, service, draft_service_mock,
    ):
        """draft 삭제 실패해도 게시글 생성은 성공 — best-effort."""
        draft_service_mock.delete_draft.side_effect = RuntimeError("draft missing")

        # raise 없이 정상 종료
        await service.create_post(
            user_id="USER_a",
            title="t",
            content="c",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender=PreferredGender.ANY,
            region="r",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type=CompanionType.FRIEND,
        )


    async def test_profile_image_url_none_when_detail_missing(
        self, service, detail_repo_mock,
    ):
        """detail 결손 → profile_image_url=None fallback."""
        detail_repo_mock.find_by_user_id.return_value = None

        result = await service.create_post(
            user_id="USER_a",
            title="t",
            content="c",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender=PreferredGender.ANY,
            region="r",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type=CompanionType.FRIEND,
        )

        assert result.profile_image_url is None


# ──────────────────────────────────────────────────────────────────
# get_post — 단건 조회
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetPost:
    """Tests for TripmatePostService.get_post."""

    async def test_returns_dto_when_post_exists(
        self, service, post_repo_mock,
    ):
        post = TripmatePostFactory.create(
            post_id="TMP_x", user_id="USER_owner", title="제주",
            like_count=5, is_liked=True,
            images=[make_post_image("https://img/1", 0), make_post_image("https://img/2", 1)],
        )
        post_repo_mock.find_by_id_with_detail.return_value = post

        result = await service.get_post(post_id="TMP_x", user_id="USER_viewer")

        assert result.post_id == "TMP_x"
        assert result.title == "제주"
        assert result.like_count == 5
        assert result.is_liked is True
        assert result.image_urls == ["https://img/1", "https://img/2"]


    async def test_orders_images_by_image_order(
        self, service, post_repo_mock,
    ):
        """image_order asc 정렬 — image_urls 순서 검증."""
        post = TripmatePostFactory.create(
            images=[
                make_post_image("https://img/3", 2),
                make_post_image("https://img/1", 0),
                make_post_image("https://img/2", 1),
            ],
        )
        post_repo_mock.find_by_id_with_detail.return_value = post

        result = await service.get_post(post_id=post.post_id)

        assert result.image_urls == ["https://img/1", "https://img/2", "https://img/3"]


    async def test_raises_when_not_found(self, service, post_repo_mock):
        post_repo_mock.find_by_id_with_detail.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.get_post(post_id="TMP_x")


# ──────────────────────────────────────────────────────────────────
# get_posts / search_posts — 페이지네이션
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetPosts:
    """Tests for TripmatePostService.get_posts (목록 페이지네이션)."""

    async def test_returns_empty_when_none(self, service, post_repo_mock):
        post_repo_mock.find_all_displayed.return_value = []

        result = await service.get_posts()

        assert result.posts == []
        assert result.next_cursor is None


    async def test_no_next_cursor_when_under_page_size(
        self, service, post_repo_mock,
    ):
        post_repo_mock.find_all_displayed.return_value = [
            TripmatePostFactory.create() for _ in range(PAGE_SIZE - 1)
        ]

        result = await service.get_posts()

        assert len(result.posts) == PAGE_SIZE - 1
        assert result.next_cursor is None


    async def test_next_cursor_is_last_post_id_when_exact_page_size(
        self, service, post_repo_mock,
    ):
        """딱 PAGE_SIZE 만큼 fetch → 마지막 post_id 가 next_cursor."""
        posts = [TripmatePostFactory.create(post_id=f"TMP_{i:03d}") for i in range(PAGE_SIZE)]
        post_repo_mock.find_all_displayed.return_value = posts

        result = await service.get_posts()

        assert result.next_cursor == posts[-1].post_id


@pytest.mark.unit
class TestSearchPosts:
    """Tests for TripmatePostService.search_posts."""

    async def test_passes_keyword_and_cursor_to_repo(
        self, service, post_repo_mock,
    ):
        post_repo_mock.search.return_value = []

        await service.search_posts(
            keyword="제주", cursor="TMP_xxx", user_id="USER_viewer",
        )

        post_repo_mock.search.assert_awaited_once_with(
            "제주", "TMP_xxx", user_id="USER_viewer",
        )


# ──────────────────────────────────────────────────────────────────
# update_post — 권한 + 이미지 차집합 cleanup
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUpdatePost:
    """Tests for TripmatePostService.update_post."""

    async def _do_update(self, service, post_id, user_id, image_urls=None):
        return await service.update_post(
            post_id=post_id,
            user_id=user_id,
            title="updated",
            content="updated content",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender=PreferredGender.ANY,
            region="제주",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type=CompanionType.FRIEND,
            image_urls=image_urls,
        )


    async def test_raises_when_not_found(self, service, post_repo_mock):
        post_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await self._do_update(service, "TMP_x", "USER_a")


    async def test_raises_when_not_author(self, service, post_repo_mock):
        post = TripmatePostFactory.create(user_id="USER_owner")
        post_repo_mock.find_by_id.return_value = post

        with pytest.raises(PermissionError, match="권한"):
            await self._do_update(service, post.post_id, "USER_other")


    async def test_cleans_only_removed_images(
        self, service, post_repo_mock, image_repo_mock,
        storage_mock, mongo_image_repo_mock,
    ):
        """차집합(old - new) 만 storage / mongo 정리 — 유지되는 이미지는 건드리지 않음."""
        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post
        post_repo_mock.find_by_id_with_detail.return_value = post  # 응답용 reload
        image_repo_mock.find_by_post_id.return_value = [
            make_post_image("https://img/old1"),
            make_post_image("https://img/keep"),
        ]

        await self._do_update(
            service, post.post_id, "USER_a",
            image_urls=["https://img/keep", "https://img/new"],
        )

        # 제거된 것만 cleanup (old1)
        storage_mock.delete_many.assert_awaited_once()
        removed = storage_mock.delete_many.await_args.args[0]
        assert removed == ["https://img/old1"]
        mongo_image_repo_mock.delete_by_urls.assert_awaited_once_with(["https://img/old1"])


    async def test_image_cleanup_failure_is_swallowed(
        self, service, post_repo_mock, image_repo_mock, storage_mock,
    ):
        """제거 이미지 cleanup 실패 → swallow + 로그, RDB 변경은 유지."""
        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post
        post_repo_mock.find_by_id_with_detail.return_value = post
        image_repo_mock.find_by_post_id.return_value = [make_post_image("https://img/old")]
        storage_mock.delete_many.side_effect = RuntimeError("s3 down")

        # raise 없이 정상 종료
        await self._do_update(service, post.post_id, "USER_a", image_urls=None)


# ──────────────────────────────────────────────────────────────────
# delete_post — 권한 + 이미지 cleanup
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestDeletePost:
    """Tests for TripmatePostService.delete_post.

    인박스 cascade — 게시글 삭제 시 해당 게시글의 알림을 soft hide (display=False).
    `_delete_post_tx` 커밋 후 `inbox_service.cascade_post_deleted` 호출을 검증한다.
    실패 swallow / TargetType 매칭 등의 best-effort 동작은 InboxService 단위 테스트가 담당.
    """

    async def test_raises_when_not_found(self, service, post_repo_mock):
        post_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.delete_post(post_id="TMP_x", user_id="USER_a")


    async def test_raises_when_not_author(self, service, post_repo_mock):
        post = TripmatePostFactory.create(user_id="USER_owner")
        post_repo_mock.find_by_id.return_value = post

        with pytest.raises(PermissionError, match="권한"):
            await service.delete_post(post_id=post.post_id, user_id="USER_other")


    async def test_deletes_post_and_cleans_images(
        self, service, post_repo_mock, image_repo_mock,
        storage_mock, mongo_image_repo_mock, inbox_service_mock,
    ):
        from app.domain.notification.model.inbox import TargetType

        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post
        image_repo_mock.find_by_post_id.return_value = [
            make_post_image("https://img/1"),
            make_post_image("https://img/2"),
        ]

        await service.delete_post(post_id=post.post_id, user_id="USER_a")

        post_repo_mock.delete.assert_awaited_once_with(post)
        storage_mock.delete_many.assert_awaited_once_with(
            ["https://img/1", "https://img/2"],
        )
        mongo_image_repo_mock.delete_by_urls.assert_awaited_once_with(
            ["https://img/1", "https://img/2"],
        )
        inbox_service_mock.cascade_post_deleted.assert_awaited_once_with(
            target_type=TargetType.TRIPMATE_POST,
            target_id=post.post_id,
        )


    async def test_no_cascade_when_unauthorized(
        self, service, post_repo_mock, inbox_service_mock,
    ):
        """권한 실패 → 트랜잭션 raise → outer 가 cascade 호출 안 함 (RDB 롤백 race 회피 contract)."""
        post = TripmatePostFactory.create(user_id="USER_owner")
        post_repo_mock.find_by_id.return_value = post

        with pytest.raises(PermissionError):
            await service.delete_post(post_id=post.post_id, user_id="USER_other")

        inbox_service_mock.cascade_post_deleted.assert_not_awaited()


    async def test_no_image_cleanup_when_no_images(
        self, service, post_repo_mock, image_repo_mock, storage_mock,
    ):
        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post
        image_repo_mock.find_by_post_id.return_value = []

        await service.delete_post(post_id=post.post_id, user_id="USER_a")

        storage_mock.delete_many.assert_not_awaited()


    async def test_image_cleanup_failure_is_swallowed(
        self, service, post_repo_mock, image_repo_mock, storage_mock,
    ):
        """이미지 정리 실패 → swallow. RDB 게시글 삭제는 이미 commit."""
        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post
        image_repo_mock.find_by_post_id.return_value = [make_post_image("https://img/1")]
        storage_mock.delete_many.side_effect = RuntimeError("s3 down")

        # raise 없이 정상 종료
        await service.delete_post(post_id=post.post_id, user_id="USER_a")
        post_repo_mock.delete.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────
# toggle_display
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestToggleDisplay:
    """Tests for TripmatePostService.toggle_display."""

    async def test_toggles_true_to_false(self, service, post_repo_mock):
        post = TripmatePostFactory.create(user_id="USER_a", is_displayed=True)
        post_repo_mock.find_by_id.return_value = post

        result = await service.toggle_display(post_id=post.post_id, user_id="USER_a")

        assert result is False
        assert post.is_displayed is False


    async def test_toggles_false_to_true(self, service, post_repo_mock):
        post = TripmatePostFactory.create(user_id="USER_a", is_displayed=False)
        post_repo_mock.find_by_id.return_value = post

        result = await service.toggle_display(post_id=post.post_id, user_id="USER_a")

        assert result is True
        assert post.is_displayed is True


    async def test_raises_when_not_found(self, service, post_repo_mock):
        post_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.toggle_display(post_id="TMP_x", user_id="USER_a")


    async def test_raises_when_not_author(self, service, post_repo_mock):
        post = TripmatePostFactory.create(user_id="USER_owner")
        post_repo_mock.find_by_id.return_value = post

        with pytest.raises(PermissionError, match="권한"):
            await service.toggle_display(post_id=post.post_id, user_id="USER_other")
