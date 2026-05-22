import type { CSSProperties } from "react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { NavigateFunction } from "react-router-dom";
import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { confirmTokenSaved, readToken, removeToken, saveToken } from "./utils/tokens";
import AppShell from "./components/AppShell";
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import DeleteAccountTermsPage from "./pages/DeleteAccountTermsPage";
import WithdrawalPendingPage from "./pages/WithdrawalPendingPage";
import HomePage from "./features/tour/HomePage";
import MenuPage from "./pages/MenuPage";
import MatePage from "./features/mate/MatePage";
import ChatPage from "./features/friend-chat/ChatPage";
import ChatRoomPage from "./features/friend-chat/ChatRoomPage";
import { ChatProvider } from "./features/friend-chat/ChatProvider";
import MyPage from "./pages/MyPage";
import HelpInfoPage from "./pages/HelpInfoPage";
import UserFeedPage from "./pages/UserFeedPage";
import SharedPlanPage from "./pages/SharedPlanPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import PlanSelectionPage from "./features/plan/PlanSelectionPage";
import AiPlanDesignPage from "./features/plan/AiPlanDesignPage";
import AiPlanResultPage from "./features/plan/AiPlanResultPage";
import ManualPlanPage from "./features/plan/Manualplanpage";
import "./lib/firebase";
import {
  consumePendingNotificationPath,
  hasPendingNotificationPath,
  listenForegroundMessages,
  unregisterFcmToken,
} from "./lib/fcm";
import type { AppToastDetail } from "./utils/appToast";
import {
  clearPreferences,
  clonePreferences,
  defaultPreferences,
  getSavedPlanById,
  loadPreferences,
  savePreferences,
  type AiPreferenceState,
} from "./api/aiPlanShared";
import {
  getNotificationInbox,
  getNotificationUnreadCount,
  type InboxNotification,
} from "./api/notification";

const DEBUG_AUTH_LOG = import.meta.env.DEV && import.meta.env.VITE_DEBUG_AUTH_LOG === "true";

function AiPlanDesignRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  const planId = new URLSearchParams(location.search).get("planId");
  const [preferences, setPreferences] = useState<AiPreferenceState>(() => {
    const savedPlan = getSavedPlanById(planId);
    if (savedPlan?.type === "ai" && savedPlan.aiPreferences) {
      return clonePreferences(savedPlan.aiPreferences);
    }
    return clonePreferences(defaultPreferences);
  });
  const [isGenerating, setIsGenerating] = useState(false);

  useEffect(() => {
    if (!planId) {
      clearPreferences();
    }
  }, [planId]);

  useEffect(() => {
    savePreferences(preferences);
  }, [preferences]);

  const handleSubmit = async () => {
    setIsGenerating(true);
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    savePreferences(preferences);
    setIsGenerating(false);
    navigate("/plan/ai/result");
  };

  return (
    <AiPlanDesignPage
      value={preferences}
      onBack={() => navigate("/plan")}
      onChange={setPreferences}
      onSubmit={() => void handleSubmit()}
      isGenerating={isGenerating}
    />
  );
}

function AiPlanResultRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  const planId = new URLSearchParams(location.search).get("planId");
  const preferences = useMemo(() => {
    const savedPlan = getSavedPlanById(planId);
    if (savedPlan?.type === "ai" && savedPlan.aiPreferences) {
      return clonePreferences(savedPlan.aiPreferences);
    }
    return clonePreferences(loadPreferences());
  }, [planId]);

  return (
    <AiPlanResultPage
      preferences={preferences}
      onBack={() => navigate("/plan")}
      onEdit={() =>
        navigate(planId ? `/plan/ai?planId=${planId}` : "/plan/ai")
      }
    />
  );
}

function ManualPlanRoute() {
  const navigate = useNavigate();
  return (
    <ManualPlanPage
      onBack={() => navigate("/plan")}
      onHome={() => navigate("/home")}
      onMyPage={() => navigate("/my")}
    />
  );
}

function RouteScrollReset() {
  const location = useLocation();

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [location.pathname]);

  return null;
}

