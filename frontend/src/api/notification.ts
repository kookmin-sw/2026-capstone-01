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

type RawInboxNotification = Partial<InboxNotification> & {
  id?: string;
  _id?: string;
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
    notifications: rawNotifications.map(normalizeInboxNotification),
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
}

function normalizeInboxNotification(notification: RawInboxNotification): InboxNotification {
  return {
    notification_id:
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
