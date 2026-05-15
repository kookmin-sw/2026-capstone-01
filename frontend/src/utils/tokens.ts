const LEGACY_TOKEN_KEY = import.meta.env.VITE_LEGACY_TOKEN_STORAGE_KEY || "";
const TOKEN_KEYS = ["utk", "accessToken", "token", LEGACY_TOKEN_KEY].filter(Boolean);

let tokenCache = "";

/** Persists a JWT token for use by the native app. */
export function saveToken(token: string): void {
  const normalizedToken = token.trim();
  removeToken();
  tokenCache = normalizedToken;
  localStorage.setItem("utk", normalizedToken);
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

export function removeToken(): void {
  tokenCache = "";
  TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

export function notifyUnauthorized(): void {
  window.dispatchEvent(new CustomEvent("krip:unauthorized"));
}

export function notifyForbidden(): void {
  window.dispatchEvent(new CustomEvent("krip:forbidden"));
}