function getToastRoot(): HTMLElement {
  const existing = document.getElementById("krip-toast-root");
  if (existing) return existing;

  const root = document.createElement("div");
  root.id = "krip-toast-root";
  Object.assign(root.style, {
    position: "fixed",
    top: "0",
    left: "0",
    right: "0",
    zIndex: "2147483647",
    pointerEvents: "none",
    isolation: "isolate",
  });
  document.body.appendChild(root);
  return root;
}

type ChatToastState = {
  roomId?: string;
  path?: string;
  title: string;
  body: string;
  imageUrl?: string | null;
  toastId: number;
};

const GESTURE_TAB_PATHS = ["/home", "/plan", "/menu", "/mate", "/my"] as const;
const MIN_HORIZONTAL_SWIPE_PX: number = 96;
const MAX_VERTICAL_SWIPE_PX: number = 32;
const HORIZONTAL_SWIPE_DOMINANCE: number = 2;
const ACTIVITY_TOAST_POLL_INTERVAL_MS: number = 5000;
const DOUBLE_BACK_EXIT_INTERVAL_MS: number = 1800;

type TouchPoint = {
  x: number;
  y: number;
  target: EventTarget | null;
};

function ChatMessageToast() {
  const navigate = useNavigate();
  const [toast, setToast] = useState<ChatToastState | null>(null);
  const [isDismissing, setIsDismissing] = useState(false);
  const toastSequenceRef = useRef(0);
  const dismissTimerRef = useRef<number | undefined>(undefined);
  const removeTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    function handleChatToast(event: Event): void {
      const detail = (event as CustomEvent<ChatToastState>).detail;
      if (!detail?.roomId && !detail?.path) return;

      window.clearTimeout(dismissTimerRef.current);
      window.clearTimeout(removeTimerRef.current);
      setIsDismissing(false);

      toastSequenceRef.current += 1;
      setToast({
        ...detail,
        toastId: toastSequenceRef.current,
      });

      dismissTimerRef.current = window.setTimeout(() => {
        setIsDismissing(true);
        removeTimerRef.current = window.setTimeout(() => {
          setToast(null);
          setIsDismissing(false);
        }, 380);
      }, 3500);
    }

    window.addEventListener("krip:chat-message-toast", handleChatToast);

    return () => {
      window.clearTimeout(dismissTimerRef.current);
      window.clearTimeout(removeTimerRef.current);
      window.removeEventListener("krip:chat-message-toast", handleChatToast);
    };
  }, []);

  if (!toast) return null;

  return createPortal(
    <div style={toastLayerStyles.chatSlot}>
      <button
        key={toast.toastId}
        type="button"
        style={{
          ...chatToastStyles.toast,
          ...(isDismissing
            ? {
                opacity: 0,
                transform: "translateX(-50%) translateY(-8px)",
                transition: "opacity 380ms ease, transform 380ms ease",
              }
            : {}),
        }}
        onClick={() => {
          window.clearTimeout(dismissTimerRef.current);
          window.clearTimeout(removeTimerRef.current);
          const nextPath: string = toast.path || `/chat/${toast.roomId}`;
          window.sessionStorage.setItem("krip:chat-scroll-room", toast.roomId || "");
          navigate(nextPath, { state: { scrollToRecentMessage: true } });
          setToast(null);
          setIsDismissing(false);
        }}
      >
        <span style={chatToastStyles.icon}>
          <img
            src={toast.imageUrl || "/default-profile.png"}
            alt=""
            style={chatToastStyles.iconImage}
          />
        </span>
        <span style={chatToastStyles.text}>
          <strong style={chatToastStyles.title}>{toast.title}</strong>
          <span style={chatToastStyles.body}>{toast.body}</span>
        </span>
        <span style={chatToastStyles.action}>Open</span>
      </button>
    </div>,
    getToastRoot()
  );
}

