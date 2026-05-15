import { Capacitor } from "@capacitor/core";
import { notifyForbidden, notifyUnauthorized, readToken, removeToken } from "../../utils/tokens";
import { getUserAuthorizationBearer } from "../client";
import {
  API_BASE_URL,
  AUTHORIZATION_BEARER,
  TOUR_PLACES_AUTHORIZATION_BEARER,
} from "./config";

export interface UserProfile {
  user_id?: string;
  auth_provider?: string;
  status?: string;
  email: string;
  user_name: string;
  phone_number?: string;
  age?: number;
  gender?: string;
  nationality?: string;
  travel_styles?: string[];
  image_url?: string;
  imageUrl?: string;
  profile_image_url?: string | null;
  profileImageUrl?: string;
  avatar_url?: string;
}

export interface ProfileImageResponse {
  profile_image_url: string | null;
}

export type ProfilePreferencesPayload = Pick<
  RegisterPayload,
  | "travel_styles"
>;

export type ProfileUpdatePayload = Partial<
  Pick<
    RegisterPayload,
    | "email"
    | "user_name"
    | "phone_number"
    | "age"
    | "gender"
    | "nationality"
    | "travel_styles"
  >
>;

export interface RegisterPayload {
  email: string;
  user_name: string;
  phone_number: string;
  age: number;
  gender: string;
  nationality: string;
  travel_styles: string[];
}

export interface TourPlaceApiItem {
  id?: string | number;
  place_id?: string | number;
  is_favorite?: boolean | null;
  name?: string;
  display_name?: string;
  title?: string;
  category?: string;
  type?: string;
  place_type?: string;
  description?: string;
  summary?: string;
  editorial_summary?: string | null;
  generative_summary?: string | null;
  review_summary?: string | null;
  address?: string;
  short_address?: string | null;
  review_count?: number;
  reviewCount?: number;
  rating_count?: number;
  rating?: number;
  latitude?: number;
  lat?: number;
  longitude?: number;
  lng?: number;
  location?: {
    lat?: number;
    lng?: number;
    latitude?: number;
    longitude?: number;
    lon?: number;
    x?: number;
    y?: number;
  } | null;
  coordinates?:
    | {
        lat?: number;
        lng?: number;
        latitude?: number;
        longitude?: number;
        lon?: number;
        x?: number;
        y?: number;
      }
    | [number, number]
    | null;
  tags?: string[];
  types?: string[];
  distance?: number;
  phone?: string | number | null;
  phone_international?: string | number | null;
  website?: string | null;
  google_maps_url?: string | null;
  google_map_review_link?: string | null;
  opening_hours?: unknown[];
  services?: unknown[];
  payment?: unknown[];
  accessibility?: unknown[];
  parking?: unknown[];
  price_level?: string | number | null;
  price_range?:
    | {
        min?: string | number | null;
        max?: string | number | null;
      }
    | null;
  reviews?:
    | Array<{
        author?: string | null;
        rating?: number | string | null;
        relative_time?: string | null;
        text?: string | null;
      }>
    | null;
  image_url?: string;
  imageUrl?: string;
  thumbnail?: string;
  photos?: string[];
  [key: string]: unknown;
}

export interface TourPlacesParams {
  lat?: number;
  lng?: number;
  keyword?: string;
  cursor?: string;
  max_distance?: number;
}

export interface TourPlacesResponse {
  items: TourPlaceApiItem[];
  nextCursor?: string;
}

export interface FavoritePlaceApiItem {
  favorite_id?: string;
  created_at?: string;
  place?: TourPlaceApiItem | null;
}

export interface FavoritePlacesResponse {
  favorites: FavoritePlaceApiItem[];
  totalCount: number;
}

export interface SearchHistoryItem {
  search_name: string;
  created_at: string;
}

export interface SearchHistoryResponse {
  histories: SearchHistoryItem[];
}

type RequestHeaders = Record<string, string>;
type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: RequestHeaders;
};

interface ApiError extends Error {
  status?: number;
}

function toErrorMessage(value: unknown, fallback: string): string {
  if (!value) return fallback;

  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    const items = value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          return item.msg || item.message || JSON.stringify(item);
        }
        return String(item);
      })
      .filter(Boolean);

    return items.length > 0 ? items.join(", ") : fallback;
  }

  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return (obj.detail as string) || (obj.message as string) || JSON.stringify(value);
  }

  return String(value);
}

