import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { getMyProfile } from "../api/auth/auth";
import { getReceivedFriendRequests } from "../api/friend";
import { registerFcmToken } from "../lib/fcm";

const TAB_ITEMS = [
  { to: "/home", label: "Home", icon: "H" },
  { to: "/plan", label: "Plan", icon: "P" },
  { to: "/menu", label: "Menu", icon: "M" },
  { to: "/mate", label: "Mate", icon: "T" },
  { to: "/chat", label: "Friend/Chat", icon: "C" },
] as const;

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const isFriendChatRoute =
    location.pathname === "/chat" || location.pathname.startsWith("/chat/");
  const [friendChatNotificationCount, setFriendChatNotificationCount] = useState(0);

  useEffect(() => {
    getMyProfile()
      .then(() =>
        registerFcmToken()
          .catch((error) => {
            console.warn("Failed to register FCM token", error);
          })
      )
      .catch((error) => {
        if (isWithdrawalPendingError(error)) {
          navigate("/withdrawal-pending", { replace: true });
          return;
        }

        console.warn("Failed to load /api/auth/profile/me", error);
      });
  }, [navigate]);

  useEffect(() => {
    if (isFriendChatRoute) {
      return undefined;
    }

    let isMounted = true;

    async function refreshFriendChatNotifications(): Promise<void> {
      const chatUnreadCount = readStoredChatUnreadCount();

      try {
        const receivedRequests = await getReceivedFriendRequests();
        if (!isMounted) return;
        setFriendChatNotificationCount(receivedRequests.items.length + chatUnreadCount);
      } catch {
        if (!isMounted) return;
        setFriendChatNotificationCount(chatUnreadCount);
      }
    }

    void refreshFriendChatNotifications();

    const intervalId = window.setInterval(() => {
      void refreshFriendChatNotifications();
    }, 30000);

    const handleRefresh = () => void refreshFriendChatNotifications();
    window.addEventListener("focus", handleRefresh);
    window.addEventListener("storage", handleRefresh);
    window.addEventListener("krip:friend-chat-notifications-updated", handleRefresh);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleRefresh);
      window.removeEventListener("storage", handleRefresh);
      window.removeEventListener("krip:friend-chat-notifications-updated", handleRefresh);
    };
  }, [isFriendChatRoute]);

  return (
    <div style={styles.shell}>
      <div style={styles.content}>
        <Outlet />
      </div>

      <nav style={styles.nav}>
        {TAB_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={({ isActive }) => ({
              ...styles.navItem,
              ...(isActive ? styles.navItemActive : {}),
            })}
          >
            <span style={styles.navIconWrap}>
              <span style={styles.navIcon}>{item.icon}</span>
              {item.to === "/chat" && friendChatNotificationCount > 0 ? (
                <span style={styles.notificationBadge}>
                  {friendChatNotificationCount > 99 ? "99+" : friendChatNotificationCount}
                </span>
              ) : null}
            </span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function isWithdrawalPendingError(error: unknown): boolean {
  const apiError = error as {
    status?: number;
    response?: {
      status?: number;
      data?: {
        status?: string;
      };
    };
  };

  return (
    apiError.status === 419 ||
    (apiError.response?.status === 419 &&
      (!apiError.response.data?.status ||
        apiError.response.data.status === "withdrawal_pending"))
  );
}

function readStoredChatUnreadCount(): number {
  const directKeys = ["krip-chat-unread-count", "krip:chat-unread-count"];
  const mapKeys = ["krip-chat-unread", "krip:chat-unread", "krip-chat-unread-by-room"];

  const directCount = directKeys.reduce((sum, key) => {
    const value = Number(window.localStorage.getItem(key) || 0);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);

  const mapCount = mapKeys.reduce((sum, key) => {
    const raw = window.localStorage.getItem(key);
    if (!raw) return sum;

    try {
      const value = JSON.parse(raw) as unknown;
      if (typeof value === "number") return sum + value;
      if (!value || typeof value !== "object") return sum;

      return (
        sum +
        Object.values(value as Record<string, unknown>).reduce<number>((roomSum, roomValue) => {
          const count = Number(roomValue || 0);
          return roomSum + (Number.isFinite(count) ? count : 0);
        }, 0)
      );
    } catch {
      const value = Number(raw);
      return sum + (Number.isFinite(value) ? value : 0);
    }
  }, 0);

  return Math.max(0, directCount + mapCount);
}

const styles: Record<string, CSSProperties> = {
  shell: {
    minHeight: "var(--app-viewport-height)",
    width: "100%",
    minWidth: "var(--app-design-width)",
    background: "transparent",
  },
  content: {
    minHeight: "var(--app-viewport-height)",
    paddingBottom: "calc(96px + var(--app-safe-bottom))",
  },
  nav: {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    display: "grid",
    gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
    gap: 12,
    paddingLeft: "var(--app-safe-left)",
    paddingRight: "var(--app-safe-right)",
    paddingBottom: "calc(10px + var(--app-safe-bottom))",
    background: "rgba(255,255,255,0.94)",
    border: "1px solid var(--border-soft)",
    backdropFilter: "blur(16px)",
    zIndex: 15,
  },
  navItem: {
    textDecoration: "none",
    color: "var(--neutral-700)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    minHeight: 58,
    borderRadius: 18,
    fontSize: "0.7rem",
    fontWeight: 800,
    lineHeight: 1.1,
  },
  navItemActive: {
    background:
      "linear-gradient(135deg, rgba(5, 181, 187, 0.16), rgba(248, 180, 0, 0.18))",
    color: "var(--text-primary)",
  },
  navIconWrap: {
    position: "relative",
    display: "grid",
    placeItems: "center",
  },
  navIcon: {
    width: 20,
    height: 20,
    borderRadius: "50%",
    background: "rgba(1,192,192,0.12)",
    color: "var(--brand-primary-deep)",
    display: "grid",
    placeItems: "center",
    fontSize: "0.72rem",
    lineHeight: 1,
  },
  notificationBadge: {
    position: "absolute",
    top: -7,
    right: -11,
    minWidth: 18,
    height: 18,
    padding: "0 5px",
    borderRadius: 999,
    display: "grid",
    placeItems: "center",
    background: "#ef4444",
    color: "#ffffff",
    border: "2px solid rgba(255,255,255,0.96)",
    fontSize: "0.62rem",
    fontWeight: 900,
    lineHeight: 1,
  },
};
