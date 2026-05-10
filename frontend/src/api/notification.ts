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

export async function getNotificationInbox(
  cursor?: string
): Promise<NotificationInboxResponse> {
  const { data } = await client.get<
    NotificationInboxResponse & { items?: InboxNotification[] }
  >("/api/notification/inbox", {
    params: cursor ? { cursor } : undefined,
  });
  const notifications = Array.isArray(data.notifications)
    ? data.notifications
    : Array.isArray(data.items)
      ? data.items
      : [];

  return {
    notifications,
    next_cursor: data.next_cursor ?? null,
  };
}

export async function getNotificationUnreadCount(): Promise<number> {
  const { data } = await client.get<NotificationUnreadCountResponse>(
    "/api/notification/inbox/unread-count"
  );
  return Math.min(999, Math.max(0, Number(data.unread_count || 0)));
}

export async function hideNotification(notificationId: string): Promise<void> {
  await client.patch(
    `/api/notification/inbox/${encodeURIComponent(notificationId)}/hide`
  );
}
