import {
  API_BASE_URL,
  TOUR_PLACES_AUTHORIZATION_BEARER,
} from "./auth/config";
import { Capacitor } from "@capacitor/core";

import { readToken } from "../utils/tokens";

export const BRAND = "#58C9D4";
export const ACCENT = "#FFB765";
export const AI_PLAN_STORAGE_KEY = "krip-ai-trip-preferences";
export const SAVED_PLANS_STORAGE_KEY = "krip-saved-trip-plans";
export const SAVED_PLANS_EVENT = "krip:saved-plans-updated";
export const DEFAULT_MAP_CENTER = { lat: 37.5665, lng: 126.978 };
export const INCHEON_AIRPORT_CENTER = { lat: 37.4602, lng: 126.4407 };
export const SEOUL_SHILLA_HOTEL_CENTER = { lat: 37.5564, lng: 127.0056 };
export const TOUR_RECOMMEND_TIMEOUT_MS = 120000;

type RequestHeaders = Record<string, string>;

function getTourApiHeaders(headers: RequestHeaders = {}): RequestHeaders {
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

export type PaceOption = "Slow" | "Balanced" | "Packed";
export type TransportOption = "Public Transit" | "Taxi" | "Walk";
export type CompanionOption =
  | "Solo"
  | "Couple"
  | "Spouse"
  | "Friends"
  | "Family"
  | "Family with Kids";
export type BudgetCategory = "Low" | "Moderate" | "High";
export type PlannerMode = "ai" | "manual";

type SelectableValue<T extends string> = T | "";

export interface AiPreferenceState {
  departure: string;
  arrival: string;
  styles: string[];
  pace: SelectableValue<PaceOption>;
  extraPlace: string;
  transport: SelectableValue<TransportOption>;
  startTime: string;
  endTime: string;
  companion: SelectableValue<CompanionOption>;
  budgetValue: number;
  budgetCategory: BudgetCategory;
  foodNeed: string;
  durationDays: number;
  days?: AiPlanDayInput[];
  additionalPlaceId?: string | null;
  additionalPlaceName?: string;
}

export interface AiRouteStop {
  id: string;
  name: string;
  category: string;
  summary: string;
  address: string;
  latitude?: number;
  longitude?: number;
  keyword: string;
  timeLabel?: string;
  day?: number;
  order?: number;
  clusterName?: string;
  tip?: string;
  rating?: number | null;
  eventType?: "start" | "place" | "meal" | "return" | "airport" | "required";
}

export interface SavedManualStop {
  plannedId: string;
  id: string;
  name: string;
  category: string;
  summary: string;
  address: string;
  rating?: number;
  visitDate: string;
  visitTime: string;
  durationMinutes: number;
  note: string;
  latitude?: number;
  longitude?: number;
}

export interface SavedTripPlan {
  id: string;
  type: PlannerMode;
  title: string;
  summary: string;
  updatedAt: string;
  aiPreferences?: AiPreferenceState;
  aiRouteStops?: AiRouteStop[];
  manualStartDate?: string;
  manualEndDate?: string;
  manualStops?: SavedManualStop[];
}

export interface PlanSummaryResponse {
  plan_id: string;
  title: string | null;
  travel_days: number;
  created_at: string;
  updated_at: string;
}

export interface PlanItemResponse {
  item_id: string;
  day_number: number;
  position: number;
  place_id: string;
  display_name: string;
  address: string;
  visit_time: string | null;
  rating: number | null;
  photos: string[];
  category?: string;
  latitude?: number;
  longitude?: number;
  location?: {
    lat?: number;
    lng?: number;
  } | null;
}

export interface PlanDetailResponse extends PlanSummaryResponse {
  user_id?: string;
  items: PlanItemResponse[];
}

export interface PlanListResponse {
  plans: PlanSummaryResponse[];
}

interface TourPlacesLookupItem {
  place_id?: string;
  display_name?: string;
  category?: string;
  address?: string;
  short_address?: string | null;
  location?: {
    lat?: number;
    lng?: number;
  } | null;
  rating?: number | null;
}

interface TourPlacesLookupResponse {
  places?: TourPlacesLookupItem[];
  items?: TourPlacesLookupItem[];
  data?: TourPlacesLookupItem[];
}

export interface CreatePlanItemRequest {
  day_number: number;
  place_id: string;
  visit_time?: string | null;
}

export interface MovePlanItemRequest {
  target_day_number: number;
  after_item_id: string | null;
}

export interface CreatePlanRequest {
  title: string | null;
  travel_days: number;
  items: CreatePlanItemRequest[];
}

export interface SharePlanResponse {
  share_token: string;
  expires_at: string;
}

export interface TourRecommendRequest {
  travel_days: number;
  travel_style: "맛집 탐방" | "쇼핑" | "문화/역사" | "카페" | "자연/공원";
  budget: "저예산" | "중간" | "고예산";
  companion_type: "혼자" | "연인" | "친구" | "가족";
  schedule_density: "빽빽하게" | "널널하게";
}

export interface TourRecommendPlace {
  place_id: string;
  display_name: string;
  category: string;
  address: string;
  location?: {
    lat?: number;
    lng?: number;
  } | null;
  rating?: number | null;
  description?: string;
  tip?: string;
  photos?: string[];
}

export interface TourRecommendDayPlan {
  day: number;
  cluster_name: string;
  places: TourRecommendPlace[];
}

export interface TourRecommendResponse {
  tour_plan: TourRecommendDayPlan[];
}
export interface AiPlanDayInput {
  departureCluster: string;
  arrivalCluster: string;
  startTime: string;
  endTime: string;
  additionalPlaceId: string | null;
  additionalPlaceName?: string;
}

export type FoodPreferenceCode = "halal" | "vegetarian" | "any";
export type TransportCode = "public_transport";
export type ScheduleDensityCode = "relaxed" | "packed";
export type CompanionCode =
  | "solo"
  | "couple"
  | "spouse"
  | "friends_colleagues"
  | "family_parents"
  | "family_with_kids";
export type StyleCode =
  | "activity"
  | "famous_attractions"
  | "healing"
  | "culture_history"
  | "shopping"
  | "food_tour"
  | "photo_aesthetic"
  | "festival_event";

export interface TourDayRequestV2 {
  departure_cluster: string;
  arrival_cluster: string;
  additional_place_id: string | null;
  transport: TransportCode;
  start_time: string;
  end_time: string;
  companion: CompanionCode;
  budget_per_person_krw: number;
  styles: StyleCode[];
  schedule_density: ScheduleDensityCode;
}

export interface TourRecommendRequestV2 {
  travel_days: number;
  food_preference: FoodPreferenceCode;
  days: TourDayRequestV2[];
}

export interface TimelineSlotV2 {
  time: string;
  place_id: string;
  title: string;
}

export interface PlaceDetailV2 {
  place_id: string;
  display_name: string;
  category: string;
  address: string;
  location: { lat: number; lng: number };
  rating: number | null;
  reason: string;
  estimated_cost_krw: number;
  stay_minutes: number;
  photos: string[];
}

export interface MovementHopV2 {
  from_place: string;
  to_place: string;
  method: string;
}

export interface BudgetItemV2 {
  label: string;
  amount_krw: number;
}

export interface TourDayResponseV2 {
  day: number;
  timeline: TimelineSlotV2[];
  places: PlaceDetailV2[];
  movements: MovementHopV2[];
  budget_breakdown: BudgetItemV2[];
  budget_total_krw: number;
  summary: string;
}

export interface TourRecommendResponseV2 {
  tour_plan: TourDayResponseV2[];
}

export const defaultPreferences: AiPreferenceState = {
  departure: "",
  arrival: "",
  styles: [],
  pace: "",
  extraPlace: "",
  transport: "",
  startTime: "10:00",
  endTime: "21:00",
  companion: "",
  budgetValue: 5,
  budgetCategory: "Low",
  foodNeed: "",
  durationDays: 1,
};

export const styleTokens = [
  "Experiences & Activities",
  "Hot Place",
  "Relaxation & Wellness",
  "Culture & History",
  "Festivals & Events",
  "Food Tours",
  "Shopping",
  "Photography & Aesthetics",
];

export const paceOptions: PaceOption[] = ["Slow", "Packed"];
export const transportOptions: TransportOption[] = [
  "Public Transit",
  "Taxi",
  "Walk",
];
export const companionOptions: CompanionOption[] = [
  "Solo",
  "Couple",
  "Spouse",
  "Friends",
  "Family",
  "Family with Kids",
];
export const foodNeeds = ["Halal Food", "Vegetarian"];
export const durationOptions = [1, 2, 3];
export const KRW_PER_BUDGET_UNIT = 10000;
export const BUDGET_SLIDER_MIN = 5;
export const BUDGET_SLIDER_MAX = 50;
export const BUDGET_SLIDER_STEP = 1;
export const BUDGET_TIER_HINTS = {
  Low: "$40-$70 / day",
  Moderate: "$100-$200 / day",
  High: "$250+ / day",
} satisfies Record<BudgetCategory, string>;
export const seoulClusterKeys = [
  "Myeongdong / Euljiro",
  "Gangnam Station",
  "Hongdae / Hapjeong",
  "Itaewon",
  "Jamsil",
  "Konkuk Univ. Station (Kondae)",
  "Sinchon / Yonsei Univ.",
  "Jongno / Insadong",
  "Yeouido",
  "Seongsu-dong",
  "Mangwon / Yeonnam-dong",
  "Euljiro 3-ga / Chungmuro",
  "Apgujeong / Cheongdam",
  "Garosu-gil (Sinsa)",
  "Bukchon / Samcheong-dong",
  "Gwangjang Market / Dongdaemun",
  "Yongsan / Haebangchon (HBC)",
  "Hannam-dong",
  "Mullae-dong",
  "Songridan-gil (Songpa)",
  "Seoul Forest / Ttukseom",
  "Mapo / Gongdeok",
  "Nakseongdae / Sharosu-gil",
  "Hyehwa / Daehangno",
  "Hoegi / Kyung Hee Univ.",
  "Noryangjin / Dongjak",
  "Wangsimni / Sangwangsimni",
  "Dosan Park / Hak-dong",
  "Samseong / COEX",
  "Bangbae / Seorae Village",
  "Sangsu-dong",
  "Ikseon-dong",
  "Banpo Hangang Park",
  "N Seoul Tower Area (Namsan)",
  "DDP / Dongdaemun",
  "Seongbuk-dong",
  "Yeonhui-dong",
  "Ssangmun / Suyu",
];

export function getAiPlanDayInputs(value: AiPreferenceState): AiPlanDayInput[] {
  const travelDays = Math.max(1, Math.min(3, value.durationDays || 1));
  const existing = Array.isArray(value.days) ? value.days : [];
  const defaultCluster = seoulClusterKeys[0];

  return Array.from({ length: travelDays }, (_, index) => {
    const existingDay = existing[index];
    const shouldUseLegacyAdditionalPlace = !existingDay && index === 0;

    return {
      departureCluster:
        existingDay?.departureCluster || value.departure || defaultCluster,
      arrivalCluster:
        existingDay?.arrivalCluster || value.arrival || defaultCluster,
      startTime: existingDay?.startTime || value.startTime || "10:00",
      endTime: existingDay?.endTime || value.endTime || "21:00",
      additionalPlaceId:
        existingDay?.additionalPlaceId ??
        (shouldUseLegacyAdditionalPlace ? value.additionalPlaceId ?? null : null),
      additionalPlaceName:
        existingDay?.additionalPlaceName ||
        (shouldUseLegacyAdditionalPlace ? value.additionalPlaceName || "" : ""),
    };
  });
}

export function toFoodPreferenceCode(value: AiPreferenceState): FoodPreferenceCode {
  if (value.foodNeed === "Halal Food") return "halal";
  if (value.foodNeed === "Vegetarian" || value.foodNeed === "Vegan") return "vegetarian";
  return "any";
}

export function toCompanionCode(value: AiPreferenceState): CompanionCode {
  if (value.companion === "Couple") return "couple";
  if (value.companion === "Spouse") return "spouse";
  if (value.companion === "Friends") return "friends_colleagues";
  if (value.companion === "Family with Kids") return "family_with_kids";
  if (value.companion === "Family") return "family_parents";
  return "solo";
}

export function toScheduleDensityCode(
  pace: AiPreferenceState["pace"]
): ScheduleDensityCode {
  return pace === "Packed" ? "packed" : "relaxed";
}

export function toStyleCode(token: string): StyleCode {
  const normalized = token.toLowerCase();
  if (normalized.includes("food")) return "food_tour";
  if (normalized.includes("shopping")) return "shopping";
  if (normalized.includes("culture") || normalized.includes("history")) return "culture_history";
  if (normalized.includes("relaxation") || normalized.includes("wellness")) return "healing";
  if (normalized.includes("festival") || normalized.includes("event")) return "festival_event";
  if (normalized.includes("photo") || normalized.includes("aesthetic")) return "photo_aesthetic";
  if (normalized.includes("hot")) return "famous_attractions";
  return "activity";
}

export function toStyleCodes(styles: string[]): StyleCode[] {
  const unique = Array.from(new Set(styles.map(toStyleCode)));
  return unique.length > 0 ? unique : ["activity"];
}

export function toRecommendRequestV2(
  preferences: AiPreferenceState
): TourRecommendRequestV2 {
  const days = getAiPlanDayInputs(preferences);
  const styles = toStyleCodes(preferences.styles);

  return {
    travel_days: days.length,
    food_preference: toFoodPreferenceCode(preferences),
    days: days.map((day) => ({
      departure_cluster: day.departureCluster,
      arrival_cluster: day.arrivalCluster,
      additional_place_id: day.additionalPlaceId || null,
      transport: "public_transport",
      start_time: day.startTime,
      end_time: day.endTime,
      companion: toCompanionCode(preferences),
      budget_per_person_krw: Math.max(
        0,
        Math.round(preferences.budgetValue * KRW_PER_BUDGET_UNIT)
      ),
      styles,
      schedule_density: toScheduleDensityCode(preferences.pace),
    })),
  };
}

export async function getTourRecommendationsV2(
  preferences: AiPreferenceState,
  timeoutMs = TOUR_RECOMMEND_TIMEOUT_MS
): Promise<TourRecommendResponseV2> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}/api/tour/recommend`, {
      method: "POST",
      credentials: "include",
      signal: controller.signal,
      headers: getTourApiHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(toRecommendRequestV2(preferences)),
    });

    if (!response.ok) {
      let detail = "Failed to load recommended tour plan.";

      try {
        const data = (await response.json()) as { detail?: unknown; message?: unknown };
        const message = data.detail || data.message;
        detail = typeof message === "string" ? message : detail;
      } catch {
        // Keep default message for non-JSON responses.
      }

      const error = new Error(detail) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    const data = (await response.json()) as Partial<TourRecommendResponseV2>;
    return {
      tour_plan: Array.isArray(data.tour_plan) ? data.tour_plan : [],
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Recommendation timed out after 120 seconds.");
    }

    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function flattenRecommendedPlacesV2(
  response: TourRecommendResponseV2 | null
): PlaceDetailV2[] {
  const seen = new Set<string>();
  const places: PlaceDetailV2[] = [];

  response?.tour_plan.forEach((day) => {
    day.places.forEach((place) => {
      if (!seen.has(place.place_id)) {
        seen.add(place.place_id);
        places.push(place);
      }
    });
  });

  return places;
}

export function placeDetailToRouteStop(
  place: PlaceDetailV2,
  day: number,
  index: number
): AiRouteStop {
  return {
    id: place.place_id,
    name: place.display_name,
    category: place.category,
    summary: place.reason,
    address: place.address,
    latitude: place.location?.lat,
    longitude: place.location?.lng,
    keyword: place.category,
    day,
    order: index + 1,
    rating: place.rating,
    eventType: "place",
  };
}

export function tourPlanV2ToRouteStops(
  response: TourRecommendResponseV2 | null
): AiRouteStop[] {
  return response
    ? response.tour_plan.flatMap((day) =>
        day.places.map((place, index) => placeDetailToRouteStop(place, day.day, index))
      )
    : [];
}

export function formatKrw(value: number): string {
  if (!value) return "₩—";
  return `₩${value.toLocaleString()}`;
}

export function budgetCategoryFromValue(value: number): BudgetCategory {
  if (value <= 10) return "Low";
  if (value >= 35) return "High";
  return "Moderate";
}

export function budgetCategoryLabel(category: BudgetCategory): string {
  if (category === "Low") return "Low Budget";
  if (category === "High") return "High Budget";
  return "Mid Budget";
}

export function budgetCategoryHint(category: BudgetCategory): string {
  return BUDGET_TIER_HINTS[category];
}

export function budgetCategoryIcon(category: BudgetCategory): string {
  if (category === "Low") return "$";
  if (category === "High") return "$$$";
  return "$$";
}

export function formatBudgetValue(value: number): string {
  return (value * KRW_PER_BUDGET_UNIT).toLocaleString();
}

export function clonePreferences(
  value?: Partial<AiPreferenceState> | null
): AiPreferenceState {
  const rawBudgetValue =
    typeof value?.budgetValue === "number"
      ? value.budgetValue
      : defaultPreferences.budgetValue;
  const budgetValue = Math.max(
    BUDGET_SLIDER_MIN,
    Math.min(BUDGET_SLIDER_MAX, rawBudgetValue)
  );

  return {
    ...defaultPreferences,
    ...value,
    styles:
      Array.isArray(value?.styles) && value.styles.length > 0 ? value.styles : [],
    budgetValue,
    budgetCategory: budgetCategoryFromValue(budgetValue),
  };
}

export function loadPreferences(): AiPreferenceState {
  if (typeof window === "undefined") return defaultPreferences;

  try {
    const raw = window.localStorage.getItem(AI_PLAN_STORAGE_KEY);
    if (!raw) return defaultPreferences;
    return clonePreferences(JSON.parse(raw) as Partial<AiPreferenceState>);
  } catch {
    return defaultPreferences;
  }
}

export function savePreferences(value: AiPreferenceState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AI_PLAN_STORAGE_KEY, JSON.stringify(value));
}

export function clearPreferences(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AI_PLAN_STORAGE_KEY);
}

export function buildPlanTitle(mode: PlannerMode, seed?: string): string {
  const fallback = mode === "ai" ? "AI Trip Plan" : "Manual Trip Plan";
  const trimmed = seed?.trim();
  return trimmed ? trimmed : fallback;
}

export function loadSavedPlans(): SavedTripPlan[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = window.localStorage.getItem(SAVED_PLANS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedTripPlan[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistSavedPlans(plans: SavedTripPlan[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SAVED_PLANS_STORAGE_KEY, JSON.stringify(plans));
  window.dispatchEvent(new CustomEvent(SAVED_PLANS_EVENT));
}

export function getSavedPlanById(
  planId: string | null | undefined
): SavedTripPlan | null {
  if (!planId) return null;
  return loadSavedPlans().find((plan) => plan.id === planId) || null;
}

export function upsertSavedPlan(
  plan: Omit<SavedTripPlan, "id" | "updatedAt"> & { id?: string }
): SavedTripPlan {
  const currentPlans = loadSavedPlans();
  const nextPlan: SavedTripPlan = {
    ...plan,
    id: plan.id || createPlanId(plan.type),
    updatedAt: new Date().toISOString(),
  };

  const nextPlans = [
    nextPlan,
    ...currentPlans.filter((item) => item.id !== nextPlan.id),
  ];

  persistSavedPlans(nextPlans);
  return nextPlan;
}

export function removeSavedPlan(planId: string): void {
  const currentPlans = loadSavedPlans();
  persistSavedPlans(currentPlans.filter((plan) => plan.id !== planId));
}

export function createPlanId(mode: PlannerMode): string {
  return `${mode}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createAiSummary(
  preferences: AiPreferenceState,
  stopCount: number
): string {
  const activeStyles =
    preferences.styles.length > 0 ? preferences.styles.join(", ") : "no style selected";
  const budgetLabel = budgetCategoryLabel(preferences.budgetCategory);
  return `This is a ${budgetLabel.toLowerCase()} itinerary connecting ${stopCount} locations, based on ${activeStyles}`;
}

