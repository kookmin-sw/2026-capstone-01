from typing import Any, BinaryIO

from app.util.storage_prefix import profile_prefix
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.domain.auth.repository.user_travel_style import UserTravelStyleRepository
from app.domain.auth.model.user_travel_style import UserTravelStyle
from app.domain.auth.dto.profile import ProfileData, ProfileImageData, OtherUserProfileData
from app.domain.auth.service.exception import (
    ProfileNotRegisteredError,
    ProfileImageAlreadyExistsError,
    ProfileImageNotFoundError,
)
from app.database.session import UnitOfWork, transactional
from app.core.object_storage import get_object_storage
from app.core.logger import get_logger


logger = get_logger("auth.profile.service")


class ProfileService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.storage = get_object_storage()


    @transactional
    async def get_all_other_users(self, user_id: str) -> list[OtherUserProfileData]:
        """본인을 제외한 ACTIVE 유저 목록 조회.

        2차 회원가입 미완료(detail=None) 유저는 user_name 등 필수 필드가 없어 제외한다.
        """
        user_repo = UserRepository(self._session)
        users = await user_repo.find_active_others_with_profile(user_id)

        return [
            OtherUserProfileData(
                user_id=u.user_id,
                user_name=u.detail.user_name,
                nationality=u.detail.nationality,
                travel_styles=[s.style for s in u.travel_styles],
                profile_image_url=u.detail.profile_image_url,
            )
            for u in users
            if u.detail is not None
        ]


    @transactional
    async def get_my_profile(self, user_id: str) -> ProfileData:
        """유저 프로필 전체 정보 조회"""
        user_repo = UserRepository(self._session)

        user = await user_repo.find_by_id_with_profile(user_id)
        if user is None:
            raise ValueError("존재하지 않는 유저입니다.")
        if user.detail is None:
            raise ProfileNotRegisteredError("2차 회원가입이 완료되지 않은 유저입니다.")

        return ProfileData(
            user_id=user.user_id,
            auth_provider=user.auth_provider,
            status=user.status,
            email=user.detail.email,
            user_name=user.detail.user_name,
            phone_number=user.detail.phone_number,
            age=user.detail.age,
            gender=user.detail.gender,
            nationality=user.detail.nationality,
            travel_styles=[s.style for s in user.travel_styles],
            profile_image_url=user.detail.profile_image_url,
            notification_muted=user.notification_muted is True,
        )


    # ──────────────────── 프로필 수정 ────────────────────

    @transactional
    async def update_profile(self, user_id: str, updates: dict[str, Any]) -> ProfileData:
        """프로필 부분 수정.

        `updates` 는 `ProfileUpdateRequest.model_dump(exclude_none=True)` 결과로,
        클라가 실제로 보낸 non-null 필드만 포함한다.

        - detail scalar 필드(email, user_name, ...): 포함된 것만 in-place mutate.
        - travel_styles: 포함되어 있으면 기존 전체 삭제 후 새 set 으로 교체.
            ([] 입력 시 전체 삭제만 수행.)
        - 빈 dict (변경 없음) → DB write 스킵, 현재 프로필 그대로 반환.
        """
        user_repo = UserRepository(self._session)
        detail_repo = UserDetailInformRepository(self._session)
        style_repo = UserTravelStyleRepository(self._session)

        user = await user_repo.find_by_id_with_profile(user_id)
        if user is None:
            raise ValueError("존재하지 않는 유저입니다.")
        if user.detail is None:
            raise ProfileNotRegisteredError("2차 회원가입이 완료되지 않은 유저입니다.")

        detail = user.detail
        scalar_fields = ("email", "user_name", "phone_number", "age", "gender", "nationality")
        scalar_changed = False
        for field in scalar_fields:
            if field in updates:
                setattr(detail, field, updates[field])
                scalar_changed = True
        if scalar_changed:
            await detail_repo.update(detail)

        if "travel_styles" in updates:
            new_styles = updates["travel_styles"]
            await style_repo.delete_by_user_id(user_id)
            if new_styles:
                await style_repo.save_all(
                    [UserTravelStyle(user_id=user_id, style=s) for s in new_styles]
                )
            current_styles = list(new_styles)
        else:
            current_styles = [s.style for s in user.travel_styles]

        logger.info("프로필 수정 완료 (user_id={}, fields={})", user_id, list(updates.keys()))

        return ProfileData(
            user_id=user.user_id,
            auth_provider=user.auth_provider,
            status=user.status,
            email=detail.email,
            user_name=detail.user_name,
            phone_number=detail.phone_number,
            age=detail.age,
            gender=detail.gender,
            nationality=detail.nationality,
            travel_styles=current_styles,
            profile_image_url=detail.profile_image_url,
            notification_muted=user.notification_muted is True,
        )


    # ──────────────────── 프로필 이미지 추가 ────────────────────

    @transactional
    async def add_profile_image(
        self,
        user_id: str,
        file: BinaryIO,
        file_name: str,
        content_type: str,
    ) -> ProfileImageData:
        """
        프로필 이미지 추가 (유저당 1장 정책)

        1. detail 존재 검증
        2. 기존 이미지가 있으면 409 (수정은 PUT 사용)
        3. Object Storage 업로드
        4. DB 컬럼 갱신

        DB 갱신 실패 시 rollback 되며, 업로드된 S3 파일은 orphan 으로 남는다.
        탈퇴 시 prefix 단위로 정리되므로 영구 누적은 아니다.
        """
        detail_repo = UserDetailInformRepository(self._session)

        detail = await detail_repo.find_by_user_id(user_id)
        if detail is None:
            raise ProfileNotRegisteredError("2차 회원가입이 완료되지 않은 유저입니다.")
        if detail.profile_image_url is not None:
            raise ProfileImageAlreadyExistsError("이미 프로필 이미지가 존재합니다. 수정은 PUT 으로 요청해주세요.")

        new_url = await self.storage.upload_perm(
            file, file_name, content_type, prefix=profile_prefix(user_id),
        )

        detail.profile_image_url = new_url
        await detail_repo.update(detail)
        logger.info("프로필 이미지 추가 완료 (user_id={})", user_id)

        return ProfileImageData(profile_image_url=new_url)


    # ──────────────────── 프로필 이미지 수정 ────────────────────

    async def update_profile_image(
        self,
        user_id: str,
        file: BinaryIO,
        file_name: str,
        content_type: str,
    ) -> ProfileImageData:
        """
        프로필 이미지 수정 (기존 1장 → 새 1장)

        1. (트랜잭션) detail 검증 + S3 업로드 + DB 갱신 → 이전 URL 반환
        2. (트랜잭션 밖) 이전 S3 파일 삭제 (best-effort)

        S3 삭제를 트랜잭션 안에서 하면 commit 실패 시 broken link 위험 → 분리.
        """
        new_url, old_url = await self._replace_profile_image(
            user_id, file, file_name, content_type,
        )

        try:
            await self.storage.delete(old_url)
        except Exception as e:
            logger.warning("이전 프로필 이미지 삭제 실패 — orphan 파일 잔존 (user_id={}): {}", user_id, e)

        logger.info("프로필 이미지 수정 완료 (user_id={})", user_id)
        return ProfileImageData(profile_image_url=new_url)


    @transactional
    async def _replace_profile_image(
        self,
        user_id: str,
        file: BinaryIO,
        file_name: str,
        content_type: str,
    ) -> tuple[str, str]:
        """수정 흐름의 트랜잭션 부분 — (new_url, old_url) 반환."""
        detail_repo = UserDetailInformRepository(self._session)

        detail = await detail_repo.find_by_user_id(user_id)
        if detail is None:
            raise ProfileNotRegisteredError("2차 회원가입이 완료되지 않은 유저입니다.")
        if detail.profile_image_url is None:
            raise ProfileImageNotFoundError("수정할 프로필 이미지가 없습니다. 먼저 POST 로 추가해주세요.")

        old_url = detail.profile_image_url

        new_url = await self.storage.upload_perm(
            file, file_name, content_type, prefix=profile_prefix(user_id),
        )

        detail.profile_image_url = new_url
        await detail_repo.update(detail)

        return new_url, old_url


    # ──────────────────── 프로필 이미지 삭제 ────────────────────

    async def delete_profile_image(self, user_id: str) -> None:
        """
        프로필 이미지 삭제

        1. (트랜잭션) detail 검증 + DB 컬럼 NULL 처리 → 이전 URL 반환
        2. (트랜잭션 밖) S3 파일 삭제 (best-effort)
        """
        old_url = await self._null_profile_image(user_id)

        try:
            await self.storage.delete(old_url)
        except Exception as e:
            logger.warning("프로필 이미지 파일 삭제 실패 — orphan 파일 잔존 (user_id={}): {}", user_id, e)

        logger.info("프로필 이미지 삭제 완료 (user_id={})", user_id)


    @transactional
    async def _null_profile_image(self, user_id: str) -> str:
        """삭제 흐름의 트랜잭션 부분 — 이전 URL 반환."""
        detail_repo = UserDetailInformRepository(self._session)

        detail = await detail_repo.find_by_user_id(user_id)
        if detail is None:
            raise ProfileNotRegisteredError("2차 회원가입이 완료되지 않은 유저입니다.")
        if detail.profile_image_url is None:
            raise ProfileImageNotFoundError("삭제할 프로필 이미지가 없습니다.")

        old_url = detail.profile_image_url
        detail.profile_image_url = None
        await detail_repo.update(detail)

        return old_url
