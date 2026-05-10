import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getMyProfile } from "../../api/auth";
import { getFriendDetail } from "../../api/friend";
import {
  createDirectChatRoom,
  getChatMessages,
  getChatRoom,
  getChatRooms,
  getChatWebSocketUrl,
  type ChatMessage,
  type ChatRoom,
} from "../../api/chat";
import { reportChatNetworkError } from "../../utils/chatDiagnostics";

type ConnectionState = "connecting" | "ready" | "reconnecting" | "closed";

type ChatServerEvent =
  | { type: "connected"; session_id: string }
  | { type: "unread_synced"; counts: Record<string, number> }
  | {
      type: "message.sent";
      client_msg_id: string;
      message_id: string;
      server_seq: number;
      created_at: string;
    }
  | { type: "message.new"; sender_session_id: string; message: ChatMessage }
  | {
      type: "message.updated";
      sender_session_id: string;
      message_id: string;
      content: unknown;
      edited_at: string;
    }
  | {
      type: "message.deleted";
      sender_session_id: string;
      message_id: string;
      deleted_at: string;
    }
  | { type: "read"; user_id: string; up_to_server_seq: number; sender_session_id: string }
  | { type: "read_ack"; room_id: string; up_to_server_seq: number }
  | { type: "read_failed"; room_id: string; reason: string }
  | { type: "room_joined"; room_id: string }
  | { type: "room_left"; room_id: string }
  | { type: "session_revoked"; session_id: string }
  | { type: "auth_expired" }
  | { type: "server_error"; client_msg_id?: string | null; reason?: string | null }
  | { type: "server_restart" };

interface RoomPageState {
  hasMoreOlderMessages: boolean;
  olderMessageCursor: number | null;
  isLoadingInitialMessages: boolean;
  isLoadingOlderMessages: boolean;
}

interface ChatContextValue {
  rooms: ChatRoom[];
  roomsLoading: boolean;
  connectionState: ConnectionState;
  currentUserId: string | null;
  activeRoomId: string;
  messagesByRoom: Record<string, ChatMessage[]>;
  roomPageStateByRoom: Record<string, RoomPageState>;
  refreshRooms: () => Promise<void>;
  openDirectChat: (userId: string) => Promise<ChatRoom>;
  ensureRoom: (roomId: string) => Promise<ChatRoom>;
  setActiveRoomId: (roomId: string) => void;
  loadInitialMessages: (roomId: string) => Promise<void>;
  loadOlderMessages: (roomId: string) => Promise<void>;
  sendMessage: (roomId: string, content: string) => void;
  sendRead: (roomId: string, serverSeq: number) => void;
}

