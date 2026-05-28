from typing import List

from app.domain.auth.repository.user_travel_style import UserTravelStyleRepository
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.model.user_travel_style import UserTravelStyle, TravelStyle
from app.domain.auth.model.user_detail_inform import UserDetailInform, Gender
from app.database.session import UnitOfWork, transactional


class RegisterService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def register_detail(
        self,
        user_id: str,
        email: str,
        user_name: str,
        phone_number: str,
        age: int,
        gender: Gender,
        nationality: str,
        travel_styles: List[TravelStyle],
    ) -> None:
        """
        2차 회원가입 - 유저 상세 정보 + 여행 스타일 저장

        1. user_detail_inform 이미 존재하는지 확인 (중복 방지)
        2. user_detail_inform 저장
        3. user_travel_style 저장 (복수)
        """
        user_repo = UserRepository(self._session)
        detail_repo = UserDetailInformRepository(self._session)
        style_repo = UserTravelStyleRepository(self._session)

        user = await user_repo.find_by_id(user_id)
        if user is None:
            raise ValueError("존재하지 않는 유저입니다.")

        existing = await detail_repo.find_by_user_id(user_id)
        if existing is not None:
            raise ValueError("이미 2차 회원가입이 완료된 유저입니다.")

        detail = UserDetailInform(
            user_id=user_id,
            email=email,
            user_name=user_name,
            phone_number=phone_number,
            age=age,
            gender=gender,
            nationality=nationality,
        )
        await detail_repo.save(detail)

        styles = [
            UserTravelStyle(user_id=user_id, style=style)
            for style in travel_styles
        ]
        await style_repo.save_all(styles)
