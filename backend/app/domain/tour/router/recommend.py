from fastapi import APIRouter, Depends, HTTPException
from dependency_injector.wiring import Provide, inject

from app.domain.tour.service.recommend import RecommendService
from app.domain.tour.service.exception import (
    TourRecommendCredentialExpiredError,
    TourRecommendQuotaExceededError,
    TourRecommendVendorError,
)
from app.domain.tour.schema.recommend import (
    TourRecommendRequest,
    TourRecommendResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/recommend", tags=["여행 추천"])
logger = get_logger("tour.recommend")


@router.post("", status_code=200)
@inject
async def recommend_tour(
    body: TourRecommendRequest,
    recommend_service: RecommendService = Depends(Provide[Container.recommend_service]),
) -> TourRecommendResponse:
    """사용자 맞춤 서울 여행 코스 추천 (v2)

    - 일자별 출발/도착 권역, 추가 장소(최대 1개, 강제 포함), 시간/예산/스타일을 받아 시간 기반 코스 생성
    - 음식 옵션(halal/vegetarian)은 식당 선정 시 강제 적용
    """
    try:
        return await recommend_service.recommend(body)
    except ValueError as e:
        # 추가 장소 미존재 등 입력 검증 실패
        raise HTTPException(status_code=400, detail=str(e))
    except TourRecommendCredentialExpiredError as e:
        logger.critical("Gemini 인증 만료 / 권한 거부: {}", e)
        raise HTTPException(status_code=503, detail="여행 추천 서비스가 일시 중단되었습니다.")
    except TourRecommendQuotaExceededError as e:
        logger.warning("Gemini 쿼터 소진: {}", e)
        raise HTTPException(status_code=429, detail="요청이 많아 처리하지 못했습니다. 잠시 후 다시 시도해주세요.")
    except TourRecommendVendorError as e:
        logger.error("Gemini 벤더 오류: {}", e)
        raise HTTPException(status_code=502, detail="여행 추천에 실패했습니다.")
