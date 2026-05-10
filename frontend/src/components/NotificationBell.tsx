import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { getReceivedFriendRequests, type Friendship } from "../api/friend";
import {
  getNotificationInbox,
  getNotificationUnreadCount,
  hideNotification,
  type InboxNotification,
} from "../api/notification";

type NotificationTab = "activity" | "friends";

export default function NotificationBell() {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [tab, setTab] = useState<NotificationTab>("activity");
  const [notifications, setNotifications] = useState<InboxNotification[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [friendNotifications, setFriendNotifications] = useState<Friendship[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [actionId, setActionId] = useState("");
  const previousUnreadCountRef = useRef<number | null>(null);

  async function refreshUnreadAndFriends(showToast = false): Promise<void> {
    const [count, friendRequests] = await Promise.all([
      getNotificationUnreadCount().catch(() => 0),
      getReceivedFriendRequests().catch(() => ({ items: [] as Friendship[] })),
    ]);
    const previousCount = previousUnreadCountRef.current;
    if (showToast && previousCount !== null && count > previousCount) {
      const newCount = count - previousCount;
      window.dispatchEvent(
        new CustomEvent("krip:app-toast", {
          detail: {
            title: "New activity",
            message: `${newCount} new feed notification${
              newCount > 1 ? "s" : ""
            }. Open the bell to see details.`,
            variant: "info",
          },
        })
      );
    }
    previousUnreadCountRef.current = count;
    setUnreadCount(count);
    setFriendNotifications(friendRequests.items);
  }

  async function showLatestNotificationToast(): Promise<void> {
    return;
    try {
      const inbox = await getNotificationInbox();
      const latest = inbox.notifications[0];
      if (!latest) return;

      setNotifications(inbox.notifications);
      setNextCursor(inbox.next_cursor);
      setUnreadCount(0);
      previousUnreadCountRef.current = 0;

      window.dispatchEvent(
        new CustomEvent("krip:app-toast", {
          detail: {
            title: getNotificationTitle(latest),
            message: latest.comment_preview || getNotificationSubtitle(latest),
            variant: "info",
            path: getNotificationPath(latest),
            imageUrl: latest.actor_profile_image_url || latest.target_preview,
          },
        })
      );
    } catch {
      window.dispatchEvent(
        new CustomEvent("krip:app-toast", {
          detail: {
            title: "New activity",
            message: "알림함에서 새 게시글 알림을 확인해 주세요.",
            variant: "info",
            path: "/my",
          },
        })
      );
    }
  }

  async function fetchFirstPage(): Promise<void> {
    setIsLoading(true);
    try {
      const [inbox, friendRequests] = await Promise.all([
        getNotificationInbox(),
        getReceivedFriendRequests().catch(() => ({ items: [] as Friendship[] })),
      ]);
      setNotifications(inbox.notifications);
      setNextCursor(inbox.next_cursor);
      setFriendNotifications(friendRequests.items);
      setUnreadCount(0);
      previousUnreadCountRef.current = 0;
    } finally {
      setIsLoading(false);
    }
  }

  async function loadMore(): Promise<void> {
    if (!nextCursor || isLoadingMore) return;

    setIsLoadingMore(true);
    try {
      const inbox = await getNotificationInbox(nextCursor);
      setNotifications((current) => {
        const existing = new Set(current.map((item) => item.notification_id));
        return [
          ...current,
          ...inbox.notifications.filter((item) => !existing.has(item.notification_id)),
        ];
      });
      setNextCursor(inbox.next_cursor);
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function handleHideNotification(notificationId: string): Promise<void> {
    setActionId(notificationId);
    try {
      await hideNotification(notificationId);
      setNotifications((current) =>
        current.filter((item) => item.notification_id !== notificationId)
      );
      await refreshUnreadAndFriends();
    } finally {
      setActionId("");
    }
  }

  useEffect(() => {
    void refreshUnreadAndFriends();

    const intervalId = window.setInterval(() => {
      void refreshUnreadAndFriends(true);
    }, 30000);

    const handleRefresh = () => void refreshUnreadAndFriends(false);
    const handleRealtimeRefresh = (event: Event) => {
      const toastHandled = Boolean(
        (event as CustomEvent<{ toastHandled?: boolean }>).detail?.toastHandled
      );
      void refreshUnreadAndFriends(!toastHandled);
    };
    window.addEventListener("focus", handleRefresh);
    window.addEventListener("storage", handleRefresh);
    window.addEventListener("krip:friend-chat-notifications-updated", handleRefresh);
    window.addEventListener("krip:like-notifications-updated", handleRefresh);
    window.addEventListener("krip:notification-inbox-updated", handleRealtimeRefresh);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleRefresh);
      window.removeEventListener("storage", handleRefresh);
      window.removeEventListener("krip:friend-chat-notifications-updated", handleRefresh);
      window.removeEventListener("krip:like-notifications-updated", handleRefresh);
      window.removeEventListener("krip:notification-inbox-updated", handleRealtimeRefresh);
    };
  }, []);

  const notificationCount = unreadCount + friendNotifications.length;

  return (
    <>
      <button
        type="button"
        style={styles.notificationButton}
        onClick={() => {
          setIsOpen(true);
          setTab("activity");
          void fetchFirstPage();
        }}
        aria-label="Open notifications"
      >
        <BellIcon />
        {notificationCount > 0 ? (
          <span style={styles.notificationBadge}>
            {notificationCount >= 999 ? "999+" : notificationCount}
          </span>
        ) : null}
      </button>

      {isOpen ? (
        <div style={styles.notificationOverlay} onClick={() => setIsOpen(false)}>
          <aside style={styles.notificationPanel} onClick={(event) => event.stopPropagation()}>
            <div style={styles.notificationHeader}>
              <div>
                <p style={styles.eyebrow}>Notifications</p>
                <h2 style={styles.notificationTitle}>Updates</h2>
              </div>
              <button
                type="button"
                style={styles.notificationCloseButton}
                onClick={() => setIsOpen(false)}
                aria-label="Close notifications"
              >
                x
              </button>
            </div>

            <div style={styles.notificationTabs}>
              <button
                type="button"
                style={{
                  ...styles.notificationTab,
                  ...(tab === "activity" ? styles.notificationTabActive : {}),
                }}
                onClick={() => setTab("activity")}
              >
                Activity
                {unreadCount > 0 ? (
                  <span style={styles.notificationTabBadge}>
                    {unreadCount >= 999 ? "999+" : unreadCount}
                  </span>
                ) : null}
              </button>
              <button
                type="button"
                style={{
                  ...styles.notificationTab,
                  ...(tab === "friends" ? styles.notificationTabActive : {}),
                }}
                onClick={() => setTab("friends")}
              >
                Friends
                {friendNotifications.length > 0 ? (
                  <span style={styles.notificationTabBadge}>{friendNotifications.length}</span>
                ) : null}
              </button>
            </div>

            <div style={styles.notificationList}>
              {isLoading ? (
                <div style={styles.notificationEmpty}>
                  <span style={styles.spinner} />
                  <p style={styles.emptyCopy}>Loading notifications...</p>
                </div>
              ) : tab === "activity" ? (
                <>
                  {notifications.length > 0 ? (
                    notifications.map((item) => (
                      <NotificationItem
                        key={item.notification_id}
                        item={item}
                        hiding={actionId === item.notification_id}
                        onHide={() => void handleHideNotification(item.notification_id)}
                        onOpen={() => {
                          setIsOpen(false);
                          navigate(getNotificationPath(item));
                        }}
                      />
                    ))
                  ) : (
                    <div style={styles.notificationEmpty}>
                      <p style={styles.emptyTitle}>No activity notifications yet.</p>
                      <p style={styles.emptyCopy}>
                        Likes and comments from other users will appear here.
                      </p>
                    </div>
                  )}
                  {nextCursor ? (
                    <button
                      type="button"
                      style={styles.loadMoreButton}
                      onClick={() => void loadMore()}
                      disabled={isLoadingMore}
                    >
                      {isLoadingMore ? "Loading..." : "More"}
                    </button>
                  ) : null}
                </>
              ) : friendNotifications.length > 0 ? (
                friendNotifications.map((request) => (
                  <button
                    key={request.friendship_id}
                    type="button"
                    style={styles.notificationItem}
                    onClick={() => {
                      setIsOpen(false);
                      navigate("/chat");
                    }}
                  >
                    <img
                      src={request.peer.profile_image_url || "/default-profile.png"}
                      alt=""
                      style={styles.notificationAvatar}
                    />
                    <span style={styles.notificationItemText}>
                      <strong>{request.peer.user_name} sent you a friend request.</strong>
                      <span>
                        {request.peer.nationality} / {formatGenderLabel(request.peer.gender)}
                      </span>
                      <small>{formatNotificationDate(request.created_at)}</small>
                    </span>
                  </button>
                ))
              ) : (
                <div style={styles.notificationEmpty}>
                  <p style={styles.emptyTitle}>No friend notifications yet.</p>
                  <p style={styles.emptyCopy}>New friend requests will appear here.</p>
                </div>
              )}
            </div>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function NotificationItem({
  item,
  hiding,
  onHide,
  onOpen,
}: {
  item: InboxNotification;
  hiding: boolean;
  onHide: () => void;
  onOpen: () => void;
}) {
  const isUnread = !item.is_read;

  return (
    <div
      style={{
        ...styles.notificationItem,
        ...(isUnread ? styles.unreadItem : styles.readItem),
      }}
    >
      <button type="button" style={styles.notificationMain} onClick={onOpen}>
        <img
          src={item.actor_profile_image_url || "/default-profile.png"}
          alt=""
          style={styles.notificationAvatar}
        />
        <span
          style={{
            ...styles.notificationItemText,
            ...(isUnread ? styles.unreadItemText : styles.readItemText),
          }}
        >
          <strong style={styles.notificationItemTitle}>
            {isUnread ? <span style={styles.unreadDot} /> : null}
            {getNotificationTitle(item)}
          </strong>
          <span style={styles.notificationItemBody}>
            {item.comment_preview || getNotificationSubtitle(item)}
          </span>
          <small>{formatNotificationDate(item.created_at)}</small>
        </span>
        {item.target_preview ? (
          <img src={item.target_preview} alt="" style={styles.targetPreview} />
        ) : null}
      </button>
      <button
        type="button"
        style={styles.hideButton}
        onClick={onHide}
        disabled={hiding}
        aria-label="Hide notification"
      >
        x
      </button>
    </div>
  );
}

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M18 8.8a6 6 0 0 0-12 0c0 7.2-3 7.2-3 7.2h18s-3 0-3-7.2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M13.73 20a2 2 0 0 1-3.46 0"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function getNotificationTitle(item: InboxNotification): string {
  const actor = item.actor_name || "Someone";
  if (item.type === "feed_like") return `${actor} liked your feed post.`;
  if (item.type === "feed_comment") return `${actor} commented on your feed post.`;
  if (item.type === "tripmate_like") return `${actor} liked your tripmate post.`;
  return `${actor} sent a notification.`;
}

function getNotificationSubtitle(item: InboxNotification): string {
  if (item.target_type === "feed_post") return "Feed post";
  if (item.target_type === "tripmate_post") return "Tripmate post";
  return "";
}

function getNotificationPath(item: InboxNotification): string {
  if (item.target_type === "tripmate_post") return "/mate";
  if (item.target_type === "feed_post") return "/my";
  return "/home";
}

function formatNotificationDate(value: string): string {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function formatGenderLabel(gender: string): string {
  if (gender === "male") return "Male";
  if (gender === "female") return "Female";
  return gender;
}

const styles: Record<string, CSSProperties> = {
  notificationButton: {
    position: "relative",
    width: 48,
    height: 48,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "rgba(255,255,255,0.94)",
    color: "var(--brand-primary-deep)",
    boxShadow: "var(--shadow-soft)",
    cursor: "pointer",
    flexShrink: 0,
  },
  notificationBadge: {
    position: "absolute",
    top: -4,
    right: -4,
    minWidth: 20,
    height: 20,
    padding: "0 6px",
    borderRadius: 999,
    display: "grid",
    placeItems: "center",
    background: "#ef4444",
    color: "#ffffff",
    border: "2px solid rgba(255,255,255,0.96)",
    fontSize: "0.64rem",
    fontWeight: 900,
    lineHeight: 1,
  },
  notificationOverlay: {
    position: "fixed",
    inset: 0,
    zIndex: 90,
    background: "rgba(24,26,32,0.26)",
    display: "flex",
    justifyContent: "flex-end",
  },
  notificationPanel: {
    width: "min(390px, 92vw)",
    height: "100dvh",
    padding: "22px 18px 28px",
    background: "rgba(255,255,255,0.98)",
    boxShadow: "-24px 0 54px rgba(24,26,32,0.18)",
    borderLeft: "1px solid var(--border-soft)",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    animation: "slideInFromRight 260ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  notificationHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 14,
  },
  eyebrow: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 800,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
  },
  notificationTitle: {
    margin: "4px 0 0",
    color: "var(--text-primary)",
    fontSize: "1.45rem",
    lineHeight: 1.1,
  },
  notificationCloseButton: {
    width: 38,
    height: 38,
    border: "1px solid rgba(5,181,187,0.16)",
    borderRadius: "50%",
    background: "rgba(255,255,255,0.9)",
    color: "var(--text-secondary)",
    fontWeight: 900,
    cursor: "pointer",
  },
  notificationTabs: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 8,
    padding: 6,
    borderRadius: 18,
    background: "var(--surface-muted)",
  },
  notificationTab: {
    minHeight: 42,
    border: "none",
    borderRadius: 14,
    background: "transparent",
    color: "var(--neutral-700)",
    fontWeight: 900,
    cursor: "pointer",
  },
  notificationTabActive: {
    background: "#ffffff",
    color: "var(--text-primary)",
    boxShadow: "0 8px 20px rgba(24,26,32,0.08)",
  },
  notificationTabBadge: {
    display: "inline-grid",
    placeItems: "center",
    minWidth: 18,
    height: 18,
    marginLeft: 6,
    padding: "0 5px",
    borderRadius: 999,
    background: "var(--brand-secondary)",
    color: "var(--text-primary)",
    fontSize: "0.68rem",
  },
  notificationList: {
    minHeight: 0,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    paddingRight: 2,
  },
  notificationItem: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: 10,
    border: "1px solid var(--border-soft)",
    borderRadius: 18,
    background: "rgba(255,255,255,0.9)",
    color: "var(--text-primary)",
    textAlign: "left",
  },
  unreadItem: {
    borderColor: "rgba(5,181,187,0.38)",
    background: "#ffffff",
    boxShadow: "0 12px 28px rgba(5,181,187,0.11)",
  },
  readItem: {
    borderColor: "rgba(15,23,42,0.08)",
    background: "rgba(24,26,32,0.055)",
    opacity: 0.72,
  },
  notificationMain: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    alignItems: "center",
    gap: 12,
    border: "none",
    background: "transparent",
    padding: 0,
    color: "inherit",
    textAlign: "left",
    cursor: "pointer",
  },
  notificationAvatar: {
    width: 42,
    height: 42,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  notificationItemText: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 3,
    fontSize: "0.82rem",
  },
  unreadItemText: {
    color: "var(--text-primary)",
  },
  readItemText: {
    color: "var(--neutral-700)",
  },
  notificationItemTitle: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    color: "inherit",
    fontSize: "0.88rem",
    lineHeight: 1.25,
  },
  notificationItemBody: {
    color: "inherit",
    lineHeight: 1.35,
    overflowWrap: "anywhere",
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "var(--brand-primary)",
    flexShrink: 0,
  },
  targetPreview: {
    width: 42,
    height: 42,
    borderRadius: 8,
    objectFit: "cover",
    background: "var(--surface-muted)",
    flexShrink: 0,
  },
  hideButton: {
    width: 28,
    height: 28,
    border: "none",
    borderRadius: "50%",
    background: "var(--surface-muted)",
    color: "var(--neutral-700)",
    fontWeight: 900,
    cursor: "pointer",
    flexShrink: 0,
  },
  loadMoreButton: {
    minHeight: 42,
    border: "none",
    borderRadius: 14,
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  notificationEmpty: {
    minHeight: 180,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 22,
    borderRadius: 20,
    background: "var(--surface-muted)",
    textAlign: "center",
  },
  spinner: {
    display: "block",
    width: 42,
    height: 42,
    borderRadius: "50%",
    border: "4px solid rgba(5, 181, 187, 0.16)",
    borderTop: "4px solid var(--brand-primary)",
    animation: "spin 0.8s linear infinite",
  },
  emptyTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontWeight: 900,
  },
  emptyCopy: {
    margin: 0,
    color: "var(--neutral-700)",
    lineHeight: 1.55,
  },
};