const INITIAL_BEFORE_SEQ = 999999999;
const RETRY_DELAY_MS = 5000;
const MAX_SEND_RETRY_COUNT = 3;
const DEFAULT_ROOM_PAGE_STATE: RoomPageState = {
  hasMoreOlderMessages: false,
  olderMessageCursor: null,
  isLoadingInitialMessages: false,
  isLoadingOlderMessages: false,
};

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const shouldConnectChatSocket =
    location.pathname !== "/" &&
    location.pathname !== "/login" &&
    location.pathname !== "/register";
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const sessionIdRef = useRef("");
  const shouldReconnectRef = useRef(false);
  const currentUserIdRef = useRef<string | null>(null);
  const activeRoomIdRef = useRef("");
  const roomsRef = useRef<ChatRoom[]>([]);
  const messagesByRoomRef = useRef<Record<string, ChatMessage[]>>({});
  const roomPageStateByRoomRef = useRef<Record<string, RoomPageState>>({});
  const handleSocketEventRef = useRef<(event: ChatServerEvent | null) => void>(() => {});
  const retryTimersRef = useRef<Record<string, number>>({});
  const pendingSendsRef = useRef<
    Record<string, { roomId: string; clientMsgId: string; content: string; attempts: number }>
  >({});
  const pendingReadRef = useRef<{ roomId: string; serverSeq: number } | null>(null);
  const inFlightReadRef = useRef<{ roomId: string; serverSeq: number } | null>(null);
  const lastReadSeqByRoomRef = useRef<Record<string, number>>({});
  const peerImageCacheRef = useRef<Record<string, string | null>>({});
  const [rooms, setRooms] = useState<ChatRoom[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("closed");
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [activeRoomId, setActiveRoomIdState] = useState("");
  const [messagesByRoom, setMessagesByRoom] = useState<Record<string, ChatMessage[]>>({});
  const [roomPageStateByRoom, setRoomPageStateByRoom] = useState<
    Record<string, RoomPageState>
  >({});

  useEffect(() => {
    messagesByRoomRef.current = messagesByRoom;
  }, [messagesByRoom]);

  useEffect(() => {
    currentUserIdRef.current = currentUserId;
  }, [currentUserId]);

  useEffect(() => {
    roomsRef.current = rooms;
  }, [rooms]);

  useEffect(() => {
    roomPageStateByRoomRef.current = roomPageStateByRoom;
  }, [roomPageStateByRoom]);

  const enrichRoomProfileImages = useCallback(
    async (roomsToEnrich: ChatRoom[]): Promise<ChatRoom[]> => {
      return Promise.all(
        roomsToEnrich.map(async (room) => {
          const peerId = room.type === "direct" ? room.peer?.user_id : null;
          if (!peerId || room.peer?.profile_image_url) {
            return room;
          }

          if (peerId in peerImageCacheRef.current) {
            return {
              ...room,
              peer: {
                ...room.peer,
                profile_image_url: peerImageCacheRef.current[peerId],
              },
            };
          }

          try {
            const detail = await getFriendDetail(peerId);
            peerImageCacheRef.current[peerId] = detail.profile_image_url ?? null;
            return {
              ...room,
              peer: {
                ...room.peer,
                profile_image_url: detail.profile_image_url ?? null,
              },
            };
          } catch {
            peerImageCacheRef.current[peerId] = null;
            return room;
          }
        })
      );
    },
    []
  );

  const refreshRooms = useCallback(async (): Promise<void> => {
    setRoomsLoading(true);
    try {
      const response = await getChatRooms();
      setRooms(await enrichRoomProfileImages(response.items));
    } finally {
      setRoomsLoading(false);
    }
  }, [enrichRoomProfileImages]);

  const sendSocketPayload = useCallback((payload: Record<string, unknown>): boolean => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    socket.send(JSON.stringify(payload));
    return true;
  }, []);

  const sendRead = useCallback(
    (roomId: string, serverSeq: number): void => {
      if (!roomId || serverSeq <= (lastReadSeqByRoomRef.current[roomId] ?? 0)) {
        return;
      }

      const payload = {
        op: "read",
        room_id: roomId,
        up_to_server_seq: serverSeq,
      };

      clearStoredChatUnreadCount(roomId);

      if (sendSocketPayload(payload)) {
        inFlightReadRef.current = { roomId, serverSeq };
      } else {
        pendingReadRef.current = { roomId, serverSeq };
      }
    },
    [sendSocketPayload]
  );

  const flushPendingRead = useCallback((): void => {
    const pendingRead = pendingReadRef.current;
    if (!pendingRead) return;

    const payload = {
      op: "read",
      room_id: pendingRead.roomId,
      up_to_server_seq: pendingRead.serverSeq,
    };

    if (sendSocketPayload(payload)) {
      pendingReadRef.current = null;
      inFlightReadRef.current = pendingRead;
    }
  }, [sendSocketPayload]);

  const setActiveRoomId = useCallback((roomId: string): void => {
    activeRoomIdRef.current = roomId;
    setActiveRoomIdState(roomId);

    if (roomId) {
      window.sessionStorage.setItem("krip-active-chat-room-id", roomId);
    } else {
      window.sessionStorage.removeItem("krip-active-chat-room-id");
    }
  }, []);

  const updateRoomLastMessage = useCallback((message: ChatMessage): void => {
    setRooms((current) =>
      moveRoomToTop(
        current.map((room) =>
          room.chat_room_id === message.chat_room_id
            ? {
                ...room,
                last_message: {
                  message_id: message.message_id,
                  server_seq: message.server_seq,
                  sender_id: message.sender_id,
                  type: message.type,
                  content: message.content,
                  created_at: message.created_at,
                },
                last_message_at: message.created_at,
                effective_last_at: message.created_at,
                unread_count:
                  message.type === "system" ||
                  message.sender_id === currentUserIdRef.current ||
                  activeRoomIdRef.current === message.chat_room_id
                    ? room.unread_count
                    : Math.min(999, room.unread_count + 1),
              }
            : room
        ),
        message.chat_room_id
      )
    );
  }, []);

  const mergeServerMessages = useCallback((roomId: string, serverMessages: ChatMessage[]): void => {
    if (serverMessages.length === 0) return;

    let replacedClientMsgIds: string[] = [];

    setMessagesByRoom((current) => {
      const previousMessages = current[roomId] ?? [];
      const nextMessages = appendMessagesDeduped(
        previousMessages,
        serverMessages,
        currentUserIdRef.current
      );

      replacedClientMsgIds = getReplacedClientMsgIds(previousMessages, nextMessages);

      return {
        ...current,
        [roomId]: nextMessages,
      };
    });

    replacedClientMsgIds.forEach((clientMsgId) => {
      clearRetryTimer(retryTimersRef.current, clientMsgId);
      delete pendingSendsRef.current[clientMsgId];
    });
  }, []);

  const catchUpActiveRoom = useCallback(async (): Promise<void> => {
    const roomId = activeRoomIdRef.current;
    if (!roomId) return;

    const lastSeq = getLastServerSeq(messagesByRoomRef.current[roomId] ?? []);
    if (lastSeq <= 0) return;

    try {
      const response = await getChatMessages({
        chatRoomId: roomId,
        afterServerSeq: lastSeq,
        limit: 200,
      });
      mergeServerMessages(roomId, response.messages);
    } catch {
      reportChatNetworkError({
        action: "catch_up_messages",
        roomId,
        detail: "Failed to catch up missed messages.",
      });
    }
  }, [mergeServerMessages]);

  const loadInitialMessages = useCallback(
    async (roomId: string): Promise<void> => {
      setRoomPageStateByRoom((current) => ({
        ...current,
        [roomId]: {
          ...(current[roomId] ?? DEFAULT_ROOM_PAGE_STATE),
          isLoadingInitialMessages: true,
        },
      }));

      try {
        const response = await getChatMessages({
          chatRoomId: roomId,
          beforeServerSeq: INITIAL_BEFORE_SEQ,
          limit: 50,
        });
        const nextMessages = [...response.messages].sort(sortByServerSeq);
        setMessagesByRoom((current) => ({ ...current, [roomId]: nextMessages }));
        setRoomPageStateByRoom((current) => ({
          ...current,
          [roomId]: {
            hasMoreOlderMessages: response.has_more,
            olderMessageCursor: response.next_cursor,
            isLoadingInitialMessages: false,
            isLoadingOlderMessages: false,
          },
        }));

        const lastSeq = getLastServerSeq(nextMessages);
        if (lastSeq > 0) sendRead(roomId, lastSeq);
      } catch (error) {
        setRoomPageStateByRoom((current) => ({
          ...current,
          [roomId]: {
            ...(current[roomId] ?? DEFAULT_ROOM_PAGE_STATE),
            isLoadingInitialMessages: false,
          },
        }));
        reportChatNetworkError({
          action: "load_messages",
          roomId,
          detail: toErrorMessage(error, "Failed to load messages."),
          extra: getErrorStatus(error),
        });
      }
    },
    [sendRead]
  );

  const loadOlderMessages = useCallback(
    async (roomId: string): Promise<void> => {
      const roomPageState =
        roomPageStateByRoomRef.current[roomId] ?? DEFAULT_ROOM_PAGE_STATE;
      if (
        !roomPageState.hasMoreOlderMessages ||
        roomPageState.olderMessageCursor === null ||
        roomPageState.isLoadingOlderMessages
      ) {
        return;
      }

      setRoomPageStateByRoom((current) => ({
        ...current,
        [roomId]: {
          ...(current[roomId] ?? DEFAULT_ROOM_PAGE_STATE),
          isLoadingOlderMessages: true,
        },
      }));

      try {
        const response = await getChatMessages({
          chatRoomId: roomId,
          beforeServerSeq: roomPageState.olderMessageCursor,
          limit: 50,
        });

        setMessagesByRoom((current) => ({
          ...current,
          [roomId]: appendMessagesDeduped(
            current[roomId] ?? [],
            response.messages,
            currentUserIdRef.current
          ),
        }));
        setRoomPageStateByRoom((current) => ({
          ...current,
          [roomId]: {
            hasMoreOlderMessages: response.has_more,
            olderMessageCursor: response.next_cursor,
            isLoadingInitialMessages: false,
            isLoadingOlderMessages: false,
          },
        }));
      } catch (error) {
        setRoomPageStateByRoom((current) => ({
          ...current,
          [roomId]: {
            ...(current[roomId] ?? DEFAULT_ROOM_PAGE_STATE),
            isLoadingOlderMessages: false,
          },
        }));
        reportChatNetworkError({
          action: "load_older_messages",
          roomId,
          detail: toErrorMessage(error, "Failed to load older messages."),
          extra: getErrorStatus(error),
        });
      }
    },
    []
  );

  const ensureRoom = useCallback(async (roomId: string): Promise<ChatRoom> => {
    const existingRoom = roomsRef.current.find((room) => room.chat_room_id === roomId);
    if (existingRoom) return existingRoom;

    const [room] = await enrichRoomProfileImages([await getChatRoom(roomId)]);
    setRooms((current) => moveRoomToTop(upsertRoom(current, room), room.chat_room_id));
    return room;
  }, [enrichRoomProfileImages]);

  const openDirectChat = useCallback(async (userId: string): Promise<ChatRoom> => {
    const [room] = await enrichRoomProfileImages([await createDirectChatRoom(userId)]);
    setRooms((current) => moveRoomToTop(upsertRoom(current, room), room.chat_room_id));
    return room;
  }, [enrichRoomProfileImages]);

  const sendMessagePayload = useCallback(
    (clientMsgId: string): void => {
      if (retryTimersRef.current[clientMsgId]) return;

      const pendingSend = pendingSendsRef.current[clientMsgId];
      if (!pendingSend) return;

      if (pendingSend.attempts >= MAX_SEND_RETRY_COUNT) {
        markMessageFailed(clientMsgId);
        return;
      }

      const payload = {
        op: "send",
        room_id: pendingSend.roomId,
        client_msg_id: clientMsgId,
        type: "text",
        content: pendingSend.content,
      };

      if (!sendSocketPayload(payload)) return;

      pendingSendsRef.current[clientMsgId] = {
        ...pendingSend,
        attempts: pendingSend.attempts + 1,
      };
      retryTimersRef.current[clientMsgId] = window.setTimeout(() => {
        delete retryTimersRef.current[clientMsgId];
        sendMessagePayload(clientMsgId);
      }, RETRY_DELAY_MS);
    },
    [sendSocketPayload]
  );

  const flushPendingSends = useCallback((): void => {
    Object.keys(pendingSendsRef.current).forEach(sendMessagePayload);
  }, [sendMessagePayload]);

  const sendMessage = useCallback(
    (roomId: string, content: string): void => {
      const trimmedContent = content.trim();
      if (!roomId || !trimmedContent || trimmedContent.length > 2000) return;

      const clientMsgId = crypto.randomUUID();
      const optimisticMessage: ChatMessage = {
        message_id: clientMsgId,
        chat_room_id: roomId,
        server_seq: Number.MAX_SAFE_INTEGER,
        sender_id: currentUserIdRef.current,
        type: "text",
        content: trimmedContent,
        created_at: new Date().toISOString(),
        edited_at: null,
        deleted_at: null,
        client_msg_id: clientMsgId,
        status: "sending",
      };

      setMessagesByRoom((current) => ({
        ...current,
        [roomId]: [...(current[roomId] ?? []), optimisticMessage],
      }));
      pendingSendsRef.current[clientMsgId] = {
        roomId,
        clientMsgId,
        content: trimmedContent,
        attempts: 0,
      };
      sendMessagePayload(clientMsgId);
    },
    [sendMessagePayload]
  );

  function markMessageFailed(clientMsgId: string): void {
    setMessagesByRoom((current) => mapMessagesByRoom(current, (message) =>
      message.client_msg_id === clientMsgId
        ? { ...message, status: "failed" as const }
        : message
    ));
    clearRetryTimer(retryTimersRef.current, clientMsgId);
    delete pendingSendsRef.current[clientMsgId];
  }

  function clearPendingSendsForRoom(roomId: string): void {
    Object.entries(pendingSendsRef.current).forEach(([clientMsgId, pendingSend]) => {
      if (pendingSend.roomId !== roomId) return;

      clearRetryTimer(retryTimersRef.current, clientMsgId);
      delete pendingSendsRef.current[clientMsgId];
    });
  }

  function clearAllPendingSends(): void {
    Object.keys(pendingSendsRef.current).forEach((clientMsgId) => {
      clearRetryTimer(retryTimersRef.current, clientMsgId);
      delete pendingSendsRef.current[clientMsgId];
    });
  }

  const markSendingMessagesFailed = useCallback((reason: string, clientMsgId?: string): void => {
    if (clientMsgId) {
      markMessageFailed(clientMsgId);
      return;
    }

    const failedClientMsgIds: string[] = [];
    const shouldFailAll = isPermanentSendFailure(reason);

    setMessagesByRoom((current) => {
      if (shouldFailAll) {
        return mapMessagesByRoom(current, (message) => {
          if (message.status === "sending" && message.client_msg_id) {
            failedClientMsgIds.push(message.client_msg_id);
            return { ...message, status: "failed" as const };
          }

          return message;
        });
      }

      const activeMessages = current[activeRoomIdRef.current] ?? [];
      const latestSendingMessage = [...activeMessages]
        .reverse()
        .find((message) => message.status === "sending" && message.client_msg_id);

      if (!latestSendingMessage?.client_msg_id) return current;

      failedClientMsgIds.push(latestSendingMessage.client_msg_id);

      return {
        ...current,
        [activeRoomIdRef.current]: activeMessages.map((message) =>
          message.client_msg_id === latestSendingMessage.client_msg_id
            ? { ...message, status: "failed" as const }
            : message
        ),
      };
    });

    failedClientMsgIds.forEach((id) => {
      clearRetryTimer(retryTimersRef.current, id);
      delete pendingSendsRef.current[id];
    });
  }, []);

  const loadJoinedRoom = useCallback(
    async (roomId: string): Promise<void> => {
      try {
        const [room] = await enrichRoomProfileImages([await getChatRoom(roomId)]);
        setRooms((current) => moveRoomToTop(upsertRoom(current, room), room.chat_room_id));
      } catch {
        reportChatNetworkError({
          action: "load_joined_room",
          roomId,
          detail: "Failed to fetch joined room; refreshing chat room list.",
        });
        void refreshRooms();
      }
    },
    [enrichRoomProfileImages, refreshRooms]
  );

  const confirmOptimisticMessage = useCallback(
    (event: Extract<ChatServerEvent, { type: "message.sent" }>): void => {
      const pendingSend = pendingSendsRef.current[event.client_msg_id];
      const optimisticMessage = Object.values(messagesByRoomRef.current)
        .flat()
        .find((message) => message.client_msg_id === event.client_msg_id);
      const confirmedMessage = optimisticMessage
        ? {
            ...optimisticMessage,
            message_id: event.message_id,
            server_seq: event.server_seq,
            created_at: event.created_at,
            status: "sent" as const,
          }
        : null;

      clearRetryTimer(retryTimersRef.current, event.client_msg_id);
      delete pendingSendsRef.current[event.client_msg_id];

      setMessagesByRoom((current) =>
        mapMessagesByRoom(current, (message) =>
          message.client_msg_id === event.client_msg_id && confirmedMessage
            ? confirmedMessage
            : message
        )
      );

      if (confirmedMessage) {
        updateRoomLastMessage(confirmedMessage);
        sendRead(confirmedMessage.chat_room_id, event.server_seq);
      } else if (pendingSend?.roomId) {
        void loadJoinedRoom(pendingSend.roomId);
      } else {
        void refreshRooms();
      }
    },
    [loadJoinedRoom, refreshRooms, sendRead, updateRoomLastMessage]
  );

  const handleSocketEvent = useCallback(
    (event: ChatServerEvent | null): void => {
      if (!event) return;

      switch (event.type) {
        case "connected":
          sessionIdRef.current = event.session_id;
          setConnectionState("ready");
          flushPendingRead();
          flushPendingSends();
          void catchUpActiveRoom();
          return;
        case "unread_synced":
          setRooms((current) =>
            current.map((room) => ({
              ...room,
              unread_count: event.counts[room.chat_room_id] ?? 0,
            }))
          );
          return;
        case "message.sent":
          confirmOptimisticMessage(event);
          return;
        case "message.new":
          mergeServerMessages(event.message.chat_room_id, [event.message]);
          updateRoomLastMessage(event.message);
          if (event.message.sender_id !== currentUserIdRef.current) {
            if (event.message.chat_room_id !== activeRoomIdRef.current) {
              incrementStoredChatUnreadCount(event.message.chat_room_id);
              dispatchChatToast(
                event.message,
                getRoomTitle(roomsRef.current, event.message.chat_room_id),
                getRoomProfileImageUrl(roomsRef.current, event.message.chat_room_id)
              );
            }
          }
          if (event.message.chat_room_id === activeRoomIdRef.current) {
            sendRead(event.message.chat_room_id, event.message.server_seq);
          }
          return;
        case "message.updated":
          setMessagesByRoom((current) => mapMessagesByRoom(current, (message) =>
            message.message_id === event.message_id
              ? { ...message, content: event.content, edited_at: event.edited_at }
              : message
          ));
          setRooms((current) =>
            current.map((room) =>
              room.last_message?.message_id === event.message_id
                ? { ...room, last_message: { ...room.last_message, content: event.content } }
                : room
            )
          );
          return;
        case "message.deleted":
          setMessagesByRoom((current) => mapMessagesByRoom(current, (message) =>
            message.message_id === event.message_id
              ? { ...message, content: null, deleted_at: event.deleted_at }
              : message
          ));
          setRooms((current) =>
            current.map((room) =>
              room.last_message?.message_id === event.message_id
                ? { ...room, last_message: { ...room.last_message, content: null } }
                : room
            )
          );
          return;
        case "read":
          return;
        case "read_ack":
          lastReadSeqByRoomRef.current[event.room_id] = Math.max(
            lastReadSeqByRoomRef.current[event.room_id] ?? 0,
            event.up_to_server_seq
          );
          inFlightReadRef.current = null;
          setRooms((current) =>
            current.map((room) =>
              room.chat_room_id === event.room_id ? { ...room, unread_count: 0 } : room
            )
          );
          return;
        case "read_failed":
          reportChatNetworkError({
            action: "read_failed",
            roomId: event.room_id,
            detail: event.reason,
          });
          if (shouldRetryRead(event.reason) && inFlightReadRef.current?.roomId === event.room_id) {
            pendingReadRef.current = inFlightReadRef.current;
            window.setTimeout(flushPendingRead, 1000);
          }
          inFlightReadRef.current = null;
          return;
        case "room_joined":
          void loadJoinedRoom(event.room_id);
          return;
        case "room_left":
          setRooms((current) => current.filter((room) => room.chat_room_id !== event.room_id));
          setMessagesByRoom((current) => omitRecordKey(current, event.room_id));
          setRoomPageStateByRoom((current) => omitRecordKey(current, event.room_id));
          clearPendingSendsForRoom(event.room_id);
          delete lastReadSeqByRoomRef.current[event.room_id];
          if (event.room_id === activeRoomIdRef.current) {
            setActiveRoomId("");
            navigate("/chat", { replace: true });
          }
          return;
        case "session_revoked":
          if (event.session_id === sessionIdRef.current) {
            shouldReconnectRef.current = false;
            navigate("/login", { replace: true });
          }
          return;
        case "auth_expired":
          shouldReconnectRef.current = false;
          navigate("/login", { replace: true });
          return;
        case "server_error":
          markSendingMessagesFailed(event.reason || "", event.client_msg_id || undefined);
          reportChatNetworkError({
            action: "server_error",
            roomId: activeRoomIdRef.current,
            detail: event.reason || "Chat server error.",
          });
          return;
        case "server_restart":
          setConnectionState("reconnecting");
          return;
        default:
          return;
      }
    },
    [
      catchUpActiveRoom,
      confirmOptimisticMessage,
      flushPendingRead,
      flushPendingSends,
      markSendingMessagesFailed,
      mergeServerMessages,
      loadJoinedRoom,
      navigate,
      sendRead,
      updateRoomLastMessage,
    ]
  );

  useEffect(() => {
    handleSocketEventRef.current = handleSocketEvent;
  }, [handleSocketEvent]);

  useEffect(() => {
    if (!shouldConnectChatSocket) {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      socketRef.current?.close(1000);
      socketRef.current = null;
      clearAllPendingSends();
      setConnectionState("closed");
      return;
    }

    let cancelled = false;
    shouldReconnectRef.current = true;

    void getMyProfile()
      .then((profile) => {
        if (!cancelled) setCurrentUserId(profile?.user_id ?? null);
      })
      .catch(() => {
        if (!cancelled) setCurrentUserId(null);
      });
    void refreshRooms();

    function scheduleReconnect(): void {
      const base = Math.min(60000, 1000 * 2 ** reconnectAttemptRef.current);
      const jitter = Math.random() * 500;

      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      reconnectTimerRef.current = window.setTimeout(connect, base + jitter);
      reconnectAttemptRef.current += 1;
    }

    function connect(): void {
      setConnectionState(reconnectAttemptRef.current > 0 ? "reconnecting" : "connecting");
      const ws = new WebSocket(getChatWebSocketUrl());
      socketRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
      };

      ws.onmessage = (socketEvent) => {
        handleSocketEventRef.current(parseSocketEvent(socketEvent.data));
      };

      ws.onerror = () => {
        reportChatNetworkError({
          action: "websocket_error",
          detail: "WebSocket connection failed.",
          extra: getChatWebSocketUrl(),
        });
      };

      ws.onclose = (socketEvent) => {
        if (socketRef.current === ws) socketRef.current = null;

        if (!shouldReconnectRef.current || socketEvent.code === 1000) {
          setConnectionState("closed");
          return;
        }

        if (socketEvent.code === 4001 || socketEvent.code === 4403) {
          shouldReconnectRef.current = false;
          setConnectionState("closed");
          navigate("/login", { replace: true });
          return;
        }

        setConnectionState("reconnecting");
        reportChatNetworkError({
          action: "websocket_close",
          detail: `WebSocket closed with code ${socketEvent.code}`,
          extra: socketEvent.reason,
        });
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      cancelled = true;
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const socket = socketRef.current;
      if (socket) {
        if (socket.readyState === WebSocket.CONNECTING) {
          socket.onopen = () => socket.close(1000);
          socket.onmessage = null;
          socket.onclose = null;
        } else {
          socket.close(1000);
        }
      }
      socketRef.current = null;
    };
  }, [navigate, refreshRooms, shouldConnectChatSocket]);

  useEffect(() => {
    return () => {
      Object.values(retryTimersRef.current).forEach((timerId) => {
        window.clearTimeout(timerId);
      });
      retryTimersRef.current = {};
    };
  }, []);

  const value = useMemo<ChatContextValue>(
    () => ({
      rooms,
      roomsLoading,
      connectionState,
      currentUserId,
      activeRoomId,
      messagesByRoom,
      roomPageStateByRoom,
      refreshRooms,
      openDirectChat,
      ensureRoom,
      setActiveRoomId,
      loadInitialMessages,
      loadOlderMessages,
      sendMessage,
      sendRead,
    }),
    [
      activeRoomId,
      connectionState,
      currentUserId,
      ensureRoom,
      loadInitialMessages,
      loadOlderMessages,
      messagesByRoom,
      openDirectChat,
      refreshRooms,
      roomPageStateByRoom,
      rooms,
      roomsLoading,
      sendMessage,
      sendRead,
      setActiveRoomId,
    ]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChat(): ChatContextValue {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChat must be used within ChatProvider.");
  }

  return context;
}

