/* global importScripts, firebase */

importScripts("https://www.gstatic.com/firebasejs/12.12.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.12.1/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyCNhoADPVfV74tbb9WI9i2eJha7RY4FsyM",
  authDomain: "krip-a4d7d.firebaseapp.com",
  projectId: "krip-a4d7d",
  storageBucket: "krip-a4d7d.firebasestorage.app",
  messagingSenderId: "149172625115",
  appId: "1:149172625115:web:6a337f849a08826243f6fe",
  measurementId: "G-KVHM5PW0MC",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const notification = payload.notification || {};
  const title = notification.title || "Krip";
  const options = {
    body: notification.body,
    icon: "/favicon.png",
    data: payload.data,
  };

  self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
    clients.forEach((client) => {
      client.postMessage({
        type: "KRIP_FCM_BACKGROUND_MESSAGE",
        payload,
      });
    });
  });

  self.registration.showNotification(title, options);
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const targetUrl = getNotificationTargetUrl(event.notification.data || {});
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const existingClient = clients.find((client) => "focus" in client);
      if (existingClient) {
        existingClient.postMessage({
          type: "KRIP_FCM_BACKGROUND_MESSAGE",
          payload: {
            notification: {
              title: event.notification.title,
              body: event.notification.body,
            },
            data: event.notification.data || {},
          },
        });
        if ("navigate" in existingClient) {
          return existingClient.navigate(targetUrl).then((client) => client?.focus());
        }
        return existingClient.focus();
      }

      return self.clients.openWindow(targetUrl);
    })
  );
});

function getNotificationTargetUrl(data) {
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
  if (type.includes("feed") || type.includes("comment") || type.includes("like")) {
    const targetId =
      data.target_id ||
      data.targetId ||
      data.post_id ||
      data.postId ||
      data.feed_post_id ||
      data.feedPostId;
    return targetId ? `/my?feedPost=${encodeURIComponent(targetId)}` : "/my";
  }

  return data.url || data.path || "/mate";
}
