"""`is_liked` correlated subquery e2e 통합 — 실 PostgreSQL 회귀 가드.

검증 매트릭스:

    | 시나리오                              | 기대                       |
    |---|---|
    | viewer 가 좋아요 누른 게시물           | is_liked=True              |
    | viewer 가 안 누른 게시물               | is_liked=False             |
    | 다른 사람만 좋아요, viewer 는 안 누름   | is_liked=False (privacy)   |
    | viewer_id=None                        | is_liked=False (단락 평가) |
    | 본인 글에 본인이 좋아요 (인스타 동치)  | is_liked=True              |
    | find_by_owner 목록 — 게시물별 독립 평가 | True/False 혼재 정확       |

이 영역은 SQL 단의 EXISTS subquery 동작에 의존하므로 PG 가 실제로 평가해야 의미가 있음.
unit 의 mock 검증은 service↔repo 경계만 — SQL 정합성은 본 파일이 책임.
"""
import pytest

from app.domain.feed.repository.feed_post import FeedPostRepository
from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.feed.model.feed_post import FeedVisibility


pytestmark = pytest.mark.integration


# ──────────────────── helpers ────────────────────

async def _insert_like(session_factory, user_id: str, post_id: str) -> None:
    async with session_factory() as session:
        session.add(FeedPostLike(user_id=user_id, post_id=post_id))
        await session.commit()


# ──────────────────── find_by_post_id ────────────────────

class TestFindByPostIdIsLiked:
    """단건 조회 경로 — get_my_post / update_* / load_viewable_post 가 공통 사용."""

    async def test_viewer_liked_returns_true(
        self, session_factory, seed_feed_post,
    ):
        """viewer 가 좋아요 누른 게시물 — EXISTS=True 가 정확히 노출."""
        post_id, owner_id = await seed_feed_post()
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            row = await repo.find_by_post_id(post_id, viewer_id=owner_id)

        assert row is not None
        assert row.is_liked is True


    async def test_viewer_not_liked_returns_false(
        self, session_factory, seed_feed_post,
    ):
        """viewer 가 안 누른 게시물 — EXISTS=False."""
        post_id, owner_id = await seed_feed_post()

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            row = await repo.find_by_post_id(post_id, viewer_id=owner_id)

        assert row is not None
        assert row.is_liked is False


    async def test_other_users_like_does_not_leak_to_viewer(
        self, session_factory, seed_feed_post, seed_users,
    ):
        """다른 사람이 좋아요 누른 게시물 — viewer 의 is_liked 는 여전히 False.
        privacy 회귀 가드 — 누가 누른 좋아요든 viewer 자신의 좋아요 여부만 반영해야 함.
        """
        post_id, owner_id = await seed_feed_post()
        # owner 가 누름. viewer 는 안 누름.
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)
        # viewer 는 별개 user
        [viewer_id, *_] = await seed_users(1)

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            row = await repo.find_by_post_id(post_id, viewer_id=viewer_id)

        assert row is not None
        assert row.is_liked is False, "다른 사람의 좋아요가 viewer 응답에 누출됨"


    async def test_viewer_id_none_returns_false(
        self, session_factory, seed_feed_post,
    ):
        """viewer_id=None — SQL 측 literal(false) 로 단락 평가. 실 PG 컴파일 검증."""
        post_id, owner_id = await seed_feed_post()
        # owner 가 좋아요를 눌러도, viewer_id=None 이라면 is_liked 는 False 여야 함.
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            row = await repo.find_by_post_id(post_id, viewer_id=None)

        assert row is not None
        assert row.is_liked is False


    async def test_self_like_on_own_post_is_visible(
        self, session_factory, seed_feed_post,
    ):
        """본인이 본인 글에 좋아요 (인스타 동치) — get_my_post 응답에 is_liked=True."""
        post_id, owner_id = await seed_feed_post()
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            row = await repo.find_by_post_id(post_id, viewer_id=owner_id)

        assert row.is_liked is True


# ──────────────────── find_by_owner ────────────────────