function PageGestureController() {
  const location = useLocation();
  const navigate = useNavigate();
  const touchStartRef = useRef<TouchPoint | null>(null);

  useEffect(() => {
    function handleTouchStart(event: TouchEvent): void {
      if (event.touches.length !== 1) return;

      const touch: Touch = event.touches[0];
      touchStartRef.current = {
        x: touch.clientX,
        y: touch.clientY,
        target: event.target,
      };
    }

    function handleTouchEnd(event: TouchEvent): void {
      const touchStart: TouchPoint | null = touchStartRef.current;
      touchStartRef.current = null;
      if (!touchStart || event.changedTouches.length !== 1) return;
      if (isGestureIgnored(touchStart.target)) return;

      const touch: Touch = event.changedTouches[0];
      const deltaX: number = touch.clientX - touchStart.x;
      const deltaY: number = touch.clientY - touchStart.y;
      const absoluteDeltaX: number = Math.abs(deltaX);
      const absoluteDeltaY: number = Math.abs(deltaY);

      if (
        absoluteDeltaX >= MIN_HORIZONTAL_SWIPE_PX &&
        absoluteDeltaY <= MAX_VERTICAL_SWIPE_PX &&
        absoluteDeltaX >= absoluteDeltaY * HORIZONTAL_SWIPE_DOMINANCE
      ) {
        moveTabBySwipe(deltaX, location.pathname, navigate);
      }
    }

    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchend", handleTouchEnd);
    };
  }, [location.pathname, navigate]);

  return null;
}

function AndroidBackButtonHandler() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationRef = useRef(location);
  const lastExitBackPressedAtRef = useRef(0);

  useEffect(() => {
    locationRef.current = location;
    lastExitBackPressedAtRef.current = 0;
  }, [location]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    const listenerPromise = CapacitorApp.addListener("backButton", (event) => {
      const backEvent = new CustomEvent("krip:android-back", { cancelable: true });
      window.dispatchEvent(backEvent);
      if (backEvent.defaultPrevented) return;

      const pathname = locationRef.current.pathname;
      if (isDoubleBackExitPath(pathname)) {
        const now = window.performance.now();
        if (now - lastExitBackPressedAtRef.current <= DOUBLE_BACK_EXIT_INTERVAL_MS) {
          void CapacitorApp.exitApp();
          return;
        }

        lastExitBackPressedAtRef.current = now;
        window.dispatchEvent(
          new CustomEvent<AppToastDetail>("krip:app-toast", {
            detail: {
              title: "Press back again to exit",
              variant: "info",
              placement: "center",
            },
          })
        );
        return;
      }

      if (pathname.startsWith("/chat/")) {
        navigate("/mate", { replace: true, state: { mainTab: "chat" } });
        return;
      }

      if (event.canGoBack) {
        navigate(-1);
        return;
      }

      if (pathname !== "/home") {
        navigate("/home", { replace: true });
      }
    });

    return () => {
      void listenerPromise.then((handle) => handle.remove());
    };
  }, [navigate]);

  return null;
}

function isDoubleBackExitPath(pathname: string): boolean {
  return pathname === "/" || pathname === "/login" || pathname === "/home";
}

function ViewportHeightController() {
  useEffect(() => {
    const viewport = window.visualViewport;

    function syncViewportHeight(): void {
      const height = viewport?.height ?? window.innerHeight;
      document.documentElement.style.setProperty("--app-viewport-height", `${height}px`);
    }

    syncViewportHeight();
    window.addEventListener("resize", syncViewportHeight);
    viewport?.addEventListener("resize", syncViewportHeight);
    viewport?.addEventListener("scroll", syncViewportHeight);

    return () => {
      window.removeEventListener("resize", syncViewportHeight);
      viewport?.removeEventListener("resize", syncViewportHeight);
      viewport?.removeEventListener("scroll", syncViewportHeight);
    };
  }, []);

  return null;
}

