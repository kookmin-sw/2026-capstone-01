export interface LikeNotification {
  id: string;
  actorName: string;
  targetTitle: string;
  body: string;
  createdAt: string;
  path?: string;
  imageUrl?: string | null;
}

const LIKE_NOTIFICATION_STORAGE_KEY = "krip-like-notifications";

export function rememberLikeNotification(notification: LikeNotification): void {
  const current = readStoredLikeNotifications();
  const next = [
    notification,
    ...current.filter((item) => item.id !== notification.id),
  ].slice(0, 50);

  window.localStorage.setItem(LIKE_NOTIFICATION_STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new Event("krip:like-notifications-updated"));
}

export function readStoredLikeNotifications(): LikeNotification[] {
  try {
    const raw = window.localStorage.getItem(LIKE_NOTIFICATION_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(parsed)) return [];

    return parsed.filter(isLikeNotification);
  } catch {
    return [];
  }
}

function isLikeNotification(value: unknown): value is LikeNotification {
  if (!value || typeof value !== "object") return false;

  const item = value as Partial<LikeNotification>;
  return Boolean(item.id && item.actorName && item.createdAt);
}
