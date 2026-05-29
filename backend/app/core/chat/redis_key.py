"""채팅 도메인 Redis 키 / TTL 상수.

키 문자열을 코드 전체에 흩뿌리지 않기 위한 모듈 — 네이밍 실수로 키 공간이 어긋나는 사고 방지.
"""

# ─────────────────────────────────────────────────────────────
# TTL (seconds)
# ─────────────────────────────────────────────────────────────
SESSION_TTL = 90            # sess / ws_route / sessions ZSET 갱신 주기와 동일
ROOM_MEMBERS_TTL = 600      # RDB fallback 전제 — 짧아도 안전
ROOM_BLOCKS_TTL = 600       # friend hook 미호출 시 stale 상한
RATE_LIMIT_TTL = 1          # 1초 윈도우
DEDUPE_TTL = 600            # 클라 재전송 최대 갭보다 충분히 길게
NODE_TTL = 90               # chat:nodes ZSET — SESSION_TTL 과 동일 주기로 갱신

# ─────────────────────────────────────────────────────────────
# 임계값
# ─────────────────────────────────────────────────────────────
RATE_LIMIT_THRESHOLD = 10   # 초당 메시지 상한
MAX_SESSIONS_PER_USER = 10  # 유저당 동시 세션 상한

# force_jump 와 recover 의 base gap — 같게 맞춰 간섭 최소화.
SEQ_FORCE_JUMP_GAP = 1000
SEQ_FORCE_JUMP_JITTER_MAX = 10000
SEQ_RECOVER_GAP = 1000


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
    """노드별 Pub/Sub 채널 — `FANOUT_MODE=node_channel` 에서 각 노드가 자기 채널만 구독.

    publisher 는 broadcast 시 활성 노드 전체에 PUBLISH, 세션 직송은 `ws_route:{sid}` 로
    타깃 노드에만.
    """
    return f"node:{node_id}"


DIRTY_CHAT_ROOM_KEY = "dirty:chat_room"   # reconcile worker 가 소비하는 SET
NODES_ZSET_KEY = "chat:nodes"             # ZSET: score=만료시각ms, member=node_id


# ─────────────────────────────────────────────────────────────
# 키 빌더 — DB 1 (dedupe 격리)
# ─────────────────────────────────────────────────────────────
def dedupe_key(user_id: str, client_msg_id: str) -> str:
    return f"dedupe:{user_id}:{client_msg_id}"