function getAuthHeaders(headers: RequestHeaders = {}): RequestHeaders {
  const rawToken = readToken();

  const userAuthorization = rawToken
    ? rawToken.toLowerCase().startsWith("bearer ")
      ? rawToken
      : `Bearer ${rawToken}`
    : "";

  const authorization =
    (Capacitor.isNativePlatform() ? userAuthorization : getUserAuthorizationBearer()) ||
    AUTHORIZATION_BEARER;

  if (!authorization) return headers;

  const result: RequestHeaders = {
    ...headers,
    Authorization: authorization,
  };

  if (Capacitor.isNativePlatform() && rawToken) {
    result["X-Auth-Token"] = rawToken;
  }

  return result;
}

function getTourPlacesHeaders(headers: RequestHeaders = {}): RequestHeaders {
  if (!TOUR_PLACES_AUTHORIZATION_BEARER) return headers;

  const result: RequestHeaders = {
    ...headers,
    Authorization: TOUR_PLACES_AUTHORIZATION_BEARER,
  };

  const rawToken = readToken();
  if (Capacitor.isNativePlatform() && rawToken) {
    result["X-Auth-Token"] = rawToken;
  }

  return result;
}

function buildQueryString(params: TourPlacesParams = {}): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }

    searchParams.set(key, String(value));
  });

  searchParams.set("_ts", String(Date.now()));

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : "";
}

async function authRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T | null> {
  const { headers, ...rest } = options;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    cache: "no-store",
    headers: getAuthHeaders(headers),
    ...rest,
  });

  if (response.ok) {
    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get("content-type") || "";
    return contentType.includes("application/json") ? response.json() : null;
  }

  let detail = "Something went wrong while processing the request.";

  try {
    const data = (await response.json()) as {
      detail?: unknown;
      message?: unknown;
    };
    detail = toErrorMessage(data.detail || data.message || data, detail);
  } catch {
    // Keep the default message when the response is not JSON.
  }

  if (response.status === 401) {
  const rawToken = readToken();
  const authorization = rawToken
    ? `Bearer ${rawToken}`
    : getUserAuthorizationBearer() || AUTHORIZATION_BEARER;

  console.warn("Unauthorized request", {
    path,
    hasAuthorization: Boolean(authorization),
    hasStoredToken: Boolean(rawToken),
    tokenPreview: authorization ? `${authorization.slice(0, 40)}...` : "",
  });

  notifyUnauthorized();
}

  if (response.status === 403) {
    notifyForbidden();
  }

  if (response.status === 419) {
    window.dispatchEvent(new CustomEvent("krip:withdrawal-pending"));
  }

  const error: ApiError = new Error(detail);
  error.status = response.status;
  throw error;
}

export function createLoginUrl(platform?: "android"): string {
  if (platform === "android") {
    // Native app uses a dedicated endpoint that returns a JWT deep link
    // (krip://auth/callback?utk=...&status=...) instead of a session cookie.
    const url = new URL("/api/auth/login/app", API_BASE_URL);
    url.searchParams.set("type", "google");
    return url.toString();
  }

  const url = new URL("/api/auth/login", API_BASE_URL);
  url.searchParams.set("type", "google");

  if (import.meta.env.VITE_AUTH_IS_LOCAL === "true") {
    url.searchParams.set("is_local", "true");
  }

  return url.toString();
}

export function registerUser(
  payload: RegisterPayload
): Promise<Record<string, unknown> | null> {
  return authRequest("/api/auth/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function logoutUser(): Promise<Record<string, unknown> | null> {
  try {
    return await authRequest("/api/auth/logout", {
      method: "POST",
    });
  } finally {
    removeToken();
  }
}

export async function withdrawUser(): Promise<Record<string, unknown> | string | null> {
  try {
    return await authRequest<Record<string, unknown> | string>("/api/auth/withdraw", {
      method: "DELETE",
    });
  } finally {
    removeToken();
  }
}

export function cancelWithdrawUser(): Promise<Record<string, unknown> | null> {
  return authRequest("/api/auth/withdraw/cancel", {
    method: "POST",
  });
}

export async function getMyProfile(): Promise<UserProfile | null> {
  const data = await authRequest<unknown>("/api/auth/profile/me");
  return normalizeUserProfile(data);
}

export async function updateMyProfile(
  payload: ProfileUpdatePayload
): Promise<UserProfile | null> {
  const data = await authRequest<unknown>("/api/auth/profile/me", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return normalizeUserProfile(data);
}

function buildProfileImageFormData(file: File): FormData {
  const formData = new FormData();
  formData.append("file", file);
  return formData;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function unwrapProfileResponse(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) return null;

  const nestedKeys = ["profile", "user", "data", "item"] as const;
  for (const key of nestedKeys) {
    if (isRecord(value[key])) {
      return value[key];
    }
  }

  return value;
}

function readStringList(
  source: Record<string, unknown>,
  ...keys: string[]
): string[] | undefined {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) {
      return value.filter((item): item is string => typeof item === "string");
    }
  }

  return undefined;
}

