from dataclasses import dataclass


@dataclass
class DetectData:
    """언어 감지 결과 DTO"""
    lang_code: str


@dataclass
class TranslateData:
    """번역 결과 DTO"""
    translated_text: str