function parseSocketEvent(data: unknown): ChatServerEvent | null {
  if (typeof data !== "string") return null;

  try {
    return JSON.parse(data) as ChatServerEvent;
  } catch {
    return null;
  }
}

function appendMessagesDeduped(
  messages: ChatMessage[],
  incomingMessages: ChatMessage[],
  currentUserId: string | null
): ChatMessage[] {
  const nextMessages = [...messages];

  incomingMessages.forEach((incomingMessage) => {
    const existingIndex = findExistingServerMessageIndex(nextMessages, incomingMessage);

    if (existingIndex >= 0) {
      nextMessages[existingIndex] = {
        ...nextMessages[existingIndex],
        ...incomingMessage,
      };
      return;
    }

    const optimisticIndex = findMatchingOptimisticMessageIndex(
      nextMessages,
      incomingMessage,
      currentUserId
    );

    if (optimisticIndex >= 0) {
      nextMessages[optimisticIndex] = {
        ...incomingMessage,
        status: "sent",
      };
      return;
    }

    nextMessages.push(incomingMessage);
  });

  return nextMessages.sort(sortByServerSeq);
}

function findExistingServerMessageIndex(
  messages: ChatMessage[],
  incomingMessage: ChatMessage
): number {
  if (incomingMessage.server_seq !== Number.MAX_SAFE_INTEGER) {
    const serverSeqIndex = messages.findIndex(
      (message) => message.server_seq === incomingMessage.server_seq
    );

    if (serverSeqIndex >= 0) {
      return serverSeqIndex;
    }
  }

  return messages.findIndex(
    (message) => message.message_id === incomingMessage.message_id
  );
}

function findMatchingOptimisticMessageIndex(
  messages: ChatMessage[],
  serverMessage: ChatMessage,
  currentUserId: string | null
): number {
  if (!currentUserId || serverMessage.sender_id !== currentUserId) {
    return -1;
  }

  return messages.findIndex((message) => {
    if (!message.client_msg_id || message.status !== "sending") return false;
    if (message.chat_room_id !== serverMessage.chat_room_id) return false;
    if (message.sender_id !== serverMessage.sender_id) return false;
    if (message.type !== serverMessage.type) return false;

    return message.content === serverMessage.content;
  });
}

function getReplacedClientMsgIds(
  previousMessages: ChatMessage[],
  nextMessages: ChatMessage[]
): string[] {
  const nextIds = new Set(nextMessages.map((message) => message.message_id));

  return previousMessages
    .filter((message) => message.client_msg_id && !nextIds.has(message.message_id))
    .map((message) => message.client_msg_id as string);
}

function sortByServerSeq(a: ChatMessage, b: ChatMessage): number {
  return a.server_seq - b.server_seq;
}

function dispatchChatToast(
  message: ChatMessage,
  roomTitle: string,
  imageUrl?: string | null
): void {
  window.dispatchEvent(
    new CustomEvent("krip:chat-message-toast", {
      detail: {
        roomId: message.chat_room_id,
        title: roomTitle || "New message",
        body: formatChatToastBody(message),
        imageUrl,
      },
    })
  );
}

function incrementStoredChatUnreadCount(roomId: string): void {
  const storageKey = "krip-chat-unread-by-room";
  let unreadByRoom: Record<string, number> = {};

  try {
    const raw = window.localStorage.getItem(storageKey);
    const parsed = raw ? (JSON.parse(raw) as unknown) : {};
    if (parsed && typeof parsed === "object") {
      unreadByRoom = parsed as Record<string, number>;
    }
  } catch {
    unreadByRoom = {};
  }

  unreadByRoom[roomId] = Math.max(0, Number(unreadByRoom[roomId] || 0)) + 1;
  window.localStorage.setItem(storageKey, JSON.stringify(unreadByRoom));
  window.dispatchEvent(new Event("krip:friend-chat-notifications-updated"));
}

function clearStoredChatUnreadCount(roomId: string): void {
  const storageKey = "krip-chat-unread-by-room";

  try {
    const raw = window.localStorage.getItem(storageKey);
    const parsed = raw ? (JSON.parse(raw) as unknown) : {};
    if (!parsed || typeof parsed !== "object") return;

    const unreadByRoom = parsed as Record<string, number>;
    if (!(roomId in unreadByRoom)) return;

    delete unreadByRoom[roomId];
    window.localStorage.setItem(storageKey, JSON.stringify(unreadByRoom));
    window.dispatchEvent(new Event("krip:friend-chat-notifications-updated"));
  } catch {
    window.localStorage.removeItem(storageKey);
    window.dispatchEvent(new Event("krip:friend-chat-notifications-updated"));
  }
}

function getRoomTitle(rooms: ChatRoom[], roomId: string): string {
  const room = rooms.find((item) => item.chat_room_id === roomId);
  return room?.title || room?.peer?.user_name || "New message";
}

function getRoomProfileImageUrl(rooms: ChatRoom[], roomId: string): string | null {
  const room = rooms.find((item) => item.chat_room_id === roomId);
  return room?.type === "direct" ? room.peer?.profile_image_url ?? null : null;
}

function formatChatToastBody(message: ChatMessage): string {
  if (message.deleted_at) return "Deleted message";
  if (message.type === "image") return "Sent an image";
  if (message.type === "file") return "Sent a file";
  if (message.type === "system") return "System message";

  if (typeof message.content === "string") {
    return message.content;
  }

  if (message.content && typeof message.content === "object") {
    const value = message.content as Record<string, unknown>;
    if (typeof value.text === "string") return value.text;
    if (typeof value.message === "string") return value.message;
  }

  return "New message";
}

function getLastServerSeq(messages: ChatMessage[]): number {
  return messages.reduce(
    (maxSeq, message) =>
      message.server_seq === Number.MAX_SAFE_INTEGER
        ? maxSeq
        : Math.max(maxSeq, message.server_seq),
    0
  );
}

function upsertRoom(rooms: ChatRoom[], room: ChatRoom): ChatRoom[] {
  const exists = rooms.some((item) => item.chat_room_id === room.chat_room_id);
  if (!exists) return [room, ...rooms];

  return rooms.map((item) =>
    item.chat_room_id === room.chat_room_id ? room : item
  );
}

