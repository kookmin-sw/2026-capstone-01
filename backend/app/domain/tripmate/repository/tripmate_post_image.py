from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.domain.tripmate.model.tripmate_post_image import TripmatePostImage
from app.domain.tripmate.model.tripmate_post import TripmatePost


class TripmatePostImageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, image: TripmatePostImage) -> TripmatePostImage:
        """이미지 단건 저장"""
        self.session.add(image)
        await self.session.flush()
        return image


    async def save_all(self, images: list[TripmatePostImage]) -> list[TripmatePostImage]:
        """이미지 여러 건 일괄 저장"""
        self.session.add_all(images)
        await self.session.flush()
        return images


    # ──────────────────── Read ────────────────────

    async def find_by_post_id(self, post_id: str) -> list[TripmatePostImage]:
        """게시글의 이미지 목록 조회 (정렬 순서대로)"""
        stmt = (
            select(TripmatePostImage)
            .where(TripmatePostImage.post_id == post_id)
            .order_by(TripmatePostImage.image_order.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def find_urls_by_user_id(self, user_id: str) -> list[str]:
        """유저의 게시글에 연결된 이미지 URL 전체 조회"""
        stmt = (
            select(TripmatePostImage.image_url)
            .join(TripmatePost, TripmatePostImage.post_id == TripmatePost.post_id)
            .where(TripmatePost.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    # ──────────────────── Delete ────────────────────

    async def delete(self, image: TripmatePostImage) -> None:
        """이미지 단건 삭제"""
        await self.session.delete(image)


    async def delete_by_post_id(self, post_id: str) -> None:
        """게시글의 이미지 전체 삭제 (게시글 수정 시 교체용)"""
        stmt = delete(TripmatePostImage).where(TripmatePostImage.post_id == post_id)
        await self.session.execute(stmt)
