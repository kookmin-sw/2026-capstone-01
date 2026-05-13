import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMyProfile } from "../../api/auth";
import {
  createGroupChatRoom,
  type ChatRoom,
  type SystemContent,
} from "../../api/chat";
import {
  acceptFriendRequest,
  blockUser,
  cancelFriendRequest,
  deleteFriend,
  getBlockedUsers,
  getFriends,
  getReceivedFriendRequests,
  getSentFriendRequests,
  rejectFriendRequest,
  searchFriendUsers,
  sendFriendRequest,
  unblockUser,
  type FriendSearchUser,
  type FriendPeer,
  type Friendship,
  type UserBlock,
} from "../../api/friend";
import { useChat } from "./ChatProvider";
import { reportChatNetworkError } from "../../utils/chatDiagnostics";
import ConfirmToast from "../../components/ConfirmToast";
import FeedPopup from "../../components/FeedPopup";
import { navigateBackOrFallback } from "../../utils/navigation";

type FriendManagerTab = "friend" | "request";
type LoadingKey = "received" | "sent" | "friends" | "blocks";

const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

export default function ChatPage({
  embedded = false,
  hideHeader = false,
}: {
  embedded?: boolean;
  hideHeader?: boolean;
}) {
  const navigate = useNavigate();
  const {
    rooms: chatRooms,
    roomsLoading: chatLoading,
    connectionState: chatConnectionStatus,
    currentUserId,
    refreshRooms,
    openDirectChat,
  } = useChat();
  const [receivedRequests, setReceivedRequests] = useState<Friendship[]>([]);
  const [sentRequests, setSentRequests] = useState<Friendship[]>([]);
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [blockedUsers, setBlockedUsers] = useState<UserBlock[]>([]);
  const [cursors, setCursors] = useState<Record<LoadingKey, string | null>>({
    received: null,
    sent: null,
    friends: null,
    blocks: null,
  });
  const [loading, setLoading] = useState<Record<LoadingKey, boolean>>({
    received: false,
    sent: false,
    friends: false,
    blocks: false,
  });
  const [actionId, setActionId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [currentUserName, setCurrentUserName] = useState<string | null>(null);
  const [feedPopupUserId, setFeedPopupUserId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isFriendManagerOpen, setIsFriendManagerOpen] = useState(false);
  const [friendManagerTab, setFriendManagerTab] = useState<FriendManagerTab>("friend");
  const [friendSearchQuery, setFriendSearchQuery] = useState("");
  const [friendSearchResults, setFriendSearchResults] = useState<FriendSearchUser[]>([]);
  const [friendSearchLoading, setFriendSearchLoading] = useState(false);
  const [friendSearchError, setFriendSearchError] = useState("");
  const [isGroupCreateOpen, setIsGroupCreateOpen] = useState(false);
  const [groupTitle, setGroupTitle] = useState("");
  const [selectedGroupMemberIds, setSelectedGroupMemberIds] = useState<string[]>([]);
  const [isGroupCreateConfirmOpen, setIsGroupCreateConfirmOpen] = useState(false);

  const pendingCount = receivedRequests.length;
  const displayNamesById = useMemo(() => {
    const names = new Map<string, string>();

    if (currentUserId && currentUserName) {
      names.set(currentUserId, currentUserName);
    }

    friends.forEach((friend) => {
      names.set(friend.peer.user_id, friend.peer.user_name);
    });

    chatRooms.forEach((room) => {
      if (room.peer?.user_id && room.peer.user_name) {
        names.set(room.peer.user_id, room.peer.user_name);
      }

      room.members?.forEach((member) => {
        if (member.user_id && member.user_name) {
          names.set(member.user_id, member.user_name);
        }
      });
    });

    return names;
  }, [chatRooms, currentUserId, currentUserName, friends]);
  const resolveDisplayName = useCallback(
    (userId: string | null): string =>
      userId === null ? "Unknown user" : displayNamesById.get(userId) || "Unknown user",
    [displayNamesById]
  );
  const chatRows = useMemo(
    () => chatRooms.map((room) => toChatRow(room, resolveDisplayName)),
    [chatRooms, resolveDisplayName]
  );
  const normalizedSearchQuery = searchQuery.trim().toLowerCase();
  const filteredChatRows = useMemo(
    () =>
      normalizedSearchQuery
        ? chatRows.filter((chat) => chat.name.toLowerCase().includes(normalizedSearchQuery))
        : chatRows,
    [chatRows, normalizedSearchQuery]
  );
  useEffect(() => {
    void refreshAll();
  }, []);

  useEffect(() => {
    function openGroupCreate(): void {
      setIsGroupCreateOpen(true);
    }

    function openFriendManager(): void {
      setFriendManagerTab("friend");
      setIsFriendManagerOpen(true);
    }

    window.addEventListener("krip:chat-open-group-create", openGroupCreate);
    window.addEventListener("krip:chat-open-friend-manager", openFriendManager);

    return () => {
      window.removeEventListener("krip:chat-open-group-create", openGroupCreate);
      window.removeEventListener("krip:chat-open-friend-manager", openFriendManager);
    };
  }, []);

  async function loadReceived(cursor?: string, append = false): Promise<void> {
    setLoading((current) => ({ ...current, received: true }));
    try {
      const response = await getReceivedFriendRequests(cursor);
      setReceivedRequests((current) =>
        append ? [...current, ...response.items] : response.items
      );
      setCursors((current) => ({ ...current, received: response.next_cursor }));
    } finally {
      setLoading((current) => ({ ...current, received: false }));
    }
  }

  async function loadSent(cursor?: string, append = false): Promise<void> {
    setLoading((current) => ({ ...current, sent: true }));
    try {
      const response = await getSentFriendRequests(cursor);
      setSentRequests((current) =>
        append ? [...current, ...response.items] : response.items
      );
      setCursors((current) => ({ ...current, sent: response.next_cursor }));
    } finally {
      setLoading((current) => ({ ...current, sent: false }));
    }
  }

  async function loadFriends(cursor?: string, append = false): Promise<void> {
    setLoading((current) => ({ ...current, friends: true }));
    try {
      const response = await getFriends(cursor);
      setFriends((current) => (append ? [...current, ...response.items] : response.items));
      setCursors((current) => ({ ...current, friends: response.next_cursor }));
    } finally {
      setLoading((current) => ({ ...current, friends: false }));
    }
  }

  async function loadBlocks(cursor?: string, append = false): Promise<void> {
    setLoading((current) => ({ ...current, blocks: true }));
    try {
      const response = await getBlockedUsers(cursor);
      setBlockedUsers((current) =>
        append ? [...current, ...response.items] : response.items
      );
      setCursors((current) => ({ ...current, blocks: response.next_cursor }));
    } finally {
      setLoading((current) => ({ ...current, blocks: false }));
    }
  }

  async function loadCurrentUserName(): Promise<void> {
    try {
      const profile = await getMyProfile();
      setCurrentUserName(profile?.user_name ?? null);
    } catch {
      setCurrentUserName(null);
    }
  }

  async function refreshAll(): Promise<void> {
    setError("");
    try {
      await Promise.all([
        refreshRooms(),
        loadCurrentUserName(),
        loadReceived(),
        loadSent(),
        loadFriends(),
        loadBlocks(),
      ]);
      window.dispatchEvent(new CustomEvent("krip:friend-chat-notifications-updated"));
    } catch (loadError) {
      reportChatNetworkError({
        action: "refresh_chat_page",
        detail: toErrorMessage(loadError, "Failed to load friend data."),
        extra: getErrorStatus(loadError),
      });
      setError(toErrorMessage(loadError, "Failed to load friend data."));
    }
  }

  async function runAction(action: () => Promise<unknown>, successMessage: string): Promise<void> {
    setNotice("");
    setError("");
    try {
      await action();
      setNotice(successMessage);
      await refreshAll();
    } catch (actionError) {
      setError(toErrorMessage(actionError, "Action failed. Please try again."));
    } finally {
      setActionId("");
    }
  }

  function isBusy(id: string): boolean {
    return actionId === id;
  }

  async function handleOpenDirectChat(userId: string): Promise<void> {
    setActionId(`chat:${userId}`);
    setError("");

    try {
      const room = await openDirectChat(userId);
      navigate(`/chat/${room.chat_room_id}`);
    } catch (chatError) {
      reportChatNetworkError({
        action: "open_direct_chat",
        detail: toErrorMessage(chatError, "Failed to open chat."),
        extra: getErrorStatus(chatError),
      });
      setError(toErrorMessage(chatError, "Failed to open chat."));
    } finally {
      setActionId("");
    }
  }

  async function handleFriendSearch(): Promise<void> {
    const keyword = friendSearchQuery.trim();
    if (!keyword) {
      setFriendSearchResults([]);
      setFriendSearchError("");
      return;
    }

    setFriendSearchLoading(true);
    setFriendSearchError("");
    try {
      const response = await searchFriendUsers(keyword);
      setFriendSearchResults(response.items);
    } catch (searchError) {
      setFriendSearchResults([]);
      setFriendSearchError(toErrorMessage(searchError, "Failed to search users."));
    } finally {
      setFriendSearchLoading(false);
    }
  }

  async function handleCreateGroupChat(): Promise<void> {
    const title = groupTitle.trim();
    if (!title || selectedGroupMemberIds.length === 0 || actionId) return;

    setActionId("create-group");
    setError("");
    try {
      const room = await createGroupChatRoom(title, selectedGroupMemberIds);
      setIsGroupCreateOpen(false);
      setGroupTitle("");
      setSelectedGroupMemberIds([]);
      await refreshRooms();
      navigate(`/chat/${room.chat_room_id}`);
    } catch (groupError) {
      setError(toErrorMessage(groupError, "Failed to create group chat."));
    } finally {
      setActionId("");
      setIsGroupCreateConfirmOpen(false);
    }
  }

  function requestCreateGroupChat(): void {
    if (!groupTitle.trim() || selectedGroupMemberIds.length === 0 || actionId) return;
    setIsGroupCreateConfirmOpen(true);
  }

  function toggleGroupMember(userId: string): void {
    setSelectedGroupMemberIds((current) =>
      current.includes(userId)
        ? current.filter((item) => item !== userId)
        : [...current, userId]
    );
  }

  async function handleSendFriendRequest(user: FriendSearchUser): Promise<void> {
    setActionId(`request:${user.user_id}`);
    setFriendSearchError("");
    try {
      await sendFriendRequest(user.user_id);
      setNotice("Friend request sent.");
      setFriendSearchResults((current) =>
        current.map((item) =>
          item.user_id === user.user_id
            ? { ...item, friendship_status: "pending", is_requester: true }
            : item
        )
      );
      await Promise.all([loadSent(), loadReceived(), loadFriends()]);
      window.dispatchEvent(new CustomEvent("krip:friend-chat-notifications-updated"));
    } catch (requestError) {
      setFriendSearchError(toErrorMessage(requestError, "Failed to send friend request."));
    } finally {
      setActionId("");
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        {hideHeader ? null : (
          <header style={embedded ? styles.embeddedHeader : styles.header}>
            {embedded ? (
              <div style={styles.embeddedTitleBlock}>
                <p style={styles.eyebrow}>Trip Mate</p>
                <h1 style={styles.embeddedTitle}>Chat</h1>
              </div>
            ) : (
              <button
                type="button"
                style={styles.backButton}
                onClick={() => navigateBackOrFallback(navigate, "/home")}
              >
                <img src="/icon-back.svg" alt="" style={styles.headerIcon} />
              </button>
            )}
            {embedded ? null : <h1 style={styles.title}>Chat</h1>}
            <div style={styles.headerIconGroup}>
              <button
                type="button"
                style={styles.friendManagerButton}
                onClick={() => setIsGroupCreateOpen(true)}
                aria-label="Create group chat"
              >
                <img src="/icon-plus.svg" alt="" style={styles.friendManagerIcon} />
              </button>
              <button
                type="button"
                style={styles.friendManagerButton}
                onClick={() => {
                  setFriendManagerTab("friend");
                  setIsFriendManagerOpen(true);
                }}
                aria-label="Manage friends"
              >
                <img src="/user-add-alt.png" alt="" style={styles.friendManagerIcon} />
                {pendingCount > 0 ? <span style={styles.addButtonDot} /> : null}
              </button>
            </div>
          </header>
        )}

        <label style={styles.searchWrap}>
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search"
            style={styles.searchInput}
          />
          <img src="/icon-search.svg" alt="" style={styles.searchIconImage} />
        </label>

        {notice ? <div style={styles.notice}>{notice}</div> : null}
        {error ? <div style={styles.error}>{error}</div> : null}

        <section style={styles.list}>
          {chatLoading && filteredChatRows.length === 0 ? (
            <p style={styles.mutedText}>Loading chats...</p>
          ) : filteredChatRows.length > 0 ? (
            filteredChatRows.map((chat) => (
              <button
                key={chat.id}
                type="button"
                style={styles.chatRow}
                onClick={() => navigate(`/chat/${chat.id}`)}
              >
                <Avatar name={chat.name} imageUrl={chat.imageUrl} />
                <span style={styles.rowMain}>
                  <strong style={styles.rowTitle}>{chat.name}</strong>
                  <span style={styles.rowSubtitle}>{chat.preview}</span>
                </span>
                {chat.unreadCount > 0 ? (
                  <span style={styles.unreadBadge}>
                    {chat.unreadCount >= 999 ? "999+" : chat.unreadCount}
                  </span>
                ) : null}
              </button>
            ))
          ) : (
            <EmptyCard
              title={searchQuery.trim() ? "No matching chats" : "No chats yet"}
              copy={
                searchQuery.trim()
                  ? "Try another friend name."
                  : "Accepted friends will appear here as chat-ready contacts."
              }
            />
          )}
        </section>

        {isFriendManagerOpen ? (
          <div style={styles.managerBackdrop} onClick={() => setIsFriendManagerOpen(false)}>
            <section style={styles.managerPanel} onClick={(event) => event.stopPropagation()}>
              <div style={styles.managerHeader}>
                <h2 style={styles.managerTitle}>Friends</h2>
                <button
                  type="button"
                  style={styles.managerCloseButton}
                  onClick={() => setIsFriendManagerOpen(false)}
                >
                  <img src="/icon-close.svg" alt="" style={styles.closeIcon} />
                </button>
              </div>

              <div style={styles.managerTabs} aria-label="Friend manager tabs">
                {(["friend", "request"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    style={{
                      ...styles.managerTabButton,
                      ...(friendManagerTab === item ? styles.managerTabButtonActive : {}),
                    }}
                    onClick={() => setFriendManagerTab(item)}
                  >
                    {item === "friend" ? "Friend" : "Request"}
                    {item === "request" && pendingCount > 0 ? (
                      <span style={styles.managerTabBadge}>{pendingCount}</span>
                    ) : null}
                  </button>
                ))}
              </div>

              {friendManagerTab === "friend" ? (
                <>
              <div style={styles.addFriendPanel}>
                <label style={styles.managerSearchWrap}>
                  <input
                    type="search"
                    value={friendSearchQuery}
                    onChange={(event) => setFriendSearchQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void handleFriendSearch();
                    }}
                    placeholder="Search users"
                    style={styles.managerSearchInput}
                  />
                  <button
                    type="button"
                    style={styles.managerSearchButton}
                    onClick={() => void handleFriendSearch()}
                    disabled={friendSearchLoading}
                  >
                    Search
                  </button>
                </label>
                {friendSearchError ? <p style={styles.inlineError}>{friendSearchError}</p> : null}
                {friendSearchLoading ? (
                  <p style={styles.mutedText}>Searching users...</p>
                ) : friendSearchResults.length > 0 ? (
                  <div style={styles.friendList}>
                    {friendSearchResults.map((user) => (
                      <div key={user.user_id} style={styles.friendCard}>
                        <PeerSummary peer={toFriendPeer(user)} />
                        <button
                          type="button"
                          style={styles.primaryButton}
                          disabled={
                            Boolean(actionId) ||
                            user.i_blocked_peer ||
                            user.friendship_status === "pending" ||
                            user.friendship_status === "accepted"
                          }
                          onClick={() => void handleSendFriendRequest(user)}
                        >
                          {isBusy(`request:${user.user_id}`)
                            ? "Sending..."
                            : getFriendSearchActionLabel(user)}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : friendSearchQuery.trim() ? (
                  <p style={styles.mutedText}>No users found.</p>
                ) : null}
              </div>

              <div style={styles.panel}>
                <div style={styles.sectionHeader}>
                  <h2 style={styles.sectionTitle}>Friend List</h2>
                  {cursors.friends ? (
                    <button
                      type="button"
                      style={styles.linkButton}
                      onClick={() => void loadFriends(cursors.friends || undefined, true)}
                    >
                      Load More
                    </button>
                  ) : null}
                </div>

                {loading.friends && friends.length === 0 ? (
                  <p style={styles.mutedText}>Loading friends...</p>
                ) : friends.length > 0 ? (
                  <div style={styles.friendList}>
                    {friends.map((friend) => (
                      <FriendCard
                        key={friend.friendship_id}
                        item={friend}
                        onChat={() => void handleOpenDirectChat(friend.peer.user_id)}
                        onViewFeed={() => setFeedPopupUserId(friend.peer.user_id)}
                        onDelete={() => {
                          setActionId(`delete:${friend.friendship_id}`);
                          void runAction(
                            () => deleteFriend(friend.friendship_id),
                            "Friend deleted."
                          );
                        }}
                        onBlock={() => {
                          setActionId(`block:${friend.peer.user_id}`);
                          void runAction(
                            () => blockUser(friend.peer.user_id),
                            "User blocked."
                          );
                        }}
                        busy={Boolean(actionId)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyCard title="No friends yet" copy="Accepted friends will appear here." />
                )}
              </div>

              <div style={styles.panel}>
                <div style={styles.sectionHeader}>
                  <h2 style={styles.sectionTitle}>Blocked Users</h2>
                  {cursors.blocks ? (
                    <button
                      type="button"
                      style={styles.linkButton}
                      onClick={() => void loadBlocks(cursors.blocks || undefined, true)}
                    >
                      Load More
                    </button>
                  ) : null}
                </div>

                {loading.blocks && blockedUsers.length === 0 ? (
                  <p style={styles.mutedText}>Loading blocked users...</p>
                ) : blockedUsers.length > 0 ? (
                  <div style={styles.friendList}>
                    {blockedUsers.map((block) => (
                      <div key={block.block_id} style={styles.friendCard}>
                        <PeerSummary peer={block.blocked} />
                        <button
                          type="button"
                          style={styles.secondaryButton}
                          disabled={Boolean(actionId)}
                          onClick={() => {
                            setActionId(`unblock:${block.blocked.user_id}`);
                            void runAction(
                              () => unblockUser(block.blocked.user_id),
                              "User unblocked."
                            );
                          }}
                        >
                          Unblock
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyCard title="No blocked users" copy="Blocked users will appear here." />
                )}
              </div>
                </>
              ) : (
                <>

              <RequestSection
                title="Received Requests"
                emptyTitle="No received requests"
                emptyCopy="Incoming friend requests will show up here."
                loading={loading.received}
                items={receivedRequests}
                nextCursor={cursors.received}
                onLoadMore={() => void loadReceived(cursors.received || undefined, true)}
                renderActions={(item) => (
                  <>
                    <button
                      type="button"
                      style={styles.primaryButton}
                      disabled={Boolean(actionId)}
                      onClick={() => {
                        setActionId(`accept:${item.friendship_id}`);
                        void runAction(
                          () => acceptFriendRequest(item.friendship_id),
                          "Friend request accepted."
                        );
                      }}
                    >
                      {isBusy(`accept:${item.friendship_id}`) ? "Accepting..." : "Accept"}
                    </button>
                    <button
                      type="button"
                      style={styles.secondaryButton}
                      disabled={Boolean(actionId)}
                      onClick={() => {
                        setActionId(`reject:${item.friendship_id}`);
                        void runAction(
                          () => rejectFriendRequest(item.friendship_id),
                          "Friend request rejected."
                        );
                      }}
                    >
                      Reject
                    </button>
                  </>
                )}
              />

              <RequestSection
                title="Sent Requests"
                emptyTitle="No sent requests"
                emptyCopy="Requests you send will stay here until accepted or canceled."
                loading={loading.sent}
                items={sentRequests}
                nextCursor={cursors.sent}
                onLoadMore={() => void loadSent(cursors.sent || undefined, true)}
                renderActions={(item) => (
                  <button
                    type="button"
                    style={styles.secondaryButton}
                    disabled={Boolean(actionId)}
                    onClick={() => {
                      setActionId(`cancel:${item.friendship_id}`);
                      void runAction(
                        () => cancelFriendRequest(item.friendship_id),
                        "Friend request canceled."
                      );
                    }}
                  >
                    {isBusy(`cancel:${item.friendship_id}`) ? "Canceling..." : "Cancel Request"}
                  </button>
                )}
              />
                </>
              )}
            </section>
          </div>
        ) : null}

        {isGroupCreateOpen ? (
          <div style={styles.managerBackdrop} onClick={() => setIsGroupCreateOpen(false)}>
            <section style={styles.managerPanel} onClick={(event) => event.stopPropagation()}>
              <div style={styles.managerHeader}>
                <h2 style={styles.managerTitle}>New Group</h2>
                <button
                  type="button"
                  style={styles.managerCloseButton}
                  onClick={() => setIsGroupCreateOpen(false)}
                >
                  <img src="/icon-close.svg" alt="" style={styles.closeIcon} />
                </button>
              </div>

              <label style={styles.managerSearchWrap}>
                <input
                  type="text"
                  value={groupTitle}
                  onChange={(event) => setGroupTitle(event.target.value)}
                  placeholder="Group name"
                  style={styles.managerSearchInput}
                />
              </label>

              <div style={styles.friendList}>
                {friends.length > 0 ? (
                  friends.map((friend) => {
                    const selected = selectedGroupMemberIds.includes(friend.peer.user_id);

                    return (
                      <label key={friend.friendship_id} style={styles.groupFriendRow}>
                        <PeerSummary peer={friend.peer} />
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleGroupMember(friend.peer.user_id)}
                          style={styles.groupCheckbox}
                        />
                      </label>
                    );
                  })
                ) : (
                  <p style={styles.mutedText}>Add friends before creating a group.</p>
                )}
              </div>

              <button
                type="button"
                style={{
                  ...styles.primaryButton,
                  ...styles.groupCreateButton,
                  ...(!groupTitle.trim() || selectedGroupMemberIds.length === 0
                    ? styles.disabledButton
                    : {}),
                }}
                disabled={
                  !groupTitle.trim() ||
                  selectedGroupMemberIds.length === 0 ||
                  actionId === "create-group"
                }
                onClick={requestCreateGroupChat}
              >
                {actionId === "create-group"
                  ? "Creating..."
                  : `Create Group (${selectedGroupMemberIds.length})`}
              </button>
            </section>
          </div>
        ) : null}

        {isGroupCreateConfirmOpen ? (
          <ConfirmToast
            title="Create this group chat?"
            message={`${selectedGroupMemberIds.length} friend(s) will be added to "${groupTitle.trim()}".`}
            confirmLabel="Create"
            busy={actionId === "create-group"}
            onConfirm={() => void handleCreateGroupChat()}
            onCancel={() => setIsGroupCreateConfirmOpen(false)}
          />
        ) : null}

        {feedPopupUserId ? (
          <FeedPopup
            key={feedPopupUserId}
            userId={feedPopupUserId}
            onClose={() => setFeedPopupUserId(null)}
          />
        ) : null}
      </div>
    </div>
  );
}

function RequestSection({
  title,
  emptyTitle,
  emptyCopy,
  loading,
  items,
  nextCursor,
  onLoadMore,
  renderActions,
}: {
  title: string;
  emptyTitle: string;
  emptyCopy: string;
  loading: boolean;
  items: Friendship[];
  nextCursor: string | null;
  onLoadMore: () => void;
  renderActions: (item: Friendship) => React.ReactNode;
}) {
  return (
    <div style={styles.panel}>
      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>{title}</h2>
        {nextCursor ? (
          <button type="button" style={styles.linkButton} onClick={onLoadMore}>
            Load More
          </button>
        ) : null}
      </div>

      {loading && items.length === 0 ? (
        <p style={styles.mutedText}>Loading...</p>
      ) : items.length > 0 ? (
        <div style={styles.friendList}>
          {items.map((item) => (
            <div key={item.friendship_id} style={styles.friendCard}>
              <PeerSummary peer={item.peer} />
              <div style={styles.actionRow}>{renderActions(item)}</div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyCard title={emptyTitle} copy={emptyCopy} />
      )}
    </div>
  );
}

function toFriendPeer(user: FriendSearchUser): FriendPeer {
  return {
    user_id: user.user_id,
    user_name: user.user_name,
    age: 0,
    gender: "" as FriendPeer["gender"],
    nationality: user.nationality || "",
    profile_image_url: user.profile_image_url,
  };
}

function getFriendSearchActionLabel(user: FriendSearchUser): string {
  if (user.i_blocked_peer) return "Blocked";
  if (user.friendship_status === "accepted") return "Friends";
  if (user.friendship_status === "pending") {
    return user.is_requester ? "Requested" : "Respond";
  }
  return "Add";
}

function FriendCard({
  item,
  onChat,
  onViewFeed,
  onDelete,
  onBlock,
  busy,
}: {
  item: Friendship;
  onChat: () => void;
  onViewFeed: () => void;
  onDelete: () => void;
  onBlock: () => void;
  busy: boolean;
}) {
  return (
    <div style={styles.friendCard}>
      <PeerSummary peer={item.peer} />
      <div style={styles.actionRow}>
        <button type="button" style={styles.primaryButton} onClick={onChat}>
          Chat
        </button>
        <button type="button" style={styles.secondaryButton} onClick={onViewFeed}>
          Feed
        </button>
        <button type="button" style={styles.secondaryButton} disabled={busy} onClick={onDelete}>
          Delete
        </button>
        <button type="button" style={styles.dangerButton} disabled={busy} onClick={onBlock}>
          Block
        </button>
      </div>
    </div>
  );
}

function PeerSummary({ peer }: { peer: FriendPeer }) {
  const meta = [peer.nationality, peer.age ? String(peer.age) : "", formatGender(peer.gender)]
    .filter(Boolean)
    .join(" / ");

  return (
    <div style={styles.peerSummary}>
      <Avatar name={peer.user_name} imageUrl={peer.profile_image_url} />
      <span style={styles.rowMain}>
        <strong style={styles.rowTitle}>{peer.user_name}</strong>
        {meta ? <span style={styles.rowSubtitle}>{meta}</span> : null}
        <span style={styles.userId}>{peer.user_id}</span>
      </span>
    </div>
  );
}

function Avatar({ name, imageUrl }: { name: string; imageUrl?: string | null }) {
  return (
    <span style={styles.avatar}>
      {imageUrl ? (
        <img src={imageUrl} alt={name} style={styles.avatarImage} />
      ) : (
        <img src={DEFAULT_PROFILE_IMAGE_URL} alt={name} style={styles.avatarImage} />
      )}
    </span>
  );
}

function EmptyCard({ title, copy }: { title: string; copy: string }) {
  return (
    <div style={styles.emptyCard}>
      <p style={styles.emptyTitle}>{title}</p>
      <p style={styles.emptyCopy}>{copy}</p>
    </div>
  );
}

function formatGender(gender: string): string {
  if (gender === "male") return "Male";
  if (gender === "female") return "Female";
  return gender;
}

function toChatRow(
  room: ChatRoom,
  resolveDisplayName: (userId: string | null) => string
): {
  id: string;
  name: string;
  imageUrl: string | null;
  subtitle: string;
  preview: string;
  unreadCount: number;
} {
  const name =
    room.type === "direct"
      ? room.peer?.user_name || "Deleted User"
      : room.title || "Group Chat";
  const subtitle = room.type === "direct" ? "Direct message" : "Group chat";

  return {
    id: room.chat_room_id,
    name,
    imageUrl: room.type === "direct" ? room.peer?.profile_image_url ?? null : null,
    subtitle,
    preview: renderLastMessage(room.last_message, resolveDisplayName),
    unreadCount: room.unread_count,
  };
}

function renderLastMessage(
  lastMessage: ChatRoom["last_message"],
  resolveDisplayName: (userId: string | null) => string
): string {
  if (!lastMessage) return "No messages yet.";
  if (lastMessage.content === null) return "Message deleted.";
  if (lastMessage.type === "system") {
    return renderSystemLastMessage(lastMessage.content, resolveDisplayName);
  }
  if (typeof lastMessage.content === "string") return lastMessage.content;
  return "";
}

function renderSystemLastMessage(
  content: ChatRoom["last_message"]["content"],
  resolveDisplayName: (userId: string | null) => string
): string {
  if (!isSystemContent(content)) return "System message";

  const actorName = resolveDisplayName(content.actor_id);
  if (content.action === "created") {
    return `${actorName} created the chat.`;
  }
  if (content.action === "join") {
    const targetNames = content.target_ids.map(resolveDisplayName);
    if (
      targetNames.length === 1 &&
      (!content.actor_id || content.actor_id === content.target_ids[0])
    ) {
      return `${targetNames[0]} joined the chat.`;
    }
    return `${actorName} invited ${formatTargetNames(targetNames)}.`;
  }
  if (content.action === "leave") {
    return `${actorName} left the chat.`;
  }
  if (content.action === "kick") {
    return `${actorName} removed ${formatTargetNames(
      content.target_ids.map(resolveDisplayName)
    )}.`;
  }

  return "System message";
}

function isSystemContent(content: unknown): content is SystemContent {
  if (!content || typeof content !== "object") return false;

  const value = content as Partial<SystemContent>;
  if (value.action === "created" || value.action === "leave") {
    return "actor_id" in value;
  }
  if (value.action === "join" || value.action === "kick") {
    return "actor_id" in value && Array.isArray(value.target_ids);
  }
  return false;
}

function formatTargetNames(names: string[]): string {
  if (names.length === 0) return "someone";
  if (names.length === 1) return names[0];
  return `${names[0]} and ${names.length - 1} others`;
}
function getErrorStatus(error: unknown): number | undefined {
  const apiError = error as { response?: { status?: number } };
  return apiError.response?.status;
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(20px + var(--app-safe-top)) 0 34px",
    background: "#ffffff",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  shell: {
    width: "100%",
    maxWidth: 393,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    minHeight: 42,
    padding: "0 16px",
  },
  embeddedHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 16,
    padding: "8px 16px 0",
  },
  embeddedTitleBlock: {
    minWidth: 0,
  },
  eyebrow: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 800,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
  },
  embeddedTitle: {
    margin: "6px 0 8px",
    color: "var(--text-primary)",
    fontSize: "clamp(1.9rem, 5vw, 2.4rem)",
    fontWeight: 900,
    lineHeight: 1.05,
  },
  title: {
    margin: 0,
    color: "#171717",
    fontSize: "1.06rem",
    fontWeight: 900,
    lineHeight: 1,
  },
  backButton: {
    width: 36,
    height: 36,
    border: "none",
    background: "transparent",
    color: "#8d8d8d",
    fontSize: "2.6rem",
    lineHeight: 0.8,
    cursor: "pointer",
  },
  headerIcon: {
    width: 24,
    height: 24,
    objectFit: "contain",
  },
  backButtonSpacer: {
    width: 36,
    height: 36,
    display: "block",
    flexShrink: 0,
  },
  headerIconGroup: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 4,
    minWidth: 76,
  },
  friendManagerButton: {
    position: "relative",
    width: 36,
    height: 36,
    border: "none",
    background: "transparent",
    display: "grid",
    placeItems: "center",
    cursor: "pointer",
  },
  friendManagerIcon: {
    width: 24,
    height: 24,
    objectFit: "contain",
  },
  addButtonDot: {
    position: "absolute",
    top: 5,
    right: 2,
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: "#ffb300",
  },
  searchWrap: {
    margin: "0 17px",
    minHeight: 44,
    borderRadius: 999,
    background: "#f5f5f5",
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "0 18px 0 22px",
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    border: "none",
    outline: "none",
    background: "transparent",
    color: "#171717",
    fontSize: "0.94rem",
    fontWeight: 500,
  },
  searchIconImage: {
    width: 22,
    height: 22,
    objectFit: "contain",
    flexShrink: 0,
  },
  refreshButton: {
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 999,
    padding: "12px 16px",
    background: "rgba(255,255,255,0.88)",
    color: "var(--text-secondary)",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "var(--shadow-soft)",
  },
  segment: {
    position: "relative",
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 0,
    borderBottom: "2px solid #ededed",
  },
  segmentButton: {
    border: "none",
    borderBottomWidth: 3,
    borderBottomStyle: "solid",
    borderBottomColor: "transparent",
    minHeight: 32,
    background: "transparent",
    color: "#d4d4d4",
    fontSize: "0.88rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  segmentButtonActive: {
    borderBottomColor: "#01c0c0",
    color: "#01c0c0",
  },
  countBadge: {
    display: "inline-grid",
    placeItems: "center",
    minWidth: 20,
    height: 20,
    marginLeft: 6,
    padding: "0 6px",
    borderRadius: 999,
    background: "var(--brand-secondary)",
    color: "var(--text-primary)",
    fontSize: "0.72rem",
  },
  notice: {
    padding: "12px 14px",
    borderRadius: 16,
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
  },
  error: {
    padding: "12px 14px",
    borderRadius: 16,
    background: "rgba(220,38,38,0.1)",
    color: "#b91c1c",
    fontWeight: 800,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  stack: {
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  panel: {
    padding: 16,
    borderRadius: 20,
    background: "#ffffff",
    border: "1px solid #eeeeee",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 12,
  },
  sectionTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.05rem",
    fontWeight: 800,
  },
  inputRow: {
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 10,
  },
  input: {
    width: "100%",
    minHeight: 48,
    border: "1px solid rgba(5,181,187,0.16)",
    borderRadius: 16,
    padding: "0 14px",
    background: "var(--surface-panel)",
    color: "var(--text-primary)",
    outline: "none",
  },
  friendList: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  friendCard: {
    display: "flex",
    flexDirection: "column",
    alignItems: "stretch",
    justifyContent: "space-between",
    gap: 12,
    padding: 12,
    borderRadius: 14,
    background: "#ffffff",
    border: "1px solid #f0f0f0",
  },
  peerSummary: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
    width: "100%",
  },
  chatRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    width: "100%",
    padding: "13px 17px",
    borderRadius: 0,
    background: "#ffffff",
    border: "none",
    cursor: "pointer",
    textAlign: "left",
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    flexShrink: 0,
    background: "linear-gradient(135deg, var(--brand-primary), var(--brand-primary-deep))",
    color: "#ffffff",
    fontWeight: 800,
    overflow: "hidden",
  },
  avatarImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  rowMain: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 4,
    flex: 1,
  },
  rowTitle: {
    color: "#171717",
    fontSize: "1.06rem",
    lineHeight: 1.1,
  },
  rowSubtitle: {
    color: "#8c8c8c",
    fontSize: "0.88rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  userId: {
    color: "var(--neutral-500)",
    fontSize: "0.72rem",
    overflowWrap: "anywhere",
  },
  chevron: {
    color: "var(--neutral-700)",
    fontSize: "1.4rem",
  },
  actionRow: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "flex-start",
    gap: 8,
  },
  primaryButton: {
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 16,
    minHeight: 42,
    padding: "0 14px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  disabledButton: {
    opacity: 0.48,
    cursor: "not-allowed",
  },
  secondaryButton: {
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 16,
    minHeight: 42,
    padding: "0 14px",
    background: "rgba(255,255,255,0.88)",
    color: "var(--text-secondary)",
    fontWeight: 800,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  dangerButton: {
    border: "1px solid rgba(220,38,38,0.18)",
    borderRadius: 16,
    minHeight: 42,
    padding: "0 14px",
    background: "rgba(255,255,255,0.88)",
    color: "#dc2626",
    fontWeight: 800,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  linkButton: {
    border: "none",
    background: "transparent",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
    cursor: "pointer",
    padding: 0,
  },
  mutedText: {
    margin: 0,
    color: "var(--neutral-700)",
    lineHeight: 1.5,
  },
  statusText: {
    margin: "0 0 2px",
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  unreadBadge: {
    display: "inline-grid",
    placeItems: "center",
    minWidth: 20,
    height: 20,
    padding: "0 6px",
    borderRadius: 999,
    background: "#ffb300",
    color: "#ffffff",
    fontSize: "0.9rem",
    fontWeight: 900,
  },
  emptyCard: {
    padding: 22,
    borderRadius: 24,
    background: "rgba(255,255,255,0.88)",
    border: "1px solid var(--border-soft)",
  },
  emptyTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontWeight: 800,
  },
  emptyCopy: {
    margin: "8px 0 0",
    color: "var(--neutral-700)",
    lineHeight: 1.55,
  },
  managerBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 80,
    display: "flex",
    justifyContent: "center",
    alignItems: "flex-end",
    padding: "18px 14px 0",
    background: "rgba(15,23,42,0.36)",
  },
  managerPanel: {
    width: "min(760px, 100%)",
    maxHeight: "88dvh",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    padding: 18,
    borderRadius: "26px 26px 0 0",
    background: "#ffffff",
    boxShadow: "0 22px 70px rgba(15,23,42,0.22)",
  },
  managerHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  managerTitle: {
    margin: 0,
    color: "#171717",
    fontSize: "1.2rem",
    fontWeight: 900,
  },
  managerCloseButton: {
    width: 36,
    height: 36,
    border: "none",
    borderRadius: "50%",
    background: "#f4f4f4",
    color: "#555555",
    fontSize: "1.35rem",
    lineHeight: 1,
    cursor: "pointer",
  },
  managerTabs: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 8,
    padding: 4,
    borderRadius: 16,
    background: "#f4f4f4",
  },
  managerTabButton: {
    minHeight: 40,
    border: "none",
    borderRadius: 12,
    background: "transparent",
    color: "#7a7a7a",
    fontWeight: 900,
    cursor: "pointer",
  },
  managerTabButtonActive: {
    background: "#ffffff",
    color: "#171717",
    boxShadow: "0 8px 18px rgba(15,23,42,0.08)",
  },
  managerTabBadge: {
    display: "inline-grid",
    placeItems: "center",
    minWidth: 18,
    height: 18,
    marginLeft: 6,
    padding: "0 5px",
    borderRadius: 999,
    background: "#04bfbf",
    color: "#ffffff",
    fontSize: "0.68rem",
  },
  closeIcon: {
    width: 18,
    height: 18,
    objectFit: "contain",
  },
  addFriendPanel: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 16,
    borderRadius: 20,
    border: "1px solid #eeeeee",
    background: "#ffffff",
  },
  managerSearchWrap: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto",
    gap: 8,
  },
  managerSearchInput: {
    minHeight: 44,
    border: "1px solid #e8e8e8",
    borderRadius: 14,
    padding: "0 12px",
    outline: "none",
    color: "#171717",
    fontWeight: 800,
  },
  managerSearchButton: {
    minHeight: 44,
    border: "none",
    borderRadius: 14,
    padding: "0 14px",
    background: "#04bfbf",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  groupFriendRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: 12,
    borderRadius: 16,
    background: "#ffffff",
    border: "1px solid #eeeeee",
  },
  groupCheckbox: {
    width: 20,
    height: 20,
    accentColor: "#04bfbf",
    flexShrink: 0,
  },
  groupCreateButton: {
    width: "100%",
  },
  inlineError: {
    margin: 0,
    color: "#dc2626",
    fontSize: "0.84rem",
    fontWeight: 800,
  },
};
