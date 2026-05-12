import axios from "axios";
import type { AxiosRequestConfig } from "axios";

import { API_BASE_URL, AUTHORIZATION_BEARER } from "./auth/config";

declare module "axios" {
  export interface AxiosRequestConfig {
    requireUserBearer?: boolean;
    useConfiguredBearer?: boolean;
  }
}

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  withCredentials: true,
});

export function readAccessToken(): string {
  const tokenKeys = [
    "accessToken",
    "token",
    "utk",
    import.meta.env.VITE_LEGACY_TOKEN_STORAGE_KEY || "",
  ].filter(Boolean);

  for (const key of tokenKeys) {
    const token = localStorage.getItem(key);
    if (token) return token;
  }

  return "";
}

export function getUserAuthorizationBearer(): string {
  const token = readAccessToken().trim();
  if (!token) return "";
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

client.interceptors.request.use((config) => {
  const authorization = getRequestAuthorization(config);
  if (config.requireUserBearer && !authorization) {
    return Promise.reject(new Error("A logged-in Bearer token is required."));
  }

  if (authorization) {
    config.headers.Authorization = authorization;
  }
  return config;
});

function getRequestAuthorization(config: AxiosRequestConfig): string {
  const userAuthorization = getUserAuthorizationBearer();
  if (config.useConfiguredBearer) return AUTHORIZATION_BEARER;
  if (config.requireUserBearer) return userAuthorization;
  return userAuthorization || AUTHORIZATION_BEARER;
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("accessToken");
    }

    if (
      error.response?.status === 419 &&
      (!error.response.data?.status ||
        error.response.data.status === "withdrawal_pending")
    ) {
      window.dispatchEvent(new CustomEvent("krip:withdrawal-pending"));
    }

    return Promise.reject(error);
  }
);

export default client;
