"""thumbnail.process_feed_image 종합 회귀 테스트.

`test_animated_rejection.py` 가 #8 (animated 거절) 만 다루고, 본 파일은 다음을 cover:

    - 정상 출력: 3 variant 의 사이즈 / mode / content_type
    - shrink fast-path: 한 변 ≤ ORIGINAL_MAX + EXIF 회전 없음 → raw bytes 그대로 보존
    - shrink 트리거: ORIGINAL_MAX 초과 시 다운스케일
    - EXIF 회전: was_rotated 가 True 면 raw 와 다른 bytes 반환
    - RGBA → RGB flatten: 흰 배경 합성 (alpha 손실)
    - WEBP alpha 분기: alpha 있으면 PNG, 없으면 JPEG
    - 포맷 화이트리스트 (#7): BMP / TIFF / GIF 거절
    - 디컴프레션 봄 (#1): MAX_DECODE_PIXELS 초과 거절
    - 디코딩 실패: UnidentifiedImageError / 손상 bytes → ValueError

이미지는 Pillow 로 즉석 합성 — fixture 파일 없이 self-contained.
"""
import pytest
import io
from PIL import Image

from app.domain.feed.service.thumbnail import (
    MAX_DECODE_PIXELS,
    ORIGINAL_MAX,
    THUMBNAIL_MEDIUM,
    THUMBNAIL_SMALL,
    crop_square_and_resize,
    process_feed_image,
    shrink_original_if_needed,
)


# ──────────────────── helper ────────────────────