class TestFindByOwnerIsLiked:
    """목록 조회 경로 — get_my_feed / get_user_feed / popup 이 공통 사용.

    핵심 가드: 한 viewer 가 게시물 N개 중 일부만 좋아요 눌렀을 때, EXISTS subquery 가
    row 별로 독립 평가되어 정확히 True/False 가 혼재해야 함 (전체 카운트 vs row 카운트
    혼동 회귀 가드).
    """

    async def test_mixed_liked_unliked_in_same_query(
        self, session_factory, seed_users,
    ):
        """같은 owner 의 게시물 2개 중 1개만 좋아요 — 결과에 True/False 혼재."""
        from app.domain.feed.model.feed_post import FeedPost

        [owner_id, *_] = await seed_users(1)
        async with session_factory() as session:
            post_liked = FeedPost(
                user_id=owner_id, visibility=FeedVisibility.PUBLIC, caption="liked",
                original_url="https://x/o1.jpg",
                thumbnail_small_url="https://x/s1.jpg",
                thumbnail_medium_url="https://x/m1.jpg",
            )
            post_unliked = FeedPost(
                user_id=owner_id, visibility=FeedVisibility.PUBLIC, caption="unliked",
                original_url="https://x/o2.jpg",
                thumbnail_small_url="https://x/s2.jpg",
                thumbnail_medium_url="https://x/m2.jpg",
            )
            session.add_all([post_liked, post_unliked])
            await session.commit()
            liked_id = post_liked.post_id
            unliked_id = post_unliked.post_id

        await _insert_like(session_factory, user_id=owner_id, post_id=liked_id)

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            rows = await repo.find_by_owner(
                owner_id=owner_id,
                visibilities=[FeedVisibility.PUBLIC],
                viewer_id=owner_id,
            )

        by_post_id = {r.post.post_id: r.is_liked for r in rows}
        assert by_post_id[liked_id] is True
        assert by_post_id[unliked_id] is False


    async def test_viewer_id_none_yields_all_false(
        self, session_factory, seed_users,
    ):
        """viewer_id=None — 좋아요가 있어도 모든 row 의 is_liked 가 False (단락)."""
        from app.domain.feed.model.feed_post import FeedPost

        [owner_id, *_] = await seed_users(1)
        async with session_factory() as session:
            post = FeedPost(
                user_id=owner_id, visibility=FeedVisibility.PUBLIC, caption=None,
                original_url="https://x/o.jpg",
                thumbnail_small_url="https://x/s.jpg",
                thumbnail_medium_url="https://x/m.jpg",
            )
            session.add(post)
            await session.commit()
            post_id = post.post_id
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)

        async with session_factory() as session:
            repo = FeedPostRepository(session)
            rows = await repo.find_by_owner(
                owner_id=owner_id,
                visibilities=[FeedVisibility.PUBLIC],
                viewer_id=None,
            )

        assert all(r.is_liked is False for r in rows)


# ──────────────────── service 레이어 e2e ────────────────────

class TestServiceLayerIsLiked:
    """service → repo → SQL → response DTO 전체 경로의 is_liked 합성."""

    async def test_get_my_post_reflects_self_like(
        self, feed_post_service, seed_feed_post, session_factory,
    ):
        """get_my_post 응답의 is_liked 가 본인 좋아요 상태 정확히 반영 (인스타 동치)."""
        post_id, owner_id = await seed_feed_post()
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)

        result = await feed_post_service.get_my_post(
            user_id=owner_id, post_id=post_id,
        )
        assert result.is_liked is True


    async def test_get_my_post_no_like_is_false(
        self, feed_post_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()

        result = await feed_post_service.get_my_post(
            user_id=owner_id, post_id=post_id,
        )
        assert result.is_liked is False


    async def test_get_user_feed_shows_viewer_like_on_other_owner_post(
        self, feed_post_service, seed_feed_post, session_factory, seed_users,
    ):
        """다른 유저 글에 viewer 가 좋아요 — get_user_feed 응답 is_liked=True."""
        post_id, owner_id = await seed_feed_post()  # PUBLIC default
        [viewer_id, *_] = await seed_users(1)
        await _insert_like(session_factory, user_id=viewer_id, post_id=post_id)

        result = await feed_post_service.get_user_feed(
            viewer_id=viewer_id, owner_id=owner_id,
        )
        assert len(result.posts) == 1
        assert result.posts[0].post_id == post_id
        assert result.posts[0].is_liked is True


    async def test_get_user_feed_other_viewers_like_does_not_leak(
        self, feed_post_service, seed_feed_post, session_factory, seed_users,
    ):
        """owner 자기 글에 좋아요 누른 상태에서 비친구 viewer 가 조회 →
        viewer 응답의 is_liked 는 False (privacy)."""
        post_id, owner_id = await seed_feed_post()  # PUBLIC
        await _insert_like(session_factory, user_id=owner_id, post_id=post_id)
        [viewer_id, *_] = await seed_users(1)

        result = await feed_post_service.get_user_feed(
            viewer_id=viewer_id, owner_id=owner_id,
        )
        assert result.posts[0].is_liked is False
