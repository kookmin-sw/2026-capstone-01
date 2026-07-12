const LEGACY_TOKEN_KEY = import.meta.env.VITE_LEGACY_TOKEN_STORAGE_KEY || "";
const TOKEN_KEYS = ["utk", "accessToken", "token", LEGACY_TOKEN_KEY].filter(Boolean);
const PRIMARY_TOKEN_KEYS = ["utk", "accessToken"] as const;
const TOKEN_SAVE_SETTLE_MS = 100;
const DEBUG_AUTH_LOG = import.meta.env.DEV && import.meta.env.VITE_DEBUG_AUTH_LOG === "true";

let tokenCache = "";
let unauthorizedNotified = false;

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

  if (DEBUG_AUTH_LOG) {
    console.info("[auth] token saved check", JSON.stringify({ hasSavedToken }));
  }

  return hasSavedToken;
}

export function removeToken(): void {
  tokenCache = "";
  unauthorizedNotified = false;
  TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

export function notifyUnauthorized(): void {
  if (unauthorizedNotified) return;

  removeToken();
  unauthorizedNotified = true;
  window.dispatchEvent(new CustomEvent("krip:unauthorized"));
}

export function notifyForbidden(): void {
  window.dispatchEvent(new CustomEvent("krip:forbidden"));
}