function ActivityNotificationToastWatcher() {
  const location = useLocation();
  const isAuthFreeRef = useRef(isAuthFreePath(location.pathname));
  const previousUnreadCountRef = useRef<number | null>(null);
  const lastHandledActivityToastAtRef = useRef(0);
  const fallbackToastTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const authFree = isAuthFreePath(location.pathname);
    isAuthFreeRef.current = authFree;
    if (authFree) {
      previousUnreadCountRef.current = null;
    }
  }, [location.pathname]);

  useEffect(() => {
    let cancelled = false;

    async function syncUnreadCount(): Promise<void> {
      if (isAuthFreeRef.current) return;

      try {
        const count = await getNotificationUnreadCount();
        if (cancelled) return;

        const previousCount = previousUnreadCountRef.current;
        previousUnreadCountRef.current = count;

        if (previousCount !== null && count > previousCount) {
          const detectedAt = Date.now();
          window.clearTimeout(fallbackToastTimerRef.current);
          fallbackToastTimerRef.current = window.setTimeout(() => {
            if (lastHandledActivityToastAtRef.current >= detectedAt) return;

            void showLatestNotificationToastFromInbox(detectedAt);
          }, 1000);
        }
      } catch {
        // Ignore transient notification polling failures.
      }
    }

    function handleInboxUpdated(event: Event): void {
      if ((event as CustomEvent<{ toastHandled?: boolean }>).detail?.toastHandled) {
        lastHandledActivityToastAtRef.current = Date.now();
        markActivityToastHandled();
        window.clearTimeout(fallbackToastTimerRef.current);
      }
      void syncUnreadCount();
    }

    function handleFocus(): void {
      void syncUnreadCount();
    }

    void syncUnreadCount();
    const intervalId: number = window.setInterval(
      () => void syncUnreadCount(),
      ACTIVITY_TOAST_POLL_INTERVAL_MS
    );

    window.addEventListener("focus", handleFocus);
    window.addEventListener("krip:like-notifications-updated", handleInboxUpdated);
    window.addEventListener("krip:notification-inbox-updated", handleInboxUpdated);

    return () => {
      cancelled = true;
      window.clearTimeout(fallbackToastTimerRef.current);
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("krip:like-notifications-updated", handleInboxUpdated);
      window.removeEventListener("krip:notification-inbox-updated", handleInboxUpdated);
    };
  }, []);

  return null;
}

async function showLatestNotificationToastFromInbox(detectedAt: number): Promise<void> {
  if (lastActivityToastHandledAt() >= detectedAt) return;

  try {
    const inbox = await getNotificationInbox();
    const notification =
      inbox.notifications.find((item) => !item.is_read) ?? inbox.notifications[0];
    if (!notification || lastActivityToastHandledAt() >= detectedAt) return;

    markActivityToastHandled();
    window.dispatchEvent(
      new CustomEvent<AppToastDetail>("krip:app-toast", {
        detail: {
          title: getInboxNotificationTitle(notification),
          message: getInboxNotificationMessage(notification),
          variant: "info",
          path: getInboxNotificationPath(notification),
          imageUrl:
            notification.actor_profile_image_url ||
            notification.target_preview,
        },
      })
    );
  } catch {
    if (lastActivityToastHandledAt() >= detectedAt) return;

    markActivityToastHandled();
    window.dispatchEvent(
      new CustomEvent<AppToastDetail>("krip:app-toast", {
        detail: {
          title: "New notification",
          message: "Open notifications to view the latest activity.",
          variant: "info",
          path: "/my",
        },
      })
    );
  }
}

function lastActivityToastHandledAt(): number {
  return activityToastHandledAt;
}

function markActivityToastHandled(): void {
  activityToastHandledAt = Date.now();
}

let activityToastHandledAt = 0;

function getInboxNotificationTitle(item: InboxNotification): string {
  const actor = item.actor_name || "Someone";

  if (item.type === "feed_like") return `${actor} liked your feed post.`;
  if (item.type === "feed_comment") return `${actor} commented on your feed post.`;
  if (item.type === "tripmate_like") return `${actor} liked your tripmate post.`;

  return `${actor} sent a notification.`;
}

function getInboxNotificationMessage(item: InboxNotification): string {
  if (item.comment_preview) return item.comment_preview;
  if (item.target_type === "feed_post") return "Feed post";
  if (item.target_type === "tripmate_post") return "Tripmate post";

  return "";
}

function getInboxNotificationPath(item: InboxNotification): string {
  if (item.target_type === "tripmate_post") return "/mate";
  if (item.target_type === "feed_post" && item.target_id) {
    return `/my?feedPost=${encodeURIComponent(item.target_id)}`;
  }
  if (item.target_type === "feed_post") return "/my";

  return "/home";
}
/**
 * Avoid notification requests on auth routes where a user token may not exist.
 */