async function parsePlanApiError(
  response: Response,
  fallback: string
): Promise<Error & { status?: number }> {
  let detail = fallback;

  try {
    const data = (await response.json()) as { detail?: unknown; message?: unknown };
    const message = data.detail || data.message;
    detail = typeof message === "string" ? message : fallback;
  } catch {
    // Keep fallback for non-JSON responses.
  }

  const error = new Error(detail) as Error & { status?: number };
  error.status = response.status;
  return error;
}

async function planApiFetch<T>(
  path: string,
  options: RequestInit = {},
  fallback = "Plan request failed."
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: getTourApiHeaders({
      "Content-Type": "application/json",
      ...options.headers,
    } as RequestHeaders),
  });

  if (!response.ok) {
    throw await parsePlanApiError(response, fallback);
  }

  return (await response.json()) as T;
}

function readPlanItemLatitude(item: PlanItemResponse): number {
  return Number(item.latitude ?? item.location?.lat);
}

function readPlanItemLongitude(item: PlanItemResponse): number {
  return Number(item.longitude ?? item.location?.lng);
}

function planItemHasCoordinates(item: PlanItemResponse): boolean {
  return (
    Number.isFinite(readPlanItemLatitude(item)) &&
    Number.isFinite(readPlanItemLongitude(item))
  );
}

