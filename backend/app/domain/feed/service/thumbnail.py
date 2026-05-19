"""Pillow 기반 피드 이미지 전처리.

본 모듈은 모두 순수 함수 (S3 / DB / I/O 의존 없음) — 단위 테스트 친화.
호출 측 (`feed_post.py` 서비스) 은 결과 bytes 를 그대로 S3 에 업로드한다.

리사이징 규칙:
    - 1:1 center crop (짧은 축 기준)
    - 썸네일 small / medium 2종 + 원본 (한 변 최대 2048px)
    - jpg: quality 75~85 → 80 으로 고정
    - png: 무손실 유지 (RGBA 보존). webp 변환은 Phase 2.

변형(variant) 별 출력 포맷:
    - small / medium  : JPEG q80. RGBA 는 흰색 배경 합성 후 변환 (그리드/상세 미리보기 용도라 투명도 손실 허용).
    - original        : 한 변 ≤ 2048 이고 EXIF 회전 없음 → **raw bytes 그대로 보존** (무손실 + 비용 0).
                        그 외 → 입력 포맷 별 분기:
                            - JPEG  → JPEG q80
                            - WEBP  → alpha 있으면 PNG, 없으면 JPEG q80 (PNG 통일 시 lossy→lossless 로 용량 폭증)
                            - PNG   → PNG (spec: 무손실 유지)

방어 / 정책:
    - **디컴프레션 봄 (#1)**: `Image.open` 직후 dimension 만 읽고 `MAX_DECODE_PIXELS` 초과면 즉시 거절.
      Pillow 기본 89MP 임계는 89~178MP 구간을 경고만 주고 통과시키므로 명시 cap 필요.
    - **포맷 화이트리스트 (#7)**: 라우터의 content-type 검증을 우회한 BMP/TIFF/GIF 등을 디코딩 가능 포맷이라도
      `_FORMAT_TO_CONTENT_TYPE` 의 3종이 아니면 거절. 거짓 content-type 헤더로 들어와도 차단.
    - **Animation 거절 (#8)**: Feed 는 정지 이미지 전용. 라우터의 content-type 만으로는
      animated WEBP / APNG 를 정지본과 구분할 수 없어 (둘 다 `image/webp` / `image/png`),
      `_decode` 가 헤더 디코딩 직후 `is_animated` 로 차단. small/medium 은 first-frame JPEG
      이고 original 은 raw bytes 보존 fast-path 가 있어 multi-frame 입력 시 표시 불일치 위험.
      GIF 는 포맷 화이트리스트 (#7) 에서 별도로 거절.
    - **JPEG `optimize=False` (#5)**: 동기 업로드 흐름의 latency 절감 (Huffman 최적화 100~300ms vs 5~10% 절감).
      PNG 는 호출 빈도 낮고 무손실이라 `optimize=True` 유지.
    - **ICC 프로파일은 보존하지 않음 (#6)**: casual photo feed scope 외. Phase 2 에서 사진가 모드 도입 시 재검토.

예외:
    - 이미지 디코딩 실패 / 손상 / 봄 / 미지원 포맷 / 해상도 초과는 모두 ValueError 로 변환.
      라우터에서 400 으로 매핑 (도메인 컨벤션).
"""
import warnings
from typing import Final
import io
from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.feed.dto.image import ProcessedFeedImage, ProcessedVariant
from app.core.logger import get_logger


logger = get_logger("feed.thumbnail")


# ──────────────────── 튜닝 상수 ────────────────────

# 썸네일 한 변 (정사각형). "생성 이미지 규격".
THUMBNAIL_SMALL: Final[int] = 240
THUMBNAIL_MEDIUM: Final[int] = 720

# 원본 한 변 최대. 초과 시 LANCZOS 로 다운스케일.
ORIGINAL_MAX: Final[int] = 2048

# JPEG 품질 — 기획안 75~85 의 중간값.
JPEG_QUALITY: Final[int] = 80

