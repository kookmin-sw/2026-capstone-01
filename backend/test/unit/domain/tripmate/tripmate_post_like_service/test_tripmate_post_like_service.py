"""TripmatePostLikeService — 좋아요 추가/취소/조회 + 인박스 fan-out 통합 단위 테스트.

검증 대상:
    - `get_liked_user_ids`: 게시글 존재 가드 + ID 목록 반환
    - `add_like`: 트랜잭션 분리 + 본인→본인 fan-out skip + actor snapshot + detail 결손 fallback
    - `remove_like`: 좋아요 취소는 인박스 변경 없음 (정책 — Q1: 좋아요 취소해도 인박스 보존)

fan-out 은 `inbox_service_mock` 으로 호출 인자 검증, 실 Mongo 비접근.
"""
from test.unit.domain.tripmate.tripmate_post_like_service.model_factory import (
    TripmatePostFactory,
    UserDetailInformFactory,
)
import pytest


# ──────────────────────────────────────────────────────────────────
# get_liked_user_ids
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetLikedUserIds:
    """Tests for TripmatePostLikeService.get_liked_user_ids."""

    async def test_returns_user_ids_when_post_exists(
        self, service, post_repo_mock, like_repo_mock,
    ):
        post = TripmatePostFactory.create(post_id="TMP_x")
        post_repo_mock.find_by_id.return_value = post
        like_repo_mock.find_user_ids_by_post.return_value = ["USER_a", "USER_b"]

        result = await service.get_liked_user_ids(post_id="TMP_x")

        assert result == ["USER_a", "USER_b"]
        like_repo_mock.find_user_ids_by_post.assert_awaited_once_with("TMP_x")


    async def test_raises_when_post_not_found(
        self, service, post_repo_mock, like_repo_mock,
    ):
        post_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.get_liked_user_ids(post_id="TMP_x")

        like_repo_mock.find_user_ids_by_post.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# add_like — 트랜잭션 + 알림 fan-out 통합
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAddLike:
    """Tests for TripmatePostLikeService.add_like.

    트랜잭션 분리(`_add_like_tx` → outer)와 본인→본인 가드 + actor snapshot 합성 + detail 결손
    fallback 을 모두 검증.
    """

    async def test_returns_updated_like_count(
        self, service, post_repo_mock, like_repo_mock,
    ):
        post = TripmatePostFactory.create(user_id="USER_owner")
        post_repo_mock.find_by_id.return_value = post
        like_repo_mock.count_by_post.return_value = 7

        result = await service.add_like(user_id="USER_actor", post_id=post.post_id)

        assert result == 7
        like_repo_mock.save.assert_awaited_once()


    async def test_external_like_calls_fanout_with_actor_snapshot(
        self, service, post_repo_mock, detail_repo_mock, inbox_service_mock,
    ):
        """외부 actor → detail fetch → fan-out 에 닉네임/프로필 전달."""
        post = TripmatePostFactory.create(
            post_id="TMP_x", user_id="USER_owner", title="제주 동행 구함",
        )
        post_repo_mock.find_by_id.return_value = post
        detail_repo_mock.find_by_user_id.return_value = UserDetailInformFactory.create(
            user_id="USER_actor",
            user_name="요한",
            profile_image_url="https://img/p.jpg",
        )

        await service.add_like(user_id="USER_actor", post_id="TMP_x")

        inbox_service_mock.notify_tripmate_like.assert_awaited_once_with(
            recipient_id="USER_owner",
            actor_id="USER_actor",
            actor_name="요한",
            actor_profile_image_url="https://img/p.jpg",
            post_id="TMP_x",
            post_preview="제주 동행 구함",  # post.title 이 preview
        )


    async def test_self_like_skips_fanout_but_inserts_rdb(
        self, service, post_repo_mock, like_repo_mock, inbox_service_mock,
    ):
        """본인이 본인 글에 좋아요 — RDB INSERT 는 진행, fan-out 만 skip."""
        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post

        await service.add_like(user_id="USER_a", post_id=post.post_id)

        like_repo_mock.save.assert_awaited_once()
        inbox_service_mock.notify_tripmate_like.assert_not_awaited()


    async def test_self_like_skips_detail_fetch(
        self, service, post_repo_mock, detail_repo_mock,
    ):
        """본인→본인 — detail repo 호출 자체 안 함 (불필요한 RDB round-trip 회피)."""
        post = TripmatePostFactory.create(user_id="USER_a")
        post_repo_mock.find_by_id.return_value = post

        await service.add_like(user_id="USER_a", post_id=post.post_id)

        detail_repo_mock.find_by_user_id.assert_not_awaited()


    async def test_external_like_falls_back_when_detail_missing(
        self, service, post_repo_mock, detail_repo_mock, inbox_service_mock,
    ):
        """detail 결손 (회원가입 미완료 등) — actor_name="" / profile_image_url=None fallback.

        fan-out 은 여전히 호출됨 (recipient 가 알림을 받지만 actor 표시가 빈 문자열).
        """
        post = TripmatePostFactory.create(post_id="TMP_x", user_id="USER_owner")
        post_repo_mock.find_by_id.return_value = post
        detail_repo_mock.find_by_user_id.return_value = None  # 결손

        await service.add_like(user_id="USER_actor", post_id="TMP_x")

        call = inbox_service_mock.notify_tripmate_like.await_args.kwargs
        assert call["actor_name"] == ""
        assert call["actor_profile_image_url"] is None


    async def test_raises_when_post_not_found(
        self, service, post_repo_mock, like_repo_mock, inbox_service_mock,
    ):
        post_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.add_like(user_id="USER_a", post_id="TMP_x")

        like_repo_mock.save.assert_not_awaited()
        inbox_service_mock.notify_tripmate_like.assert_not_awaited()


    async def test_raises_when_already_liked(
        self, service, post_repo_mock, like_repo_mock, inbox_service_mock,
    ):
        """중복 좋아요 — 400 매핑용 ValueError. RDB INSERT / fan-out 모두 skip."""
        post = TripmatePostFactory.create()
        post_repo_mock.find_by_id.return_value = post
        like_repo_mock.find_by_user_and_post.return_value = object()  # 이미 누름

        with pytest.raises(ValueError, match="이미 좋아요"):
            await service.add_like(user_id="USER_a", post_id=post.post_id)

        like_repo_mock.save.assert_not_awaited()
        inbox_service_mock.notify_tripmate_like.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# remove_like — 좋아요 취소는 알림 변경 없음
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveLike:
    """Tests for TripmatePostLikeService.remove_like."""

    async def test_removes_existing_like_and_returns_count(
        self, service, like_repo_mock,
    ):
        like_repo_mock.find_by_user_and_post.return_value = object()  # 누름
        like_repo_mock.count_by_post.return_value = 3

        result = await service.remove_like(user_id="USER_a", post_id="TMP_x")

        assert result == 3
        like_repo_mock.delete_by_user_and_post.assert_awaited_once_with("USER_a", "TMP_x")


    async def test_raises_when_not_liked(
        self, service, like_repo_mock,
    ):
        like_repo_mock.find_by_user_and_post.return_value = None

        with pytest.raises(ValueError, match="좋아요를 누르지 않은"):
            await service.remove_like(user_id="USER_a", post_id="TMP_x")

        like_repo_mock.delete_by_user_and_post.assert_not_awaited()


    async def test_does_not_call_fanout(
        self, service, like_repo_mock, inbox_service_mock,
    ):
        """좋아요 취소 정책 (Q1) — 알림 보존, 변경 없음."""
        like_repo_mock.find_by_user_and_post.return_value = object()

        await service.remove_like(user_id="USER_a", post_id="TMP_x")

        inbox_service_mock.notify_tripmate_like.assert_not_awaited()