function normalizeLookupItems(
  payload: TourPlacesLookupResponse | TourPlacesLookupItem[]
): TourPlacesLookupItem[] {
  if (Array.isArray(payload)) return payload;
  return payload.places || payload.items || payload.data || [];
}

async function findPlaceForPlanItem(
  item: PlanItemResponse
): Promise<TourPlacesLookupItem | null> {
  const queries = Array.from(
    new Set([item.display_name, item.address].map((value) => value.trim()).filter(Boolean))
  );

  for (const keyword of queries) {
    const params = new URLSearchParams({
      lat: String(DEFAULT_MAP_CENTER.lat),
      lng: String(DEFAULT_MAP_CENTER.lng),
      keyword,
    });
    const payload = await planApiFetch<
      TourPlacesLookupResponse | TourPlacesLookupItem[]
    >(
      `/api/tour/places?${params.toString()}`,
      { method: "GET" },
      "Failed to load place coordinates."
    );
    const matched = normalizeLookupItems(payload).find(
      (place) => place.place_id === item.place_id
    );

    if (matched) return matched;
  }

  return null;
}

export async function hydratePlanItemCoordinates(
  plan: PlanDetailResponse
): Promise<PlanDetailResponse> {
  const lookupByPlaceId = new Map<string, Promise<TourPlacesLookupItem | null>>();

  const items = await Promise.all(
    plan.items.map(async (item) => {
      if (planItemHasCoordinates(item)) return item;

      if (!lookupByPlaceId.has(item.place_id)) {
        lookupByPlaceId.set(
          item.place_id,
          findPlaceForPlanItem(item).catch(() => null)
        );
      }

      const place = await lookupByPlaceId.get(item.place_id);
      const latitude = Number(place?.location?.lat);
      const longitude = Number(place?.location?.lng);

      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return item;
      }

      return {
        ...item,
        display_name: place?.display_name || item.display_name,
        address: place?.short_address || place?.address || item.address,
        rating:
          typeof place?.rating === "number" ? place.rating : item.rating,
        category: place?.category || item.category,
        latitude,
        longitude,
        location: {
          lat: latitude,
          lng: longitude,
        },
      };
    })
  );

  return {
    ...plan,
    items,
  };
}

