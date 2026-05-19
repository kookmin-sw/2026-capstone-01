from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, case, or_
from datetime import datetime

from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.chat.model.chat_room import ChatRoom, ChatRoomType


# 방 리스트 페이지 크기 (폭주 방어용 상한, 정식 페이지네이션 도입 전)
PAGE_SIZE = 500


class ChatRoomRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, chat_room: ChatRoom) -> ChatRoom:
        """채팅방 insert.

        1:1 방은 UNIQUE(direct_user_a_id, direct_user_b_id) 제약이 있어 동시 생성 race 는
        `IntegrityError` 로 올라간다. 호출측(Service)에서 SAVEPOINT + catch 후 기존 방
        재조회로 idempotent 처리 — friend 도메인의 `send_request` 패턴과 동일.
        """
        self.session.add(chat_room)
        await self.session.flush()
        return chat_room


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, chat_room_id: str) -> Optional[ChatRoom]:
        """chat_room_id 로 단건 조회"""
        return await self.session.get(ChatRoom, chat_room_id)


    async def find_direct_by_pair(
        self,
        user_a_id: str,
        user_b_id: str,
    ) -> Optional[ChatRoom]:
        """canonical 정렬된 1:1 방 조회 (없으면 None).

        호출측이 먼저 `user_a_id < user_b_id` 로 정렬해서 넘겨야 한다 (CheckConstraint
        에 맞춤). 탈퇴로 한 쪽이 NULL 인 방은 이 조회에 매칭되지 않으므로 자동으로
        "새 방 생성 대상" 취급된다 — 의도된 동작 (탈퇴자와 연결된 방과 격리).
        """
        stmt = select(ChatRoom).where(
            ChatRoom.type == ChatRoomType.DIRECT,
            ChatRoom.direct_user_a_id == user_a_id,
            ChatRoom.direct_user_b_id == user_b_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    # ──────────────────── Read (목록) ────────────────────

    async def find_rooms_of_user(
        self,
        user_id: str,
        limit: int = PAGE_SIZE,
    ) -> list[tuple[ChatRoom, Optional[str], Optional[bool]]]:
        """유저가 속한 활성 방 목록을 effective_last_at DESC 로 정렬.

        반환값은 `(ChatRoom, peer_user_id, notification_muted)` 튜플 — 이미 JOIN 한
        `chat_room_member.notification_muted` 를 함께 SELECT 해 N+1 없이 mute 상태까지
        한 번에 가져온다. 1:1 방은 상대방 user_id 를 함께 계산 (그룹방은 None).

        LIMIT `PAGE_SIZE` 의 단일 페이지 500개.
        커서 페이지네이션은 정식 출시 시 도입 예정 — 그때 PAGE_SIZE 도 30으로 환원.
        """
        # 1:1 방의 상대방 user_id 파생 (내가 a 면 b, 내가 b 면 a, 그룹이면 None)
        peer_user_id = case(
            (
                ChatRoom.type == ChatRoomType.DIRECT,
                case(
                    (ChatRoom.direct_user_a_id == user_id, ChatRoom.direct_user_b_id),
                    else_=ChatRoom.direct_user_a_id,
                ),
            ),
            else_=None,
        ).label("peer_user_id")

        stmt = (
            select(ChatRoom, peer_user_id, ChatRoomMember.notification_muted)
            .join(ChatRoomMember, ChatRoomMember.chat_room_id == ChatRoom.chat_room_id)
            .where(
                ChatRoomMember.user_id == user_id,
                ChatRoomMember.is_left.is_(False),
            )
            .order_by(ChatRoom.effective_last_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]


    # ──────────────────── Update ────────────────────

    async def update_last_message(
        self,
        chat_room_id: str,
        message_id: str,
        server_seq: int,
        at: datetime,
    ) -> None:
        """방의 최신 메시지 역정규화 필드 갱신

        실패하더라도 메시지 자체는 이미 MongoDB 에 저장됐으므로 서비스 가용성에 치명적이지
        않다 — Service 에서 이 호출이 실패하면 `dirty:chat_room` Redis SET 에 방 ID 를
        적재하고 reconcile job 이 최종 정합성 복구.
        """
        # synchronize_session=False — bulk UPDATE 후 메모리의 ChatRoom 인스턴스를
        # expire 시키지 않아 뒤따르는 `_to_dto` 접근에서 GENERATED 컬럼 lazy load 가
        # 발생하지 않도록 한다 (async session 에서 lazy load → MissingGreenlet).
        stmt = (
            update(ChatRoom)
            .where(ChatRoom.chat_room_id == chat_room_id)
            .values(
                last_message_id=message_id,
                last_message_server_seq=server_seq,
                last_message_at=at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)


    async def update_last_message_if_greater(
        self,
        chat_room_id: str,
        message_id: str,
        server_seq: int,
        at: datetime,
    ) -> None:
        """reconcile job 전용 — `:server_seq` 가 기존보다 클 때만 UPDATE.

        `update_last_message` 는 송신 경로(이미 최신 seq 를 알고 있음)라 단순 덮어쓰기지만,
        reconcile 은 **송신과 병렬로 돌 수 있어** regress 위험이 있다. 예:

            [T0] reconcile 이 방 R 을 SPOP, Mongo 조회해 seq=100 찾음
            [T1] 같은 방에 새 메시지 도착 → last_message_server_seq=101 로 갱신됨
            [T2] reconcile 이 UPDATE 실행 — 단순 덮어쓰기면 100 으로 후퇴!

        `WHERE` 절에 GREATEST 가드를 박아 **기존 값 ≥ new 면 no-op** 으로 처리.
        NULL 컬럼(한 번도 메시지 없던 방이 dirty 로 들어온 이상 시나리오) 도 커버.
        """
        stmt = (
            update(ChatRoom)
            .where(
                ChatRoom.chat_room_id == chat_room_id,
                or_(
                    ChatRoom.last_message_server_seq.is_(None),
                    ChatRoom.last_message_server_seq < server_seq,
                ),
            )
            .values(
                last_message_id=message_id,
                last_message_server_seq=server_seq,
                last_message_at=at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)
