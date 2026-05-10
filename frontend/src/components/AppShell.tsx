import type { CSSProperties } from "react";
import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { getMyProfile } from "../api/auth/auth";
import { registerFcmToken } from "../lib/fcm";

const TAB_ITEMS = [
  { to: "/home", label: "Home", icon: "home" },
  { to: "/plan", label: "Plan", icon: "calendar" },
  { to: "/menu", label: "Menu", icon: "grid" },
  { to: "/mate", label: "Mate", icon: "mate" },
  { to: "/my", label: "My Page", icon: "my" },
] as const;

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const currentPath = location.pathname;

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
            aria-label={item.label}
            style={({ isActive }) => ({
              ...styles.navItem,
              ...(isActive || (item.to === "/my" && currentPath.startsWith("/profile/"))
                ? styles.navItemActive
                : {}),
            })}
          >
            <span style={styles.navIconWrap}>
              <NavIcon name={item.icon} />
            </span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function NavIcon({ name }: { name: (typeof TAB_ITEMS)[number]["icon"] }) {
  return (
    <svg
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
      style={styles.navIcon}
    >
      {name === "home" ? (
        <path d="M10 30.5 32 11l22 19.5V55a4 4 0 0 1-4 4H39V43a4 4 0 0 0-4-4h-6a4 4 0 0 0-4 4v16H14a4 4 0 0 1-4-4V30.5Z" />
      ) : null}
      {name === "grid" ? (
        <>
          <rect x="10" y="10" width="18" height="18" rx="5" />
          <rect x="36" y="10" width="18" height="18" rx="5" />
          <rect x="10" y="36" width="18" height="18" rx="5" />
          <rect x="36" y="36" width="18" height="18" rx="5" />
        </>
      ) : null}
      {name === "calendar" ? (
        <>
          <rect x="11" y="14" width="42" height="42" rx="8" />
          <rect x="11" y="22" width="42" height="5" />
          <rect x="20" y="8" width="5" height="13" rx="2.5" />
          <rect x="39" y="8" width="5" height="13" rx="2.5" />
          {[20, 32, 44].map((x) =>
            [34, 45].map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2.6" fill="#ffffff" />)
          )}
        </>
      ) : null}
      {name === "mate" ? (
        <>
          <circle cx="26" cy="25" r="11" />
          <circle cx="42" cy="24" r="9" opacity="0.75" />
          <path d="M10 51c0-10 8-17 20-17s20 7 20 17c0 6-40 6-40 0Z" />
          <path d="M37 39c8 1 15 6 15 13 0 4-8 6-17 5 5-3 7-9 2-18Z" opacity="0.75" />
        </>
      ) : null}
      {name === "my" ? (
        <>
          <circle cx="32" cy="22" r="13" />
          <path d="M10 56c0-13 9.8-22 22-22s22 9 22 22c0 5-44 5-44 0Z" />
        </>
      ) : null}
    </svg>
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

const styles: Record<string, CSSProperties> = {
  shell: {
    minHeight: "var(--app-viewport-height)",
    width: "100%",
    background: "transparent",
    overflowX: "hidden",
  },
  content: {
    minHeight: "var(--app-viewport-height)",
    paddingBottom: "var(--app-bottom-nav-reserved)",
  },
  nav: {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    width: "auto",
    display: "grid",
    gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
    gap: 8,
    paddingLeft: "var(--app-safe-left)",
    paddingRight: "var(--app-safe-right)",
    paddingBottom: "var(--app-safe-bottom)",
    background: "rgba(255,255,255,0.94)",
    border: "1px solid var(--border-soft)",
    backdropFilter: "blur(16px)",
    zIndex: 15,
  },
  navItem: {
    textDecoration: "none",
    color: "#a9a9a9",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "var(--app-bottom-nav-height)",
  },
  navItemActive: {
    color: "#01C0C0",
  },
  navIconWrap: {
    position: "relative",
    display: "grid",
    placeItems: "center",
  },
  navIcon: {
    width: 40,
    height: 40,
    display: "block",
    fill: "currentColor",
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
