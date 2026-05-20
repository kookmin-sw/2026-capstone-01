"""Pillow 기반 피드 이미지 전처리 — 순수 함수 (S3/DB 의존 없음).

리사이징:
- 1:1 center crop (짧은 축 기준) → small/medium JPEG q80 2종
- original: 한 변 ≤ 2048 + EXIF 회전 없으면 raw bytes 보존, 아니면 포맷별 재인코딩

방어선:
- (#1) 디컴프레션 봄: `Image.open` 직후 dimension 만 읽고 `MAX_DECODE_PIXELS` 초과 거절.
- (#7) 포맷 화이트리스트: JPEG/PNG/WEBP 외 (BMP/TIFF/GIF 등) 디코딩 가능해도 거절.
- (#8) Animation 거절: animated WEBP/APNG 는 content-type 만으로 정지본과 구분 불가하므로
       `is_animated` 로 헤더 디코딩 직후 차단.
- (#5) JPEG `optimize=False`: latency 우선 (Huffman 최적화 100~300ms vs 5~10% 절감).

디코딩/봄/미지원/해상도 초과는 모두 ValueError → 라우터 400.
"""
import warnings
from typing import Final
import io
from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.feed.dto.image import ProcessedFeedImage, ProcessedVariant
from app.core.logger import get_logger


logger = get_logger("feed.thumbnail")


THUMBNAIL_SMALL: Final[int] = 240
THUMBNAIL_MEDIUM: Final[int] = 720
ORIGINAL_MAX: Final[int] = 2048
JPEG_QUALITY: Final[int] = 80

# 50MP = ~7000×7000. RAW (~24MP) 안전 통과, 단색 PNG 폭탄은 차단.
# Pillow 기본 ~89MP cap 은 89~178MP 구간을 경고만 주고 통과시키므로 명시 cap.
MAX_DECODE_PIXELS: Final[int] = 50_000_000

_RGBA_BG_COLOR: Final[tuple[int, int, int]] = (255, 255, 255)

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

# EXIF Orientation. 1 = 정상, 그 외 = transpose 필요.
_EXIF_ORIENTATION_TAG: Final[int] = 0x0112


def process_feed_image(src_bytes: bytes) -> ProcessedFeedImage:
    """원본 bytes → (원본 + small + medium) 3종. 디코딩은 1회만 공유."""
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
    """단위 테스트 진입점 — small/medium 단독 호출."""
    src_image, _, _ = _decode(src_bytes)
    return _crop_square_and_resize(src_image, target_size)


def shrink_original_if_needed(src_bytes: bytes) -> ProcessedVariant:
    """단위 테스트 진입점 — original 단독 호출."""
    src_image, src_format, was_rotated = _decode(src_bytes)
    return _shrink_original(
        src_image, src_bytes, src_format=src_format, was_rotated=was_rotated,
    )


