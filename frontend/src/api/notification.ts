import client from "./client";

export type NotificationType = "feed_like" | "feed_comment" | "tripmate_like";
export type NotificationTargetType = "feed_post" | "tripmate_post";

export interface InboxNotification {
  notification_id: string;
  type: NotificationType;
  actor_id: string;
  actor_name: string;
  actor_profile_image_url: string | null;
  target_type: NotificationTargetType;
  target_id: string;
  comment_id: string | null;
  target_preview: string | null;
  comment_preview: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationInboxResponse {
  notifications: InboxNotification[];
  next_cursor: string | null;
}

export interface NotificationUnreadCountResponse {
  unread_count: number;
}

const HIDDEN_NOTIFICATION_STORAGE_KEY = "krip-hidden-notification-ids";
const HIDDEN_NOTIFICATION_TTL_MS = 30 * 24 * 60 * 60 * 1000;

type HiddenNotificationRecord = {
  hiddenAt: number;
};

type RawInboxNotification = Partial<InboxNotification> & {
  id?: string;
  _id?: string;
  inbox_item_id?: string;
  inboxItemId?: string;
  notificationId?: string;
};

export async function getNotificationInbox(
  cursor?: string
): Promise<NotificationInboxResponse> {
  const { data } = await client.get<
    Omit<NotificationInboxResponse, "notifications"> & {
      notifications?: RawInboxNotification[];
      items?: RawInboxNotification[];
    }
  >("/api/notification/inbox", {
    params: cursor ? { cursor } : undefined,
    useConfiguredBearer: true,
  });

  const rawNotifications = Array.isArray(data.notifications)
    ? data.notifications
    : Array.isArray(data.items)
      ? data.items
      : [];

  return {
    notifications: rawNotifications
      .map(normalizeInboxNotification)
      .filter((notification) => !isNotificationHidden(notification.notification_id)),
    next_cursor: data.next_cursor ?? null,
  };
}

export async function getNotificationUnreadCount(): Promise<number> {
  const { data } = await client.get<NotificationUnreadCountResponse>(
    "/api/notification/inbox/unread-count",
    { useConfiguredBearer: true }
  );
  return Math.min(999, Math.max(0, Number(data.unread_count || 0)));
}

export async function hideNotification(notificationId: string): Promise<void> {
  await client.patch(
    `/api/notification/inbox/${encodeURIComponent(notificationId)}/hide`,
    undefined,
    { useConfiguredBearer: true }
  );
  rememberHiddenNotification(notificationId);
}

function normalizeInboxNotification(notification: RawInboxNotification): InboxNotification {
  return {
    notification_id:
      notification.inbox_item_id ||
      notification.inboxItemId ||
      notification.notification_id ||
      notification.notificationId ||
      notification.id ||
      notification._id ||
      "",
    type: notification.type || "feed_like",
    actor_id: notification.actor_id || "",
    actor_name: notification.actor_name || "",
    actor_profile_image_url: notification.actor_profile_image_url ?? null,
    target_type: notification.target_type || "feed_post",
    target_id: notification.target_id || "",
    comment_id: notification.comment_id ?? null,
    target_preview: notification.target_preview ?? null,
    comment_preview: notification.comment_preview ?? null,
    is_read: Boolean(notification.is_read),
    created_at: notification.created_at || "",
  };
}

function rememberHiddenNotification(notificationId: string): void {
  if (!notificationId) return;

  const hiddenNotifications = readHiddenNotifications();
  hiddenNotifications[notificationId] = { hiddenAt: Date.now() };
  writeHiddenNotifications(hiddenNotifications);
}

function isNotificationHidden(notificationId: string): boolean {
  if (!notificationId) return false;
  return Boolean(readHiddenNotifications()[notificationId]);
}

function readHiddenNotifications(): Record<string, HiddenNotificationRecord> {
  try {
    const raw = localStorage.getItem(HIDDEN_NOTIFICATION_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};

    const now = Date.now();
    const entries = Object.entries(parsed as Record<string, HiddenNotificationRecord>)
      .filter(([id, record]) => {
        const hiddenAt = Number(record?.hiddenAt || 0);
        return id && hiddenAt > 0 && now - hiddenAt < HIDDEN_NOTIFICATION_TTL_MS;
      });

    const hiddenNotifications = Object.fromEntries(entries);
    if (entries.length !== Object.keys(parsed).length) {
      writeHiddenNotifications(hiddenNotifications);
    }
    return hiddenNotifications;
  } catch {
    return {};
  }
}

function writeHiddenNotifications(
  hiddenNotifications: Record<string, HiddenNotificationRecord>
): void {
  localStorage.setItem(
    HIDDEN_NOTIFICATION_STORAGE_KEY,
    JSON.stringify(hiddenNotifications)
  );
}
