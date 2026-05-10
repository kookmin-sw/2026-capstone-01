import client from "./client";
import type { RecommendationCandidate } from "../utils/mateRecommendation";

export interface RecommendationCandidatesResponse {
  items: RecommendationCandidate[];
}

export async function getRecommendationCandidates(): Promise<RecommendationCandidatesResponse> {
  const { data } = await client.get<
    | RecommendationCandidate[]
    | RecommendationCandidatesResponse
    | { users?: RecommendationCandidate[]; profiles?: RecommendationCandidate[] }
  >("/api/auth/profile/all");

  if (Array.isArray(data)) {
    return { items: normalizeRecommendationCandidates(data) };
  }

  return {
    items: normalizeRecommendationCandidates(
      data.items ?? data.users ?? data.profiles ?? []
    ),
  };
}

function normalizeRecommendationCandidates(
  candidates: RecommendationCandidate[]
): RecommendationCandidate[] {
  return candidates
    .filter((candidate) => candidate.user_id && candidate.user_name)
    .map((candidate) => ({
      ...candidate,
      user_id: candidate.user_id,
      user_name: candidate.user_name,
      profile_image_url: candidate.profile_image_url ?? null,
      travel_styles: readTravelStyles(candidate),
      food_preferences: readStringList(candidate, "food_preferences", "foodPreferences"),
      density_preference: readStringValue(candidate, "density_preference", "densityPreference"),
      budget_preference: readStringValue(candidate, "budget_preference", "budgetPreference"),
      walking_preference: readStringValue(candidate, "walking_preference", "walkingPreference"),
      transport_preferences: readStringList(
        candidate,
        "transport_preferences",
        "transportPreferences"
      ),
      companion_preference: readStringValue(
        candidate,
        "companion_preference",
        "companionPreference"
      ),
      time_preferences: readStringList(candidate, "time_preferences", "timePreferences"),
      communication_preference: readStringValue(
        candidate,
        "communication_preference",
        "communicationPreference"
      ),
      planning_preference: readStringValue(
        candidate,
        "planning_preference",
        "planningPreference"
      ),
      nationality: candidate.nationality ?? "",
    }));
}

function readTravelStyles(candidate: RecommendationCandidate): string[] {
  const value = candidate as RecommendationCandidate & {
    travelStyles?: unknown;
    travel_style?: unknown;
    travelStyle?: unknown;
    style_tags?: unknown;
    styles?: unknown;
    travel_style_preferences?: unknown;
  };

  return toStringArray(
    value.travel_styles ??
      value.travelStyles ??
      value.travel_style ??
      value.travelStyle ??
      value.style_tags ??
      value.styles ??
      value.travel_style_preferences
  );
}

function toStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string");
  }
  if (typeof value === "string") {
    return value
      .split(/[,\|/]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function readStringList(
  candidate: RecommendationCandidate,
  ...keys: string[]
): string[] {
  const record = candidate as Record<string, unknown>;
  for (const key of keys) {
    const items = toStringArray(record[key]);
    if (items.length > 0) return items;
  }
  return [];
}

function readStringValue(
  candidate: RecommendationCandidate,
  ...keys: string[]
): string | undefined {
  const record = candidate as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}
