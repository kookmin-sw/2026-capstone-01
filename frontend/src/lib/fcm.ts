import { deleteToken, getMessaging, getToken, isSupported, onMessage } from "firebase/messaging";
import type { MessagePayload } from "firebase/messaging";

import client from "../api/client";
import { firebaseApp } from "./firebase";
import { rememberLikeNotification } from "./notifications";

const FCM_TOKEN_STORAGE_KEY = "FCMtoken";
const DEBUG_FCM_LOG = import.meta.env.DEV && import.meta.env.VITE_DEBUG_FCM_LOG === "true";
const FCM_REGISTER_PATH = import.meta.env.VITE_FCM_REGISTER_PATH?.trim() || "";
let fcmTokenRegistrationPromise: Promise<string | null> | null = null;
let foregroundMessageListenerStarted = false;

async function issueAndRegisterFcmToken(): Promise<string | null> {
  const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY;
  if (!vapidKey || !("Notification" in window)) {
    return null;
  }

  const supported = await isSupported();
  if (!supported) {
    return null;
  }

  if (Notification.permission !== "granted") {
    return null;
  }

  const messaging = getMessaging(firebaseApp);
  const currentToken = await getToken(messaging, {
    vapidKey,
  });

  if (!currentToken) {
    return null;
  }

  const storedToken = localStorage.getItem(FCM_TOKEN_STORAGE_KEY);
  localStorage.setItem(FCM_TOKEN_STORAGE_KEY, currentToken);

  if (storedToken === currentToken) {
    return currentToken;
  }

  if (!FCM_REGISTER_PATH) {
    return currentToken;
  }

  try {
    await client.post(FCM_REGISTER_PATH, {
      token: currentToken,
    });
  } catch (error) {
    if (DEBUG_FCM_LOG) {
      console.warn("Failed to save FCM token to backend", error);
    }
  }

  return currentToken;
}

export function registerFcmToken(): Promise<string | null> {
  if (!fcmTokenRegistrationPromise) {
    fcmTokenRegistrationPromise = issueAndRegisterFcmToken().finally(() => {
      fcmTokenRegistrationPromise = null;
    });
  }

  return fcmTokenRegistrationPromise;
}

export async function unregisterFcmToken(): Promise<void> {
  const storedToken = localStorage.getItem(FCM_TOKEN_STORAGE_KEY);
  localStorage.removeItem(FCM_TOKEN_STORAGE_KEY);

  if (!storedToken) return;

  try {
    if (!(await isSupported())) return;
    await deleteToken(getMessaging(firebaseApp));
    // TODO: call backend FCM unregister endpoint when available.
  } catch (error) {
    if (DEBUG_FCM_LOG) {
      console.warn("Failed to delete FCM token", error);
    }
  }
}

export async function requestPermission(): Promise<void> {
  if (!("Notification" in window) || Notification.permission !== "default") {
    return;
  }

  try {
    const permission = await Notification.requestPermission();

    if (permission === "granted") {
      if (DEBUG_FCM_LOG) console.info("Push permission granted");
      await registerFcmToken();
      return;
    }

    if (permission === "denied") {
      if (DEBUG_FCM_LOG) console.info("Push permission denied");
    }
  } catch (error) {
    if (DEBUG_FCM_LOG) console.warn("Error while requesting push permission", error);
  }
}

export async function listenForegroundMessages(): Promise<void> {
  if (foregroundMessageListenerStarted) {
    return;
  }

  const supported = await isSupported();
  if (!supported) {
    return;
  }

  const messaging = getMessaging(firebaseApp);
  foregroundMessageListenerStarted = true;

  onMessage(messaging, (payload) => {
    if (DEBUG_FCM_LOG) console.info("Received foreground notification");
    handleNotificationPayload(payload);
  });

  navigator.serviceWorker?.addEventListener("message", (event) => {
    const payload =
      event.data?.type === "KRIP_FCM_BACKGROUND_MESSAGE"
        ? event.data.payload
        : null;
    if (!payload) return;

    if (DEBUG_FCM_LOG) console.info("Received background notification message");
    handleNotificationPayload(payload as MessagePayload);
  });
}

