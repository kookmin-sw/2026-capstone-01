import { deleteToken, getMessaging, getToken, isSupported, onMessage } from "firebase/messaging";
import type { MessagePayload } from "firebase/messaging";
import { Capacitor } from "@capacitor/core";
import type { PluginListenerHandle } from "@capacitor/core";
import {
  PushNotifications,
  type ActionPerformed as PushNotificationActionPerformed,
  type PushNotificationSchema,
} from "@capacitor/push-notifications";
import {
  LocalNotifications,
  type ActionPerformed as LocalNotificationActionPerformed,
} from "@capacitor/local-notifications";

import client from "../api/client";
import type { InboxNotification, NotificationType } from "../api/notification";
import { firebaseApp } from "./firebase";
import { rememberLikeNotification } from "./notifications";

const FCM_TOKEN_STORAGE_KEY = "FCMtoken";
const FCM_REGISTERED_TOKEN_STORAGE_KEY = "FCMtokenRegistered";
const PENDING_NOTIFICATION_PATH_STORAGE_KEY = "krip:pending-notification-path";
const PENDING_NOTIFICATION_PATH_TTL_MS = 10 * 60 * 1000;
const DEBUG_FCM_LOG = import.meta.env.DEV && import.meta.env.VITE_DEBUG_FCM_LOG === "true";
const FCM_REGISTER_PATH =
  import.meta.env.VITE_FCM_REGISTER_PATH?.trim() || "/api/notification/fcm-token";
let fcmTokenRegistrationPromise: Promise<string | null> | null = null;
let foregroundMessageListenerStarted = false;
let nativePushSetupPromise: Promise<string | null> | null = null;
let nativePushListenersStarted = false;
let nativePushRegistered = false;
const nativePushListenerHandles: PluginListenerHandle[] = [];

type PushData = Record<string, string>;

type KripPushPayload = {
  notification?: {
    title?: string;
    body?: string;
  };
  data?: PushData;
};

type ToastPayload = {
  title: string;
  body: string;
  path: string;
  imageUrl: string | null;
  notification?: InboxNotification;
};

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

  await persistPushToken(currentToken);
  return currentToken;
}

export function registerFcmToken(): Promise<string | null> {
  if (Capacitor.isNativePlatform()) {
    return registerNativePushNotifications();
  }

  if (!fcmTokenRegistrationPromise) {
    fcmTokenRegistrationPromise = issueAndRegisterFcmToken().finally(() => {
      fcmTokenRegistrationPromise = null;
    });
  }

  return fcmTokenRegistrationPromise;
}

async function persistPushToken(token: string): Promise<void> {
  if (!token) return;

  const registeredToken = localStorage.getItem(FCM_REGISTERED_TOKEN_STORAGE_KEY);
  localStorage.setItem(FCM_TOKEN_STORAGE_KEY, token);

  if (registeredToken === token || !FCM_REGISTER_PATH) {
    return;
  }

  try {
    await client.post(FCM_REGISTER_PATH, { token });
    localStorage.setItem(FCM_REGISTERED_TOKEN_STORAGE_KEY, token);
  } catch (error) {
    if (DEBUG_FCM_LOG) {
      console.warn("Failed to save FCM token to backend", error);
    }
  }
}

function registerNativePushNotifications(): Promise<string | null> {
  if (nativePushRegistered) {
    return Promise.resolve(localStorage.getItem(FCM_TOKEN_STORAGE_KEY));
  }

  if (!nativePushSetupPromise) {
    nativePushSetupPromise = setupNativePushNotifications().finally(() => {
      nativePushSetupPromise = null;
    });
  }

  return nativePushSetupPromise;
}

async function setupNativePushNotifications(): Promise<string | null> {
  if (!Capacitor.isNativePlatform()) return null;

  try {
    await ensureNativePushListeners();
    await ensureNativeNotificationChannels();

    const currentPermission = await PushNotifications.checkPermissions();
    const pushPermission =
      currentPermission.receive === "granted"
        ? currentPermission
        : await PushNotifications.requestPermissions();
    await requestLocalNotificationPermissionIfNeeded();

    if (pushPermission.receive !== "granted") {
      if (DEBUG_FCM_LOG) console.warn("Push notification permission denied");
      return null;
    }

    await PushNotifications.register();
    nativePushRegistered = true;
    return localStorage.getItem(FCM_TOKEN_STORAGE_KEY);
  } catch (error) {
    console.warn("Native push initialization failed", error);
    return null;
  }
}