function isAuthFreePath(pathname: string): boolean {
  return (
    pathname === "/" ||
    pathname === "/login" ||
    pathname.startsWith("/register") ||
    pathname.startsWith("/share/") ||
    pathname === "/withdrawal-pending"
  );
}

/**
 * ?낅젰 以묒씠嫄곕굹 紐⑤떖??議곗옉 以묒씤 ?곗튂???섏씠吏 ?쒖뒪泥섏뿉???쒖쇅?쒕떎.
 */
function isGestureIgnored(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;

  return Boolean(
    target.closest(
      "input, textarea, select, button, a, [role='dialog'], [data-gesture-lock='true']"
    )
  );
}

/**
 * ?섎떒 ??寃쎈줈 ?덉뿉??醫뚯슦 ?ㅼ??댄봽瑜??몄젒 ?섏씠吏 ?대룞?쇰줈 蹂?섑븳??
 */
function moveTabBySwipe(
  deltaX: number,
  currentPath: string,
  navigate: NavigateFunction
): void {
  const currentIndex: number = GESTURE_TAB_PATHS.findIndex((path) =>
    currentPath === path || currentPath.startsWith(`${path}/`)
  );
  if (currentIndex < 0) return;

  const direction: number = deltaX < 0 ? 1 : -1;
  const nextIndex: number = currentIndex + direction;
  const nextPath: string | undefined = GESTURE_TAB_PATHS[nextIndex];
  if (!nextPath) return;

  navigate(nextPath);
}

type AppToastState = AppToastDetail & {
  toastId: number;
};

function AppToast() {
  const navigate = useNavigate();
  const [toast, setToast] = useState<AppToastState | null>(null);
  const toastSequenceRef = useRef(0);

  useEffect(() => {
    let timeoutId: number | undefined;

    function handleAppToast(event: Event): void {
      const detail = (event as CustomEvent<AppToastDetail>).detail;
      if (!detail?.title) return;

      toastSequenceRef.current += 1;
      setToast({
        ...detail,
        variant: detail.variant ?? "info",
        toastId: toastSequenceRef.current,
      });
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(() => setToast(null), 3600);
    }

    window.addEventListener("krip:app-toast", handleAppToast);

    return () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      window.removeEventListener("krip:app-toast", handleAppToast);
    };
  }, []);

  if (!toast) return null;
  const ToastElement = toast.path ? "button" : "div";
  const isCenteredToast = toast.placement === "center";

  return createPortal(
    <div style={isCenteredToast ? toastLayerStyles.appCenterSlot : toastLayerStyles.appSlot}>
      <ToastElement
        key={toast.toastId}
        type={toast.path ? "button" : undefined}
        role="status"
        style={{
          ...appToastStyles.toast,
          ...(isCenteredToast ? appToastStyles.toastCentered : {}),
          ...(toast.path ? appToastStyles.toastClickable : {}),
          ...(toast.variant === "error" ? appToastStyles.toastError : {}),
          ...(toast.variant === "success" ? appToastStyles.toastSuccess : {}),
        }}
        onClick={() => {
          if (!toast.path) return;
          navigate(toast.path);
          setToast(null);
        }}
      >
        {toast.imageUrl ? (
          <img src={toast.imageUrl} alt="" style={appToastStyles.avatar} />
        ) : (
          <span
            style={{
              ...appToastStyles.indicator,
              ...(toast.variant === "error" ? appToastStyles.indicatorError : {}),
              ...(toast.variant === "success" ? appToastStyles.indicatorSuccess : {}),
            }}
          />
        )}
        <span style={appToastStyles.text}>
          <strong style={appToastStyles.title}>{toast.title}</strong>
          {toast.message ? <span style={appToastStyles.body}>{toast.message}</span> : null}
        </span>
        {toast.path ? <span style={appToastStyles.action}>Open</span> : null}
      </ToastElement>
    </div>,
    getToastRoot()
  );
}

