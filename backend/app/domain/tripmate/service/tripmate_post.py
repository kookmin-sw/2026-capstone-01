from typing import Optional, List
from datetime import date

from app.domain.tripmate.service.tripmate_post_draft import TripmatePostDraftService
from app.domain.tripmate.repository.tripmate_post_image import TripmatePostImageRepository
from app.domain.tripmate.repository.tripmate_post import TripmatePostRepository, PAGE_SIZE
from app.domain.tripmate.repository.tripmate_image import TripmateImageRepository
from app.domain.tripmate.model.tripmate_post_image import TripmatePostImage
from app.domain.tripmate.model.tripmate_post import TripmatePost, PreferredGender, CompanionType
from app.domain.tripmate.dto.tripmate_post import TripmatePostCreateData, TripmatePostData, TripmatePostListData, PostAuthorData
from app.domain.notification.service.inbox import InboxService
from app.domain.notification.model.inbox import TargetType
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.domain.auth.model.user_detail_inform import Gender
from app.database.session import UnitOfWork, transactional
from app.core.object_storage import get_object_storage
from app.core.logger import get_logger


logger = get_logger("tripmate.post.service")


class TripmatePostService:
    def __init__(
        self,
        uow: UnitOfWork,
        draft_service: TripmatePostDraftService,
        inbox_service: InboxService,
    ):
        self.uow = uow
        self.draft_service = draft_service
        self.inbox_service = inbox_service
        self.storage = get_object_storage()
        self.mongo_image_repo = TripmateImageRepository()

    # ──────────────────── 게시글 생성 ────────────────────

    @transactional
    async def create_post(
        self,
        user_id: str,
        title: str,
        content: str,
        preferred_age_min: int,
        preferred_age_max: int,
        preferred_gender: PreferredGender,
        region: str,
        travel_start_date: date,
        travel_end_date: date,
        companion_type: CompanionType,
        image_urls: Optional[List[str]] = None,
    ) -> TripmatePostCreateData:
        """
        여행 메이트 모집 게시글 생성

        1. 게시글 저장
        2. 첨부 이미지가 있으면 일괄 저장
        3. DTO 변환 후 반환
        """
        post_repo = TripmatePostRepository(self._session)
        image_repo = TripmatePostImageRepository(self._session)
        detail_repo = UserDetailInformRepository(self._session)

        post = TripmatePost(
            user_id=user_id,
            title=title,
            content=content,
            preferred_age_min=preferred_age_min,
            preferred_age_max=preferred_age_max,
            preferred_gender=preferred_gender,
            region=region,
            travel_start_date=travel_start_date,
            travel_end_date=travel_end_date,
            companion_type=companion_type,
        )
        await post_repo.save(post)

        saved_urls = []
        if image_urls:
            images = [
                TripmatePostImage(post_id=post.post_id, image_url=url, image_order=idx)
                for idx, url in enumerate(image_urls)
            ]
            await image_repo.save_all(images)
            saved_urls = image_urls

        # 게시글 발행 성공 → 임시저장 삭제 (실패해도 게시글 생성은 유지)
        try:
            await self.draft_service.delete_draft(user_id)
        except Exception as e:
            logger.warning("임시저장 삭제 실패 (user_id={}): {}", user_id, e)

        detail = await detail_repo.find_by_user_id(user_id)
        return self._to_create_dto(
            post,
            image_urls=saved_urls,
            profile_image_url=detail.profile_image_url if detail else None,
        )


    # ──────────────────── 게시글 단건 조회 ────────────────────

    @transactional
    async def get_post(self, post_id: str, user_id: Optional[str] = None) -> TripmatePostData:
        """
        게시글 단건 조회 (이미지 + 좋아요 수 + is_liked 포함)
        """
        post_repo = TripmatePostRepository(self._session)

        post = await post_repo.find_by_id_with_detail(post_id, user_id=user_id)
        if post is None:
            raise ValueError("존재하지 않는 게시글입니다.")

        return self._to_dto(
            post,
            like_count=post.like_count,
            is_liked=post.is_liked,
            image_urls=[img.image_url for img in sorted(post.images, key=lambda i: i.image_order)],
        )


    # ──────────────────── 게시글 목록 조회 ────────────────────

    @transactional
    async def get_posts(self, cursor: Optional[str] = None, user_id: Optional[str] = None) -> TripmatePostListData:
        """
        게시글 목록 조회 (최신순 30개, 커서 페이지네이션)
        """
        post_repo = TripmatePostRepository(self._session)

        posts = await post_repo.find_all_displayed(cursor, user_id=user_id)
        return self._to_list_dto(posts)


    # ──────────────────── 게시글 검색 ────────────────────

    @transactional
    async def search_posts(self, keyword: str, cursor: Optional[str] = None, user_id: Optional[str] = None) -> TripmatePostListData:
        """
        제목, 내용, 작성자 닉네임으로 검색
        """
        post_repo = TripmatePostRepository(self._session)

        posts = await post_repo.search(keyword, cursor, user_id=user_id)
        return self._to_list_dto(posts)


    # ──────────────────── 게시글 수정 ────────────────────

    @transactional
    async def update_post(
        self,
        post_id: str,
        user_id: str,
        title: str,
        content: str,
        preferred_age_min: int,
        preferred_age_max: int,
        preferred_gender: PreferredGender,
        region: str,
        travel_start_date: date,
        travel_end_date: date,
        companion_type: CompanionType,
        image_urls: Optional[List[str]] = None,
    ) -> TripmatePostData:
        """
        게시글 수정

        1. 게시글 존재 및 작성자 검증
        2. 필드 업데이트
        3. 기존 이미지 삭제 후 새 이미지 저장
        """
        post_repo = TripmatePostRepository(self._session)
        image_repo = TripmatePostImageRepository(self._session)

        post = await post_repo.find_by_id(post_id)
        if post is None:
            raise ValueError("존재하지 않는 게시글입니다.")
        if post.user_id != user_id:
            raise PermissionError("게시글 수정 권한이 없습니다.")

        post.title = title
        post.content = content
        post.preferred_age_min = preferred_age_min
        post.preferred_age_max = preferred_age_max
        post.preferred_gender = preferred_gender
        post.region = region
        post.travel_start_date = travel_start_date
        post.travel_end_date = travel_end_date
        post.companion_type = companion_type
        await post_repo.update(post)

        # 기존 이미지와 새 이미지의 차집합 계산 → 제거된 이미지만 정리
        existing_images = await image_repo.find_by_post_id(post_id)
        old_urls = {img.image_url for img in existing_images}
        new_urls = set(image_urls) if image_urls else set()
        removed_urls = old_urls - new_urls

        await image_repo.delete_by_post_id(post_id)
        if image_urls:
            images = [
                TripmatePostImage(post_id=post_id, image_url=url, image_order=idx)
                for idx, url in enumerate(image_urls)
            ]
            await image_repo.save_all(images)

        # 제거된 이미지 → Object Storage + MongoDB 정리
        if removed_urls:
            try:
                await self.storage.delete_many(list(removed_urls))
                await self.mongo_image_repo.delete_by_urls(list(removed_urls))
            except Exception as e:
                logger.warning("수정 시 이미지 정리 실패 (post_id={}): {}", post_id, e)

        # 수정 완료 후 좋아요 수 + is_liked + 이미지 포함하여 반환
        updated = await post_repo.find_by_id_with_detail(post_id, user_id=user_id)
        return self._to_dto(
            updated,
            like_count=updated.like_count,
            is_liked=updated.is_liked,
            image_urls=[img.image_url for img in sorted(updated.images, key=lambda i: i.image_order)],
        )


    # ──────────────────── 게시글 삭제 ────────────────────

    async def delete_post(self, post_id: str, user_id: str) -> None:
        """게시글 삭제 — DB / 이미지 정리는 트랜잭션 안, 인박스 cascade 는 트랜잭션 밖.

        흐름:
            1. `_delete_post_tx` — 권한 검증 + DB row 삭제 (CASCADE 로 image·좋아요 자동 삭제)
               + Object Storage 파일 + MongoDB 메타데이터 정리.
            2. (트랜잭션 밖) `InboxService.cascade_post_deleted` — 해당 게시글의 좋아요
               알림을 일괄 soft hide. RDB 롤백된 삭제에 대해 알림이 먼저 숨겨지는 race 회피.
        """
        await self._delete_post_tx(post_id=post_id, user_id=user_id)

        # (트랜잭션 밖) 인박스 cascade — 해당 게시글의 TRIPMATE_LIKE 알림 일괄 soft hide.
        # service 내부에서 예외 swallow + 로그 — 호출측 try 불필요. 실패 시 stale 알림은
        # deep link 404 + TTL 30일로 자연 정리.
        await self.inbox_service.cascade_post_deleted(
            target_type=TargetType.TRIPMATE_POST,
            target_id=post_id,
        )


    @transactional
    async def _delete_post_tx(self, *, post_id: str, user_id: str) -> None:
        """게시글 삭제 트랜잭션 부분 — 권한 검증 + DB delete + 이미지 자원 정리."""
        post_repo = TripmatePostRepository(self._session)
        image_repo = TripmatePostImageRepository(self._session)

        post = await post_repo.find_by_id(post_id)
        if post is None:
            raise ValueError("존재하지 않는 게시글입니다.")
        if post.user_id != user_id:
            raise PermissionError("게시글 삭제 권한이 없습니다.")

        # 삭제 전 이미지 URL 수집
        post_images = await image_repo.find_by_post_id(post_id)
        image_urls = [img.image_url for img in post_images]

        # 게시글 삭제 (CASCADE)
        await post_repo.delete(post)

        # Object Storage + MongoDB 정리
        if image_urls:
            try:
                storage = get_object_storage()
                mongo_image_repo = TripmateImageRepository()
                await storage.delete_many(image_urls)
                await mongo_image_repo.delete_by_urls(image_urls)
            except Exception as e:
                logger.warning("삭제 시 이미지 정리 실패 (post_id={}): {}", post_id, e)


    # ──────────────────── 게시글 Display 토글 ────────────────────

    @transactional
    async def toggle_display(self, post_id: str, user_id: str) -> bool:
        """
        게시글 표시 여부 토글 (활성화 ↔ 비활성화)

        1. 게시글 존재 및 작성자 검증
        2. is_displayed 반전
        3. 변경된 is_displayed 값 반환
        """
        post_repo = TripmatePostRepository(self._session)

        post = await post_repo.find_by_id(post_id)
        if post is None:
            raise ValueError("존재하지 않는 게시글입니다.")
        if post.user_id != user_id:
            raise PermissionError("게시글 표시 상태 변경 권한이 없습니다.")

        post.is_displayed = not post.is_displayed
        await post_repo.update(post)

        return post.is_displayed


    # ──────────────────── 내부 변환 유틸 ────────────────────

    @staticmethod
    def _to_author_dto(post: TripmatePost) -> PostAuthorData:
        detail = post.user.detail if post.user else None
        if detail is None:
            return PostAuthorData(user_name="anonymous", age=0, gender=Gender.MALE, nationality="")
        return PostAuthorData(
            user_name=detail.user_name,
            age=detail.age,
            gender=detail.gender,
            nationality=detail.nationality,
        )


    @staticmethod
    def _to_create_dto(
        post: TripmatePost,
        image_urls: List[str],
        profile_image_url: Optional[str] = None,
    ) -> TripmatePostCreateData:
        return TripmatePostCreateData(
            post_id=post.post_id,
            user_id=post.user_id,
            title=post.title,
            content=post.content,
            preferred_age_min=post.preferred_age_min,
            preferred_age_max=post.preferred_age_max,
            preferred_gender=post.preferred_gender,
            region=post.region,
            travel_start_date=post.travel_start_date,
            travel_end_date=post.travel_end_date,
            companion_type=post.companion_type,
            is_displayed=post.is_displayed,
            created_at=post.created_at,
            updated_at=post.updated_at,
            image_urls=image_urls,
            profile_image_url=profile_image_url,
        )


    @staticmethod
    def _to_dto(post: TripmatePost, like_count: int, is_liked: bool, image_urls: List[str]) -> TripmatePostData:
        detail = post.user.detail if post.user else None
        return TripmatePostData(
            post_id=post.post_id,
            user_id=post.user_id,
            author=TripmatePostService._to_author_dto(post),
            title=post.title,
            content=post.content,
            preferred_age_min=post.preferred_age_min,
            preferred_age_max=post.preferred_age_max,
            preferred_gender=post.preferred_gender,
            region=post.region,
            travel_start_date=post.travel_start_date,
            travel_end_date=post.travel_end_date,
            companion_type=post.companion_type,
            is_displayed=post.is_displayed,
            created_at=post.created_at,
            updated_at=post.updated_at,
            like_count=like_count,
            is_liked=is_liked,
            image_urls=image_urls,
            profile_image_url=detail.profile_image_url if detail else None,
        )


    def _to_list_dto(self, posts: list[TripmatePost]) -> TripmatePostListData:
        post_dtos = [
            self._to_dto(
                post,
                like_count=post.like_count,
                is_liked=post.is_liked,
                image_urls=[img.image_url for img in sorted(post.images, key=lambda i: i.image_order)],
            )
            for post in posts
        ]
        next_cursor = posts[-1].post_id if len(posts) == PAGE_SIZE else None
        return TripmatePostListData(posts=post_dtos, next_cursor=next_cursor)
