"""thumbnail._decode 의 애니메이션 이미지 거절 회귀 테스트.

라우터의 content-type 만으로는 animated WEBP / APNG 를 정지본과 구분할 수 없어 (둘 다
`image/webp` / `image/png`) thumbnail 단에서 차단해야 한다. 이 테스트가 깨지면 multi-frame
입력 시 small/medium 은 first-frame JPEG, original 은 raw 애니메이션 bytes 로 갈리는
표시 불일치가 재발한다.

JPEG / 정적 PNG / 정적 WEBP 가 통과하는지도 같이 검증 — `getattr` 기본값으로 오탐 없는지 확인.
"""
import pytest
import io
from PIL import Image

from app.domain.feed.service.thumbnail import process_feed_image


def _make_webp(*, animated: bool) -> bytes:
    """단일/다중 프레임 WEBP bytes 합성."""
    buf = io.BytesIO()
    base = Image.new("RGB", (64, 64), (255, 0, 0))
    if animated:
        frame2 = Image.new("RGB", (64, 64), (0, 0, 255))
        base.save(buf, format="WEBP", save_all=True, append_images=[frame2], duration=100, loop=0)
    else:
        base.save(buf, format="WEBP")
    return buf.getvalue()


def _make_png(*, animated: bool) -> bytes:
    """단일 PNG / APNG bytes 합성."""
    buf = io.BytesIO()
    base = Image.new("RGB", (64, 64), (255, 0, 0))
    if animated:
        frame2 = Image.new("RGB", (64, 64), (0, 255, 0))
        base.save(buf, format="PNG", save_all=True, append_images=[frame2], duration=100, loop=0)
    else:
        base.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


@pytest.mark.unit
class TestAnimatedRejection:
    def test_animated_webp_raises_value_error(self):
        with pytest.raises(ValueError, match="애니메이션"):
            process_feed_image(_make_webp(animated=True))


    def test_apng_raises_value_error(self):
        with pytest.raises(ValueError, match="애니메이션"):
            process_feed_image(_make_png(animated=True))


@pytest.mark.unit
class TestStaticImagesPass:
    """정지 이미지는 `is_animated` 가 False 이거나 속성 자체가 없어 통과해야 한다."""

    def test_static_webp_passes(self):
        result = process_feed_image(_make_webp(animated=False))
        assert result.original.content_type == "image/webp"
        assert result.small.content_type == "image/jpeg"
        assert result.medium.content_type == "image/jpeg"


    def test_static_png_passes(self):
        result = process_feed_image(_make_png(animated=False))
        assert result.original.content_type == "image/png"


    def test_jpeg_passes(self):
        # JPEG 는 `is_animated` 속성 자체가 없는 경로 — getattr 기본값 False 검증.
        result = process_feed_image(_make_jpeg())
        assert result.original.content_type == "image/jpeg"
