from fastapi import APIRouter

from app.domain.translation.router import translation


translation_router = APIRouter(prefix="/translation")
translation_router.include_router(translation.router)
