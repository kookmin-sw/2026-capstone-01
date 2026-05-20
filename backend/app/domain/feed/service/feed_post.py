"""피드 게시물 서비스 — 본인 피드 CRUD + 타 유저 피드 조회.

업로드 (S3 → 트랜잭션 두 단계):
1. Pillow 처리 (트랜잭션 밖) — 잘못된 이미지 fast-fail.
2. S3 병렬 업로드 3건 (트랜잭션 밖) — DB 커넥션 미점유.
3. PG INSERT (트랜잭션).
4. 어느 단계든 실패 시 prefix cleanup 후 재던짐.

S3 를 트랜잭션 밖으로 빼는 이유 — 정합성 의존이 0 이라 안에 두면 wall time 만큼 커넥션이
idle hold 되어 풀 압박. 의미 손해 없이 점유 시간 30~50× 감소.

삭제 순서 — DB 먼저, S3 best-effort: S3 가 먼저 사라지면 broken URL 노출, DB 가 먼저
지워지면 orphan 만 invisible 하게 남음.
"""
from typing import Optional
import asyncio

from app.util.storage_prefix import feed_post_prefix
from app.util.id_generator import generate_feed_post_id
from app.domain.notification.service.inbox import InboxService
from app.domain.notification.model.inbox import TargetType
from app.domain.feed.service.thumbnail import process_feed_image
from app.domain.feed.service.exception import FeedNotFoundError
from app.domain.feed.service.access import resolve_viewer_visibilities
from app.domain.feed.repository.feed_post import FeedPostRepository, PAGE_SIZE
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility
from app.domain.feed.dto.feed_post import (
    FeedPostData,
    FeedPostListData,
    FeedPostWithCounts,
)
from app.database.session import UnitOfWork, transactional
from app.core.object_storage import get_object_storage
from app.core.logger import get_logger


logger = get_logger("feed.post.service")


def _normalize_caption(caption: Optional[str]) -> Optional[str]:
    """빈 문자열 / 공백만 → None. 비-빈 캡션의 양끝 공백은 보존 (의도된 입력일 수 있음).

    POST(업로드) / PATCH(수정) 모두 동일 규칙 — DB 의 "캡션 없음" 표현을 null 단일로 통일.
    """
    if caption is None or not caption.strip():
        return None
    return caption