function NotificationOpenNavigator() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let pendingCheckAttempts = 0;

    function openPath(path: string): void {
      if (!path) return;

      const roomId = path.match(/^\/chat\/([^/?#]+)/)?.[1];
      if (roomId) {
        window.sessionStorage.setItem("krip:chat-scroll-room", decodeURIComponent(roomId));
      }

      navigate(path, { replace: true });
    }

    function handleNotificationOpen(event: Event): void {
      const path = (event as CustomEvent<{ path?: string }>).detail?.path;
      if (!path) return;
      if (!readToken()) return;

      if (location.pathname !== "/home") {
        navigate("/home", { replace: true });
        window.setTimeout(() => {
          window.dispatchEvent(new Event("krip:auth-ready"));
        }, 80);
        return;
      }

      consumePendingNotificationPath();
      openPath(path);
    }

    function openPendingPath(): boolean {
      if (!hasPendingNotificationPath()) return false;
      if (!readToken()) return false;
      if (location.pathname !== "/home") return false;

      const pendingPath = consumePendingNotificationPath();
      if (!pendingPath) return false;

      openPath(pendingPath);
      return true;
    }

    window.addEventListener("krip:notification-open", handleNotificationOpen);
    window.addEventListener("krip:auth-ready", openPendingPath);
    window.addEventListener("focus", openPendingPath);
    window.setTimeout(openPendingPath, 0);
    const pendingCheckInterval = window.setInterval(() => {
      pendingCheckAttempts += 1;
      if (openPendingPath() || pendingCheckAttempts >= 30) {
        window.clearInterval(pendingCheckInterval);
      }
    }, 100);

    return () => {
      window.clearInterval(pendingCheckInterval);
      window.removeEventListener("krip:notification-open", handleNotificationOpen);
      window.removeEventListener("krip:auth-ready", openPendingPath);
      window.removeEventListener("focus", openPendingPath);
    };
  }, [location.pathname, navigate]);

  return null;
}

/**
 * Handles the JWT deep link callback from the native Google OAuth flow.
 * The backend redirects to krip://auth/callback?utk=...&status=...&email=...&name=...
 * after the user authenticates. This component captures that URL, saves the token,
 * and navigates to the appropriate screen.
 */
function AppUrlOpenHandler() {
  const navigate = useNavigate();
  const handledUrlRef = useRef("");

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    async function handleAppUrlOpen(url?: string): Promise<void> {
      if (!url || handledUrlRef.current === url) return;
      handledUrlRef.current = url;

      if (DEBUG_AUTH_LOG) {
        console.info(
          "[auth] appUrlOpen received",
          JSON.stringify({ pathname: getSafeUrlPathname(url) })
        );
      }
      if (!url.startsWith("krip://")) return;

      const callback = parseAuthCallbackUrl(url);
      if (!callback) {
        console.warn("[auth] appUrlOpen ignored non-auth callback");
        return;
      }

      const { utk, status, email, name } = callback;

      if (DEBUG_AUTH_LOG) {
        console.info(
          "[auth] appUrlOpen parsed",
          JSON.stringify({
            status,
            hasToken: Boolean(utk),
            hasEmail: Boolean(email),
            hasName: Boolean(name),
          })
        );
      }

      if (!utk) {
        removeToken();
        navigate("/login", { replace: true });
        void closeAuthBrowser();
        return;
      }

      saveToken(utk);
      const hasSavedToken = await confirmTokenSaved(utk);

      if (!hasSavedToken) {
        console.error("[auth] token save failed");
        void closeAuthBrowser();
        return;
      }
      if (status === "complete") {
        if (hasPendingNotificationPath()) {
          navigate("/home", { replace: true });
          window.setTimeout(() => {
            window.dispatchEvent(new Event("krip:auth-ready"));
          }, 120);
          void closeAuthBrowser();
          return;
        }
        navigate("/home", { replace: true });
      } else if (status === "new" || status === "in_progress") {
        navigate("/register", { state: { email, name }, replace: true });
      } else if (status === "withdrawal_pending") {
        navigate("/withdrawal-pending", { replace: true });
      }

      void closeAuthBrowser();
    }

    const listenerPromise = CapacitorApp.addListener("appUrlOpen", (data) => {
      void handleAppUrlOpen(data.url);
    });
    void CapacitorApp.getLaunchUrl().then((data) => handleAppUrlOpen(data?.url));

    return () => {
      void listenerPromise.then((handle) => handle.remove());
    };
  }, [navigate]);

  return null;
}

