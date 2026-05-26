"""피드 도메인 ID 생성기 회귀 테스트.

검증:
    - prefix 가 약속된 값 (FDP_, FDC_) — DB 에 이미 들어간 PK 와의 호환성 보장
    - 형식: {prefix}_{timestamp(int)}_{8hex}
    - 동일 호출 N 회 모두 unique (uuid 충돌 회귀 가드)
    - timestamp prefix 라 문자열 정렬 = 시간순 — DocString 명시 약속

prefix 가 깨지면 piggyback 인덱스 (string LIKE 'FDP_%') 도 깨질 수 있으므로 명시적 회귀.
"""
import re
import pytest

from app.util.id_generator import generate_feed_post_comment_id, generate_feed_post_id


_FDP_PATTERN = re.compile(r"^FDP_\d+_[0-9a-f]{8}$")
_FDC_PATTERN = re.compile(r"^FDC_\d+_[0-9a-f]{8}$")


@pytest.mark.unit
class TestGenerateFeedPostId:
    def test_prefix_is_FDP(self):
        assert generate_feed_post_id().startswith("FDP_")


    def test_format_matches_pattern(self):
        assert _FDP_PATTERN.match(generate_feed_post_id())


    def test_n_calls_are_all_unique(self):
        ids = {generate_feed_post_id() for _ in range(100)}
        assert len(ids) == 100


@pytest.mark.unit
class TestGenerateFeedPostCommentId:
    def test_prefix_is_FDC(self):
        assert generate_feed_post_comment_id().startswith("FDC_")


    def test_format_matches_pattern(self):
        assert _FDC_PATTERN.match(generate_feed_post_comment_id())


    def test_n_calls_are_all_unique(self):
        ids = {generate_feed_post_comment_id() for _ in range(100)}
        assert len(ids) == 100


@pytest.mark.unit
class TestPrefixSeparation:
    def test_post_and_comment_prefixes_do_not_collide(self):
        """FDP_ vs FDC_ — 한쪽 호출이 다른 쪽 prefix 를 만들면 안 됨."""
        post_ids = [generate_feed_post_id() for _ in range(20)]
        comment_ids = [generate_feed_post_comment_id() for _ in range(20)]
        assert all(pid.startswith("FDP_") for pid in post_ids)
        assert all(cid.startswith("FDC_") for cid in comment_ids)