function normalizeUserProfile(value: unknown): UserProfile | null {
  const profile = unwrapProfileResponse(value);
  if (!profile) return null;

  return {
    ...(profile as UserProfile),
    travel_styles: readStringList(profile, "travel_styles"),
  };
}

export function uploadMyProfileImage(file: File): Promise<ProfileImageResponse | null> {
  return authRequest("/api/auth/profile/image", {
    method: "POST",
    body: buildProfileImageFormData(file),
  });
}

export function replaceMyProfileImage(file: File): Promise<ProfileImageResponse | null> {
  return authRequest("/api/auth/profile/image", {
    method: "PUT",
    body: buildProfileImageFormData(file),
  });
}

export function deleteMyProfileImage(): Promise<Record<string, string> | null> {
  return authRequest("/api/auth/profile/image", {
    method: "DELETE",
  });
}

export function addTourPlaceFavorite(
  placeId: string
): Promise<Record<string, unknown> | null> {
  return authRequest("/api/tour/places/favorites", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      place_id: placeId,
    }),
  });
}

function deleteTourPlaceFavorite(
  favoriteOrPlaceId: string
): Promise<Record<string, unknown> | null> {
  return authRequest(`/api/tour/places/favorites/${encodeURIComponent(favoriteOrPlaceId)}`, {
    method: "DELETE",
  });
}

export async function removeTourPlaceFavorite(
  favoriteOrPlaceId: string,
  fallbackPlaceId?: string
): Promise<Record<string, unknown> | null> {
  try {
    return await deleteTourPlaceFavorite(favoriteOrPlaceId);
  } catch (error) {
    if (!fallbackPlaceId || fallbackPlaceId === favoriteOrPlaceId) {
      throw error;
    }

    return deleteTourPlaceFavorite(fallbackPlaceId);
  }
}

export async function getTourPlaceFavorites(): Promise<FavoritePlacesResponse> {
  const payload =
    (await authRequest<{
      favorites?: FavoritePlaceApiItem[] | null;
      total_count?: number | null;
      totalCount?: number | null;
    }>("/api/tour/places/favorites")) || {};

  return {
    favorites: Array.isArray(payload.favorites) ? payload.favorites : [],
    totalCount: Number(payload.total_count ?? payload.totalCount ?? 0),
  };
}

export async function getTourSearchHistory(): Promise<SearchHistoryResponse> {
  const payload =
    (await authRequest<{
      histories?: SearchHistoryItem[] | null;
    }>("/api/tour/search-history")) || {};

  return {
    histories: Array.isArray(payload.histories) ? payload.histories : [],
  };
}

export function deleteTourSearchHistoryOne(
  searchName: string
): Promise<Record<string, unknown> | null> {
  const params = new URLSearchParams({
    search_name: searchName,
  });

  return authRequest(`/api/tour/search-history/one?${params.toString()}`, {
    method: "DELETE",
  });
}

export function deleteTourSearchHistoryAll(): Promise<Record<string, unknown> | null> {
  return authRequest("/api/tour/search-history", {
    method: "DELETE",
  });
}

export async function getTourPlaces(
  params: TourPlacesParams = {}
): Promise<TourPlacesResponse> {
  const response = await fetch(`${API_BASE_URL}/api/tour/places${buildQueryString(params)}`, {
    method: "GET",
    cache: "no-store",
    credentials: "include",
    headers: getTourPlacesHeaders(),
  });

  if (!response.ok) {
    let detail = "Failed to load places.";

    try {
      const data = (await response.json()) as {
        detail?: unknown;
        message?: unknown;
      };
      detail = toErrorMessage(data.detail || data.message || data, detail);
    } catch {
      // Keep the default message when the response is not JSON.
    }

    const error: ApiError = new Error(detail);
    error.status = response.status;
    throw error;
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return {
      items: [],
    };
  }

  const payload = (await response.json()) as
    | TourPlaceApiItem[]
    | {
        data?: TourPlaceApiItem[];
        places?: TourPlaceApiItem[];
        items?: TourPlaceApiItem[];
        next_cursor?: string | null;
        nextCursor?: string | null;
      };

  if (Array.isArray(payload)) {
    return {
      items: payload,
    };
  }

  return {
    items: payload.data || payload.places || payload.items || [],
    nextCursor: payload.next_cursor || payload.nextCursor || undefined,
  };
}