function getSafeUrlPathname(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return "";
  }
}

async function closeAuthBrowser(): Promise<void> {
  try {
    await Browser.close();
  } catch {
    // The browser may already be closed by the OS deep link handoff.
  }
}

function parseAuthCallbackUrl(
  url: string
): { utk: string; status: string; email: string; name: string } | null {
  const callbackPrefix = "krip://auth/callback";
  if (!url.startsWith(callbackPrefix)) return null;

  const queryStart = url.indexOf("?");
  const query = queryStart >= 0 ? url.slice(queryStart + 1) : "";
  const params = new URLSearchParams(query);

  return {
    utk: params.get("utk") ?? "",
    status: params.get("status") ?? "",
    email: params.get("email") ?? "",
    name: params.get("name") ?? "",
  };
}

/**
 * Listens for 403 Forbidden API responses and navigates to the registration
 * screen. A 403 means the user is authenticated but has not completed
 * registration (incomplete profile).
 */
function ForbiddenRedirect() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationRef = useRef(location);

  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  useEffect(() => {
    function handleForbidden(): void {
      const currentLocation = locationRef.current;
      // Avoid redirect loops on auth-free paths
      if (
        currentLocation.pathname === "/register" ||
        isAuthFreePath(currentLocation.pathname)
      ) {
        return;
      }
      navigate("/register", { replace: true });
    }

    window.addEventListener("krip:forbidden", handleForbidden);

    return () => {
      window.removeEventListener("krip:forbidden", handleForbidden);
    };
  }, [navigate]);

  return null;
}

function WithdrawalPendingRedirect() {
  const navigate = useNavigate();

  useEffect(() => {
    function handleWithdrawalPending(): void {
      navigate("/withdrawal-pending", { replace: true });
    }

    window.addEventListener("krip:withdrawal-pending", handleWithdrawalPending);

    return () => {
      window.removeEventListener("krip:withdrawal-pending", handleWithdrawalPending);
    };
  }, [navigate]);

  return null;
}

function UnauthorizedRedirect() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationRef = useRef(location);

  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  useEffect(() => {
    function handleUnauthorized(): void {
      const currentLocation = locationRef.current;
      if (isAuthFreePath(currentLocation.pathname)) return;

      void unregisterFcmToken();

      if (Capacitor.isNativePlatform()) {
        window.location.replace("/login");
        return;
      }

      navigate("/login", {
        replace: true,
        state: {
          from: `${currentLocation.pathname}${currentLocation.search}${currentLocation.hash}`,
        },
      });
    }

    window.addEventListener("krip:unauthorized", handleUnauthorized);

    return () => {
      window.removeEventListener("krip:unauthorized", handleUnauthorized);
    };
  }, [navigate]);

  return null;
}

