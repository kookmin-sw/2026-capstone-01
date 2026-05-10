import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { getReceivedFriendRequests, type Friendship } from "../api/friend";
import {
  readStoredLikeNotifications,
  type LikeNotification,
} from "../lib/notifications";

type NotificationTab = "likes" | "friends";

export default function NotificationBell() {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [tab, setTab] = useState<NotificationTab>("likes");
  const [likeNotifications, setLikeNotifications] = useState<LikeNotification[]>([]);
  const [friendNotifications, setFriendNotifications] = useState<Friendship[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  async function fetchNotifications(): Promise<void> {
    setIsLoading(true);
    try {
      const friendRequests = await getReceivedFriendRequests();
      setFriendNotifications(friendRequests.items);
      setLikeNotifications(readStoredLikeNotifications());
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void fetchNotifications().catch(() => {
      setFriendNotifications([]);
      setLikeNotifications(readStoredLikeNotifications());
      setIsLoading(false);
    });

    const intervalId = window.setInterval(() => {
      void fetchNotifications().catch(() => setIsLoading(false));
    }, 30000);

    const handleRefresh = () => {
      setLikeNotifications(readStoredLikeNotifications());
      void fetchNotifications().catch(() => setIsLoading(false));
    };

    window.addEventListener("focus", handleRefresh);
    window.addEventListener("storage", handleRefresh);
    window.addEventListener("krip:friend-chat-notifications-updated", handleRefresh);
    window.addEventListener("krip:like-notifications-updated", handleRefresh);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleRefresh);
      window.removeEventListener("storage", handleRefresh);
      window.removeEventListener("krip:friend-chat-notifications-updated", handleRefresh);
      window.removeEventListener("krip:like-notifications-updated", handleRefresh);
    };
  }, []);

  const notificationCount = likeNotifications.length + friendNotifications.length;

  return (
    <>
      <button
        type="button"
        style={styles.notificationButton}
        onClick={() => {
          setIsOpen(true);
          void fetchNotifications().catch(() => setIsLoading(false));
        }}
        aria-label="Open notifications"
      >
        <BellIcon />
        {notificationCount > 0 ? (
          <span style={styles.notificationBadge}>
            {notificationCount > 99 ? "99+" : notificationCount}
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
                  ...(tab === "likes" ? styles.notificationTabActive : {}),
                }}
                onClick={() => setTab("likes")}
              >
                Likes
                {likeNotifications.length > 0 ? (
                  <span style={styles.notificationTabBadge}>{likeNotifications.length}</span>
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
              ) : tab === "likes" ? (
                likeNotifications.length > 0 ? (
                  likeNotifications.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      style={styles.notificationItem}
                      onClick={() => {
                        setIsOpen(false);
                        if (item.path) navigate(item.path);
                      }}
                    >
                      {item.imageUrl ? (
                        <img src={item.imageUrl} alt="" style={styles.notificationAvatar} />
                      ) : (
                        <span style={styles.notificationItemIcon}>L</span>
                      )}
                      <span style={styles.notificationItemText}>
                        <strong>{item.actorName} liked your post.</strong>
                        <span>{item.targetTitle || item.body}</span>
                        <small>{formatNotificationDate(item.createdAt)}</small>
                      </span>
                    </button>
                  ))
                ) : (
                  <div style={styles.notificationEmpty}>
                    <p style={styles.emptyTitle}>No like notifications yet.</p>
                    <p style={styles.emptyCopy}>
                      Tripmate and feed likes will appear here when push data arrives.
                    </p>
                  </div>
                )
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
                      <span>{request.peer.nationality} / {formatGenderLabel(request.peer.gender)}</span>
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
    gap: 12,
    padding: 12,
    border: "1px solid var(--border-soft)",
    borderRadius: 18,
    background: "rgba(255,255,255,0.9)",
    color: "var(--text-primary)",
    textAlign: "left",
    cursor: "pointer",
  },
  notificationItemIcon: {
    width: 42,
    height: 42,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    flexShrink: 0,
    background: "rgba(248,180,0,0.18)",
    color: "var(--text-primary)",
    fontWeight: 900,
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
    display: "flex",
    flexDirection: "column",
    gap: 3,
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
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