# 디컴프레션 봄 방어 — 디코딩 전에 헤더의 width × height 로 거른다.
# 50MP = 약 7000×7000. 스마트폰 RAW (~24MP) 모두 안전하게 통과,
# 단색 PNG 폭탄 (10MB 안에 50000×50000 = 2500MP 가능) 은 차단.
# Pillow 기본 `MAX_IMAGE_PIXELS` (~89MP) 는 89~178MP 구간을 경고만 주고 통과시키므로 우리가 명시 cap.
MAX_DECODE_PIXELS: Final[int] = 50_000_000

# RGBA → JPEG 변환 시 alpha 합성용 배경.
_RGBA_BG_COLOR: Final[tuple[int, int, int]] = (255, 255, 255)

# Pillow 포맷 명 → MIME / ext 매핑. 입력으로 허용된 3종만 명시 (라우터에서 차단).
_FORMAT_TO_CONTENT_TYPE: Final[dict[str, str]] = {
    "JPEG": "image/jpeg",
    "PNG":  "image/png",
    "WEBP": "image/webp",
}
_FORMAT_TO_EXT: Final[dict[str, str]] = {
    "JPEG": "jpg",
    "PNG":  "png",
    "WEBP": "webp",
}

# EXIF Orientation 태그 ID. 1 = 정상, 그 외 = 회전/반전 적용 필요.
_EXIF_ORIENTATION_TAG: Final[int] = 0x0112


# ──────────────────── 공개 API ────────────────────

def process_feed_image(src_bytes: bytes) -> ProcessedFeedImage:
    """원본 bytes → (원본 + small + medium) 3종 변형 생성.

    디코딩은 한 번만 수행하고 세 변형이 같은 source 를 공유한다 (디코딩 비용이 큼).

    raises:
        ValueError: Pillow 디코딩 실패 / decompression bomb / 손상 이미지.
                    라우터에서 400 으로 매핑.
    """
    src_image, src_format, was_rotated = _decode(src_bytes)

    return ProcessedFeedImage(
        original=_shrink_original(
            src_image, src_bytes,
            src_format=src_format, was_rotated=was_rotated,
        ),
        small=_crop_square_and_resize(src_image, THUMBNAIL_SMALL),
        medium=_crop_square_and_resize(src_image, THUMBNAIL_MEDIUM),
    )


def crop_square_and_resize(src_bytes: bytes, target_size: int) -> ProcessedVariant:
    """단위 테스트 진입점 — small/medium 단계만 단독 호출. 결과는 항상 JPEG q80."""
    src_image, _, _ = _decode(src_bytes)
    return _crop_square_and_resize(src_image, target_size)


def shrink_original_if_needed(src_bytes: bytes) -> ProcessedVariant:
    """단위 테스트 진입점 — original 단계만 단독 호출."""
    src_image, src_format, was_rotated = _decode(src_bytes)
    return _shrink_original(
        src_image, src_bytes, src_format=src_format, was_rotated=was_rotated,
    )


# ──────────────────── 내부 헬퍼 ────────────────────