async function ensureNativePushListeners(): Promise<void> {
  if (nativePushListenersStarted) return;
  nativePushListenersStarted = true;

  nativePushListenerHandles.push(
    await PushNotifications.addListener("registration", (token) => {
      void persistPushToken(token.value);
    })
  );

  nativePushListenerHandles.push(
    await PushNotifications.addListener("registrationError", (error) => {
      if (DEBUG_FCM_LOG) console.warn("Native push registration failed", error);
    })
  );

  nativePushListenerHandles.push(
    await PushNotifications.addListener("pushNotificationReceived", (notification) => {
      handleNotificationPayload(toPayloadFromNativeNotification(notification));
    })
  );

  nativePushListenerHandles.push(
    await PushNotifications.addListener(
      "pushNotificationActionPerformed",
      (event: PushNotificationActionPerformed) => {
        openNotificationPath(
          getNotificationPath(toPayloadFromNativeNotification(event.notification), false)
        );
      }
    )
  );

  nativePushListenerHandles.push(
    await LocalNotifications.addListener(
      "localNotificationActionPerformed",
      (event: LocalNotificationActionPerformed) => {
        const path = getPathFromLocalNotificationAction(event);
        if (path) openNotificationPath(path);
      }
    )
  );
}

async function ensureNativeNotificationChannels(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  const channel = {
    id: "krip-activity",
    name: "Krip activity",
    description: "Likes, comments, tripmate, and chat notifications",
    importance: 4 as const,
    visibility: 1 as const,
    lights: true,
    vibration: true,
  };

  await Promise.allSettled([
    PushNotifications.createChannel(channel),
    LocalNotifications.createChannel(channel),
  ]);
}

async function requestLocalNotificationPermissionIfNeeded(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  if (Capacitor.getPlatform() === "android") {
    const getPlatformVersion = (Capacitor as { getPlatformVersion?: () => string }).getPlatformVersion;
    const androidVersion = Number(getPlatformVersion?.() ?? 0);
    if (androidVersion > 0 && androidVersion < 13) return;
  }

  const permission = await LocalNotifications.checkPermissions().catch(() => null);
  if (permission?.display === "granted") return;

  await LocalNotifications.requestPermissions().catch((error) => {
    if (DEBUG_FCM_LOG) console.warn("Local notification permission request failed", error);
  });
}

export async function unregisterFcmToken(): Promise<void> {
  const storedToken = localStorage.getItem(FCM_TOKEN_STORAGE_KEY);
  localStorage.removeItem(FCM_TOKEN_STORAGE_KEY);
  localStorage.removeItem(FCM_REGISTERED_TOKEN_STORAGE_KEY);
  nativePushRegistered = false;

  if (!storedToken) return;

  try {
    if (FCM_REGISTER_PATH) {
      await client.delete(FCM_REGISTER_PATH, { data: { token: storedToken } });
    }

    if (Capacitor.isNativePlatform()) {
      await PushNotifications.unregister();
      return;
    }

    if (await isSupported()) {
      await deleteToken(getMessaging(firebaseApp));
    }
  } catch (error) {
    if (DEBUG_FCM_LOG) {
      console.warn("Failed to delete FCM token", error);
    }
  }
}

