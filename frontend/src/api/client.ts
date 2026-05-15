import axios from "axios";
import type { AxiosRequestConfig } from "axios";
import { Capacitor } from "@capacitor/core";

import { API_BASE_URL, AUTHORIZATION_BEARER } from "./auth/config";
import { notifyForbidden, notifyUnauthorized, readToken, removeToken } from "../utils/tokens";

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
  return readToken();
}

export function getUserAuthorizationBearer(): string {
  const token = readAccessToken().trim();
  if (!token) return "";
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

client.interceptors.request.use((config) => {
  const rawToken = readAccessToken();
  const authorization = getRequestAuthorization(config);
  if (config.requireUserBearer && !rawToken) {
    removeToken();
    notifyUnauthorized();
    return Promise.reject(new Error("A logged-in Bearer token is required."));
  }

  if (authorization) {
    config.headers.Authorization = authorization;
  }

  // On native, also send the raw token as X-Auth-Token so the backend can
  // authenticate without relying on session cookies.
  if (Capacitor.isNativePlatform()) {
    if (rawToken) {
      config.headers["X-Auth-Token"] = rawToken;
    }

    const authorization = config.headers.Authorization;
    console.info(
      "[auth] request headers",
      JSON.stringify({
        url: config.url,
        hasAuthorization: Boolean(authorization),
        hasXAuthToken: Boolean(config.headers["X-Auth-Token"]),
        hasStoredToken: Boolean(rawToken),
        authPrefix: typeof authorization === "string" ? authorization.slice(0, 40) : null,
        tokenPrefix: rawToken ? rawToken.slice(0, 10) : null,
      })
    );
  }

  return config;
});

function getRequestAuthorization(config: AxiosRequestConfig): string {
  const userAuthorization = getUserAuthorizationBearer();

  if (config.useConfiguredBearer) return AUTHORIZATION_BEARER;
  if (Capacitor.isNativePlatform()) return userAuthorization || AUTHORIZATION_BEARER;
  if (config.requireUserBearer) return userAuthorization;

  return userAuthorization || AUTHORIZATION_BEARER;
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
  console.warn("[auth] axios 401", {
    url: error.config?.url,
    authPrefix:
      typeof error.config?.headers?.Authorization === "string"
        ? error.config.headers.Authorization.slice(0, 40)
        : null,
    hasXAuthToken: Boolean(error.config?.headers?.["X-Auth-Token"]),
    hasStoredToken: Boolean(readAccessToken()),
  });

  notifyUnauthorized();
}

    if (error.response?.status === 403) {
      notifyForbidden();
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
