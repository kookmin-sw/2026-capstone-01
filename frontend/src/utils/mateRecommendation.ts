export type RecommendationCandidate = {
  user_id: string;
  user_name: string;
  profile_image_url: string | null;
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
  nationality: string;
  [key: string]: unknown;
};

export type RecommendedTraveler = RecommendationCandidate & {
  similarity_score: number;
};

const TRAVEL_STYLE_ALIASES: Record<string, string> = {
  food: "food_tour",
  foodie: "food_tour",
  food_tour: "food_tour",
  restaurant: "food_tour",
  relaxation: "healing",
  relax: "healing",
  wellness: "healing",
  healing: "healing",
  tourism: "famous_attractions",
  tourist: "famous_attractions",
  attraction: "famous_attractions",
  famous_attractions: "famous_attractions",
  culture: "culture_history",
  history: "culture_history",
  culture_history: "culture_history",
  traditional: "culture_history",
  tradition: "culture_history",
  nature: "nature",
  park: "nature",
  activity: "activity",
  active: "activity",
  shopping: "shopping",
  photo: "photo_aesthetic",
  photo_aesthetic: "photo_aesthetic",
  festival: "festival_event",
  event: "festival_event",
  festival_event: "festival_event",
  trekking: "trekking",
  hiking: "trekking",
  hidden_gems: "hidden_gems",
  local: "hidden_gems",
  art: "art_exhibition",
  exhibition: "art_exhibition",
  art_exhibition: "art_exhibition",
  theme_park: "theme_park",
  amusement: "theme_park",
};

export type MatePreferenceProfile = {
  user_id?: string | null;
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
  nationality?: string;
};

export function recommendTravelers(
  currentUser: MatePreferenceProfile,
  candidates: RecommendationCandidate[],
  topN = 10
): RecommendedTraveler[] {
  const myPreferences = toPreferenceSet(currentUser);

  return candidates
    .filter((candidate) => candidate.user_id !== currentUser.user_id)
    .map((candidate) => ({
      candidate,
      candidatePreferences: toPreferenceSet(candidate),
    }))
    .filter(({ candidatePreferences }) => candidatePreferences.size > 0)
    .map((candidate) => {
      const preferenceScore = setCosineSimilarity(
        myPreferences,
        candidate.candidatePreferences
      );
      const nationalityBonus =
        currentUser.nationality &&
        candidate.candidate.nationality === currentUser.nationality
          ? 0.05
          : 0;

      return {
        ...candidate.candidate,
        similarity_score: Math.min(1, preferenceScore + nationalityBonus),
      };
    })
    .sort((a, b) => b.similarity_score - a.similarity_score)
    .slice(0, topN);
}

function toPreferenceSet(profile: MatePreferenceProfile): Set<string> {
  return new Set(
    [
      ...(profile.travel_styles ?? []),
      ...(profile.food_preferences ?? []),
      profile.density_preference,
      profile.budget_preference,
      profile.walking_preference,
      ...(profile.transport_preferences ?? []),
      profile.companion_preference,
      ...(profile.time_preferences ?? []),
      profile.communication_preference,
      profile.planning_preference,
    ]
      .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      .map(normalizePreferenceKey)
      .filter((style): style is string => Boolean(style))
  );
}

function normalizePreferenceKey(style: string): string | null {
  const normalized = style.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (!normalized) return null;
  return TRAVEL_STYLE_ALIASES[normalized] ?? normalized;
}

function setCosineSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;

  let intersection = 0;
  a.forEach((style) => {
    if (b.has(style)) intersection += 1;
  });

  return intersection / Math.sqrt(a.size * b.size);
}
