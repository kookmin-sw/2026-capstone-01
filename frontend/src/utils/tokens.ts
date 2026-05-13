const LEGACY_TOKEN_KEY = import.meta.env.VITE_LEGACY_TOKEN_STORAGE_KEY || "";

export function removeToken(): void {
  ["accessToken", "token", "utk", LEGACY_TOKEN_KEY]
    .filter(Boolean)
    .forEach((key) => localStorage.removeItem(key));
}

export function notifyUnauthorized(): void {
  window.dispatchEvent(new CustomEvent("krip:unauthorized"));
}
