import axios from "axios";
import type { AxiosRequestConfig } from "axios";
import { Capacitor } from "@capacitor/core";

import {
  API_BASE_URL,
  AUTHORIZATION_BEARER,
  getRequiredAuthorizationBearer,
} from "./auth/config";
import { notifyForbidden, notifyUnauthorized, readToken, removeToken } from "../utils/tokens";

const DEBUG_AUTH_LOG = import.meta.env.DEV && import.meta.env.VITE_DEBUG_AUTH_LOG === "true";

declare module "axios" {
  export interface AxiosRequestConfig {
    requireUserBearer?: boolean;
    useConfiguredBearer?: boolean;
    __isAuthHandled?: boolean;
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

    if (DEBUG_AUTH_LOG) {
      console.info(
        "[auth] request headers",
        JSON.stringify({
          pathname: config.url ? new URL(config.url, API_BASE_URL).pathname : "",
          hasAuthorization: Boolean(config.headers.Authorization),
          hasXAuthToken: Boolean(config.headers["X-Auth-Token"]),
          hasStoredToken: Boolean(rawToken),
        })
      );
    }
  }

  return config;
});

function getRequestAuthorization(config: AxiosRequestConfig): string {
  const userAuthorization = getUserAuthorizationBearer();

  if (config.useConfiguredBearer) return getRequiredAuthorizationBearer();
  if (Capacitor.isNativePlatform()) return getRequiredAuthorizationBearer();
  if (config.requireUserBearer) return userAuthorization;

  return userAuthorization || AUTHORIZATION_BEARER;
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;

    if (status === 401 && !error.config?.__isAuthHandled) {
      if (error.config) {
        error.config.__isAuthHandled = true;
      }
      console.warn(
        "[auth] axios 401",
        JSON.stringify({
          pathname: error.config?.url ? new URL(error.config.url, API_BASE_URL).pathname : "",
          hasXAuthToken: Boolean(error.config?.headers?.["X-Auth-Token"]),
          hasStoredToken: Boolean(readAccessToken()),
        })
      );
      notifyUnauthorized();
    }

    if (status === 403) {
      notifyForbidden();
    }

    if (
      status === 419 &&
      (!error.response.data?.status ||
        error.response.data.status === "withdrawal_pending")
    ) {
      window.dispatchEvent(new CustomEvent("krip:withdrawal-pending"));
    }

    return Promise.reject(error);
  }
);

export default client;