export async function requestPermission(): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    await registerNativePushNotifications();
    return;
  }

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

  if (Capacitor.isNativePlatform()) {
    foregroundMessageListenerStarted = true;
    await ensureNativePushListeners();
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

function handleNotificationPayload(payload: KripPushPayload): void {
  const likeNotification = isLikeNotificationPayload(payload);
  const feedActivityNotification = isFeedActivityNotificationPayload(payload);
  const inboxNotification = toInboxNotification(payload);
  const title = getToastTitle(payload, inboxNotification);
  const body = getToastBody(payload, inboxNotification);
  const roomId =
    payload.data?.chatRoomId ||
    payload.data?.chat_room_id ||
    (!feedActivityNotification && !likeNotification
      ? extractChatRoomId(payload.data?.url)
      : undefined);
  const path =
    roomId
      ? `/chat/${roomId}`
      : likeNotification || feedActivityNotification
        ? getNotificationPath(payload, true)
        : payload.data?.url || payload.data?.path || getNotificationPath(payload, false);
  const imageUrl =
    inboxNotification?.actor_profile_image_url ||
    inboxNotification?.target_preview ||
    payload.data?.actor_profile_image_url ||
    payload.data?.actorProfileImageUrl ||
    payload.data?.target_preview ||
    payload.data?.targetPreview ||
    payload.data?.profile_image_url ||
    payload.data?.profileImageUrl ||
    payload.data?.senderProfileImageUrl ||
    payload.data?.imageUrl ||
    null;

  if (Capacitor.isNativePlatform() && document.visibilityState !== "visible") {
    void scheduleNativeLocalNotification({ title, body, path, imageUrl, notification: inboxNotification }, payload.data);
  }

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
      detail: { toastHandled: true, notification: inboxNotification },
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

function toPayloadFromNativeNotification(
  notification: PushNotificationSchema
): KripPushPayload {
  const data = normalizePushData(notification.data);
  const notificationTitle =
    notification.title || data.title || data.notification_title || data.notificationTitle;
  const notificationBody =
    notification.body || data.body || data.notification_body || data.notificationBody;

  return {
    notification: {
      title: notificationTitle,
      body: notificationBody,
    },
    data,
  };
}

function normalizePushData(value: unknown): PushData {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};

  const normalized = Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key, item]) => key && item != null)
      .map(([key, item]) => [
        key,
        typeof item === "string" ? item : String(item),
      ])
  );

  for (const nestedKey of ["data", "extras", "payload"]) {
    const nestedValue = normalized[nestedKey];
    if (!nestedValue || typeof nestedValue !== "string") continue;

    try {
      const nested = JSON.parse(nestedValue) as unknown;
      Object.assign(normalized, normalizePushData(nested));
    } catch {
      // Some Android extras are plain strings; only JSON-shaped nested data is flattened.
    }
  }

  return normalized;
}

async function scheduleNativeLocalNotification(
  toast: ToastPayload,
  data?: PushData
): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  const permission = await LocalNotifications.checkPermissions().catch(() => null);
  if (permission?.display !== "granted") return;

  await LocalNotifications.schedule({
    notifications: [
      {
        id: Math.floor(Date.now() % 2147483647),
        title: toast.title,
        body: toast.body,
        channelId: "krip-activity",
        autoCancel: true,
        extra: {
          path: toast.path,
          data: data ?? {},
        },
      },
    ],
  }).catch((error) => {
    if (DEBUG_FCM_LOG) console.warn("Failed to show local notification fallback", error);
  });
}

function getPathFromLocalNotificationAction(
  event: LocalNotificationActionPerformed
): string {
  const extra = event.notification.extra as
    | { path?: string; data?: Record<string, unknown> }
    | undefined;
  if (extra?.path) return extra.path;

  return getNotificationPath(
    {
      notification: {
        title: event.notification.title,
        body: event.notification.body,
      },
      data: normalizePushData(extra?.data),
    },
    false
  );
}

function openNotificationPath(path: string): void {
  if (!path) return;

  rememberPendingNotificationPath(path);
  window.dispatchEvent(
    new CustomEvent("krip:notification-open", {
      detail: { path },
    })
  );
}

export function consumePendingNotificationPath(): string {
  const record = readPendingNotificationPath();
  sessionStorage.removeItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY);
  localStorage.removeItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY);
  return record;
}

export function hasPendingNotificationPath(): boolean {
  return Boolean(readPendingNotificationPath());
}

function readPendingNotificationPath(): string {
  const raw = localStorage.getItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as { path?: string; createdAt?: number };
      const isFresh =
        parsed.path &&
        parsed.createdAt &&
        Date.now() - parsed.createdAt < PENDING_NOTIFICATION_PATH_TTL_MS;
      if (isFresh) return parsed.path || "";
    } catch {
      if (raw.startsWith("/")) return raw;
    }
    localStorage.removeItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY);
  }

  return sessionStorage.getItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY) || "";
}

function rememberPendingNotificationPath(path: string): void {
  const record = JSON.stringify({ path, createdAt: Date.now() });
  localStorage.setItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY, record);
  sessionStorage.setItem(PENDING_NOTIFICATION_PATH_STORAGE_KEY, path);
}