function normalizeVisitTime(value?: string | null): string | null {
  if (!value) return null;
  return /^\d{2}:\d{2}$/.test(value) ? value : null;
}

export function tourPlanToCreateItems(
  response: TourRecommendResponseV2 | null
): CreatePlanItemRequest[] {
  if (!response) return [];

  return response.tour_plan.flatMap((day) => {
    const firstSlotByPlace = new Map<string, TimelineSlotV2>();
    day.timeline.forEach((slot) => {
      if (!firstSlotByPlace.has(slot.place_id)) {
        firstSlotByPlace.set(slot.place_id, slot);
      }
    });

    return day.places.map((place) => ({
      day_number: day.day,
      place_id: place.place_id,
      visit_time: normalizeVisitTime(firstSlotByPlace.get(place.place_id)?.time),
    }));
  });
}

export function routeStopsToCreateItems(
  stops: SavedManualStop[]
): CreatePlanItemRequest[] {
  const sortedDates = Array.from(new Set(stops.map((stop) => stop.visitDate))).sort();
  const dayByDate = new Map(
    sortedDates.map((date, index) => [date, index + 1] as const)
  );

  return stops.map((stop) => ({
    day_number: dayByDate.get(stop.visitDate) || 1,
    place_id: stop.id,
    visit_time: normalizeVisitTime(stop.visitTime),
  }));
}