def _decode(src_bytes: bytes) -> tuple[Image.Image, str, bool]:
    """bytes → (EXIF 회전 정상화된 Image, 입력 포맷, 회전 적용 여부).

    검증 순서가 중요:
    1. `Image.open` (헤더만)
    2. 포맷 화이트리스트
    3. dimension cap (픽셀 디코딩 전)
    4. `img.load()` — 여기서 메모리 할당
    5. EXIF 회전 캡처 + transpose

    `Image.format` 은 transpose 후 None 이 되므로 미리 캡처.
    `was_rotated` 는 raw bytes ↔ 픽셀 일치 여부 — original 재인코딩 판단에 사용.
    """
    try:
        # Pillow 의 89~178MP 구간 `DecompressionBombWarning` stderr 누수 차단.
        # 우리 50MP cap 이 더 엄격해 어차피 곧 거절되므로 ignore 가 안전 (메시지 일관성 유지).
        # 글로벌 `Image.MAX_IMAGE_PIXELS` 변경은 다른 Pillow 사용처 (menu_ai) 에 영향이라 scoped.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(src_bytes)) as img:
                src_format = img.format
                if src_format not in _FORMAT_TO_CONTENT_TYPE:
                    logger.warning("미지원 이미지 포맷: {}", src_format)
                    raise ValueError("지원하지 않는 이미지 포맷입니다.")

                # animated WEBP/APNG 차단 — JPEG/정적 PNG 는 속성 부재라 기본값 False 로 통과.
                if getattr(img, "is_animated", False):
                    logger.warning(
                        "애니메이션 이미지 거절: format={}, n_frames={}",
                        src_format, getattr(img, "n_frames", "?"),
                    )
                    raise ValueError("애니메이션 이미지는 업로드할 수 없습니다.")

                if img.width * img.height > MAX_DECODE_PIXELS:
                    logger.warning(
                        "이미지 해상도 초과: {}×{} ({} pixels > {})",
                        img.width, img.height, img.width * img.height, MAX_DECODE_PIXELS,
                    )
                    raise ValueError("이미지 해상도가 너무 큽니다.")

                img.load()  # 강제 디코딩 — truncated/깨진 파일을 여기서 catch.

                was_rotated = _has_exif_rotation(img)
                transposed = ImageOps.exif_transpose(img)

    except Image.DecompressionBombError as e:
        # Pillow 178MP 하드 cap — 헤더가 거짓이거나 Image.open 단계의 추정 픽셀 폭발 케이스.
        logger.warning("이미지 디컴프레션 봄: {}", type(e).__name__)
        raise ValueError("이미지 해상도가 너무 큽니다.") from e
    except (UnidentifiedImageError, OSError) as e:
        logger.warning("이미지 디코딩 실패: {}", type(e).__name__)
        raise ValueError("이미지를 처리할 수 없습니다.") from e

    return transposed, src_format, was_rotated


def _crop_square_and_resize(src_image: Image.Image, target_size: int) -> ProcessedVariant:
    """짧은 축 center-crop → 정사각 → target_size 다운스케일 → JPEG q80."""
    rgb_image = _flatten_to_rgb(src_image)
    cropped = ImageOps.fit(
        rgb_image, (target_size, target_size), Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
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
    """원본 보관 변형 — 가능하면 raw bytes 보존, 필요할 때만 재인코딩.

    재인코딩 트리거: 한 변 > ORIGINAL_MAX OR EXIF 회전 적용.
    포맷별: JPEG→JPEG q80, WEBP→alpha 있으면 PNG (없으면 JPEG, PNG 통일 시 용량 폭증), PNG→PNG.
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
        img.thumbnail((ORIGINAL_MAX, ORIGINAL_MAX), Image.Resampling.LANCZOS)

    if src_format == "JPEG":
        return _encode_jpeg(_flatten_to_rgb(img))

    if src_format == "WEBP":
        if img.mode in ("RGBA", "LA"):
            return _encode_png(img)
        return _encode_jpeg(_flatten_to_rgb(img))

    return _encode_png(img)


def _encode_jpeg(img: Image.Image) -> ProcessedVariant:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=False)
    return ProcessedVariant(buf.getvalue(), "image/jpeg", "jpg")


def _encode_png(img: Image.Image) -> ProcessedVariant:
    """PNG — 호출 빈도 낮고 무손실이라 optimize=True 유지."""
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return ProcessedVariant(buf.getvalue(), "image/png", "png")


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """JPEG 인코딩 전 alpha 제거 — RGBA/LA/palette+transparency → RGB 흰배경.

    Contract: RGB 입력은 동일 객체 반환 (copy 회피). 호출측이 결과를 in-place 변형하면
    원본까지 함께 바뀐다 — 현재 호출처는 모두 read-only 사용.
    """
    if img.mode == "RGB":
        return img

    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, _RGBA_BG_COLOR)
        bg.paste(img, mask=img.split()[-1])
        return bg

    if img.mode == "P" and "transparency" in img.info:
        return _flatten_to_rgb(img.convert("RGBA"))

    return img.convert("RGB")


def _has_exif_rotation(img: Image.Image) -> bool:
    """Orientation tag 가 1 이외면 transpose 가 픽셀을 회전/반전. EXIF 부재 시에도 안전 (빈 Exif 반환)."""
    return img.getexif().get(_EXIF_ORIENTATION_TAG, 1) != 1