class FeedPostService:
    def __init__(self, uow: UnitOfWork, inbox_service: InboxService):
        self.uow = uow
        self.inbox_service = inbox_service
        self.storage = get_object_storage()


    async def upload_post(
        self,
        user_id: str,
        file_bytes: bytes,
        visibility: FeedVisibility,
        caption: Optional[str] = None,
    ) -> FeedPostData:
        """피드 업로드. Pillow → S3 병렬 → PG INSERT. 어떤 단계든 실패 시 prefix cleanup."""
        # ValueError 면 라우터에서 400 — S3/DB 자원 미접근.
        processed = await asyncio.to_thread(process_feed_image, file_bytes)

        # post_id / prefix 는 트랜잭션 밖에서 발급 — 어떤 실패 경로에서도 cleanup 호출 가능.
        post_id = generate_feed_post_id()
        prefix = feed_post_prefix(user_id, post_id)

        caption = _normalize_caption(caption)

        # S3 + INSERT — 외부 try 가 cleanup 단일 진입점. `_insert_post` 의 commit 은
        # `__aexit__` 에서 일어나므로 commit 실패도 여기서 catch.
        try:
            original_url, small_url, medium_url = await asyncio.gather(
                self.storage.upload_to_key(
                    processed.original.data,
                    prefix=prefix,
                    filename=f"original.{processed.original.file_ext}",
                    content_type=processed.original.content_type,
                ),
                self.storage.upload_to_key(
                    processed.small.data,
                    prefix=prefix,
                    filename=f"small.{processed.small.file_ext}",
                    content_type=processed.small.content_type,
                ),
                self.storage.upload_to_key(
                    processed.medium.data,
                    prefix=prefix,
                    filename=f"medium.{processed.medium.file_ext}",
                    content_type=processed.medium.content_type,
                ),
            )

            post = await self._insert_post(
                user_id=user_id,
                post_id=post_id,
                visibility=visibility,
                caption=caption,
                original_url=original_url,
                small_url=small_url,
                medium_url=medium_url,
            )
        except Exception:
            await self._safe_cleanup(prefix)
            raise

        # 신규 업로드 → 카운트 0 명백. reload 없이 row 합성 (round-trip 절약).
        return self._to_dto(
            FeedPostWithCounts(post=post, like_count=0, comment_count=0, is_liked=False)
        )


    @transactional
    async def _insert_post(
        self,
        *,
        user_id: str,
        post_id: str,
        visibility: FeedVisibility,
        caption: Optional[str],
        original_url: str,
        small_url: str,
        medium_url: str,
    ) -> FeedPost:
        """INSERT 만 수행. 커넥션 점유 ~5~20ms 로 한정."""
        repo = FeedPostRepository(self._session)
        post = FeedPost(
            post_id=post_id,
            user_id=user_id,
            visibility=visibility,
            caption=caption,
            original_url=original_url,
            thumbnail_small_url=small_url,
            thumbnail_medium_url=medium_url,
        )
        saved = await repo.save(post)
        logger.info("피드 게시물 업로드 완료 (user_id={}, post_id={})", user_id, post_id)
        return saved


    @transactional
    async def get_my_feed(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> FeedPostListData:
        """본인 피드 — 모든 visibility."""
        repo = FeedPostRepository(self._session)
        rows = await repo.find_by_owner(
            owner_id=user_id,
            visibilities=list(FeedVisibility),
            cursor=cursor,
            viewer_id=user_id,
        )
        next_cursor = rows[-1].post.post_id if len(rows) == PAGE_SIZE else None
        return FeedPostListData(
            posts=[self._to_dto(r) for r in rows],
            next_cursor=next_cursor,
        )


    @transactional
    async def get_my_post(self, user_id: str, post_id: str) -> FeedPostData:
        """본인 게시물 단건 — 권한 검증 포함."""
        row = await self._load_owned_post(user_id, post_id)
        return self._to_dto(row)


    @transactional
    async def get_user_feed(
        self,
        viewer_id: str,
        owner_id: str,
        cursor: Optional[str] = None,
    ) -> FeedPostListData:
        """다른 유저 피드 — 친구/차단/visibility 합성.

        viewer == owner 면 본인 피드와 동일 결과 — 프론트가 단일 엔드포인트로 분기 없이 호출 가능.
        차단 → FeedBlockedError (403). 타 유저 케이스의 응답은 PRIVATE 제외된 visibility 만 노출.
        """
        visibilities = await resolve_viewer_visibilities(
            self._session, viewer_id=viewer_id, owner_id=owner_id,
        )
        repo = FeedPostRepository(self._session)
        rows = await repo.find_by_owner(
            owner_id=owner_id,
            visibilities=visibilities,
            cursor=cursor,
            viewer_id=viewer_id,
        )
        next_cursor = rows[-1].post.post_id if len(rows) == PAGE_SIZE else None
        return FeedPostListData(
            posts=[self._to_dto(r) for r in rows],
            next_cursor=next_cursor,
        )


    @transactional
    async def update_visibility(
        self,
        user_id: str,
        post_id: str,
        visibility: FeedVisibility,
    ) -> FeedPostData:
        """공개 범위 변경 — 본인 전용. 카운트는 영향 없으므로 row 그대로 응답에 재사용."""
        row = await self._load_owned_post(user_id, post_id)
        row.post.visibility = visibility
        repo = FeedPostRepository(self._session)
        await repo.update(row.post)
        return self._to_dto(row)


    @transactional
    async def update_caption(
        self,
        user_id: str,
        post_id: str,
        caption: Optional[str],
    ) -> FeedPostData:
        """캡션 변경 — 본인 전용. null/빈/공백만이면 캡션 삭제."""
        row = await self._load_owned_post(user_id, post_id)
        row.post.caption = _normalize_caption(caption)
        repo = FeedPostRepository(self._session)
        await repo.update(row.post)
        return self._to_dto(row)


    async def delete_post(self, user_id: str, post_id: str) -> None:
        """본인 게시물 삭제. 순서: DB → S3 best-effort → 인박스 cascade.

        FK CASCADE 가 like/comment 자동 정리.
        인박스 cascade 는 RDB 커밋 후 호출 — 롤백된 삭제에 대해 알림이 먼저 숨겨지는 race 회피.
        """
        prefix = await self._delete_post_row(user_id, post_id)

        try:
            await self.storage.delete_by_prefix(prefix)
        except Exception as e:
            logger.warning(
                "S3 prefix 삭제 실패 — orphan 객체 잔존 (prefix={}): {}",
                prefix, e,
            )

        # 해당 게시글의 LIKE/COMMENT 알림 일괄 soft hide. 내부에서 예외 swallow.
        await self.inbox_service.cascade_post_deleted(
            target_type=TargetType.FEED_POST,
            target_id=post_id,
        )


    @transactional
    async def _delete_post_row(self, user_id: str, post_id: str) -> str:
        """삭제 트랜잭션 — 권한 검증 + PG row 삭제. 정리할 prefix 반환."""
        row = await self._load_owned_post(user_id, post_id)
        post = row.post
        prefix = feed_post_prefix(post.user_id, post.post_id)

        repo = FeedPostRepository(self._session)
        await repo.delete(post)
        logger.info("피드 게시물 삭제 완료 (user_id={}, post_id={})", user_id, post_id)
        return prefix


    async def _load_owned_post(self, user_id: str, post_id: str) -> FeedPostWithCounts:
        """post 로드 + 본인 소유 검증. 미존재 → 404, 본인 아님 → 403.

        반환은 카운트 포함 row — 호출처 (`get_my_post` / `update_*` / `_delete_post_row`) 가
        `_to_dto` 그대로 사용하거나 `.post` 로 unwrap.
        """
        repo = FeedPostRepository(self._session)
        row = await repo.find_by_post_id(post_id, viewer_id=user_id)
        if row is None:
            raise FeedNotFoundError("존재하지 않는 게시물입니다.")
        if row.post.user_id != user_id:
            raise PermissionError("게시물에 대한 권한이 없습니다.")
        return row


    async def _safe_cleanup(self, prefix: str) -> None:
        """업로드 실패 경로 best-effort cleanup — 실패해도 원 예외 가리지 않도록 swallow."""
        try:
            await self.storage.delete_by_prefix(prefix)
        except Exception as e:
            logger.warning(
                "업로드 실패 경로 cleanup 실패 — orphan 객체 잔존 (prefix={}): {}",
                prefix, e,
            )


    @staticmethod
    def _to_dto(row: FeedPostWithCounts) -> FeedPostData:
        """`FeedPostWithCounts` (post + counts) → DTO. 단일 변환 진입점."""
        post = row.post
        return FeedPostData(
            post_id=post.post_id,
            user_id=post.user_id,
            visibility=post.visibility,
            caption=post.caption,
            original_url=post.original_url,
            thumbnail_small_url=post.thumbnail_small_url,
            thumbnail_medium_url=post.thumbnail_medium_url,
            like_count=row.like_count,
            comment_count=row.comment_count,
            is_liked=row.is_liked,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )
