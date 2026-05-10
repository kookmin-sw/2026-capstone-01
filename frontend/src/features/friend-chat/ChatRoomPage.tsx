import type { CSSProperties } from "react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { ChatMessage, ChatRoom } from "../../api/chat";
import { useChat } from "./ChatProvider";

const BOTTOM_THRESHOLD_PX = 160;
const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.svg";

export default function ChatRoomPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollModeRef = useRef<"bottom" | "preserve">("bottom");
  const shouldForceScrollToBottomRef = useRef(true);
  const scrollSnapshotRef = useRef<{ height: number; top: number } | null>(null);
  const {
    connectionState,
    currentUserId,
    messagesByRoom,
    roomPageStateByRoom,
    openDirectChat,
    ensureRoom,
    setActiveRoomId,
    loadInitialMessages,
    loadOlderMessages,
    sendMessage,
    sendRead,
  } = useChat();
  const [room, setRoom] = useState<ChatRoom | null>(null);
  const [input, setInput] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const roomId = room?.chat_room_id ?? "";
  const messages = useMemo(
    () => (roomId ? messagesByRoom[roomId] ?? [] : []),
    [messagesByRoom, roomId]
  );
  const roomPageState = roomId
    ? roomPageStateByRoom[roomId]
    : undefined;
  const roomName = useMemo(() => {
    if (!room) return "Chat";
    if (room.type === "direct") return room.peer?.user_name || "Deleted User";
    return room.title || "Group Chat";
  }, [room]);
  const roomProfileImageUrl =
    room?.type === "direct" ? room.peer?.profile_image_url || DEFAULT_PROFILE_IMAGE_URL : DEFAULT_PROFILE_IMAGE_URL;

  useEffect(() => {
    let cancelled = false;

    async function loadRoom(): Promise<void> {
      if (!id) return;

      try {
        const nextRoom = id.startsWith("USER_")
          ? await openDirectChat(id)
          : await ensureRoom(id);

        if (cancelled) return;

        setRoom(nextRoom);
        if (id !== nextRoom.chat_room_id) {
          navigate(`/chat/${nextRoom.chat_room_id}`, { replace: true });
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(toErrorMessage(error, "Failed to open chat room."));
        }
      }
    }

    void loadRoom();

    return () => {
      cancelled = true;
    };
  }, [ensureRoom, id, navigate, openDirectChat]);

  useEffect(() => {
    if (!roomId) return;

    shouldForceScrollToBottomRef.current = true;
    setActiveRoomId(roomId);
    void loadInitialMessages(roomId);

    return () => {
      setActiveRoomId("");
    };
  }, [loadInitialMessages, roomId, setActiveRoomId]);

  useEffect(() => {
    if (!roomId) return;

    const lastSeq = getLastServerSeq(messages);
    if (lastSeq > 0) {
      sendRead(roomId, lastSeq);
    }
  }, [messages, roomId, sendRead]);

  useLayoutEffect(() => {
    if (scrollModeRef.current === "preserve") {
      const snapshot = scrollSnapshotRef.current;
      scrollModeRef.current = "bottom";
      scrollSnapshotRef.current = null;

      if (snapshot) {
        const nextHeight = document.documentElement.scrollHeight;
        window.scrollTo({
          top: snapshot.top + nextHeight - snapshot.height,
          behavior: "auto",
        });
      }

      return;
    }

    const shouldForceScroll = shouldForceScrollToBottomRef.current;
    if (shouldForceScroll) {
      shouldForceScrollToBottomRef.current = false;
    }

    if (shouldForceScroll || isNearBottom()) {
      bottomRef.current?.scrollIntoView({
        behavior: shouldForceScroll ? "auto" : "smooth",
        block: "end",
      });

      if (shouldForceScroll) {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: "auto",
        });
      }
    }
  }, [messages]);

  async function handleLoadOlderMessages(): Promise<void> {
    if (!roomId) return;

    scrollModeRef.current = "preserve";
    scrollSnapshotRef.current = {
      height: document.documentElement.scrollHeight,
      top: window.scrollY,
    };
    await loadOlderMessages(roomId);
  }

  function handleSend(): void {
    const content = input.trim();
    if (!content || !roomId || content.length > 2000) return;

    sendMessage(roomId, content);
    setInput("");
  }

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <button type="button" style={styles.backButton} onClick={() => navigate("/chat")}>
          Back
        </button>
        <div style={styles.avatar}>
          <img src={roomProfileImageUrl} alt={roomName} style={styles.avatarImage} />
        </div>
        <span style={styles.headerText}>
          <strong style={styles.roomName}>{roomName}</strong>
          <span style={styles.connectionText}>{connectionState}</span>
        </span>
      </header>

      <main style={styles.messageList}>
        {errorMessage ? <div style={styles.error}>{errorMessage}</div> : null}
        {roomPageState?.isLoadingInitialMessages ? (
          <p style={styles.mutedText}>Loading messages...</p>
        ) : null}
        {roomPageState?.hasMoreOlderMessages ? (
          <button
            type="button"
            style={styles.loadOlderButton}
            onClick={() => void handleLoadOlderMessages()}
            disabled={roomPageState.isLoadingOlderMessages}
          >
            {roomPageState.isLoadingOlderMessages ? "Loading..." : "Load earlier messages"}
          </button>
        ) : null}
        {messages.map((message) => {
          const mine = Boolean(currentUserId && message.sender_id === currentUserId);
          return (
            <div
              key={message.client_msg_id || message.message_id}
              style={{
                ...styles.messageRow,
                ...(mine ? styles.messageRowMine : {}),
              }}
            >
              {!mine ? (
                <img
                  src={roomProfileImageUrl}
                  alt={roomName}
                  style={styles.messageAvatar}
                />
              ) : null}
              <div
                style={{
                  ...styles.bubble,
                  ...(mine ? styles.bubbleMine : {}),
                  ...(message.deleted_at ? styles.deletedBubble : {}),
                }}
              >
                {renderMessageContent(message)}
              </div>
              <span style={styles.time}>
                {formatTime(message.created_at)}
                {message.status === "sending" ? " - sending" : ""}
                {message.status === "failed" ? " - failed" : ""}
                {message.edited_at && !message.deleted_at ? " - edited" : ""}
              </span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </main>

      <footer style={styles.composer}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return;
            if (event.key === "Enter") handleSend();
          }}
          maxLength={2000}
          placeholder="Write a message"
          style={styles.input}
        />
        <button
          type="button"
          style={{
            ...styles.sendButton,
            ...(!input.trim() || connectionState === "closed" ? styles.sendButtonDisabled : {}),
          }}
          onClick={handleSend}
          disabled={!input.trim() || connectionState === "closed"}
        >
          {connectionState === "ready" ? "Send" : connectionState === "closed" ? "Offline" : "Queue"}
        </button>
      </footer>
    </div>
  );
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

function isNearBottom(): boolean {
  const distanceFromBottom =
    document.documentElement.scrollHeight - window.scrollY - window.innerHeight;
  return distanceFromBottom <= BOTTOM_THRESHOLD_PX;
}

function renderMessageContent(message: ChatMessage): string {
  if (message.deleted_at) return "Deleted message.";
  if (message.type === "system") return renderSystemMessage(message.content);
  if (typeof message.content === "string") return message.content;
  return "";
}

function renderSystemMessage(content: unknown): string {
  if (!content || typeof content !== "object") return "System message";

  const action = (content as { action?: string }).action;
  if (action === "created") return "Chat room created.";
  if (action === "join") return "Member joined.";
  if (action === "leave") return "Member left.";
  if (action === "kick") return "Member removed.";
  return "System message";
}

function formatTime(value: string): string {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as {
    response?: { data?: { detail?: string; message?: string } };
    message?: string;
  };
  return apiError.response?.data?.detail || apiError.response?.data?.message || apiError.message || fallback;
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    display: "flex",
    flexDirection: "column",
    background: "transparent",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  header: {
    position: "sticky",
    top: 0,
    zIndex: 5,
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "calc(14px + var(--app-safe-top)) 16px 14px",
    background: "rgba(255,255,255,0.94)",
    borderBottom: "1px solid var(--border-soft)",
    backdropFilter: "blur(14px)",
  },
  backButton: {
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 14,
    padding: "9px 12px",
    background: "#ffffff",
    color: "var(--text-secondary)",
    fontWeight: 800,
    cursor: "pointer",
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: "50%",
    overflow: "hidden",
    background: "var(--brand-primary-soft)",
    flexShrink: 0,
  },
  avatarImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  headerText: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  roomName: {
    color: "var(--text-primary)",
  },
  connectionText: {
    color: "var(--neutral-700)",
    fontSize: "0.72rem",
  },
  messageList: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: "18px 16px calc(110px + var(--app-safe-bottom))",
  },
  error: {
    padding: "12px 14px",
    borderRadius: 16,
    background: "rgba(220,38,38,0.1)",
    color: "#b91c1c",
    fontWeight: 800,
  },
  mutedText: {
    margin: 0,
    color: "var(--neutral-700)",
    lineHeight: 1.5,
  },
  loadOlderButton: {
    alignSelf: "center",
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 999,
    padding: "9px 14px",
    background: "rgba(255,255,255,0.9)",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
    cursor: "pointer",
  },
  messageRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
  },
  messageRowMine: {
    flexDirection: "row-reverse",
  },
  messageAvatar: {
    width: 30,
    height: 30,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
    boxShadow: "0 6px 14px rgba(24,26,32,0.08)",
  },
  bubble: {
    maxWidth: "min(72%, 420px)",
    padding: "11px 14px",
    borderRadius: "18px 18px 18px 6px",
    background: "#ffffff",
    color: "var(--text-secondary)",
    boxShadow: "var(--shadow-soft)",
    overflowWrap: "anywhere",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  bubbleMine: {
    borderRadius: "18px 18px 6px 18px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
  },
  deletedBubble: {
    opacity: 0.62,
    fontStyle: "italic",
  },
  time: {
    color: "var(--neutral-500)",
    fontSize: "0.72rem",
  },
  composer: {
    position: "fixed",
    left: "var(--app-safe-left)",
    right: "var(--app-safe-right)",
    bottom: 0,
    zIndex: 20,
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 10,
    padding: "12px 16px calc(12px + var(--app-safe-bottom))",
    background: "rgba(255,255,255,0.96)",
    borderTop: "1px solid var(--border-soft)",
  },
  input: {
    minHeight: 44,
    border: "1px solid rgba(5,181,187,0.16)",
    borderRadius: 999,
    padding: "0 16px",
    outline: "none",
    color: "var(--text-primary)",
  },
  sendButton: {
    border: "none",
    borderRadius: 999,
    padding: "0 18px",
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  sendButtonDisabled: {
    opacity: 0.5,
    cursor: "not-allowed",
  },
};