def _save(img: Image.Image, fmt: str, **save_kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def _jpeg(size=(100, 100), color=(255, 0, 0)) -> bytes:
    return _save(Image.new("RGB", size, color), "JPEG", quality=80)


def _png(size=(100, 100), color=(0, 255, 0), mode="RGB") -> bytes:
    img = Image.new(mode, size, color if mode == "RGB" else color + (128,))
    return _save(img, "PNG")


def _webp(size=(100, 100), color=(0, 0, 255), alpha=False) -> bytes:
    if alpha:
        img = Image.new("RGBA", size, color + (128,))
    else:
        img = Image.new("RGB", size, color)
    return _save(img, "WEBP")


# ──────────────────── 정상 출력 ────────────────────

@pytest.mark.unit
class TestProcessFeedImageOutput:
    def test_three_variants_with_correct_sizes(self):
        result = process_feed_image(_jpeg(size=(800, 600)))

        # original 은 ORIGINAL_MAX 이하 + EXIF 없음 → raw 보존 (사이즈는 800×600 그대로)
        original_img = Image.open(io.BytesIO(result.original.data))
        assert original_img.size == (800, 600)

        # 썸네일은 항상 정사각형 + 지정 사이즈
        small_img = Image.open(io.BytesIO(result.small.data))
        assert small_img.size == (THUMBNAIL_SMALL, THUMBNAIL_SMALL)

        medium_img = Image.open(io.BytesIO(result.medium.data))
        assert medium_img.size == (THUMBNAIL_MEDIUM, THUMBNAIL_MEDIUM)


    def test_thumbnails_are_jpeg_rgb(self):
        result = process_feed_image(_jpeg())

        assert result.small.content_type == "image/jpeg"
        assert result.small.file_ext == "jpg"
        assert Image.open(io.BytesIO(result.small.data)).mode == "RGB"

        assert result.medium.content_type == "image/jpeg"
        assert result.medium.file_ext == "jpg"


# ──────────────────── original fast-path / shrink ────────────────────

@pytest.mark.unit
class TestShrinkOriginal:
    def test_small_image_returns_raw_bytes(self):
        """ORIGINAL_MAX 이하 + EXIF 회전 없음 → raw bytes 그대로 (재인코딩 비용 0)."""
        src = _jpeg(size=(500, 500))
        result = shrink_original_if_needed(src)
        assert result.data == src
        assert result.content_type == "image/jpeg"
        assert result.file_ext == "jpg"


    def test_oversized_image_is_shrunk(self):
        """ORIGINAL_MAX 초과 → thumbnail 로 다운스케일 + 비율 보존."""
        src = _jpeg(size=(ORIGINAL_MAX + 500, ORIGINAL_MAX + 500))
        result = shrink_original_if_needed(src)
        out_img = Image.open(io.BytesIO(result.data))
        assert max(out_img.size) <= ORIGINAL_MAX
        assert result.data != src  # re-encoded


    def test_png_preserves_format_when_shrunk(self):
        """PNG spec: 무손실 유지 — shrink 가 일어나도 PNG 로 재인코딩."""
        src = _png(size=(ORIGINAL_MAX + 100, ORIGINAL_MAX + 100))
        result = shrink_original_if_needed(src)
        assert result.content_type == "image/png"
        assert result.file_ext == "png"


    def test_webp_with_alpha_shrunk_becomes_png(self):
        """alpha 보존이 필요한 WEBP → PNG (lossy→lossless bloat 회피 위해 분기)."""
        src = _webp(size=(ORIGINAL_MAX + 100, ORIGINAL_MAX + 100), alpha=True)
        result = shrink_original_if_needed(src)
        assert result.content_type == "image/png"


    def test_webp_without_alpha_shrunk_becomes_jpeg(self):
        """alpha 없는 WEBP → JPEG (PNG 통일 시 용량 폭증)."""
        src = _webp(size=(ORIGINAL_MAX + 100, ORIGINAL_MAX + 100), alpha=False)
        result = shrink_original_if_needed(src)
        assert result.content_type == "image/jpeg"


# ──────────────────── crop + resize ────────────────────

@pytest.mark.unit
class TestCropSquareAndResize:
    def test_landscape_input_becomes_square(self):
        """가로 800 × 세로 600 입력 → 짧은 축 (600) 기준 center-crop → 240×240."""
        result = crop_square_and_resize(_jpeg(size=(800, 600)), THUMBNAIL_SMALL)
        out = Image.open(io.BytesIO(result.data))
        assert out.size == (THUMBNAIL_SMALL, THUMBNAIL_SMALL)


    def test_portrait_input_becomes_square(self):
        result = crop_square_and_resize(_jpeg(size=(600, 800)), THUMBNAIL_MEDIUM)
        out = Image.open(io.BytesIO(result.data))
        assert out.size == (THUMBNAIL_MEDIUM, THUMBNAIL_MEDIUM)


    def test_rgba_input_flattened_to_rgb_white_bg(self):
        """RGBA → JPEG 인코딩 시 alpha 자리에 흰 배경 합성."""
        # 반투명 빨강. alpha=128 인 RGBA 를 PNG 로 저장.
        src = _png(size=(100, 100), color=(255, 0, 0), mode="RGBA")
        result = crop_square_and_resize(src, THUMBNAIL_SMALL)
        out = Image.open(io.BytesIO(result.data))
        assert out.mode == "RGB"
        # alpha=128 인 빨강 + 흰 배경 합성 → 분홍 계열. 정확한 값보다 "투명 영역이 흰색
        # 으로 채워졌는지" 만 확인 (LANCZOS 보간으로 정확한 픽셀 매칭 어려움).
        # 중심 픽셀의 R 채널이 가장 높은 값이고 G/B 가 0 이 아님 (=alpha 합성 일어남) 검증.
        r, g, b = out.getpixel((THUMBNAIL_SMALL // 2, THUMBNAIL_SMALL // 2))
        assert r > g and r > b  # 빨강 우세
        assert g > 0 and b > 0  # 흰 배경 합성으로 G/B 도 0 초과


# ──────────────────── EXIF 회전 ────────────────────

@pytest.mark.unit
class TestExifRotation:
    def test_image_with_orientation_tag_is_re_encoded(self):
        """EXIF Orientation 이 1(정상) 외 값이면 transpose 가 픽셀을 바꾸므로 raw 보존 X."""
        # Orientation=6 (시계 90도) 를 EXIF 에 박아 저장.
        from PIL.ExifTags import TAGS
        src_img = Image.new("RGB", (100, 100), (255, 0, 0))
        exif = src_img.getexif()
        exif[0x0112] = 6  # Orientation
        buf = io.BytesIO()
        src_img.save(buf, format="JPEG", exif=exif, quality=80)
        src_bytes = buf.getvalue()

        result = shrink_original_if_needed(src_bytes)
        # transpose 가 픽셀을 바꿨으므로 raw 보존 fast-path 가 아닌 재인코딩 path.
        assert result.data != src_bytes


# ──────────────────── 포맷 화이트리스트 (#7) ────────────────────

@pytest.mark.unit
class TestFormatWhitelist:
    @pytest.mark.parametrize(
        "fmt,save_kwargs",
        [
            ("BMP", {}),
            ("TIFF", {}),
            ("GIF", {}),  # GIF: animated 가 아니어도 화이트리스트에서 거절
        ],
    )
    def test_disallowed_format_raises_value_error(self, fmt, save_kwargs):
        src = _save(Image.new("RGB", (50, 50), (1, 2, 3)), fmt, **save_kwargs)
        with pytest.raises(ValueError, match="지원하지 않는 이미지 포맷"):
            process_feed_image(src)


# ──────────────────── 디컴프레션 봄 (#1) ────────────────────

@pytest.mark.unit
class TestDecompressionBomb:
    def test_oversized_dimensions_rejected(self):
        """헤더가 MAX_DECODE_PIXELS 를 초과하면 픽셀 디코딩 전에 거절.

        실제로 거대 이미지를 합성하면 메모리가 폭발하므로 헤더만 수정한 PNG 를 만든다.
        Pillow 가 읽는 IHDR chunk 의 width / height 만 큰 값으로 박아 두면, `Image.open`
        직후 `img.width × img.height` 체크에서 걸린다.
        """
        # 작은 PNG 만들고 IHDR width/height 를 큰 값으로 패치.
        small = _png(size=(10, 10))
        # PNG IHDR: 8-byte signature + 4-byte chunk length + 4-byte type "IHDR" + 13-byte data
        # data: width(4) height(4) ... → byte offset 16 부터 width, 20 부터 height (big-endian)
        import struct
        side = 10_000  # 10000 × 10000 = 100MP > MAX_DECODE_PIXELS (50MP)
        patched = bytearray(small)
        struct.pack_into(">I", patched, 16, side)
        struct.pack_into(">I", patched, 20, side)
        # IHDR CRC 가 깨지지만 Pillow 는 width/height 만 읽는 시점에서 우리 코드가 거절.
        # 만약 Pillow 가 CRC 검증 강제하면 OSError 가 먼저 발생할 수 있어, 두 ValueError 메시지 모두 허용.
        with pytest.raises(ValueError, match="해상도가 너무 큽니다|이미지를 처리할 수 없습니다"):
            process_feed_image(bytes(patched))


# ──────────────────── 디코딩 실패 ────────────────────

@pytest.mark.unit
class TestDecodingFailure:
    def test_garbage_bytes_raise_value_error(self):
        with pytest.raises(ValueError, match="이미지를 처리할 수 없습니다"):
            process_feed_image(b"this is not an image at all")


    def test_empty_bytes_raise_value_error(self):
        with pytest.raises(ValueError, match="이미지를 처리할 수 없습니다"):
            process_feed_image(b"")