export async function createTourPlan(
  payload: CreatePlanRequest
): Promise<PlanDetailResponse> {
  return planApiFetch<PlanDetailResponse>(
    "/api/tour/plans",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    "Failed to save plan."
  );
}

export async function listTourPlans(): Promise<PlanSummaryResponse[]> {
  const data = await planApiFetch<PlanListResponse>(
    "/api/tour/plans",
    { method: "GET" },
    "Failed to load saved plans."
  );
  return Array.isArray(data.plans) ? data.plans : [];
}

export async function getTourPlan(
  planId: string
): Promise<PlanDetailResponse> {
  return planApiFetch<PlanDetailResponse>(
    `/api/tour/plans/${encodeURIComponent(planId)}`,
    { method: "GET" },
    "Failed to load saved plan."
  );
}

export async function updateTourPlanTitle(
  planId: string,
  title: string | null
): Promise<PlanSummaryResponse> {
  return planApiFetch<PlanSummaryResponse>(
    `/api/tour/plans/${encodeURIComponent(planId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    },
    "Failed to update plan title."
  );
}

export async function deleteTourPlan(planId: string): Promise<void> {
  await planApiFetch<{ message: string }>(
    `/api/tour/plans/${encodeURIComponent(planId)}`,
    { method: "DELETE" },
    "Failed to delete plan."
  );
}

export async function createTourPlanShareToken(
  planId: string
): Promise<SharePlanResponse> {
  return planApiFetch<SharePlanResponse>(
    `/api/tour/plans/${encodeURIComponent(planId)}/share`,
    { method: "POST" },
    "Failed to create share link."
  );
}

export async function addTourPlanDay(
  planId: string
): Promise<PlanSummaryResponse> {
  return planApiFetch<PlanSummaryResponse>(
    `/api/tour/plans/${encodeURIComponent(planId)}/days`,
    { method: "POST" },
    "Failed to add day."
  );
}

export async function createTourPlanItem(
  planId: string,
  payload: CreatePlanItemRequest
): Promise<PlanItemResponse> {
  return planApiFetch<PlanItemResponse>(
    `/api/tour/plans/${encodeURIComponent(planId)}/items`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    "Failed to add place."
  );
}

export async function updateTourPlanItem(
  planId: string,
  itemId: string,
  payload: Omit<CreatePlanItemRequest, "day_number">
): Promise<PlanItemResponse> {
  return planApiFetch<PlanItemResponse>(
    `/api/tour/plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    "Failed to update place."
  );
}

