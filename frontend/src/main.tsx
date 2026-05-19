import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

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
      if (event.cancelable && now - lastTouchEndAt <= 320) {
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
