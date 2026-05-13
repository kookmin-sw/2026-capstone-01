import type { CSSProperties } from "react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  getChatRoomMembers,
  getInvitableChatRoomFriends,
  inviteChatRoomMembers,
  leaveChatRoom,
  type ChatMessage,
  type ChatRoom,
  type ChatUserProfile,
} from "../../api/chat";
import ConfirmToast from "../../components/ConfirmToast";
import FeedPopup from "../../components/FeedPopup";
import { useChat } from "./ChatProvider";

const BOTTOM_THRESHOLD_PX = 160;
const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

export default function ChatRoomPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const messageListRef = useRef<HTMLElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollModeRef = useRef<"bottom" | "preserve">("bottom");
  const shouldForceScrollToBottomRef = useRef(true);
  const scrollSnapshotRef = useRef<{ height: number; top: number } | null>(null);
  const latestMessageKeyRef = useRef("");
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
  const [members, setMembers] = useState<ChatUserProfile[]>([]);
  const [invitableFriends, setInvitableFriends] = useState<ChatUserProfile[]>([]);
  const [selectedInviteIds, setSelectedInviteIds] = useState<string[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [feedPopupUserId, setFeedPopupUserId] = useState<string | null>(null);
  const [isLeaveConfirmOpen, setIsLeaveConfirmOpen] = useState(false);
  const [incomingMessageNotice, setIncomingMessageNotice] =
    useState<ChatMessage | null>(null);

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
  const roomProfileUserId = room?.type === "direct" ? room.peer?.user_id || "" : "";
  const memberProfilesById = useMemo(() => {
    const profiles = new Map<string, ChatUserProfile>();
    members.forEach((member) => profiles.set(member.user_id, member));
    return profiles;
  }, [members]);
  const memberSummary =
    room?.type === "group"
      ? members.length > 0
        ? `${members.length} members`
        : membersLoading
          ? "Loading members"
          : "Group chat"
      : connectionState;

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
    latestMessageKeyRef.current = "";
    setIncomingMessageNotice(null);
    consumeRecentMessageScrollRequest(roomId);
    setActiveRoomId(roomId);
    void loadInitialMessages(roomId);

    return () => {
      setActiveRoomId("");
    };
  }, [loadInitialMessages, roomId, setActiveRoomId]);

  useEffect(() => {
    const routeState = location.state as { scrollToRecentMessage?: boolean } | null;
    if (!roomId || !routeState?.scrollToRecentMessage) return;

    shouldForceScrollToBottomRef.current = true;
    scrollMessageListToBottom(messageListRef.current, "smooth");
  }, [location.state, roomId]);

  useEffect(() => {
    let cancelled = false;

    async function loadMembers(): Promise<void> {
      if (!roomId || !room) {
        setMembers([]);
        return;
      }

      if (room.type === "direct") {
        setMembers(room.peer ? [room.peer] : []);
        return;
      }

      setMembersLoading(true);
      try {
        const response = await getChatRoomMembers(roomId);
        if (!cancelled) {
          setMembers(response.items);
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(toErrorMessage(error, "Failed to load members."));
        }
      } finally {
        if (!cancelled) {
          setMembersLoading(false);
        }
      }
    }

    void loadMembers();

    return () => {
      cancelled = true;
    };
  }, [room, roomId]);

  useEffect(() => {
    if (!roomId) return;

    const lastSeq = getLastServerSeq(messages);
    if (lastSeq > 0) {
      sendRead(roomId, lastSeq);
    }
  }, [messages, roomId, sendRead]);

  useEffect(() => {
    const messageList = messageListRef.current;
    if (!messageList) return undefined;

    function clearIncomingNoticeAtBottom(): void {
      if (isMessageListNearBottom(messageList)) {
        setIncomingMessageNotice(null);
      }
    }

    messageList.addEventListener("scroll", clearIncomingNoticeAtBottom, {
      passive: true,
    });

    return () => {
      messageList.removeEventListener("scroll", clearIncomingNoticeAtBottom);
    };
  }, [roomId]);

  useLayoutEffect(() => {
    const messageList = messageListRef.current;
    if (!messageList) return;

    if (scrollModeRef.current === "preserve") {
      const snapshot = scrollSnapshotRef.current;
      scrollModeRef.current = "bottom";
      scrollSnapshotRef.current = null;

      if (snapshot) {
        const nextHeight = messageList.scrollHeight;
        messageList.scrollTop = snapshot.top + nextHeight - snapshot.height;
      }

      return;
    }

    const latestMessage = messages.at(-1);
    const latestMessageKey = latestMessage ? getMessageKey(latestMessage) : "";
    const previousLatestMessageKey = latestMessageKeyRef.current;
    const hasNewLatestMessage =
      Boolean(latestMessageKey) && latestMessageKey !== previousLatestMessageKey;
    const isInitialMessageRender = !previousLatestMessageKey;

    if (latestMessageKey) {
      latestMessageKeyRef.current = latestMessageKey;
    }

    const shouldForceScroll = shouldForceScrollToBottomRef.current;
    if (shouldForceScroll) {
      shouldForceScrollToBottomRef.current = false;
    }

    if (
      hasNewLatestMessage &&
      !isInitialMessageRender &&
      latestMessage &&
      latestMessage.sender_id !== currentUserId
    ) {
      if (isMessageListNearBottom(messageList)) {
        setIncomingMessageNotice(null);
        scrollMessageListToBottom(messageList, "smooth");
      } else {
        setIncomingMessageNotice(latestMessage);
      }

      return;
    }

    if (shouldForceScroll || isMessageListNearBottom(messageList)) {
      setIncomingMessageNotice(null);
      scrollMessageListToBottom(messageList, shouldForceScroll ? "auto" : "smooth");
    }
  }, [currentUserId, messages]);

  async function handleLoadOlderMessages(): Promise<void> {
    if (!roomId) return;

    scrollModeRef.current = "preserve";
    const messageList = messageListRef.current;
    scrollSnapshotRef.current = {
      height: messageList?.scrollHeight ?? 0,
      top: messageList?.scrollTop ?? 0,
    };
    await loadOlderMessages(roomId);
  }

  function handleSend(): void {
    const content = input.trim();
    if (!content || !roomId || content.length > 2000) return;

    shouldForceScrollToBottomRef.current = true;
    setIncomingMessageNotice(null);
    sendMessage(roomId, content);
    setInput("");
  }

  async function openInvitePanel(): Promise<void> {
    if (!roomId || room?.type !== "group") return;

    setInviteOpen(true);
    setInviteLoading(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      const response = await getInvitableChatRoomFriends(roomId);
      setInvitableFriends(response.items);
      setSelectedInviteIds([]);
    } catch (error) {
      setErrorMessage(toErrorMessage(error, "Failed to load invitable friends."));
    } finally {
      setInviteLoading(false);
    }
  }

  function toggleInviteSelection(userId: string): void {
    setSelectedInviteIds((current) =>
      current.includes(userId)
        ? current.filter((item) => item !== userId)
        : [...current, userId]
    );
  }

  async function handleInviteMembers(): Promise<void> {
    if (!roomId || selectedInviteIds.length === 0) return;

    setInviteLoading(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      const result = await inviteChatRoomMembers(roomId, selectedInviteIds);
      setActionMessage(`${result.invited_user_ids.length} friend(s) invited.`);
      setInvitableFriends((current) =>
        current.filter((friend) => !result.invited_user_ids.includes(friend.user_id))
      );
      setSelectedInviteIds([]);
      const response = await getChatRoomMembers(roomId);
      setMembers(response.items);
    } catch (error) {
      setErrorMessage(toErrorMessage(error, "Failed to invite friends."));
    } finally {
      setInviteLoading(false);
    }
  }

  async function handleLeaveGroup(): Promise<void> {
    if (!roomId || room?.type !== "group") return;

    setInviteLoading(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      await leaveChatRoom(roomId);
      navigate("/mate", { state: { mainTab: "chat" } });
    } catch (error) {
      setErrorMessage(toErrorMessage(error, "Failed to leave group."));
    } finally {
      setInviteLoading(false);
      setIsLeaveConfirmOpen(false);
    }
  }

  function getMessageAvatarUrl(message: ChatMessage): string {
    if (room?.type !== "group" || !message.sender_id) return roomProfileImageUrl;
    return memberProfilesById.get(message.sender_id)?.profile_image_url || DEFAULT_PROFILE_IMAGE_URL;
  }

  function getMessageSenderName(message: ChatMessage): string {
    if (room?.type !== "group" || !message.sender_id) return roomName;
    return memberProfilesById.get(message.sender_id)?.user_name || roomName;
  }

  function openFeedPopup(userId?: string | null): void {
    if (userId) {
      setFeedPopupUserId(userId);
    }
  }

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <button
          type="button"
          style={styles.backButton}
          onClick={() => navigate("/mate", { state: { mainTab: "chat" } })}
        >
          Back
        </button>
        <button
          type="button"
          style={{
            ...styles.avatar,
            ...styles.avatarButton,
            ...(!roomProfileUserId ? styles.disabledAvatarButton : {}),
          }}
          onClick={() => openFeedPopup(roomProfileUserId)}
          disabled={!roomProfileUserId}
          aria-label={`${roomName} feed`}
        >
          <img src={roomProfileImageUrl} alt={roomName} style={styles.avatarImage} />
        </button>
        <span style={styles.headerText}>
          <strong style={styles.roomName}>{roomName}</strong>
          <span style={styles.connectionText}>{memberSummary}</span>
        </span>
        <button
          type="button"
          style={styles.infoButton}
          onClick={() => setInfoOpen(true)}
          aria-label="Open chat info"
        >
          <img src="/icon-menu.svg" alt="" style={styles.infoIcon} />
        </button>
      </header>

      <main ref={messageListRef} style={styles.messageList}>
        {errorMessage ? <div style={styles.error}>{errorMessage}</div> : null}
        {actionMessage ? <div style={styles.notice}>{actionMessage}</div> : null}
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
          if (isRoomNoticeMessage(message)) {
            return (
              <div
                key={message.client_msg_id || message.message_id}
                style={styles.roomNoticeRow}
              >
                <span style={styles.roomNoticeText}>
                  {renderMessageContent(message)}
                </span>
              </div>
            );
          }

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
                <button
                  type="button"
                  style={styles.messageAvatarButton}
                  onClick={() => openFeedPopup(message.sender_id)}
                  disabled={!message.sender_id}
                  aria-label={`${getMessageSenderName(message)} feed`}
                >
                  <img
                    src={getMessageAvatarUrl(message)}
                    alt={getMessageSenderName(message)}
                    style={styles.messageAvatar}
                  />
                </button>
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

      {incomingMessageNotice ? (
        <button
          type="button"
          style={styles.incomingNotice}
          onClick={() => {
            setIncomingMessageNotice(null);
            scrollMessageListToBottom(messageListRef.current, "smooth");
          }}
        >
          <span style={styles.incomingNoticeSender}>
            {getMessageSenderName(incomingMessageNotice)}
          </span>
          <span style={styles.incomingNoticeText}>
            {renderMessagePreview(incomingMessageNotice)}
          </span>
        </button>
      ) : null}

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

      {infoOpen ? (
        <div style={styles.infoBackdrop} onClick={() => setInfoOpen(false)}>
          <aside style={styles.infoPanel} onClick={(event) => event.stopPropagation()}>
            <div style={styles.infoHeader}>
              <div>
                <p style={styles.infoEyebrow}>Chat Info</p>
                <h2 style={styles.infoTitle}>{roomName}</h2>
              </div>
              <button
                type="button"
                style={styles.infoCloseButton}
                onClick={() => setInfoOpen(false)}
                aria-label="Close chat info"
              >
                <img src="/icon-close.svg" alt="" style={styles.infoCloseIcon} />
              </button>
            </div>

            <section style={styles.infoSection}>
              <div style={styles.infoSectionHeader}>
                <h3 style={styles.infoSectionTitle}>Members</h3>
                {room?.type === "group" ? (
                  <span style={styles.infoCount}>{members.length}</span>
                ) : null}
              </div>
              {membersLoading && members.length === 0 ? (
                <p style={styles.mutedText}>Loading members...</p>
              ) : members.length > 0 ? (
                <div style={styles.memberList}>
                  {members.map((member) => (
                    <button
                      key={member.user_id}
                      type="button"
                      style={styles.memberRow}
                      onClick={() => openFeedPopup(member.user_id)}
                    >
                      <img
                        src={member.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                        alt={member.user_name}
                        style={styles.memberAvatarLarge}
                      />
                      <span style={styles.rowMain}>
                        <strong style={styles.memberRowName}>{member.user_name}</strong>
                        <span style={styles.userId}>{member.user_id}</span>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <p style={styles.mutedText}>No members found.</p>
              )}
            </section>

            {room?.type === "group" ? (
              <>
                <div style={styles.infoActions}>
                  <button
                    type="button"
                    style={styles.infoPrimaryButton}
                    onClick={() => void openInvitePanel()}
                  >
                    Invite
                  </button>
                  <button
                    type="button"
                    style={styles.infoDangerButton}
                    onClick={() => setIsLeaveConfirmOpen(true)}
                    disabled={inviteLoading}
                  >
                    {inviteLoading ? "Leaving..." : "Leave"}
                  </button>
                </div>

                {inviteOpen ? (
                  <section style={styles.invitePanel}>
                    <div style={styles.invitePanelHeader}>
                      <strong style={styles.inviteTitle}>Invite Friends</strong>
                      <button
                        type="button"
                        style={styles.closeButton}
                        onClick={() => setInviteOpen(false)}
                      >
                        Close
                      </button>
                    </div>
                    {inviteLoading && invitableFriends.length === 0 ? (
                      <p style={styles.mutedText}>Loading friends...</p>
                    ) : invitableFriends.length > 0 ? (
                      <div style={styles.inviteList}>
                        {invitableFriends.map((friend) => {
                          const checked = selectedInviteIds.includes(friend.user_id);
                          return (
                            <label key={friend.user_id} style={styles.inviteFriend}>
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleInviteSelection(friend.user_id)}
                              />
                              <img
                                src={friend.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                                alt={friend.user_name}
                                style={styles.memberAvatar}
                              />
                              <span style={styles.rowMain}>
                                <strong style={styles.inviteFriendName}>{friend.user_name}</strong>
                                <span style={styles.userId}>{friend.user_id}</span>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    ) : (
                      <p style={styles.mutedText}>No friends available to invite.</p>
                    )}
                    <button
                      type="button"
                      style={{
                        ...styles.inviteSubmitButton,
                        ...(selectedInviteIds.length === 0 || inviteLoading
                          ? styles.sendButtonDisabled
                          : {}),
                      }}
                      onClick={() => void handleInviteMembers()}
                      disabled={selectedInviteIds.length === 0 || inviteLoading}
                    >
                      {inviteLoading ? "Inviting..." : `Invite ${selectedInviteIds.length || ""}`.trim()}
                    </button>
                  </section>
                ) : null}
              </>
            ) : null}
          </aside>
        </div>
      ) : null}

      {feedPopupUserId ? (
        <FeedPopup
          userId={feedPopupUserId}
          side="left"
          onClose={() => setFeedPopupUserId(null)}
        />
      ) : null}

      {isLeaveConfirmOpen ? (
        <ConfirmToast
          title="Leave this group chat?"
          message="You will stop receiving messages from this group."
          confirmLabel="Leave"
          destructive
          busy={inviteLoading}
          onConfirm={() => void handleLeaveGroup()}
          onCancel={() => setIsLeaveConfirmOpen(false)}
        />
      ) : null}
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

function isMessageListNearBottom(messageList: HTMLElement): boolean {
  const distanceFromBottom =
    messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight;
  return distanceFromBottom <= BOTTOM_THRESHOLD_PX;
}

/**
 * 메시지 목록에서 안정적으로 비교할 수 있는 키를 만든다.
 */
function getMessageKey(message: ChatMessage): string {
  return message.message_id || message.client_msg_id || `${message.server_seq}`;
}

/**
 * 알림에서 채팅방으로 들어온 요청을 소비한다.
 */
function consumeRecentMessageScrollRequest(roomId: string): void {
  const requestedRoomId: string | null =
    window.sessionStorage.getItem("krip:chat-scroll-room");
  if (requestedRoomId === roomId) {
    window.sessionStorage.removeItem("krip:chat-scroll-room");
  }
}

/**
 * 채팅 알림 진입 시 문서 맨 아래의 최신 메시지 위치로 이동한다.
 */
function scrollMessageListToBottom(
  messageList: HTMLElement | null,
  behavior: ScrollBehavior
): void {
  if (!messageList) return;

  window.requestAnimationFrame(() => {
    messageList.scrollTo({
      top: messageList.scrollHeight,
      behavior,
    });
  });
}

function renderMessagePreview(message: ChatMessage): string {
  const content = renderMessageContent(message).trim();
  if (!content) return "New message";
  return content.length > 80 ? `${content.slice(0, 80)}...` : content;
}

function renderMessageContent(message: ChatMessage): string {
  if (message.deleted_at) return "Message was deleted.";
  if (message.type === "system") return renderSystemMessage(message.content);
  if (typeof message.content === "string") return message.content;
  return "";
}

function isRoomNoticeMessage(message: ChatMessage): boolean {
  return Boolean(message.deleted_at) || message.type === "system";
}

function renderSystemMessage(content: unknown): string {
  if (!content || typeof content !== "object") return "System message";

  const action = (content as { action?: string }).action;
  if (action === "created") return "Chat room was created.";
  if (action === "join") return "A member joined the chat.";
  if (action === "leave") return "A member left the chat.";
  if (action === "kick") return "A member was removed from the chat.";
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
    height: "var(--app-viewport-height)",
    display: "flex",
    flexDirection: "column",
    background: "transparent",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
    overflow: "hidden",
  },
  header: {
    zIndex: 5,
    flexShrink: 0,
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
  avatarButton: {
    border: "none",
    padding: 0,
    cursor: "pointer",
  },
  disabledAvatarButton: {
    cursor: "default",
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
    flex: 1,
  },
  roomName: {
    color: "var(--text-primary)",
  },
  connectionText: {
    color: "var(--neutral-700)",
    fontSize: "0.72rem",
  },
  infoButton: {
    width: 40,
    height: 40,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "#ffffff",
    cursor: "pointer",
    flexShrink: 0,
  },
  infoIcon: {
    width: 22,
    height: 22,
    objectFit: "contain",
  },
  inviteButton: {
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 14,
    padding: "9px 12px",
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  memberStrip: {
    zIndex: 4,
    flexShrink: 0,
    display: "flex",
    gap: 8,
    overflowX: "auto",
    padding: "10px 16px",
    background: "rgba(255,255,255,0.88)",
    borderBottom: "1px solid var(--border-soft)",
  },
  memberPill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 7,
    flexShrink: 0,
    maxWidth: 180,
    padding: "6px 10px 6px 6px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.95)",
    border: "1px solid rgba(5,181,187,0.14)",
  },
  memberPillButton: {
    cursor: "pointer",
    font: "inherit",
  },
  memberAvatar: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  memberName: {
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "var(--text-secondary)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  messageList: {
    flex: 1,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    gap: 12,
    overflowY: "auto",
    overscrollBehavior: "contain",
    padding: "16px 16px 16px",
  },
  error: {
    padding: "12px 14px",
    borderRadius: 16,
    background: "rgba(220,38,38,0.1)",
    color: "#b91c1c",
    fontWeight: 800,
  },
  notice: {
    padding: "12px 14px",
    borderRadius: 16,
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
  },
  invitePanel: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 14,
    borderRadius: 18,
    background: "rgba(255,255,255,0.94)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  invitePanelHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  inviteTitle: {
    color: "var(--text-primary)",
  },
  closeButton: {
    border: "none",
    background: "transparent",
    color: "var(--brand-primary-deep)",
    fontWeight: 900,
    cursor: "pointer",
  },
  inviteList: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    maxHeight: 260,
    overflowY: "auto",
  },
  inviteFriend: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: 10,
    borderRadius: 14,
    background: "rgba(255,255,255,0.86)",
    border: "1px solid rgba(5,181,187,0.12)",
    cursor: "pointer",
  },
  inviteFriendName: {
    color: "var(--text-primary)",
    fontSize: "0.9rem",
  },
  rowMain: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 3,
    flex: 1,
  },
  userId: {
    color: "var(--neutral-500)",
    fontSize: "0.7rem",
    overflowWrap: "anywhere",
  },
  inviteSubmitButton: {
    alignSelf: "flex-end",
    border: "none",
    borderRadius: 999,
    minHeight: 40,
    padding: "0 16px",
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
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
  roomNoticeRow: {
    alignSelf: "center",
    maxWidth: "86%",
    padding: "4px 10px",
    textAlign: "center",
  },
  roomNoticeText: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 800,
    lineHeight: 1.45,
  },
  messageAvatar: {
    width: 30,
    height: 30,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
    boxShadow: "0 6px 14px rgba(24,26,32,0.08)",
  },
  messageAvatarButton: {
    width: 30,
    height: 30,
    border: "none",
    borderRadius: "50%",
    padding: 0,
    background: "transparent",
    cursor: "pointer",
    flexShrink: 0,
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
    zIndex: 20,
    flexShrink: 0,
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 10,
    padding: "12px 16px calc(12px + var(--app-safe-bottom))",
    background: "rgba(255,255,255,0.96)",
    borderTop: "1px solid var(--border-soft)",
  },
  incomingNotice: {
    position: "fixed",
    left: "50%",
    bottom: "calc(76px + var(--app-safe-bottom))",
    zIndex: 21,
    transform: "translateX(-50%)",
    width: "min(328px, calc(100% - 32px))",
    minHeight: 48,
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 16,
    background: "rgba(255,255,255,0.82)",
    boxShadow: "0 12px 32px rgba(24,26,32,0.18)",
    backdropFilter: "blur(14px)",
    color: "var(--text-primary)",
    cursor: "pointer",
    textAlign: "left",
  },
  incomingNoticeSender: {
    maxWidth: 92,
    flexShrink: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 900,
  },
  incomingNoticeText: {
    minWidth: 0,
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "var(--text-secondary)",
    fontSize: "0.82rem",
    fontWeight: 800,
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
  infoBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 80,
    display: "flex",
    justifyContent: "flex-end",
    background: "rgba(24,26,32,0.28)",
  },
  infoPanel: {
    width: "min(390px, 92vw)",
    height: "var(--app-viewport-height)",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    overflowY: "auto",
    padding: "calc(20px + var(--app-safe-top)) 16px calc(20px + var(--app-safe-bottom))",
    background: "#ffffff",
    boxShadow: "-24px 0 54px rgba(24,26,32,0.18)",
  },
  infoHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  infoEyebrow: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.72rem",
    fontWeight: 900,
    textTransform: "uppercase",
  },
  infoTitle: {
    margin: "4px 0 0",
    color: "var(--text-primary)",
    fontSize: "1.25rem",
    lineHeight: 1.2,
  },
  infoCloseButton: {
    width: 38,
    height: 38,
    border: "none",
    borderRadius: "50%",
    background: "var(--surface-muted)",
    cursor: "pointer",
  },
  infoCloseIcon: {
    width: 18,
    height: 18,
    objectFit: "contain",
  },
  infoSection: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  infoSectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  infoSectionTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "0.98rem",
  },
  infoCount: {
    minWidth: 24,
    height: 24,
    display: "grid",
    placeItems: "center",
    borderRadius: 999,
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.75rem",
    fontWeight: 900,
  },
  memberList: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  memberRow: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: 10,
    border: "1px solid var(--border-soft)",
    borderRadius: 16,
    background: "#ffffff",
    textAlign: "left",
    cursor: "pointer",
  },
  memberAvatarLarge: {
    width: 40,
    height: 40,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  memberRowName: {
    color: "var(--text-primary)",
    fontSize: "0.9rem",
  },
  infoActions: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 8,
  },
  infoPrimaryButton: {
    minHeight: 44,
    border: "none",
    borderRadius: 14,
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  infoDangerButton: {
    minHeight: 44,
    border: "1px solid rgba(220,38,38,0.18)",
    borderRadius: 14,
    background: "rgba(220,38,38,0.08)",
    color: "#b91c1c",
    fontWeight: 900,
    cursor: "pointer",
  },
};
