"""채팅 도메인 Redis 키 / TTL 상수.

키 문자열을 코드 전체에 흩뿌리지 않는 목적 — 네이밍 실수 한 번으로 dedupe/세션이
다른 키 공간을 쓰게 되는 사고를 방지한다.
"""

# ─────────────────────────────────────────────────────────────
# TTL (seconds)
# ─────────────────────────────────────────────────────────────
SESSION_TTL = 90            # sess:{sid}, ws_route:{sid}, sessions ZSET score 연장 주기와 동일
ROOM_MEMBERS_TTL = 600      # room:members:{R} 캐시 — RDB fallback 전제이므로 짧게 잡아도 됨
ROOM_BLOCKS_TTL = 600       # room:blocks:{R} 캐시 — friend 도메인 hook 미호출 시 stale 상한
RATE_LIMIT_TTL = 1          # rate:msg:{uid} — 1초 윈도우
DEDUPE_TTL = 600            # dedupe:{uid}:{cmid} — 클라 재전송 최대 갭보다 충분히 길게
NODE_TTL = 90               # chat:nodes ZSET score(만료시각) — SESSION_TTL 과 동일 주기로 갱신

# ─────────────────────────────────────────────────────────────
# 임계값
# ─────────────────────────────────────────────────────────────
RATE_LIMIT_THRESHOLD = 10   # 초당 메시지 상한
MAX_SESSIONS_PER_USER = 10  # 유저당 동시 세션 상한

# force_jump 파라미터 — recover_and_incr 의 base gap 과 맞춰 간섭 최소화
SEQ_FORCE_JUMP_GAP = 1000
SEQ_FORCE_JUMP_JITTER_MAX = 10000
SEQ_RECOVER_GAP = 1000      # mongo_max + SEQ_RECOVER_GAP 를 base 로 사용


# ─────────────────────────────────────────────────────────────
# 키 빌더 — DB 0 (hot)
# ─────────────────────────────────────────────────────────────
def sess_key(session_id: str) -> str:
    return f"sess:{session_id}"


def sessions_key(user_id: str) -> str:
    return f"sessions:{user_id}"


def ws_route_key(session_id: str) -> str:
    return f"ws_route:{session_id}"


def unread_key(user_id: str) -> str:
    return f"unread:{user_id}"


def room_seq_key(room_id: str) -> str:
    return f"room:seq:{room_id}"


def room_members_key(room_id: str) -> str:
    return f"room:members:{room_id}"


def room_blocks_key(room_id: str) -> str:
    return f"room:blocks:{room_id}"


def rate_msg_key(user_id: str) -> str:
    return f"rate:msg:{user_id}"


def node_channel_key(node_id: str) -> str:
    """노드별 Pub/Sub 채널 — `FANOUT_MODE=node_channel` 모드에서 각 노드가 자기 채널만 구독.

    publisher 는 broadcast 시 활성 노드 전체의 채널에 PUBLISH (node registry 조회), 세션
    직송 시엔 `ws_route:{sid}` 로 타깃 노드만 PUBLISH.
    """
    return f"node:{node_id}"


DIRTY_CHAT_ROOM_KEY = "dirty:chat_room"   # reconcile worker 가 소비하는 SET
NODES_ZSET_KEY = "chat:nodes"             # ZSET: score=만료시각ms, member=node_id


# ─────────────────────────────────────────────────────────────
# 키 빌더 — DB 1 (dedupe 격리)
# ─────────────────────────────────────────────────────────────
def dedupe_key(user_id: str, client_msg_id: str) -> str:
    return f"dedupe:{user_id}:{client_msg_id}"
