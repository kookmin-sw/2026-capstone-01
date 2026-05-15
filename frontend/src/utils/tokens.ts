import { Capacitor } from "@capacitor/core";

const LEGACY_TOKEN_KEY = import.meta.env.VITE_LEGACY_TOKEN_STORAGE_KEY || "";
const TOKEN_KEYS = ["utk", "accessToken", "token", LEGACY_TOKEN_KEY].filter(Boolean);
const PRIMARY_TOKEN_KEYS = ["utk", "accessToken"] as const;
const TOKEN_SAVE_SETTLE_MS = 100;

let tokenCache = "";

/** Persists a JWT token for use by the native app. */
export function saveToken(token: string): void {
  const normalizedToken = token.trim();
  removeToken();
  tokenCache = normalizedToken;
  PRIMARY_TOKEN_KEYS.forEach((key) => localStorage.setItem(key, normalizedToken));
}

export function readToken(): string {
  if (tokenCache) return tokenCache;

  for (const key of TOKEN_KEYS) {
    const token = localStorage.getItem(key);
    if (token) {
      tokenCache = token;
      return token;
    }
  }

  return "";
}

export async function confirmTokenSaved(token: string): Promise<boolean> {
  await new Promise((resolve) => window.setTimeout(resolve, TOKEN_SAVE_SETTLE_MS));

  const normalizedToken = token.trim();
  const savedToken = localStorage.getItem("utk") || localStorage.getItem("accessToken") || "";
  const hasSavedToken = savedToken === normalizedToken;

  if (hasSavedToken) {
    tokenCache = savedToken;
  }

  console.info(
    "[auth] token saved check",
    JSON.stringify({
      hasSavedToken,
      hasUtk: Boolean(localStorage.getItem("utk")),
      hasAccessToken: Boolean(localStorage.getItem("accessToken")),
    })
  );

  return hasSavedToken;
}

export function removeToken(): void {
  tokenCache = "";
  TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

export function notifyUnauthorized(): void {
  if (Capacitor.isNativePlatform() && readToken()) {
    console.warn("[auth] 401 received but stored token exists; suppressing login redirect.");
    return;
  }

  window.dispatchEvent(new CustomEvent("krip:unauthorized"));
}

export function notifyForbidden(): void {
  window.dispatchEvent(new CustomEvent("krip:forbidden"));
}
