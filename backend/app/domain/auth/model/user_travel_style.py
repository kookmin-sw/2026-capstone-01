from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Enum, ForeignKey, Index
import enum

from app.util.id_generator import generate_travel_style_id
from app.database.session import Base


class TravelStyle(str, enum.Enum):
    ACTIVITY = "activity"
    FAMOUS_ATTRACTIONS = "famous_attractions"
    HEALING = "healing"
    CULTURE_HISTORY = "culture_history"
    SHOPPING = "shopping"
    FOOD_TOUR = "food_tour"
    PHOTO_AESTHETIC = "photo_aesthetic"
    FESTIVAL_EVENT = "festival_event"
    NATURE = "nature"
    TRADITIONAL = "traditional"
    TREKKING = "trekking"
    HIDDEN_GEMS = "hidden_gems"
    ART_EXHIBITION = "art_exhibition"
    THEME_PARK = "theme_park"

    FOOD_HALAL = "food_halal"
    FOOD_VEGETARIAN = "food_vegetarian"
    FOODIE = "foodie"
    CAFE_LOVER = "cafe_lover"

    DENSITY_RELAXED = "density_relaxed"
    DENSITY_PACKED = "density_packed"

    BUDGET_SAVING = "budget_saving"
    BUDGET_MODERATE = "budget_moderate"
    BUDGET_PREMIUM = "budget_premium"

    WALKING_LOW = "walking_low"
    WALKING_MEDIUM = "walking_medium"
    WALKING_HIGH = "walking_high"

    TRANSPORT_PUBLIC = "transport_public"
    TRANSPORT_CAR = "transport_car"
    TRANSPORT_TAXI = "transport_taxi"

    COMPANION_INDEPENDENT = "companion_independent"
    COMPANION_TOGETHER = "companion_together"
    COMPANION_FLEXIBLE = "companion_flexible"

    DAYTIME = "daytime"
    NIGHTLIFE = "nightlife"
    NIGHT_VIEW = "night_view"

    COMMUNICATION_HIGH = "communication_high"
    COMMUNICATION_LOW = "communication_low"

    PLANNER = "planner"
    SPONTANEOUS = "spontaneous"
    FOLLOWER = "follower"


class UserTravelStyle(Base):
    __tablename__ = "user_travel_style"

    id = Column(String(50), primary_key=True, default=generate_travel_style_id)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    style = Column(Enum(TravelStyle), nullable=False)

    user = relationship("User", back_populates="travel_styles")

    __table_args__ = (
        Index("ix_user_travel_style_user_id", "user_id"),
    )

    def __repr__(self):
        return f"<UserTravelStyle(id={self.id}, user_id={self.user_id}, style={self.style})>"
