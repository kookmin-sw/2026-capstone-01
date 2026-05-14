import { StrictMode } from "react";
import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

const AUTH_CALLBACK_STORAGE_KEYS = [
  "accessToken",
  "access_token",
  "token",
  "utk",
] as const;

function registerNativeAuthCallback(): void {
  if (!Capacitor.isNativePlatform()) {
    return;
  }

  void CapacitorApp.addListener("appUrlOpen", async (event) => {
    const callbackUrl = toNativeAuthCallbackUrl(event.url);
    if (!callbackUrl) {
      return;
    }

    await Browser.close().catch(() => undefined);
    persistAuthCallbackParams(callbackUrl.searchParams);

    const status = callbackUrl.searchParams.get("status");
    const nextPath =
      status === "new" || status === "in_progress"
        ? `/${callbackUrl.search}`
        : status === "withdrawal_pending"
          ? "/withdrawal-pending"
          : "/home";

    window.location.href = nextPath;
  });
}

function toNativeAuthCallbackUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    if (url.protocol === "krip:" && url.hostname === "auth" && url.pathname.startsWith("/callback")) {
      return url;
    }
  } catch {
    return null;
  }

  return null;
}

function persistAuthCallbackParams(params: URLSearchParams): void {
  AUTH_CALLBACK_STORAGE_KEYS.forEach((key) => {
    const value = params.get(key);
    if (value) {
      window.localStorage.setItem(key === "access_token" ? "accessToken" : key, value);
    }
  });
}

registerNativeAuthCallback();

const iconLink =
  document.querySelector<HTMLLinkElement>("link[rel='icon']") ??
  document.head.appendChild(document.createElement("link"));

iconLink.rel = "icon";
iconLink.type = "image/png";
iconLink.href = "/favicon.png";

let lastTouchEndAt = 0;

function preventViewportZoom(): void {
  document.addEventListener(
    "gesturestart",
    (event) => {
      event.preventDefault();
    },
    { passive: false }
  );

  document.addEventListener(
    "gesturechange",
    (event) => {
      event.preventDefault();
    },
    { passive: false }
  );

  document.addEventListener(
    "touchmove",
    (event) => {
      if (event.touches.length > 1) {
        event.preventDefault();
      }
    },
    { passive: false }
  );

  document.addEventListener(
    "touchend",
    (event) => {
      const now = window.performance.now();
      if (now - lastTouchEndAt <= 320) {
        event.preventDefault();
      }
      lastTouchEndAt = now;
    },
    { passive: false }
  );
}

preventViewportZoom();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);

window.requestAnimationFrame(() => {
  window.requestAnimationFrame(() => {
    const loader = document.getElementById("app-loader");
    if (!loader) {
      return;
    }

    loader.style.opacity = "0";
    window.setTimeout(() => loader.remove(), 220);
  });
});
