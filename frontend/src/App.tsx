import type { CSSProperties } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate,} from "react-router-dom";
import AppShell from "./components/AppShell";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import OnboardingPage from "./pages/OnboardingPage";
import WithdrawalPendingPage from "./pages/WithdrawalPendingPage";
import HomePage from "./features/tour/HomePage";
import MenuPage from "./pages/MenuPage";
import MatePage from "./features/mate/MatePage";
import ChatPage from "./features/friend-chat/ChatPage";
import ChatRoomPage from "./features/friend-chat/ChatRoomPage";
import { ChatProvider } from "./features/friend-chat/ChatProvider";
import MyPage from "./pages/MyPage";
import UserFeedPage from "./pages/UserFeedPage";
import SharedPlanPage from "./pages/SharedPlanPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import PlanSelectionPage from "./features/plan/PlanSelectionPage";
import AiPlanDesignPage from "./features/plan/AiPlanDesignPage";
import AiPlanResultPage from "./features/plan/AiPlanResultPage";
import ManualPlanPage from "./features/plan/Manualplanpage";
import "./lib/firebase";
import { listenForegroundMessages, requestPermission } from "./lib/fcm";
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
  return <ManualPlanPage onBack={() => navigate("/plan")} />;
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

function ChatMessageToast() {
  const navigate = useNavigate();
  const [toast, setToast] = useState<ChatToastState | null>(null);
  const toastSequenceRef = useRef(0);

  useEffect(() => {
    let timeoutId: number | undefined;
    let animationFrameId: number | undefined;

    function handleChatToast(event: Event): void {
      const detail = (event as CustomEvent<ChatToastState>).detail;
      if (!detail?.roomId && !detail?.path) return;

      toastSequenceRef.current += 1;
      setToast(null);
      if (animationFrameId) {
        window.cancelAnimationFrame(animationFrameId);
      }
      animationFrameId = window.requestAnimationFrame(() => {
        setToast({
          ...detail,
          toastId: toastSequenceRef.current,
        });
      });
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(() => setToast(null), 4200);
    }

    window.addEventListener("krip:chat-message-toast", handleChatToast);

    return () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      if (animationFrameId) {
        window.cancelAnimationFrame(animationFrameId);
      }
      window.removeEventListener("krip:chat-message-toast", handleChatToast);
    };
  }, []);

  if (!toast) return null;

  return createPortal(
    <div style={toastLayerStyles.chatSlot}>
      <button
        key={toast.toastId}
        type="button"
        style={chatToastStyles.toast}
        onClick={() => {
          navigate(toast.path || `/chat/${toast.roomId}`);
          setToast(null);
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

  return createPortal(
    <div style={toastLayerStyles.appSlot}>
      <ToastElement
        key={toast.toastId}
        type={toast.path ? "button" : undefined}
        role="status"
        style={{
          ...appToastStyles.toast,
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

export default function App() {
  useEffect(() => {
    void requestPermission();
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
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/register/onboarding" element={<OnboardingPage />} />
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
            <Route path="/profile/:id" element={<UserFeedPage />} />
          </Route>
          <Route path="/share/plan/:shareToken" element={<SharedPlanPage />} />
          <Route path="/chat/:id" element={<ChatRoomPage />} />
          <Route path="/spots/:id" element={<PlaceholderPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <WithdrawalPendingRedirect />
        <AppToast />
        <ChatMessageToast />
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
    boxShadow: "0 18px 42px rgba(24,26,32,0.16)",
    backdropFilter: "blur(16px)",
    pointerEvents: "auto",
    textAlign: "left",
  },
  toastClickable: {
    cursor: "pointer",
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
