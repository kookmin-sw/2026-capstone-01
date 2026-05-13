from typing import Literal
from pydantic import BaseModel, Field


LangCode = Literal["ko", "en"]


# ──────────────────── Request ────────────────────

class DetectRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="언어를 감지할 원문")


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="번역할 원문")
    source: LangCode = Field(..., description="원문 언어 코드 (ko | en)")
    target: LangCode = Field(..., description="대상 언어 코드 (ko | en)")


# ──────────────────── Response ────────────────────

class DetectResponse(BaseModel):
    lang_code: str = Field(..., description="감지된 언어 코드 (예: ko, en)")


class TranslateResponse(BaseModel):
    translated_text: str = Field(..., description="번역 결과 문장")
