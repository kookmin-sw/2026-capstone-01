import type { CSSProperties } from "react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  createDirectChatRoom,
  getChatRoomMembers,
  getInvitableChatRoomFriends,
  inviteChatRoomMembers,
  leaveChatRoom,
  type ChatMessage,
  type ChatPeer,
  type ChatRoom,
  type ChatUserProfile,
} from "../../api/chat";
import { getMyProfile } from "../../api/auth/auth";
import { getFriendDetail } from "../../api/friend";
import ConfirmToast from "../../components/ConfirmToast";
import { useChat } from "./ChatProvider";

const BOTTOM_THRESHOLD_PX = 160;
const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

export default function ChatRoomPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const messageListRef = useRef<HTMLElement>(null);
  const composerInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollModeRef = useRef<"bottom" | "preserve">("bottom");
  const pendingNewRoomSendRef = useRef<string | null>(null);
  const recentComposerSendRef = useRef<{ key: string; expiresAt: number } | null>(null);
  const shouldForceScrollToBottomRef = useRef(true);
  const scrollSnapshotRef = useRef<{ height: number; top: number } | null>(null);
  const latestMessageKeyRef = useRef("");
  const {
    rooms,
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
  // Draft state: set when the user opens a 1:1 chat to a peer with no existing room yet.
  // The actual room is created on the backend only when the first message is sent.
  const [draftDirectUserId, setDraftDirectUserId] = useState<string | null>(null);
  const [draftPeer, setDraftPeer] = useState<ChatPeer | null>(null);
  const [input, setInput] = useState("");
  const [isCreatingDirectRoom, setIsCreatingDirectRoom] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [members, setMembers] = useState<ChatUserProfile[]>([]);
  const [invitableFriends, setInvitableFriends] = useState<ChatUserProfile[]>([]);
  const [selectedInviteIds, setSelectedInviteIds] = useState<string[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [isLeaveConfirmOpen, setIsLeaveConfirmOpen] = useState(false);
  const [isInviteConfirmOpen, setIsInviteConfirmOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [messageSearchQuery, setMessageSearchQuery] = useState("");
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
    if (room?.type === "direct") return room.peer?.user_name || "Deleted User";
    if (room?.type === "group") return room.title || "Group Chat";
    if (draftPeer) return draftPeer.user_name || "Chat";
    return "Chat";
  }, [room, draftPeer]);
  const roomProfileImageUrl =
    room?.type === "direct"
      ? room.peer?.profile_image_url || DEFAULT_PROFILE_IMAGE_URL
      : draftPeer
      ? draftPeer.profile_image_url || DEFAULT_PROFILE_IMAGE_URL
      : DEFAULT_PROFILE_IMAGE_URL;
  const roomProfileUserId =
    room?.type === "direct"
      ? room.peer?.user_id || ""
      : draftPeer
      ? draftPeer.user_id || ""
      : "";
  const memberProfilesById = useMemo(() => {
    const profiles = new Map<string, ChatUserProfile>();
    members.forEach((member) => profiles.set(member.user_id, member));
    return profiles;
  }, [members]);
  const messageSearchResultCount = useMemo(() => {
    const query = messageSearchQuery.trim().toLowerCase();
    if (!query) return 0;

    return messages.filter((message) =>
      renderMessageContent(message).toLowerCase().includes(query)
    ).length;
  }, [messageSearchQuery, messages]);

  useEffect(() => {
    function handleAndroidBack(event: Event): void {
      if (isLeaveConfirmOpen) {
        event.preventDefault();
        setIsLeaveConfirmOpen(false);
        return;
      }
      if (isInviteConfirmOpen) {
        event.preventDefault();
        setIsInviteConfirmOpen(false);
        return;
      }
      if (inviteOpen) {
        event.preventDefault();
        setInviteOpen(false);
        return;
      }
      if (infoOpen) {
        event.preventDefault();
        setInfoOpen(false);
        return;
      }
      if (isSearchOpen) {
        event.preventDefault();
        setIsSearchOpen(false);
      }
    }

    window.addEventListener("krip:android-back", handleAndroidBack);

    return () => {
      window.removeEventListener("krip:android-back", handleAndroidBack);
    };
  }, [
    infoOpen,
    inviteOpen,
    isInviteConfirmOpen,
    isLeaveConfirmOpen,
    isSearchOpen,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function loadRoom(): Promise<void> {
      if (!id) return;

      if (id.startsWith("USER_")) {
        // Check if a real direct room already exists with this peer
        const existingRoom = openDirectChat(id);
        if (cancelled) return;

        if (existingRoom) {
          setRoom(existingRoom);
          setDraftDirectUserId(null);
          setDraftPeer(null);
          navigate(`/chat/${existingRoom.chat_room_id}`, { replace: true });
        } else {
          // No room yet — enter draft mode.
          // The actual room is created on the backend when the first message is sent.
          setRoom(null);
          setDraftDirectUserId(id);
          try {
            const detail = await getFriendDetail(id);
            if (!cancelled) {
              setDraftPeer({
                user_id: detail.user_id,
                user_name: detail.user_name,
                profile_image_url: detail.profile_image_url,
              });
            }
          } catch {
            if (!cancelled) {
              setDraftPeer({ user_id: id, user_name: null, profile_image_url: null });
            }
          }
        }
        return;
      }

      // Real room ID — fetch or find from cache
      try {
        const nextRoom = await ensureRoom(id);
        if (cancelled) return;
        setRoom(nextRoom);
        setDraftDirectUserId(null);
        setDraftPeer(null);
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

  // When rooms list updates while in draft mode, check if the room was created elsewhere
  // (e.g., the peer sent the first message) and transition to the real room if found.
  useEffect(() => {
    if (!draftDirectUserId) return;
    const existingRoom = openDirectChat(draftDirectUserId);
    if (existingRoom) {
      setRoom(existingRoom);
      setDraftDirectUserId(null);
      setDraftPeer(null);
      navigate(`/chat/${existingRoom.chat_room_id}`, { replace: true });
    }
  }, [rooms, draftDirectUserId, openDirectChat, navigate]);

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
      if (!room) {
        // Draft mode: show the peer and self without any room API call
        if (draftPeer?.user_id) {
          const peerMember: ChatUserProfile = {
            user_id: draftPeer.user_id,
            user_name: draftPeer.user_name || "",
            profile_image_url: draftPeer.profile_image_url,
          };
          if (!cancelled) setMembers([peerMember]);
          setMembersLoading(true);
          try {
            const myProfile = await getMyProfile();
            if (!cancelled && myProfile) {
              const selfMember: ChatUserProfile = {
                user_id: myProfile.user_id || currentUserId || "",
                user_name: myProfile.user_name || "Me",
                profile_image_url:
                  myProfile.profile_image_url ||
                  myProfile.profileImageUrl ||
                  myProfile.image_url ||
                  myProfile.imageUrl ||
                  DEFAULT_PROFILE_IMAGE_URL,
              };
              setMembers([peerMember, selfMember]);
            }
          } catch {
            // Non-fatal: peer is already shown
          } finally {
            if (!cancelled) setMembersLoading(false);
          }
        } else {
          if (!cancelled) setMembers([]);
        }
        return;
      }

      if (!roomId) {
        setMembers([]);
        return;
      }

      if (room.type === "direct") {
        // Direct chat: the members API (/api/chat/rooms/{id}/members) only supports
        // group rooms and returns 400 for direct chats. Build the list manually instead.
        const peerMembers: ChatUserProfile[] = room.peer ? [room.peer] : [];
        // Show peer immediately while we fetch the current user's own profile
        if (!cancelled) setMembers(peerMembers);

        setMembersLoading(true);
        try {
          const myProfile = await getMyProfile();
          if (!cancelled && myProfile) {
            const selfMember: ChatUserProfile = {
              user_id: myProfile.user_id || currentUserId || "",
              user_name: myProfile.user_name || "Me",
              profile_image_url:
                myProfile.profile_image_url ||
                myProfile.profileImageUrl ||
                myProfile.image_url ||
                myProfile.imageUrl ||
                DEFAULT_PROFILE_IMAGE_URL,
            };
            setMembers([...peerMembers, selfMember]);
          }
        } catch {
          // Non-fatal: peer is already shown
        } finally {
          if (!cancelled) setMembersLoading(false);
        }
        return;
      }

      // Group chat: populate from cached data first, then refresh via API
      if (room.members && room.members.length > 0) {
        setMembers(room.members);
      }

      setMembersLoading(true);
      try {
        const response = await getChatRoomMembers(roomId);
        if (!cancelled) {
          setMembers(response.items);
        }
      } catch (error) {
        if (!cancelled) {
          // Non-fatal: cached data above is already shown
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
  }, [room, roomId, draftPeer, currentUserId]);

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

    const latestMessage = messages[messages.length - 1];
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
    if (!content || content.length > 2000) return;
    const targetRoomId =
      roomId || (!draftDirectUserId && id && !id.startsWith("USER_") ? id : "");

    // Draft mode: create the room on the backend first, then send
    if (draftDirectUserId) {
      if (isDuplicateComposerSend(`draft:${draftDirectUserId}:${content}`)) return;
      void handleSendToNewRoom(draftDirectUserId, content);
      return;
    }

    if (!targetRoomId) return;
    if (isDuplicateComposerSend(`room:${targetRoomId}:${content}`)) return;

    shouldForceScrollToBottomRef.current = true;
    setIncomingMessageNotice(null);
    sendMessage(targetRoomId, content);
    setInput("");
    window.requestAnimationFrame(() => composerInputRef.current?.focus());
  }

  function isDuplicateComposerSend(key: string): boolean {
    const now = Date.now();
    const recent = recentComposerSendRef.current;
    if (recent?.key === key && recent.expiresAt > now) return true;

    recentComposerSendRef.current = { key, expiresAt: now + 300 };
    return false;
  }

  async function handleSendToNewRoom(userId: string, content: string): Promise<void> {
    if (pendingNewRoomSendRef.current === userId) return;

    pendingNewRoomSendRef.current = userId;
    setIsCreatingDirectRoom(true);
    try {
      // TODO: backend must enforce direct-room uniqueness and reuse existing rooms.
      const newRoom = await createDirectChatRoom(userId);
      if (!newRoom?.chat_room_id) {
        throw new Error("Failed to open chat room.");
      }
      setDraftDirectUserId(null);
      setDraftPeer(null);
      setInput("");
      shouldForceScrollToBottomRef.current = true;
      setIncomingMessageNotice(null);
      // Send the message using the now-real room ID, then navigate there
      sendMessage(newRoom.chat_room_id, content);
      navigate(`/chat/${newRoom.chat_room_id}`, { replace: true });
    } catch (error) {
      setErrorMessage(toErrorMessage(error, "Failed to create chat room."));
    } finally {
      pendingNewRoomSendRef.current = null;
      setIsCreatingDirectRoom(false);
    }
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

    setLeaveLoading(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      await leaveChatRoom(roomId);
      navigate("/mate", { state: { mainTab: "chat" } });
    } catch (error) {
      setErrorMessage(toErrorMessage(error, "Failed to leave group."));
    } finally {
      setLeaveLoading(false);
      setIsLeaveConfirmOpen(false);
    }
  }

  function getMessageAvatarUrl(message: ChatMessage): string {
    if (room?.type !== "group" || !message.sender_id) return roomProfileImageUrl;
    return memberProfilesById.get(message.sender_id)?.profile_image_url || DEFAULT_PROFILE_IMAGE_URL;
  }

  function getMessageSenderName(message: ChatMessage): string {
    if (room?.type === "direct") return room.peer?.user_name || "Unknown User";
    if (!message.sender_id) return "Unknown User";
    return memberProfilesById.get(message.sender_id)?.user_name || "Unknown User";
  }

  function openFeedPopup(userId?: string | null): void {
    if (userId) {
      setInfoOpen(false);
      navigate(`/profile/${userId}`);
    }
  }

  return (
    <div
      style={{
        ...styles.page,
        ...(room?.type === "group" ? styles.groupPage : {}),
      }}
    >
      <header style={styles.header}>
        <button
          type="button"
          style={styles.backButton}
          onClick={() => navigate("/mate", { state: { mainTab: "chat" } })}
          aria-label="Back"
        >
          <BackIcon />
        </button>
        <span style={styles.headerText}>
          <button
            type="button"
            style={{
              ...styles.roomNameButton,
              ...(!roomProfileUserId ? styles.disabledRoomNameButton : {}),
            }}
            onClick={() => openFeedPopup(roomProfileUserId)}
            disabled={!roomProfileUserId}
          >
            <strong style={styles.roomName}>{roomName}</strong>
            {room?.type === "group" ? (
              <span style={styles.groupMemberCount}>{members.length || ""}</span>
            ) : null}
          </button>
        </span>
        <span style={styles.headerActions}>
          <button
            type="button"
            style={styles.searchButton}
            onClick={() => setIsSearchOpen((current) => !current)}
            aria-label="Search messages"
          >
            <SearchIcon />
          </button>
          <button
            type="button"
            style={styles.infoButton}
            onClick={() => setInfoOpen(true)}
            aria-label="Open chat info"
          >
            <img src="/icon-menu.svg" alt="" style={styles.infoIcon} />
          </button>
        </span>
      </header>

      {isSearchOpen ? (
        <label style={styles.messageSearchWrap}>
          <input
            type="search"
            value={messageSearchQuery}
            onChange={(event) => setMessageSearchQuery(event.target.value)}
            placeholder="Search messages"
            style={styles.messageSearchInput}
          />
          <span style={styles.messageSearchCount}>
            {messageSearchQuery.trim() ? `${messageSearchResultCount}` : ""}
          </span>
        </label>
      ) : null}

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
        {messages.map((message, messageIndex) => {
          const previousMessage = messages[messageIndex - 1];
          const showDateDivider =
            messageIndex === 0 ||
            !isSameChatDate(previousMessage?.created_at, message.created_at);

          if (isRoomNoticeMessage(message)) {
            return (
              <div key={message.client_msg_id || message.message_id}>
                {showDateDivider ? <DateDivider value={message.created_at} /> : null}
                <div style={styles.roomNoticeRow}>
                  <span style={styles.roomNoticeText}>
                    {renderMessageContent(message)}
                  </span>
                </div>
              </div>
            );
          }

          const mine = Boolean(currentUserId && message.sender_id === currentUserId);
          const showAvatar =
            !mine &&
            (!previousMessage ||
              previousMessage.sender_id !== message.sender_id ||
              isRoomNoticeMessage(previousMessage));
          const isSearchMatch =
            Boolean(messageSearchQuery.trim()) &&
            renderMessageContent(message)
              .toLowerCase()
              .includes(messageSearchQuery.trim().toLowerCase());
          return (
            <div key={message.client_msg_id || message.message_id}>
              {showDateDivider ? <DateDivider value={message.created_at} /> : null}
              <div
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
                      style={{
                        ...styles.messageAvatar,
                        ...(showAvatar ? {} : styles.hiddenMessageAvatar),
                      }}
                    />
                  </button>
                ) : null}
                <span style={styles.messageContentGroup}>
                  {!mine && showAvatar ? (
                    <span style={styles.senderName}>{getMessageSenderName(message)}</span>
                  ) : null}
                  <span style={styles.bubbleLine}>
                    {!mine ? (
                      <div
                        style={{
                          ...styles.bubble,
                          ...(room?.type === "group" ? styles.groupReceivedBubble : {}),
                          ...(isSearchMatch ? styles.searchMatchedBubble : {}),
                        }}
                      >
                        {renderMessageContent(message)}
                      </div>
                    ) : (
                      <>
                        <span style={styles.time}>
                          {formatTime(message.created_at)}
                          {message.status === "sending" ? " - sending" : ""}
                          {message.status === "failed" ? " - failed" : ""}
                          {message.edited_at && !message.deleted_at ? " - edited" : ""}
                        </span>
                        <div
                          style={{
                            ...styles.bubble,
                            ...styles.bubbleMine,
                            ...(isSearchMatch ? styles.searchMatchedBubbleMine : {}),
                          }}
                        >
                          {renderMessageContent(message)}
                        </div>
                      </>
                    )}
                    {!mine ? (
                      <span style={styles.time}>
                        {formatTime(message.created_at)}
                        {message.status === "sending" ? " - sending" : ""}
                        {message.status === "failed" ? " - failed" : ""}
                        {message.edited_at && !message.deleted_at ? " - edited" : ""}
                      </span>
                    ) : null}
                  </span>
                </span>
              </div>
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

      <form
        style={styles.composer}
        onSubmit={(event) => {
          event.preventDefault();
          handleSend();
        }}
      >
        <input
          ref={composerInputRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return;
            if (event.key === "Enter") {
              event.preventDefault();
              handleSend();
            }
          }}
          maxLength={2000}
          enterKeyHint="send"
          placeholder="Type a message"
          style={styles.input}
        />
        <button
          type="submit"
          style={{
            ...styles.sendButton,
            ...(!input.trim() || isCreatingDirectRoom
              ? styles.sendButtonDisabled
              : {}),
          }}
          onMouseDown={(event) => event.preventDefault()}
          onTouchEnd={(event) => {
            event.preventDefault();
            handleSend();
          }}
          disabled={!input.trim() || isCreatingDirectRoom}
          aria-label="Send"
          title={connectionState === "ready" ? "Send" : "Queued"}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M7 12V2M3 6l4-4 4 4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>

      {infoOpen ? (
        <div style={styles.infoBackdrop} onClick={() => setInfoOpen(false)}>
          <aside style={styles.infoPanel} onClick={(event) => event.stopPropagation()}>
            <div style={styles.infoHeader}>
              <button
                type="button"
                style={styles.infoCloseButton}
                onClick={() => setInfoOpen(false)}
                aria-label="Back to chat"
              >
                <BackIcon />
              </button>
              <h2 style={styles.infoTitle}>{roomName}</h2>
              <span style={styles.infoHeaderSpacer} />
            </div>

            <section style={styles.infoSection}>
              <div style={styles.infoSectionHeader}>
                <h3 style={styles.infoSectionTitle}>Members</h3>
                {room?.type === "group" ? (
                  <span style={styles.infoCount}>{members.length}</span>
                ) : null}
              </div>
              {room?.type === "group" ? (
                <button
                  type="button"
                  style={styles.infoPrimaryButton}
                  onClick={() => void openInvitePanel()}
                >
                  <span style={styles.inviteIcon}>+</span>
                  Invite
                </button>
              ) : null}
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
                    style={styles.infoDangerButton}
                    onClick={() => setIsLeaveConfirmOpen(true)}
                    disabled={leaveLoading}
                  >
                    {leaveLoading ? "Leaving..." : "Leave Chat"}
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
                      onClick={() => {
                        if (selectedInviteIds.length > 0 && !inviteLoading) {
                          setIsInviteConfirmOpen(true);
                        }
                      }}
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

      {isLeaveConfirmOpen ? (
        <ConfirmToast
          title="Leave this group chat?"
          message="You will stop receiving messages from this group."
          confirmLabel="Leave"
          destructive
          busy={leaveLoading}
          onConfirm={() => void handleLeaveGroup()}
          onCancel={() => setIsLeaveConfirmOpen(false)}
        />
      ) : null}

      {isInviteConfirmOpen ? (
        <ConfirmToast
          title="Invite to this group chat?"
          message={`${selectedInviteIds.length} friend(s) will be added to "${roomName}".`}
          confirmLabel="Invite"
          busy={inviteLoading}
          onConfirm={() => {
            setIsInviteConfirmOpen(false);
            void handleInviteMembers();
          }}
          onCancel={() => setIsInviteConfirmOpen(false)}
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
  return new Date(value).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatChatDate(value?: string): string {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";

  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
}

function isSameChatDate(left?: string, right?: string): boolean {
  if (!left || !right) return false;

  const leftDate = new Date(left);
  const rightDate = new Date(right);
  if (Number.isNaN(leftDate.getTime()) || Number.isNaN(rightDate.getTime())) {
    return false;
  }

  return (
    leftDate.getFullYear() === rightDate.getFullYear() &&
    leftDate.getMonth() === rightDate.getMonth() &&
    leftDate.getDate() === rightDate.getDate()
  );
}

function DateDivider({ value }: { value?: string }) {
  return (
    <div style={styles.dateDivider}>
      <span style={styles.dateLine} />
      <span style={styles.dateText}>{formatChatDate(value)}</span>
      <span style={styles.dateLine} />
    </div>
  );
}

function BackIcon() {
  return (
    <svg width="11" height="20" viewBox="0 0 11 20" fill="none" aria-hidden="true">
      <path
        d="M9.5 1.5 1.5 10l8 8.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <circle cx="9.5" cy="9.5" r="7" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M15 15l4.5 4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
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
    background: "#f5f5f5",
    fontFamily: "'Pretendard Variable', 'Nunito', 'Apple SD Gothic Neo', sans-serif",
    overflow: "hidden",
  },
  groupPage: {
    background: "#f5f5f5",
  },
  header: {
    zIndex: 5,
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    minHeight: 56,
    padding: "calc(18px + var(--app-safe-top)) 16px 8px",
    background: "transparent",
    borderBottom: "none",
    position: "relative",
  },
  backButton: {
    width: 34,
    height: 40,
    border: "none",
    padding: 4,
    background: "transparent",
    color: "#222222",
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
    display: "grid",
    placeItems: "center",
    position: "absolute",
    left: 76,
    right: 76,
    bottom: 15,
    pointerEvents: "none",
  },
  roomNameButton: {
    maxWidth: "100%",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    border: "none",
    background: "transparent",
    padding: 0,
    cursor: "pointer",
    pointerEvents: "auto",
  },
  disabledRoomNameButton: {
    cursor: "default",
  },
  roomName: {
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "#222222",
    fontSize: "1.0625rem",
    fontWeight: 700,
  },
  groupMemberCount: {
    color: "#848484",
    fontSize: "1.0625rem",
    fontWeight: 400,
  },
  searchButton: {
    width: 34,
    height: 40,
    border: "none",
    padding: "5px 2px 0",
    background: "transparent",
    color: "#222222",
    cursor: "pointer",
    flexShrink: 0,
    display: "grid",
    placeItems: "center",
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 8,
    width: 76,
    flexShrink: 0,
  },
  infoButton: {
    width: 34,
    height: 40,
    border: "none",
    borderRadius: 0,
    display: "grid",
    placeItems: "center",
    background: "transparent",
    cursor: "pointer",
    flexShrink: 0,
  },
  infoIcon: {
    width: 22,
    height: 22,
    objectFit: "contain",
  },
  messageSearchWrap: {
    minHeight: 42,
    margin: "0 17px 8px",
    borderRadius: 999,
    background: "#f6f6f6",
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "0 14px",
    flexShrink: 0,
  },
  messageSearchInput: {
    flex: 1,
    minWidth: 0,
    border: "none",
    outline: "none",
    background: "transparent",
    color: "#222222",
    fontSize: "0.9rem",
  },
  messageSearchCount: {
    minWidth: 18,
    color: "#01c0c0",
    fontSize: "0.78rem",
    fontWeight: 800,
    textAlign: "right",
  },
  dateDivider: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 16px 12px",
    flexShrink: 0,
  },
  dateLine: {
    flex: 1,
    height: 1,
    background: "#dadada",
  },
  dateText: {
    color: "#b8b8b8",
    fontSize: "0.75rem",
    whiteSpace: "nowrap",
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
    gap: 4,
    overflowY: "auto",
    overscrollBehavior: "contain",
    padding: "8px 0 14px",
    scrollbarWidth: "none",
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
    padding: "4px 16px",
  },
  messageRowMine: {
    flexDirection: "row-reverse",
    justifyContent: "flex-start",
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
    width: 40,
    height: 40,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
    boxShadow: "none",
  },
  hiddenMessageAvatar: {
    visibility: "hidden",
  },
  messageAvatarButton: {
    width: 40,
    height: 40,
    border: "none",
    borderRadius: "50%",
    padding: 0,
    background: "transparent",
    cursor: "pointer",
    flexShrink: 0,
  },
  messageContentGroup: {
    minWidth: 0,
    maxWidth: "calc(100% - 48px)",
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  senderName: {
    marginLeft: 2,
    color: "#848484",
    fontSize: "0.75rem",
    lineHeight: 1.2,
  },
  bubbleLine: {
    display: "flex",
    alignItems: "flex-end",
    gap: 4,
  },
  bubble: {
    maxWidth: 216,
    padding: "10px 20px",
    borderRadius: "25px 25px 25px 5px",
    background: "#ffffff",
    color: "#000000",
    boxShadow: "none",
    overflowWrap: "anywhere",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontSize: "0.9375rem",
    lineHeight: "20px",
  },
  groupReceivedBubble: {
    borderRadius: "5px 25px 25px 25px",
    background: "#f6f6f6",
  },
  bubbleMine: {
    borderRadius: "25px 25px 5px 25px",
    background: "#01c0c0",
    color: "#ffffff",
    fontWeight: 500,
  },
  searchMatchedBubble: {
    outline: "2px solid rgba(255,185,0,0.75)",
  },
  searchMatchedBubbleMine: {
    outline: "2px solid rgba(255,185,0,0.95)",
  },
  time: {
    color: "#aaaaaa",
    fontSize: "0.68rem",
    whiteSpace: "nowrap",
  },
  composer: {
    zIndex: 20,
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 16px calc(10px + var(--app-safe-bottom))",
    background: "rgba(255,255,255,0.9)",
    borderTop: "1px solid rgba(0,0,0,0.06)",
    backdropFilter: "blur(8px)",
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
    flex: 1,
    minWidth: 0,
    minHeight: 40,
    border: "none",
    borderRadius: 999,
    padding: "0 16px",
    outline: "none",
    background: "#ffffff",
    color: "#222222",
    fontSize: "0.9375rem",
  },
  sendButton: {
    border: "none",
    borderRadius: "50%",
    width: 32,
    height: 32,
    minWidth: 32,
    padding: 0,
    background: "#01c0c0",
    color: "#ffffff",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
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
    justifyContent: "center",
    background: "#ffffff",
  },
  infoPanel: {
    width: "min(393px, 100vw)",
    height: "var(--app-viewport-height)",
    display: "flex",
    flexDirection: "column",
    gap: 0,
    overflowY: "auto",
    padding: "calc(18px + var(--app-safe-top)) 0 calc(20px + var(--app-safe-bottom))",
    background: "#ffffff",
    boxShadow: "none",
  },
  infoHeader: {
    display: "grid",
    gridTemplateColumns: "44px minmax(0, 1fr) 44px",
    alignItems: "center",
    justifyContent: "stretch",
    gap: 10,
    minHeight: 56,
    padding: "0 16px",
  },
  infoEyebrow: {
    display: "none",
  },
  infoTitle: {
    margin: 0,
    color: "#222222",
    fontSize: "1.0625rem",
    lineHeight: 1.2,
    fontWeight: 700,
    textAlign: "center",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  infoCloseButton: {
    width: 36,
    height: 40,
    border: "none",
    borderRadius: 0,
    background: "transparent",
    color: "#222222",
    cursor: "pointer",
  },
  infoHeaderSpacer: {
    width: 36,
    height: 40,
    display: "block",
  },
  infoCloseIcon: {
    width: 18,
    height: 18,
    objectFit: "contain",
  },
  infoSection: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    paddingTop: 10,
  },
  infoSectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-start",
    gap: 4,
    padding: "16px 16px 4px",
  },
  infoSectionTitle: {
    margin: 0,
    color: "#222222",
    fontSize: "0.9375rem",
    fontWeight: 700,
  },
  infoCount: {
    minWidth: 0,
    height: "auto",
    display: "inline",
    borderRadius: 0,
    background: "transparent",
    color: "#848484",
    fontSize: "0.9375rem",
    fontWeight: 700,
  },
  memberList: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  memberRow: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 8,
    minHeight: 64,
    padding: "10px 16px",
    border: "none",
    borderBottom: "1px solid #f0f0f0",
    borderRadius: 0,
    background: "#ffffff",
    textAlign: "left",
    cursor: "pointer",
  },
  memberAvatarLarge: {
    width: 42,
    height: 42,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  memberRowName: {
    color: "#222222",
    fontSize: "1rem",
    fontWeight: 600,
  },
  infoActions: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  infoPrimaryButton: {
    minHeight: 64,
    border: "none",
    borderBottom: "1px solid #f0f0f0",
    borderRadius: 0,
    background: "#ffffff",
    color: "#000000",
    fontWeight: 600,
    fontSize: "1rem",
    cursor: "pointer",
    textAlign: "left",
    padding: "0 16px",
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  inviteIcon: {
    width: 44,
    height: 44,
    borderRadius: "50%",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#eaeaea",
    color: "#01c0c0",
    fontSize: "1.35rem",
    lineHeight: 1,
    flexShrink: 0,
  },
  infoDangerButton: {
    minHeight: 52,
    border: "none",
    borderRadius: 0,
    background: "#ffffff",
    color: "#b70000",
    fontWeight: 500,
    fontSize: "1rem",
    cursor: "pointer",
    textAlign: "left",
    padding: "0 16px",
  },
};