function toInboxNotification(payload: KripPushPayload): InboxNotification | undefined {
  const data = payload.data ?? {};
  const type = normalizeNotificationType(
    [
      data.type,
      data.notification_type,
      data.notificationType,
      data.event_type,
      data.eventType,
      data.action,
      data.target_type,
      data.targetType,
      payload.notification?.title,
      payload.notification?.body,
      data.title,
      data.body,
    ]
      .filter(Boolean)
      .join(" ")
  );
  if (!type) return undefined;

  const targetType = data.target_type || data.targetType || "";
  const targetId =
    data.target_id ||
    data.targetId ||
    data.post_id ||
    data.postId ||
    data.feed_post_id ||
    data.feedPostId ||
    "";

  return {
    notification_id:
      data.notification_id ||
      data.notificationId ||
      data.id ||
      `${Date.now()}-${type}-${targetId}`,
    type,
    actor_id: data.actor_id || data.actorId || "",
    actor_name:
      data.actor_name ||
      data.actorName ||
      data.user_name ||
      data.userName ||
      data.sender_name ||
      data.senderName ||
      extractActorName(payload.notification?.title || "", payload.notification?.body || ""),
    actor_profile_image_url:
      data.actor_profile_image_url ||
      data.actorProfileImageUrl ||
      data.profile_image_url ||
      data.profileImageUrl ||
      null,
    target_type: targetType === "tripmate_post" ? "tripmate_post" : "feed_post",
    target_id: targetId,
    comment_id: data.comment_id || data.commentId || null,
    target_preview:
      data.target_preview ||
      data.targetPreview ||
      data.target_preview_url ||
      data.targetPreviewUrl ||
      data.thumbnail_url ||
      data.thumbnailUrl ||
      null,
    comment_preview:
      data.comment_preview ||
      data.commentPreview ||
      data.comment_content ||
      data.commentContent ||
      null,
    is_read: false,
    created_at: data.created_at || data.createdAt || new Date().toISOString(),
  };
}

function normalizeNotificationType(value?: string): NotificationType | undefined {
  if (value === "feed_like" || value === "feed_comment" || value === "tripmate_like") {
    return value;
  }

  const lowerValue = (value || "").toLowerCase();
  if (lowerValue.includes("tripmate") && lowerValue.includes("like")) return "tripmate_like";
  if (lowerValue.includes("comment")) return "feed_comment";
  if (lowerValue.includes("like")) return "feed_like";

  return undefined;
}

function getToastTitle(
  payload: KripPushPayload,
  notification: InboxNotification | undefined
): string {
  if (notification) {
    const actor = notification.actor_name || "Someone";
    if (notification.type === "feed_like") return `${actor} liked your feed post.`;
    if (notification.type === "feed_comment") return `${actor} commented on your feed post.`;
    if (notification.type === "tripmate_like") return `${actor} liked your tripmate post.`;
  }

  return payload.notification?.title || payload.data?.title || "Krip";
}

function getToastBody(
  payload: KripPushPayload,
  notification: InboxNotification | undefined
): string {
  if (notification?.comment_preview) return notification.comment_preview;
  if (notification?.target_type === "feed_post") return "Feed post";
  if (notification?.target_type === "tripmate_post") return "Tripmate post";

  return payload.notification?.body || payload.data?.body || "New notification";
}

function isLikeNotificationPayload(payload: KripPushPayload): boolean {
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

function isFeedActivityNotificationPayload(payload: KripPushPayload): boolean {
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

function getNotificationPath(payload: KripPushPayload, feedNotification: boolean): string {
  const data = payload.data ?? {};
  const roomId = getChatRoomId(data);
  if (roomId) return `/chat/${encodeURIComponent(roomId)}`;

  const explicitPath = getExplicitNotificationPath(data);
  if (explicitPath) return explicitPath;

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

  if (type.includes("chat")) return "/chat";
  if (type.includes("tripmate")) return "/mate";
  if (type.includes("feed") || feedNotification) {
    const targetId =
      data.target_id ||
      data.targetId ||
      data.post_id ||
      data.postId ||
      data.feed_post_id ||
      data.feedPostId;
    return targetId ? `/my?feedPost=${encodeURIComponent(targetId)}` : "/my";
  }

  return "/chat";
}

function getChatRoomId(data: PushData): string | undefined {
  return (
    data.chatRoomId ||
    data.chat_room_id ||
    data.chat_room ||
    data.roomId ||
    data.room_id ||
    extractChatRoomId(data.url) ||
    extractChatRoomId(data.path) ||
    extractChatRoomId(data.click_action) ||
    extractChatRoomId(data.link)
  );
}

function getExplicitNotificationPath(data: PushData): string | undefined {
  const rawPath = data.url || data.path || data.click_action || data.link;
  if (!rawPath) return undefined;

  try {
    const url = new URL(rawPath, window.location.origin);
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return rawPath.startsWith("/") ? rawPath : undefined;
  }
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