def _decode(src_bytes: bytes) -> tuple[Image.Image, str, bool]:
    """bytes → (EXIF 회전 정상화된 Image, 입력 포맷 명, EXIF 회전 적용 여부).

    검증 순서가 중요하다:
        1. `Image.open` — 헤더만 읽음, 픽셀 디코딩 X.
        2. 포맷 화이트리스트 — 디코딩 가능해도 3종 외면 거절 (#7).
        3. dimension cap — 픽셀 디코딩 전에 거름 (#1).
        4. `img.load()` — 여기서 비로소 메모리 할당.
        5. EXIF 회전 캡처 + transpose.

    `Image.format` 은 transpose 결과에서 None 이 되므로 미리 캡처해 반환한다.
    `was_rotated` 는 raw bytes 와 픽셀이 달라졌는지를 의미 — original 보관 시 재인코딩 여부 판단에 사용.
    """
    try:
        # (#1 보완) Pillow 의 `DecompressionBombWarning` (89~178MP 구간) stderr 누수 차단.
        # 글로벌 `Image.MAX_IMAGE_PIXELS` 변경은 다른 Pillow 사용처 (menu_ai 등) 에도 영향이라
        # `catch_warnings` 로 함수 단위 scoped. 우리 `MAX_DECODE_PIXELS` (50MP) 가 더 엄격해
        # 어차피 경고 구간은 곧 거절되므로 `ignore` 가 안전 — 메시지 일관성 ("해상도가 너무 큽니다") 도 유지.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            # `with Image.open` — 함수 종료 시 Pillow 내부 fp 명시 close.
            # `transposed` / convert 결과는 새 Image (Pillow ≥9.5 의 `exif_transpose` 는
            # 회전이 없어도 `image.copy()` 반환) 라 컨텍스트 종료 후에도 안전.
            with Image.open(io.BytesIO(src_bytes)) as img:
                # (#7) 포맷 화이트리스트 — content-type 거짓 헤더로 들어온 BMP/TIFF/GIF 등 차단.
                src_format = img.format
                if src_format not in _FORMAT_TO_CONTENT_TYPE:
                    logger.warning("미지원 이미지 포맷: {}", src_format)
                    raise ValueError("지원하지 않는 이미지 포맷입니다.")

                # (#8) animated WEBP / APNG 차단. content-type 만으로 정지본과 구분 불가하므로
                # 라우터에서 못 잡고 여기서 헤더 디코딩 직후 거절. JPEG / 정적 PNG 는 속성 자체가
                # 없거나 False 라 `getattr` 기본값으로 안전 통과.
                if getattr(img, "is_animated", False):
                    logger.warning(
                        "애니메이션 이미지 거절: format={}, n_frames={}",
                        src_format, getattr(img, "n_frames", "?"),
                    )
                    raise ValueError("애니메이션 이미지는 업로드할 수 없습니다.")

                # (#1) dimension 사전 차단 — header 의 width / height 만 읽어 거름.
                # 픽셀 디코딩 (`load`) 전이라 봄 이미지의 메모리 할당 자체가 일어나지 않음.
                if img.width * img.height > MAX_DECODE_PIXELS:
                    logger.warning(
                        "이미지 해상도 초과: {}×{} ({} pixels > {})",
                        img.width, img.height, img.width * img.height, MAX_DECODE_PIXELS,
                    )
                    raise ValueError("이미지 해상도가 너무 큽니다.")

                img.load()  # 픽셀 디코딩 강제 — truncated / 깨진 파일을 여기서 잡는다.

                was_rotated = _has_exif_rotation(img)
                transposed = ImageOps.exif_transpose(img)

    except Image.DecompressionBombError as e:
        # Pillow 의 178MP 하드 캡 — 우리 50MP 캡 (위) 보다 느슨하지만, 헤더가 거짓이거나
        # `Image.open` 단계에서 추정 픽셀이 폭발하는 경우를 잡는다. 메시지 일관성 위해 분리.
        logger.warning("이미지 디컴프레션 봄: {}", type(e).__name__)
        raise ValueError("이미지 해상도가 너무 큽니다.") from e
    except (UnidentifiedImageError, OSError) as e:
        logger.warning("이미지 디코딩 실패: {}", type(e).__name__)
        raise ValueError("이미지를 처리할 수 없습니다.") from e

    return transposed, src_format, was_rotated


def _crop_square_and_resize(src_image: Image.Image, target_size: int) -> ProcessedVariant:
    """짧은 축 기준 center-crop → 정사각형 → target_size 다운스케일 → JPEG q80.

    `ImageOps.fit` 이 짧은 축 기준 center-crop + LANCZOS 리샘플링을 한 번에 수행.
    """
    rgb_image = _flatten_to_rgb(src_image)
    cropped = ImageOps.fit(
        rgb_image, (target_size, target_size), Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    # (#5) optimize=False — 동기 흐름의 latency 우선. Huffman 최적화 비용 vs 5~10% 절감 트레이드오프.
    cropped.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=False)
    return ProcessedVariant(
        data=buf.getvalue(),
        content_type="image/jpeg",
        file_ext="jpg",
    )