export async function moveTourPlanItem(
  planId: string,
  itemId: string,
  payload: MovePlanItemRequest
): Promise<void> {
  await planApiFetch<{ message: string }>(
    `/api/tour/plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}/move`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    "Failed to move place."
  );
}

export async function deleteTourPlanItem(
  planId: string,
  itemId: string
): Promise<void> {
  await planApiFetch<{ message: string }>(
    `/api/tour/plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}`,
    { method: "DELETE" },
    "Failed to delete place."
  );
}

export async function getPublicSharedPlan(
  shareToken: string
): Promise<PlanDetailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/public/share/plan/${encodeURIComponent(shareToken)}`
  );

  if (!response.ok) {
    throw await parsePlanApiError(response, "Failed to load shared plan.");
  }

  return (await response.json()) as PlanDetailResponse;
}

export function timeToMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return (Number.isFinite(hours) ? hours : 0) * 60 + (Number.isFinite(minutes) ? minutes : 0);
}

export function minutesToTime(totalMinutes: number): string {
  const normalized = Math.max(0, Math.min(23 * 60 + 59, Math.round(totalMinutes)));
  const hours = Math.floor(normalized / 60).toString().padStart(2, "0");
  const minutes = (normalized % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function roundDownToUnit(minutes: number, unitMinutes: number): number {
  return Math.floor(minutes / unitMinutes) * unitMinutes;
}

export function roundUpToUnit(minutes: number, unitMinutes: number): number {
  return Math.ceil(minutes / unitMinutes) * unitMinutes;
}

export function toRecommendRequest(
  preferences: AiPreferenceState
): TourRecommendRequest {
  return {
    travel_days: Math.max(1, Math.min(3, preferences.durationDays || 1)),
    travel_style: toRecommendTravelStyle(preferences.styles),
    budget: toRecommendBudget(preferences.budgetCategory),
    companion_type: toRecommendCompanion(preferences.companion),
    schedule_density: toRecommendDensity(preferences.pace),
  };
}

export function toRecommendDensity(
  pace: AiPreferenceState["pace"]
): TourRecommendRequest["schedule_density"] {
  return pace === "Packed" ? "빽빽하게" : "널널하게";
}

export function getScheduleItemTargetCount(
  pace: AiPreferenceState["pace"]
): number {
  if (pace === "Packed") return 9;
  if (pace === "Balanced") return 7;
  return 5;
}

function toRecommendTravelStyle(
  styles: string[]
): TourRecommendRequest["travel_style"] {
  const normalized = styles.join(" ").toLowerCase();
  if (normalized.includes("food")) return "맛집 탐방";
  if (normalized.includes("shopping")) return "쇼핑";
  if (normalized.includes("culture") || normalized.includes("history")) return "문화/역사";
  if (normalized.includes("relaxation") || normalized.includes("nature")) return "자연/공원";
  return "카페";
}

function toRecommendBudget(
  budget: BudgetCategory
): TourRecommendRequest["budget"] {
  if (budget === "Low") return "저예산";
  if (budget === "High") return "고예산";
  return "중간";
}

function toRecommendCompanion(
  companion: AiPreferenceState["companion"]
): TourRecommendRequest["companion_type"] {
  if (companion === "Couple") return "연인";
  if (companion === "Friends") return "친구";
  if (companion === "Family") return "가족";
  return "혼자";
}

export async function getTourRecommendations(
  preferences: AiPreferenceState
): Promise<TourRecommendResponse> {
  return postTourRecommend(toRecommendRequest(preferences));
}

export async function postTourRecommend(
  payload: TourRecommendRequest
): Promise<TourRecommendResponse> {
  const response = await fetch(`${API_BASE_URL}/api/tour/recommend`, {
    method: "POST",
    credentials: "include",
    headers: getTourApiHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = "Failed to load recommended tour plan.";

    try {
      const data = (await response.json()) as { detail?: unknown; message?: unknown };
      const message = data.detail || data.message;
      detail = typeof message === "string" ? message : detail;
    } catch {
      // Keep default message for non-JSON responses.
    }

    const error = new Error(detail) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }

  const data = (await response.json()) as unknown;
  const payloadData = data as Partial<TourRecommendResponse>;
  return {
    tour_plan: Array.isArray(payloadData.tour_plan) ? payloadData.tour_plan : [],
  };
}

export function flattenRecommendedPlaces(
  response: TourRecommendResponse
): TourRecommendPlace[] {
  return response.tour_plan.flatMap((day) =>
    Array.isArray(day.places) ? day.places : []
  );
}

export function normalizePlaceKey(value: string): string {
  return value.toLowerCase().replace(/\s+/g, "").trim();
}

export function inferExtraPlaceCategory(value: string): string | null {
  const normalized = normalizePlaceKey(value);
  if (normalized.includes("cafe") || normalized.includes("카페")) return "카페";
  if (normalized.includes("shopping") || normalized.includes("쇼핑")) return "쇼핑";
  if (normalized.includes("food") || normalized.includes("맛집")) return "맛집 탐방";
  if (normalized.includes("culture") || normalized.includes("history") || normalized.includes("문화") || normalized.includes("역사")) {
    return "문화/역사";
  }
  if (normalized.includes("park") || normalized.includes("nature") || normalized.includes("자연") || normalized.includes("공원")) {
    return "자연/공원";
  }
  return null;
}