function handleNotificationPayload(payload: MessagePayload): void {
  const title = payload.notification?.title || payload.data?.title || "Krip";
  const body = payload.notification?.body || payload.data?.body || "New notification";
  const likeNotification = isLikeNotificationPayload(payload);
  const feedActivityNotification = isFeedActivityNotificationPayload(payload);
  const roomId =
    payload.data?.chatRoomId ||
    payload.data?.chat_room_id ||
    extractChatRoomId(payload.data?.url);
  const path =
    payload.data?.url ||
    payload.data?.path ||
    (roomId
      ? `/chat/${roomId}`
      : getNotificationPath(payload, likeNotification || feedActivityNotification));
  const imageUrl =
    payload.data?.profile_image_url ||
    payload.data?.profileImageUrl ||
    payload.data?.senderProfileImageUrl ||
    payload.data?.imageUrl ||
    null;

  if (likeNotification) {
    rememberLikeNotification({
      id:
        payload.data?.notification_id ||
        payload.data?.notificationId ||
        payload.data?.like_id ||
        payload.data?.likeId ||
        `${Date.now()}-${title}-${body}`,
      actorName:
        payload.data?.actor_name ||
        payload.data?.actorName ||
        payload.data?.liker_name ||
        payload.data?.likerName ||
        payload.data?.user_name ||
        payload.data?.sender_name ||
        extractActorName(title, body),
      targetTitle:
        payload.data?.post_title ||
        payload.data?.postTitle ||
        payload.data?.feed_title ||
        payload.data?.feedTitle ||
        payload.data?.target_title ||
        payload.data?.targetTitle ||
        body,
      body,
      createdAt: payload.data?.created_at || payload.data?.createdAt || new Date().toISOString(),
      path,
      imageUrl,
    });
  }

  window.dispatchEvent(
    new CustomEvent("krip:notification-inbox-updated", {
      detail: { toastHandled: true },
    })
  );

  if (roomId) {
    window.dispatchEvent(
      new CustomEvent("krip:chat-message-toast", {
        detail: {
          roomId,
          path,
          title,
          body,
          imageUrl,
        },
      })
    );
    return;
  }

  window.dispatchEvent(
    new CustomEvent("krip:app-toast", {
      detail: {
        title,
        message: body,
        variant: "info",
        path,
        imageUrl,
      },
    })
  );
}

function isLikeNotificationPayload(payload: MessagePayload): boolean {
  const data = payload.data ?? {};
  const type = [
    data.type,
    data.notification_type,
    data.notificationType,
    data.event_type,
    data.eventType,
    data.action,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const text = `${payload.notification?.title || ""} ${payload.notification?.body || ""} ${
    data.title || ""
  } ${data.body || ""}`.toLowerCase();

  return (
    type.includes("like") ||
    type.includes("liked") ||
    type.includes("post_liked") ||
    type.includes("feed_liked") ||
    text.includes("liked") ||
    text.includes("\uC88B\uC544\uC694") ||
    text.includes("\uC88B\uC544")
  );
}

function isFeedActivityNotificationPayload(payload: MessagePayload): boolean {
  const data = payload.data ?? {};
  const type = [
    data.type,
    data.notification_type,
    data.notificationType,
    data.event_type,
    data.eventType,
    data.action,
    data.target_type,
    data.targetType,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const text = `${payload.notification?.title || ""} ${payload.notification?.body || ""} ${
    data.title || ""
  } ${data.body || ""}`.toLowerCase();

  return (
    type.includes("feed") ||
    type.includes("comment") ||
    type.includes("reply") ||
    text.includes("comment") ||
    text.includes("\uB313\uAE00")
  );
}

function getNotificationPath(payload: MessagePayload, feedNotification: boolean): string {
  const data = payload.data ?? {};
  const type = [
    data.type,
    data.notification_type,
    data.notificationType,
    data.event_type,
    data.eventType,
    data.action,
    data.target_type,
    data.targetType,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (type.includes("tripmate")) return "/mate";
  if (type.includes("feed") || feedNotification) {
    const actorId = data.actor_id || data.actorId || data.user_id || data.userId;
    return actorId ? `/profile/${encodeURIComponent(actorId)}` : "/my";
  }
  return "/chat";
}

function extractActorName(title: string, body: string): string {
  const text = `${title} ${body}`.trim();
  const englishMatch = text.match(/^(.+?)\s+liked\b/i);
  if (englishMatch?.[1]) return englishMatch[1].trim();

  const koreanMatch = text.match(/^(.+?)(?:\uB2D8\uC774|\uC774|\uAC00)\s*.*(?:\uC88B\uC544\uC694|\uC88B\uC544)/);
  if (koreanMatch?.[1]) return koreanMatch[1].trim();

  return "Someone";
}

function extractChatRoomId(url?: string): string | undefined {
  if (!url) return undefined;

  const match = url.match(/\/chat\/([^/?#]+)/);
  return match?.[1];
}
