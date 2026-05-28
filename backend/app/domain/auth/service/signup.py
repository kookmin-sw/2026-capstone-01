from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.model.user import User, UserStatus
from app.domain.auth.dto.signup import SignupStatus, SignupResult
from app.database.session import UnitOfWork, transactional


class SignupService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def check_and_register(self, auth_provider: str, auth_provider_id: str) -> SignupResult:
        """
        OAuth 콜백 후 회원가입 상태를 확인하고, 미가입 시 1차 가입을 수행한다.

        1. users 테이블에서 provider 정보로 조회
           - 없으면 → 신규 유저 생성 (1차 가입) → NEW
           - 있으면 → 2단계 확인 (단, INACTIVE 면 즉시 WITHDRAWAL_PENDING)
        2. user_detail_inform 테이블에서 user_id로 조회
           - 없으면 → IN_PROGRESS (2차 가입 필요)
           - 있으면 → COMPLETE

        탈퇴 유예(30일) 중인 유저(`status=INACTIVE`) 는 detail 존재 여부와 무관하게
        `WITHDRAWAL_PENDING` 을 반환한다.
        """
        user_repo = UserRepository(self._session)
        detail_repo = UserDetailInformRepository(self._session)

        user = await user_repo.find_by_provider(auth_provider, auth_provider_id)

        if user is None:
            user = User(
                auth_provider=auth_provider,
                auth_provider_id=auth_provider_id,
            )
            await user_repo.save(user)
            return SignupResult(user_id=user.user_id, status=SignupStatus.NEW)

        if user.status == UserStatus.INACTIVE:
            return SignupResult(user_id=user.user_id, status=SignupStatus.WITHDRAWAL_PENDING)

        detail = await detail_repo.find_by_user_id(user.user_id)

        if detail is None:
            return SignupResult(user_id=user.user_id, status=SignupStatus.IN_PROGRESS)

        return SignupResult(user_id=user.user_id, status=SignupStatus.COMPLETE)