export default function App() {
  useEffect(() => {
    listenForegroundMessages().catch((error) => {
      console.warn("Failed to listen for foreground FCM messages", error);
    });
  }, []);

  return (
    <BrowserRouter>
      <ChatProvider>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<OnboardingPage />} />
          <Route path="/register/onboarding" element={<Navigate to="/register" replace />} />
          <Route path="/withdrawal-pending" element={<WithdrawalPendingPage />} />
          <Route element={<AppShell />}>
            <Route path="/home" element={<HomePage />} />
            <Route path="/plan" element={<PlanSelectionPage />} />
            <Route path="/plan/ai" element={<AiPlanDesignRoute />} />
            <Route path="/plan/ai/result" element={<AiPlanResultRoute />} />
            <Route path="/plan/manual" element={<ManualPlanRoute />} />
            <Route path="/menu" element={<MenuPage />} />
            <Route path="/mate" element={<MatePage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/my" element={<MyPage />} />
            <Route path="/help" element={<HelpInfoPage />} />
            <Route path="/account/delete" element={<DeleteAccountTermsPage />} />
            <Route path="/profile/:id" element={<UserFeedPage />} />
            <Route path="/spots/:id" element={<PlaceholderPage />} />
          </Route>
          <Route path="/share/plan/:shareToken" element={<SharedPlanPage />} />
          <Route path="/chat/:id" element={<ChatRoomPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <AppUrlOpenHandler />
        <ForbiddenRedirect />
        <WithdrawalPendingRedirect />
        <UnauthorizedRedirect />
        <AndroidBackButtonHandler />
        <ViewportHeightController />
        <RouteScrollReset />
        <PageGestureController />
        <ActivityNotificationToastWatcher />
        <AppToast />
        <ChatMessageToast />
        <NotificationOpenNavigator />
      </ChatProvider>
    </BrowserRouter>
  );
}

const appLayoutStyles: Record<string, CSSProperties> = {
  safeAreaRoot: {
    minHeight: "var(--app-viewport-height)",
    width: "100%",
    minWidth: "var(--app-design-width)",
    paddingLeft: "var(--app-safe-left)",
    paddingRight: "var(--app-safe-right)",
  },
};

const toastLayerStyles: Record<string, CSSProperties> = {
  appSlot: {
    position: "relative",
    zIndex: 2,
  },
  appCenterSlot: {
    position: "fixed",
    inset: 0,
    zIndex: 2147483647,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    pointerEvents: "none",
  },
  chatSlot: {
    position: "relative",
    zIndex: 1,
  },
};

const chatToastStyles: Record<string, CSSProperties> = {
  toast: {
    position: "fixed",
    top: "calc(var(--app-safe-top) + 16px)",
    left: "50%",
    transform: "translateX(-50%)",
    animation: "slideDownToast 650ms cubic-bezier(0.22, 1, 0.36, 1)",
    zIndex: 2147483646,
    width: "min(calc(100% - 32px), 420px)",
    minHeight: 68,
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 22,
    background: "rgba(255,255,255,0.96)",
    boxShadow: "0 20px 46px rgba(24,26,32,0.16)",
    backdropFilter: "blur(16px)",
    cursor: "pointer",
    textAlign: "left",
    pointerEvents: "auto",
  },
  icon: {
    width: 40,
    height: 40,
    borderRadius: "50%",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    flexShrink: 0,
    overflow: "hidden",
  },
  iconImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  text: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 3,
  },
  title: {
    color: "var(--text-primary)",
    fontSize: "0.94rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  body: {
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
    fontWeight: 700,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  action: {
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 900,
    flexShrink: 0,
  },
};

const appToastStyles: Record<string, CSSProperties> = {
  toast: {
    position: "fixed",
    top: "calc(16px + var(--app-safe-top))",
    left: "50%",
    transform: "translateX(-50%)",
    animation: "slideDownToast 650ms cubic-bezier(0.22, 1, 0.36, 1)",
    zIndex: 2147483647,
    width: "min(calc(100% - 32px), 380px)",
    minHeight: 58,
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 18,
    background: "rgba(255,255,255,0.97)",
    boxShadow:
      "0 26px 64px rgba(15,23,42,0.26), 0 8px 20px rgba(15,23,42,0.14)",
    backdropFilter: "blur(16px)",
    pointerEvents: "auto",
    textAlign: "left",
  },
  toastClickable: {
    cursor: "pointer",
  },
  toastCentered: {
    position: "relative",
    top: "auto",
    left: "auto",
    transform: "none",
    animation: "fadeInToast 240ms ease-out",
    width: "min(calc(100% - 32px), 360px)",
    boxShadow: "0 24px 70px rgba(15,23,42,0.26), 0 10px 24px rgba(15,23,42,0.16)",
  },
  toastSuccess: {
    borderColor: "rgba(5,181,187,0.26)",
  },
  toastError: {
    borderColor: "rgba(220,38,38,0.24)",
  },
  indicator: {
    width: 10,
    height: 10,
    borderRadius: "50%",
    background: "var(--brand-primary)",
    flexShrink: 0,
  },
  indicatorSuccess: {
    background: "var(--brand-primary)",
  },
  indicatorError: {
    background: "#dc2626",
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  text: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 3,
  },
  title: {
    color: "var(--text-primary)",
    fontSize: "0.92rem",
  },
  body: {
    color: "var(--neutral-700)",
    fontSize: "0.8rem",
    fontWeight: 700,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  action: {
    color: "var(--brand-primary-deep)",
    fontSize: "0.76rem",
    fontWeight: 900,
    flexShrink: 0,
  },
};