function moveRoomToTop(rooms: ChatRoom[], roomId: string): ChatRoom[] {
  const room = rooms.find((item) => item.chat_room_id === roomId);
  if (!room) return rooms;

  return [
    room,
    ...rooms.filter((item) => item.chat_room_id !== roomId),
  ];
}

function mapMessagesByRoom(
  messagesByRoom: Record<string, ChatMessage[]>,
  mapper: (message: ChatMessage) => ChatMessage
): Record<string, ChatMessage[]> {
  return Object.fromEntries(
    Object.entries(messagesByRoom).map(([roomId, messages]) => [
      roomId,
      messages.map(mapper).sort(sortByServerSeq),
    ])
  );
}

function omitRecordKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  const { [key]: _omitted, ...rest } = record;
  return rest;
}

function clearRetryTimer(
  retryTimers: Record<string, number>,
  clientMsgId: string
): void {
  const timerId = retryTimers[clientMsgId];
  if (!timerId) return;

  window.clearTimeout(timerId);
  delete retryTimers[clientMsgId];
}

function isPermanentSendFailure(reason: string): boolean {
  const normalizedReason = reason.toLowerCase();

  return (
    normalizedReason.includes("차단") ||
    normalizedReason.includes("block") ||
    normalizedReason.includes("멤버") ||
    normalizedReason.includes("member") ||
    normalizedReason.includes("존재하지") ||
    normalizedReason.includes("not found")
  );
}

function shouldRetryRead(reason: string): boolean {
  return !isPermanentSendFailure(reason);
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as {
    response?: { data?: { detail?: string; message?: string } };
    message?: string;
  };
  return apiError.response?.data?.detail || apiError.response?.data?.message || apiError.message || fallback;
}

function getErrorStatus(error: unknown): number | undefined {
  const apiError = error as { response?: { status?: number } };
  return apiError.response?.status;
}
