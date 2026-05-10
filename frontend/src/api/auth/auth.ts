import { removeToken } from "../../utils/tokens";
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
  food_preferences?: string[];
  density_preference?: string;
  budget_preference?: string;
  walking_preference?: string;
  transport_preferences?: string[];
  companion_preference?: string;
  time_preferences?: string[];
  communication_preference?: string;
  planning_preference?: string;
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
  | "food_preferences"
  | "density_preference"
  | "budget_preference"
  | "walking_preference"
  | "transport_preferences"
  | "companion_preference"
  | "time_preferences"
  | "communication_preference"
  | "planning_preference"
>;

export interface RegisterPayload {
  email: string;
  user_name: string;
  phone_number: string;
  age: number;
  gender: string;
  nationality: string;
  travel_styles: string[];
  food_preferences?: string[];
  density_preference?: string;
  budget_preference?: string;
  walking_preference?: string;
  transport_preferences?: string[];
  companion_preference?: string;
  time_preferences?: string[];
  communication_preference?: string;
  planning_preference?: string;
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
  if (!AUTHORIZATION_BEARER) return headers;

  return {
    ...headers,
    Authorization: AUTHORIZATION_BEARER,
  };
}

function getTourPlacesHeaders(headers: RequestHeaders = {}): RequestHeaders {
  if (!TOUR_PLACES_AUTHORIZATION_BEARER) return headers;

  return {
    ...headers,
    Authorization: TOUR_PLACES_AUTHORIZATION_BEARER,
  };
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
    console.warn("Unauthorized request", {
      path,
      authorization: AUTHORIZATION_BEARER,
    });
    removeToken();
  }

  if (response.status === 419) {
    window.dispatchEvent(new CustomEvent("krip:withdrawal-pending"));
  }

  const error: ApiError = new Error(detail);
  error.status = response.status;
  throw error;
}

export function createLoginUrl(): string {
  const url = new URL("/api/auth/login", API_BASE_URL);
  url.searchParams.set("type", "google");

  const shouldUseLocalLogin = import.meta.env.VITE_AUTH_IS_LOCAL === "true";

  if (shouldUseLocalLogin) {
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

export function logoutUser(): Promise<Record<string, unknown> | null> {
  return authRequest("/api/auth/logout", {
    method: "POST",
  });
}

export async function withdrawUser(): Promise<Record<string, unknown> | string | null> {
  const result = await authRequest<Record<string, unknown> | string>("/api/auth/withdraw", {
    method: "DELETE",
  });

  removeToken();
  localStorage.removeItem("accessToken");

  return result;
}

export function cancelWithdrawUser(): Promise<Record<string, unknown> | null> {
  return authRequest("/api/auth/withdraw/cancel", {
    method: "POST",
  });
}

export function getMyProfile(): Promise<UserProfile | null> {
  return authRequest("/api/auth/profile/me");
}

export function updateMyProfilePreferences(
  payload: ProfilePreferencesPayload,
  profile: UserProfile
): Promise<UserProfile | null> {
  const registerPayload: RegisterPayload = {
    email: profile.email,
    user_name: profile.user_name,
    phone_number: profile.phone_number ?? "",
    age: Number(profile.age ?? 0),
    gender: profile.gender ?? "",
    nationality: profile.nationality ?? "",
    ...payload,
  };

  return authRequest("/api/auth/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(registerPayload),
  });
}

function buildProfileImageFormData(file: File): FormData {
  const formData = new FormData();
  formData.append("file", file);
  return formData;
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
