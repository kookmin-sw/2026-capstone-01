from fastapi import APIRouter

from app.domain.tripmate.router import tripmate_router
from app.domain.translation.router import translation_router
from app.domain.tour.router import tour_router
from app.domain.public.router import public_router
from app.domain.notification.router import notification_router
from app.domain.menu_ai.router import menu_ai_router
from app.domain.friend.router import friend_router
from app.domain.feed.router import feed_router
from app.domain.chat.router import chat_rest_router, chat_ws_router
from app.domain.auth.router import auth_router


api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(tripmate_router)
api_router.include_router(menu_ai_router)
api_router.include_router(translation_router)
api_router.include_router(tour_router)
api_router.include_router(friend_router)
api_router.include_router(chat_rest_router)
api_router.include_router(chat_ws_router)
api_router.include_router(public_router)
api_router.include_router(notification_router)
api_router.include_router(feed_router)