def _shrink_original(
    src_image: Image.Image,
    src_bytes: bytes,
    *,
    src_format: str,
    was_rotated: bool,
) -> ProcessedVariant:
    """원본 보관 변형 — 가능하면 raw bytes 보존, 필요할 때만 다운스케일/재인코딩.

    재인코딩 트리거:
        - 한 변이 ORIGINAL_MAX 초과 (다운스케일 필요)
        - EXIF 회전이 적용됨 (raw bytes 와 픽셀 불일치)

    재인코딩 포맷 선택:
        - JPEG → JPEG q80 (어차피 손실 포맷, optimize=False 로 latency 우선)
        - WEBP → alpha 있으면 PNG, 없으면 JPEG q80 (#3: PNG 통일은 lossy→lossless 라 용량 폭증 가능)
        - PNG  → PNG (spec: 무손실 유지)
    """
    needs_shrink = max(src_image.size) > ORIGINAL_MAX

    if not needs_shrink and not was_rotated:
        return ProcessedVariant(
            data=src_bytes,
            content_type=_FORMAT_TO_CONTENT_TYPE[src_format],
            file_ext=_FORMAT_TO_EXT[src_format],
        )

    img = src_image.copy()
    if needs_shrink:
        # thumbnail 은 in-place + aspect 비율 자동 보존 (정사각 crop 아님 — 원본 비율 유지).
        img.thumbnail((ORIGINAL_MAX, ORIGINAL_MAX), Image.Resampling.LANCZOS)

    if src_format == "JPEG":
        return _encode_jpeg(_flatten_to_rgb(img))

    if src_format == "WEBP":
        # (#3) alpha 보존이 필요한 WEBP 만 PNG. 그 외는 JPEG 로 떨어뜨려 lossy→lossless bloat 회피.
        if img.mode in ("RGBA", "LA"):
            return _encode_png(img)
        return _encode_jpeg(_flatten_to_rgb(img))

    # PNG: 무손실 유지
    return _encode_png(img)


def _encode_jpeg(img: Image.Image) -> ProcessedVariant:
    """JPEG q80, optimize=False (#5)."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=False)
    return ProcessedVariant(buf.getvalue(), "image/jpeg", "jpg")


def _encode_png(img: Image.Image) -> ProcessedVariant:
    """PNG — 호출 빈도 낮고 무손실이라 optimize=True 유지."""
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return ProcessedVariant(buf.getvalue(), "image/png", "png")


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """JPEG 인코딩을 위해 alpha 제거 — RGBA / LA / palette+transparency → RGB 흰배경 합성.

    Contract: RGB 입력은 동일 객체를, 그 외는 새 객체를 반환 (불필요한 copy 회피).
    호출측은 결과 이미지를 in-place 변형하지 말 것 — RGB fast-path 에서 입력까지 함께
    바뀐다. 현재 호출처 (`_crop_square_and_resize`, `_shrink_original`) 는 모두
    `ImageOps.fit` / `Image.save` 처럼 새 이미지를 만들거나 read-only 로만 사용한다.
    """
    if img.mode == "RGB":
        return img

    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, _RGBA_BG_COLOR)
        # split()[-1] = alpha 채널 — Pillow 가 mask 로 해석해 알파 블렌딩 수행
        bg.paste(img, mask=img.split()[-1])
        return bg

    if img.mode == "P" and "transparency" in img.info:
        # palette + transparency → RGBA 경유로 정규화
        return _flatten_to_rgb(img.convert("RGBA"))

    return img.convert("RGB")


def _has_exif_rotation(img: Image.Image) -> bool:
    """EXIF Orientation 태그가 1(정상) 외 값이면 transpose 가 픽셀을 회전/반전시킨다.

    Pillow `getexif()` 는 EXIF 없는 이미지에 대해 빈 `Exif` 를 반환하지 raise 하지 않는다.
    이전에 둔 `except Exception` 은 paranoid 방어였고 실제 버그를 숨길 위험이 있어 제거.
    """
    return img.getexif().get(_EXIF_ORIENTATION_TAG, 1) != 1
