import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, MouseEvent, SyntheticEvent, UIEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  addTourPlaceFavorite,
  deleteTourSearchHistoryOne,
  getTourPlaceFavorites,
  getTourSearchHistory,
  getMyProfile,
  getTourPlaces,
  removeTourPlaceFavorite,
  type FavoritePlaceApiItem,
  type SearchHistoryItem,
  type TourPlaceApiItem,
  type TourPlacesParams,
  type UserProfile,
} from "../../api/auth/auth";
import NotificationBell from "../../components/NotificationBell";
import { getPlaceCategoryImageUrl } from "../../data/placeCategoryImages";

import { showAppToast } from "../../utils/appToast";

const DEFAULT_LOCATION = { lat: 37.5665, lng: 126.978 };
const DEFAULT_LOCATION_LABEL = "Central Seoul";
const DETECTING_LOCATION_LABEL = "Detecting your location";
const CURRENT_LOCATION_LABEL = "Using your current location";
const GEOLOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 60000,
  timeout: 10000,
};
const GEOLOCATION_WATCH_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 60000,
  timeout: 10000,
};
const SEARCH_SUGGESTION_LIMIT = 8;
const ALL_CATEGORY = "All";
const CATEGORY_GROUPS = {
  FOOD_AND_DRINK: "Food & Drink",
  STAY: "Stay",
  SHOPPING: "Shopping",
  ATTRACTIONS: "Attractions",
  ESSENTIALS: "Essentials",
  OTHER: "Other",
} as const;

const SORT_FILTERS = ["Nearest", "Top Rated", "Most Reviewed", "Favorites"] as const;

const CATEGORY_DISPLAY_ORDER = [
  "Food & Drink",
  "Shopping",
  "Other",
  "Stay",
  "Attractions",
  "Essentials",
];

type SortFilter = (typeof SORT_FILTERS)[number];
type LocationStatus = "detecting" | "ready" | "approximate" | "fallback";
type PlaceCategory = string;
type PlaceTag = "Indoor" | "Outdoor" | "Crowded" | "Quiet";

interface Place {
  id: string;
  googlePlaceId: string;
  favoriteId?: string;
  favoriteCreatedAt?: string;
  initialIsFavorite?: boolean;
  name: string;
  category: PlaceCategory;
  groupCategory: string;
  raw: TourPlaceApiItem;
  tags: PlaceTag[];
  description: string;
  reviewCount: number;
  rating?: number;
  rawDistanceMeters?: number;
  hasCoordinates: boolean;
  address?: string;
  shortAddress?: string;
  phone?: string;
  phoneInternational?: string;
  website?: string;
  googleMapsUrl?: string;
  googleMapReviewLink?: string;
  photos: string[];
  openingHours: string[];
  services: string[];
  payment: string[];
  accessibility: string[];
  parking: string[];
  priceLevel?: string;
  priceRange?: {
    min?: string;
    max?: string;
  };
  reviews: Array<{
    author: string;
    rating?: number;
    relativeTime?: string;
    text?: string;
  }>;
  coords: {
    lat: number;
    lng: number;
  };
  thumbnail: {
    colors: readonly [string, string] | readonly string[];
    label: string;
  };
}

interface PlaceWithMeta extends Place {
  isFavorite: boolean;
  distanceKm: number;
}

function formatDistance(distanceKm: number): string {
  if (!Number.isFinite(distanceKm)) return "Checking distance";
  if (distanceKm < 1) return `${Math.round(distanceKm * 1000)}m`;
  return `${distanceKm.toFixed(1)}km`;
}

function formatRating(rating?: number, reviewCount?: number): string {
  if (!Number.isFinite(rating)) return "No rating available";
  if (!Number.isFinite(reviewCount)) return `Rating ${rating?.toFixed(1)}`;
  return `Rating ${rating?.toFixed(1)} / ${reviewCount?.toLocaleString()} reviews`;
}

function formatPriceRange(
  priceLevel?: string,
  priceRange?: { min?: string; max?: string }
): string {
  if (priceLevel) return priceLevel;
  if (priceRange?.min || priceRange?.max) {
    return [priceRange.min, priceRange.max].filter(Boolean).join(" ~ ");
  }
  return "No price information";
}

function formatCoordinate(value: number): string {
  return Number.isFinite(value) ? value.toFixed(6) : "";
}

function formatAccuracy(value: number | null): string {
  if (!Number.isFinite(value)) return "";

  const meters = Number(value);
  if (meters >= 1000) {
    return `Accuracy ±${(meters / 1000).toFixed(1)}km`;
  }

  return `Accuracy ±${Math.round(meters)}m`;
}

function haversineDistance(
  from: { lat: number; lng: number },
  to: { lat: number; lng: number }
): number {
  const earthRadiusKm = 6371;
  const latDelta = ((to.lat - from.lat) * Math.PI) / 180;
  const lngDelta = ((to.lng - from.lng) * Math.PI) / 180;
  const startLat = (from.lat * Math.PI) / 180;
  const endLat = (to.lat * Math.PI) / 180;

  const a =
    Math.sin(latDelta / 2) ** 2 +
    Math.cos(startLat) * Math.cos(endLat) * Math.sin(lngDelta / 2) ** 2;

  return earthRadiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function getPlaceDistanceKm(
  place: Place,
  currentLocation: { lat: number; lng: number }
): number {
  if (place.hasCoordinates) {
    return haversineDistance(currentLocation, place.coords);
  }

  if (Number.isFinite(place.rawDistanceMeters) && Number(place.rawDistanceMeters) > 100) {
    return Number(place.rawDistanceMeters) / 1000;
  }

  if (Number.isFinite(place.rawDistanceMeters)) {
    return Number(place.rawDistanceMeters);
  }

  return Number.MAX_SAFE_INTEGER;
}

function getLocationErrorMessage(error?: GeolocationPositionError): string {
  if (!error) {
    return "This browser does not support location. Using the default Seoul location.";
  }

  if (error.code === error.PERMISSION_DENIED) {
    return "Location permission is blocked. Allow location from the browser site settings.";
  }

  if (error.code === error.POSITION_UNAVAILABLE) {
    return "Current location is unavailable. Check OS location services.";
  }

  if (error.code === error.TIMEOUT) {
    return "Location request timed out. Tap Use my location to try again.";
  }

  return "Using the default Seoul location.";
}

async function getApproximateLocation(): Promise<{ lat: number; lng: number } | null> {
  try {
    const response = await fetch("https://ipapi.co/json/", {
      cache: "no-store",
    });
    if (!response.ok) return null;

    const data = (await response.json()) as {
      latitude?: number | string;
      longitude?: number | string;
    };
    const lat = Number(data.latitude);
    const lng = Number(data.longitude);

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return null;
    }

    return { lat, lng };
  } catch {
    return null;
  }
}

function sanitizeTags(value: unknown): PlaceTag[] {
  if (!Array.isArray(value)) return [];

  const tagMap: Record<string, PlaceTag> = {
    indoor: "Indoor",
    outdoor: "Outdoor",
    crowded: "Crowded",
    quiet: "Quiet",
  };

  return value
    .map((item) => tagMap[String(item).trim().toLowerCase()] || null)
    .filter((item): item is PlaceTag => Boolean(item));
}

function getBackendCategory(item: TourPlaceApiItem): PlaceCategory {
  const category = item.category || item.type || item.place_type;
  return String(category || "Other");
}

function formatCategoryLabel(value: string): string {
  const parts = value
    .split("/")
    .map((item) => item.trim())
    .filter(Boolean);
  const uniqueParts = Array.from(
    new Map(parts.map((item) => [item.toLowerCase(), item])).values()
  );
  const normalized = uniqueParts.length > 0 ? uniqueParts.join(" / ") : value;

  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\p{L}/gu, (letter) => letter.toLocaleUpperCase());
}

function getCategoryGroup(category: string): string {
  const normalized = category.trim().toLowerCase();

  const groups: Array<{ group: string; keywords: string[] }> = [
    {
      group: CATEGORY_GROUPS.FOOD_AND_DRINK,
      keywords: ["restaurant", "food", "cafe", "coffee", "bar", "bakery", "meal"],
    },
    {
      group: CATEGORY_GROUPS.STAY,
      keywords: ["lodging", "hotel", "hostel", "guesthouse", "resort"],
    },
    {
      group: CATEGORY_GROUPS.SHOPPING,
      keywords: ["shopping", "store", "mall", "department_store", "supermarket"],
    },
    {
      group: CATEGORY_GROUPS.ESSENTIALS,
      keywords: ["convenience", "pharmacy", "drugstore", "exchange", "bank", "atm"],
    },
    {
      group: CATEGORY_GROUPS.ATTRACTIONS,
      keywords: ["activity", "amusement", "museum", "park", "gallery", "tourist", "attraction", "landmark", "stadium", "spa", "gym"],
    },
  ];

  return groups.find((item) => item.keywords.some((keyword) => normalized.includes(keyword)))?.group || CATEGORY_GROUPS.OTHER;
}

function toNumber(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getPlaceCoordinates(item: TourPlaceApiItem): {
  lat: number;
  lng: number;
  hasCoordinates: boolean;
} {
  const location = item.location || {};
  const coordinates = item.coordinates;
  const arrayCoordinates = Array.isArray(coordinates) ? coordinates : [];
  const objectCoordinates =
    coordinates && !Array.isArray(coordinates) && typeof coordinates === "object"
      ? coordinates
      : {};
  const lat = Number(
    item.latitude ??
      item.lat ??
      location.latitude ??
      location.lat ??
      location.y ??
      objectCoordinates.latitude ??
      objectCoordinates.lat ??
      objectCoordinates.y ??
      arrayCoordinates[1]
  );
  const lng = Number(
    item.longitude ??
      item.lng ??
      location.longitude ??
      location.lng ??
      location.lon ??
      location.x ??
      objectCoordinates.longitude ??
      objectCoordinates.lng ??
      objectCoordinates.lon ??
      objectCoordinates.x ??
      arrayCoordinates[0]
  );
  const hasCoordinates = Number.isFinite(lat) && Number.isFinite(lng);

  return {
    lat: hasCoordinates ? lat : DEFAULT_LOCATION.lat,
    lng: hasCoordinates ? lng : DEFAULT_LOCATION.lng,
    hasCoordinates,
  };
}

function getPlacePhotos(item: TourPlaceApiItem): string[] {
  return Array.isArray(item.photos)
    ? item.photos
        .map((photo) => String(photo).trim())
        .filter(Boolean)
    : [];
}


function getPlaceThumbnailUrl(place: Place): string {
  const categoryImageUrl = getPlaceCategoryImageUrl(place.category);
  return place.photos[0] || categoryImageUrl || "";
}

function handlePlaceThumbnailError(
  event: SyntheticEvent<HTMLImageElement>,
  place: Place
): void {
  const image = event.currentTarget;
  const fallbackImageUrl = getPlaceCategoryImageUrl(place.category);

  if (!fallbackImageUrl || image.dataset.fallbackApplied === "true") {
    image.style.display = "none";
    return;
  }

  image.dataset.fallbackApplied = "true";
  image.src = fallbackImageUrl;
}
  
function mapTourPlace(item: TourPlaceApiItem): Place {
  const coordinates = getPlaceCoordinates(item);
  const description =
    item.description ||
    item.review_summary ||
    item.generative_summary ||
    item.editorial_summary ||
    item.short_address ||
    item.address ||
    item.summary ||
    "No description available yet.";

  return {
    id: String(item.id || item.place_id || createFallbackPlaceId()),
    googlePlaceId: String(item.place_id || item.id || ""),
    initialIsFavorite: item.is_favorite === true,
    name: String(item.display_name || item.name || item.title || "Unnamed place"),
    category: formatCategoryLabel(getBackendCategory(item)),
    groupCategory: getCategoryGroup(getBackendCategory(item)),
    raw: item,
    tags: sanitizeTags(item.tags),
    description: String(description),
    reviewCount: toNumber(
      item.review_count ?? item.reviewCount ?? item.rating_count,
      0
    ),
    rating: Number.isFinite(Number(item.rating)) ? Number(item.rating) : undefined,
    rawDistanceMeters: toNumber(item.distance, Number.NaN),
    hasCoordinates: coordinates.hasCoordinates,
    address: item.address ? String(item.address) : undefined,
    shortAddress: item.short_address ? String(item.short_address) : undefined,
    phone: item.phone ? String(item.phone) : undefined,
    phoneInternational: item.phone_international
      ? String(item.phone_international)
      : undefined,
    website: item.website ? String(item.website) : undefined,
    googleMapsUrl: item.google_maps_url ? String(item.google_maps_url) : undefined,
    googleMapReviewLink: item.google_map_review_link
      ? String(item.google_map_review_link)
      : undefined,
    photos: getPlacePhotos(item),
    openingHours: Array.isArray(item.opening_hours)
      ? item.opening_hours.map((value) => String(value))
      : [],
    services: Array.isArray(item.services)
      ? item.services.map((value) => String(value))
      : [],
    payment: Array.isArray(item.payment)
      ? item.payment.map((value) => String(value))
      : [],
    accessibility: Array.isArray(item.accessibility)
      ? item.accessibility.map((value) => String(value))
      : [],
    parking: Array.isArray(item.parking)
      ? item.parking.map((value) => String(value))
      : [],
    priceLevel: item.price_level ? String(item.price_level) : undefined,
    priceRange:
      item.price_range && typeof item.price_range === "object"
        ? {
            min: item.price_range.min ? String(item.price_range.min) : undefined,
            max: item.price_range.max ? String(item.price_range.max) : undefined,
          }
        : undefined,
    reviews: Array.isArray(item.reviews)
      ? item.reviews.map((review) => ({
          author: String(review?.author || "Anonymous"),
          rating: Number.isFinite(Number(review?.rating))
            ? Number(review?.rating)
            : undefined,
          relativeTime: review?.relative_time
            ? String(review.relative_time)
            : undefined,
          text: review?.text ? String(review.text) : undefined,
        }))
      : [],
    coords: {
      lat: coordinates.lat,
      lng: coordinates.lng,
    },
    thumbnail: {
      colors: ["#e9e9e9", "#d9d9d9"],
      label: "PLACE",
    },
  };
}

function createFallbackPlaceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `place_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function mapFavoritePlace(item: FavoritePlaceApiItem): Place | null {
  if (!item.place) {
    return null;
  }

  const mappedPlace = mapTourPlace({
    ...item.place,
    is_favorite: true,
  });

  return {
    ...mappedPlace,
    favoriteId: item.favorite_id ? String(item.favorite_id) : undefined,
    favoriteCreatedAt: item.created_at ? String(item.created_at) : undefined,
    initialIsFavorite: true,
  };
}

function getFilterMask(left: boolean, right: boolean): string {
  if (left && right) {
    return "linear-gradient(to right, transparent 0, black 16px, black calc(100% - 16px), transparent 100%)";
  }

  if (left) {
    return "linear-gradient(to right, transparent 0, black 16px, black 100%)";
  }

  if (right) {
    return "linear-gradient(to right, black 0, black calc(100% - 16px), transparent 100%)";
  }

  return "none";
}

export default function HomePage() {
  const navigate = useNavigate();
  const observerRef = useRef<HTMLDivElement | null>(null);
  const categoryFilterRef = useRef<HTMLDivElement | null>(null);
  const bodyScrollerRef = useRef<HTMLDivElement | null>(null);
  const lastScrollTopRef = useRef(0);
  const loadingCursorRef = useRef<string | null>(null);

  const [categoryFilterFade, setCategoryFilterFade] = useState({
    left: false,
    right: false,
  });
  const [isHeaderHidden, setIsHeaderHidden] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);

  const [user, setUser] = useState<UserProfile | null>(null);
  const [isProfileLoading, setIsProfileLoading] = useState(true);
  const [placesSource, setPlacesSource] = useState<Place[]>([]);
  const [favoritePlaces, setFavoritePlaces] = useState<Place[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const deferredSearch = useDeferredValue(searchInput.trim().toLowerCase());
  const [searchDraft, setSearchDraft] = useState("");
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [activeCategory, setActiveCategory] =
    useState<string>(ALL_CATEGORY);
  const [activeSort, setActiveSort] = useState<SortFilter>("Nearest");
  const [isFetchingMore, setIsFetchingMore] = useState(false);
  const [favoriteActionIds, setFavoriteActionIds] = useState<string[]>([]);
  const [recentSearches, setRecentSearches] = useState<SearchHistoryItem[]>([]);
  const [locationLabel, setLocationLabel] = useState(DEFAULT_LOCATION_LABEL);
  const [selectedPlace, setSelectedPlace] = useState<PlaceWithMeta | null>(null);
  const [placesError, setPlacesError] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [currentLocation, setCurrentLocation] = useState(DEFAULT_LOCATION);
  const [locationAccuracy, setLocationAccuracy] = useState<number | null>(null);
  const [locationStatus, setLocationStatus] = useState<LocationStatus>("detecting");
  const [locationError, setLocationError] = useState("");
  const hasGpsLocationRef = useRef(false);

  useEffect(() => {
    getMyProfile()
      .then((profile) => {
        setUser(
          profile || {
            email: "",
            user_name: "Traveler",
          }
        );
      })
      .catch((error: { status?: number }) => {
        if (error.status === 403 || error.status === 404) {
          navigate("/register");
          return;
        }
        setUser({
          email: "",
          user_name: "Traveler",
        });
      })
      .finally(() => {
        setIsProfileLoading(false);
      });
  }, [navigate]);

  function updateFadeState(
    ref: React.RefObject<HTMLDivElement>,
    setter: React.Dispatch<
      React.SetStateAction<{
        left: boolean;
        right: boolean;
      }>
    >
  ) {
    const el = ref.current;
    if (!el) return;

    const maxScrollLeft = el.scrollWidth - el.clientWidth;

    setter({
      left: el.scrollLeft > 2,
      right: maxScrollLeft <= 2 || el.scrollLeft < maxScrollLeft - 2,
    });
  }

  function applyCurrentPosition(coords: GeolocationCoordinates): void {
    hasGpsLocationRef.current = true;
    setCurrentLocation({
      lat: coords.latitude,
      lng: coords.longitude,
    });
    setLocationAccuracy(coords.accuracy);
    setLocationLabel(CURRENT_LOCATION_LABEL);
    setLocationStatus("ready");
    setLocationError("");
  }

  async function applyApproximateLocationFallback(
    error?: GeolocationPositionError
  ): Promise<void> {
    if (hasGpsLocationRef.current) {
      return;
    }

    const approximateLocation = await getApproximateLocation();
    if (hasGpsLocationRef.current) {
      return;
    }

    if (approximateLocation) {
      setCurrentLocation(approximateLocation);
      setLocationAccuracy(null);
      setLocationLabel("Using approximate location");
      setLocationStatus("approximate");
      setLocationError(
        "GPS was unavailable, so nearby places are sorted from an approximate network location."
      );
      return;
    }

    setLocationLabel(DEFAULT_LOCATION_LABEL);
    setLocationAccuracy(null);
    setLocationStatus("fallback");
    setLocationError(getLocationErrorMessage(error));
  }

  function handleLocationError(error?: GeolocationPositionError): void {
    if (hasGpsLocationRef.current) {
      return;
    }

    void applyApproximateLocationFallback(error);
  }

  function requestCurrentLocation(): void {
    if (!window.isSecureContext) {
      setLocationLabel(DEFAULT_LOCATION_LABEL);
      setLocationStatus("fallback");
      setLocationError("Location only works on HTTPS. Open the deployed HTTPS site.");
      return;
    }

    if (!navigator.geolocation) {
      handleLocationError();
      return;
    }

    setLocationLabel(DETECTING_LOCATION_LABEL);
    setLocationStatus("detecting");
    setLocationError("");

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => applyCurrentPosition(coords),
      handleLocationError,
      GEOLOCATION_OPTIONS
    );
  }

  useEffect(() => {
    if (navigator.permissions?.query) {
      navigator.permissions
        .query({ name: "geolocation" as PermissionName })
        .then((permissionStatus) => {
          if (permissionStatus.state === "denied") {
            setLocationLabel(DEFAULT_LOCATION_LABEL);
            setLocationStatus("fallback");
            setLocationError(
              "Location permission is blocked. Allow location from the browser site settings."
            );
          }

          permissionStatus.onchange = () => {
            if (permissionStatus.state !== "denied") {
              requestCurrentLocation();
            }
          };
        })
        .catch(() => {
          // Some browsers do not expose geolocation permission state.
        });
    }

    requestCurrentLocation();

    if (!navigator.geolocation) {
      return undefined;
    }

    const watchId = navigator.geolocation.watchPosition(
      ({ coords }) => {
        applyCurrentPosition(coords);
      },
      handleLocationError,
      GEOLOCATION_WATCH_OPTIONS
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  async function fetchPlaces(
    options: {
      cursor?: string;
      append?: boolean;
    } = {}
  ): Promise<void> {
    const cursorKey = options.cursor || "__initial__";
    if (loadingCursorRef.current === cursorKey) return;
    loadingCursorRef.current = cursorKey;

    const params: TourPlacesParams = {
      lat: currentLocation.lat,
      lng: currentLocation.lng,
      keyword: searchInput || undefined,
      cursor: options.cursor,
    };

    try {
      const response = await getTourPlaces(params);
      const mappedItems = response.items.map(mapTourPlace);

      setPlacesSource((current) =>
        options.append ? [...current, ...mappedItems] : mappedItems
      );
      setNextCursor(response.nextCursor || null);
      setPlacesError("");

      if (!options.cursor && searchInput.trim()) {
        fetchSearchHistory().catch(() => {
          // Keep the places UI usable even if history refresh fails.
        });
      }
    } finally {
      loadingCursorRef.current = null;
    }
  }

  async function fetchFavoritePlaces(): Promise<void> {
    const response = await getTourPlaceFavorites();
    const mappedItems = response.favorites
      .map(mapFavoritePlace)
      .filter((place): place is Place => Boolean(place));

    setFavoritePlaces(mappedItems);
  }

  async function fetchSearchHistory(): Promise<void> {
    const response = await getTourSearchHistory();
    setRecentSearches(response.histories);
  }

  useEffect(() => {
    if (locationStatus === "detecting") return;

    setIsFetchingMore(false);
    setNextCursor(null);

    fetchPlaces()
      .catch((error) => {
        const message =
          error instanceof Error ? error.message : "Failed to load places.";
        setPlacesError(message);
        setPlacesSource((current) => current);
      });
  }, [currentLocation.lat, currentLocation.lng, locationStatus, searchInput]);

  useEffect(() => {
    fetchFavoritePlaces().catch((error) => {
      const message =
        error instanceof Error ? error.message : "Failed to load favorites.";
      setPlacesError(message);
      setFavoritePlaces([]);
    });
  }, []);

  useEffect(() => {
    fetchSearchHistory().catch(() => {
      setRecentSearches([]);
    });
  }, []);

  const favoriteIds = useMemo(
    () => new Set(favoritePlaces.map((place) => place.id)),
    [favoritePlaces]
  );

  const favoriteIdByPlaceId = useMemo(
    () =>
      new Map(
        favoritePlaces
          .filter((place) => place.favoriteId)
          .map((place) => [place.id, place.favoriteId as string])
      ),
    [favoritePlaces]
  );

  const places = useMemo<PlaceWithMeta[]>(
    () =>
      placesSource.map((place) => ({
        ...place,
        favoriteId: place.favoriteId || favoriteIdByPlaceId.get(place.id),
        isFavorite: place.initialIsFavorite || favoriteIds.has(place.id),
        distanceKm: getPlaceDistanceKm(place, currentLocation),
      })),
    [currentLocation, favoriteIdByPlaceId, favoriteIds, placesSource]
  );

  const favoritePlacesWithMeta = useMemo<PlaceWithMeta[]>(
    () =>
      favoritePlaces.map((place) => ({
        ...place,
        isFavorite: true,
        distanceKm: getPlaceDistanceKm(place, currentLocation),
      })),
    [currentLocation, favoritePlaces]
  );

  const categoryFilters = useMemo<string[]>(() => {
    const categories = Array.from(
      new Set(
        places
          .map((place) => place.groupCategory.trim())
          .filter(Boolean)
      )
    ).sort((left, right) => {
      const li = CATEGORY_DISPLAY_ORDER.indexOf(left);
      const ri = CATEGORY_DISPLAY_ORDER.indexOf(right);
      if (li === -1 && ri === -1) return left.localeCompare(right, "ko");
      if (li === -1) return 1;
      if (ri === -1) return -1;
      return li - ri;
    });

    return [ALL_CATEGORY, ...categories];
  }, [places]);

  useEffect(() => {
    if (!categoryFilters.includes(activeCategory)) {
      setActiveCategory(ALL_CATEGORY);
    }
  }, [activeCategory, categoryFilters]);

  useEffect(() => {
  const el = categoryFilterRef.current;
  if (!el) return;

  const updateCategoryFade = () => {
      updateFadeState(categoryFilterRef, setCategoryFilterFade);
    };

    requestAnimationFrame(updateCategoryFade);

    el.addEventListener("scroll", updateCategoryFade);
    window.addEventListener("resize", updateCategoryFade);

    const resizeObserver = new ResizeObserver(updateCategoryFade);
    resizeObserver.observe(el);

    return () => {
      el.removeEventListener("scroll", updateCategoryFade);
      window.removeEventListener("resize", updateCategoryFade);
      resizeObserver.disconnect();
    };
  }, [categoryFilters.length]);

  const filteredPlaces = useMemo<PlaceWithMeta[]>(() => {
    const source = activeSort === "Favorites" ? favoritePlacesWithMeta : places;

    const nextPlaces = source.filter((place) => {
      const matchesCategory =
        activeCategory === ALL_CATEGORY || place.groupCategory === activeCategory;

      const matchesSearch =
        !deferredSearch ||
        place.name.toLowerCase().includes(deferredSearch) ||
        place.description.toLowerCase().includes(deferredSearch) ||
        place.category.toLowerCase().includes(deferredSearch) ||
        place.groupCategory.toLowerCase().includes(deferredSearch);

      const matchesFavorite =
        activeSort !== "Favorites" || place.isFavorite;

      return matchesCategory && matchesSearch && matchesFavorite;
    });

    nextPlaces.sort((left, right) => {
      if (activeSort === "Favorites") {
        return (
          new Date(right.favoriteCreatedAt || 0).getTime() -
          new Date(left.favoriteCreatedAt || 0).getTime()
        );
      }

      if (activeSort === "Top Rated") {
        return (right.rating || 0) - (left.rating || 0);
      }

      if (activeSort === "Most Reviewed") {
        return right.reviewCount - left.reviewCount;
      }

      return left.distanceKm - right.distanceKm;
    });

    return nextPlaces;
  }, [activeCategory, activeSort, deferredSearch, favoritePlacesWithMeta, places]);

  const visiblePlaces = filteredPlaces;
  const hasMore = activeSort !== "Favorites" && Boolean(nextCursor);
  const sentinelText = isFetchingMore ? "Loading..." : "";

  const suggestionPool = useMemo(() => {
    return Array.from(
      new Set(
        placesSource.flatMap((place) => [
          place.name,
          place.category,
          place.groupCategory,
          ...place.tags,
        ])
      )
    );
  }, [placesSource]);

  const relatedSuggestions = useMemo(() => {
    const keyword = searchDraft.trim().toLowerCase();
    const matched = suggestionPool.filter((item) =>
      !keyword ? true : item.toLowerCase().includes(keyword)
    );
    return matched.slice(0, SEARCH_SUGGESTION_LIMIT);
  }, [searchDraft, suggestionPool]);

  const recentSearchKeywords = useMemo(
    () => recentSearches.map((item) => item.search_name),
    [recentSearches]
  );

  useEffect(() => {
    if (!hasMore) return undefined;

    const target = observerRef.current;
    if (!target) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries[0]?.isIntersecting &&
          nextCursor &&
          !isFetchingMore &&
          loadingCursorRef.current !== nextCursor
        ) {
          setIsFetchingMore(true);
          fetchPlaces({ cursor: nextCursor, append: true })
            .catch((error) => {
              const message =
                error instanceof Error ? error.message : "Failed to load places.";
              setPlacesError(message);
            })
            .finally(() => {
              setIsFetchingMore(false);
            });
        }
      },
      { rootMargin: "220px 0px" }
    );

    observer.observe(target);

    return () => observer.disconnect();
  }, [hasMore, isFetchingMore, nextCursor, currentLocation.lat, currentLocation.lng, searchInput]);

  function syncPlaceFavoriteState(placeId: string, isFavorite: boolean): void {
    setPlacesSource((current) =>
      current.map((item) =>
        item.id === placeId ? { ...item, initialIsFavorite: isFavorite } : item
      )
    );
    setFavoritePlaces((current) =>
      isFavorite
        ? current
        : current.filter((item) => item.id !== placeId)
    );
    setSelectedPlace((current) =>
      current && current.id === placeId
        ? { ...current, isFavorite }
        : current
    );
  }

  async function toggleFavorite(place: PlaceWithMeta): Promise<void> {
    if (favoriteActionIds.includes(place.id)) {
      return;
    }

    setFavoriteActionIds((current) => [...current, place.id]);
    setPlacesError("");

    try {
      if (place.isFavorite) {
        await removeTourPlaceFavorite(place.googlePlaceId || place.id, place.googlePlaceId || place.id);
        syncPlaceFavoriteState(place.id, false);
      } else {
        await addTourPlaceFavorite(place.googlePlaceId || place.id);
        syncPlaceFavoriteState(place.id, true);
        await fetchFavoritePlaces();
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update favorite place.";
      setPlacesError(message);
    } finally {
      setFavoriteActionIds((current) => current.filter((item) => item !== place.id));
    }
  }

  function openPlaceDetail(place: PlaceWithMeta): void {
    setSelectedPlace(place);
  }

  function closePlaceDetail(): void {
    setSelectedPlace(null);
  }

  function openSearchSheet(): void {
    setSearchDraft(searchInput);
    setIsSearchOpen(true);
  }

  function closeSearchSheet(): void {
    setIsSearchOpen(false);
  }

  function submitSearch(nextValue: string = searchDraft): void {
    const normalized = nextValue.trim();
    setSearchInput(normalized);
    closeSearchSheet();
  }

  async function removeRecentSearch(keyword: string): Promise<void> {
    try {
      await deleteTourSearchHistoryOne(keyword);
      setRecentSearches((current) =>
        current.filter((item) => item.search_name !== keyword)
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to delete search history.";
      setPlacesError(message);
    }
  }

  if (isProfileLoading) {
    return (
      <div style={styles.loading}>
        <div style={styles.loadingShell}>
          <span style={styles.spinner} />
          <p style={styles.loadingText}>Preparing your home screen</p>
        </div>
      </div>
    );
  }

  const locationCoordinatesText = `${formatCoordinate(currentLocation.lat)}, ${formatCoordinate(
    currentLocation.lng
  )}`;
  const locationAccuracyText = formatAccuracy(locationAccuracy);
  const locationDetailText = locationAccuracyText
    ? `${locationCoordinatesText} · ${locationAccuracyText}`
    : locationCoordinatesText;

  function handleBodyScroll(event: UIEvent<HTMLDivElement>) {
    const nextScrollTop = Math.max(event.currentTarget.scrollTop, 0);
    const delta = nextScrollTop - lastScrollTopRef.current;

    if (nextScrollTop <= 8) {
      setIsHeaderHidden(false);
    } else if (delta > 5 && nextScrollTop > 72) {
      setIsHeaderHidden(true);
    } else if (delta < -5) {
      setIsHeaderHidden(false);
    }

    setShowScrollTop(nextScrollTop > 800);

    lastScrollTopRef.current = nextScrollTop;
  }

  function scrollToTop() {
    bodyScrollerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        <div
          ref={bodyScrollerRef}
          style={styles.bodyScroller}
          onScroll={handleBodyScroll}
        >
          <HomeHeader
            searchInput={searchInput}
            onOpenSearch={openSearchSheet}
            isHidden={isHeaderHidden}
          />


          <section style={styles.filtersSection}>
            <div ref={categoryFilterRef}
              className="filter-group-scroll"
              style={{
                ...styles.filterGroup,
                justifyContent: "center",
                WebkitMaskImage: getFilterMask(
                  categoryFilterFade.left,
                  categoryFilterFade.right
                ),
                maskImage: getFilterMask(
                  categoryFilterFade.left,
                  categoryFilterFade.right
                ),
              }}>
              <div style={styles.categoryFilterContent}>
                {categoryFilters.map((category) => {
                  const isActive = activeCategory === category;
                  return (
                    <button
                      key={category}
                      style={{
                        ...styles.filterChip,
                        ...(isActive ? styles.filterChipActive : {}),
                      }}
                      onClick={() => setActiveCategory(category)}
                    >
                      {category}
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={styles.filterGroup}>
              {SORT_FILTERS.map((sort) => {
                const isActive = activeSort === sort;
                return (
                  <button
                    key={sort}
                    style={{
                      ...styles.secondaryChip,
                      ...(isActive ? styles.secondaryChipActive : {}),
                    }}
                    onClick={() => setActiveSort(sort)}
                  >
                    {sort}
                  </button>
                );
              })}
            </div>
          </section>

          <section style={visiblePlaces.length > 0
            ? styles.listSection
            : styles.emptyListSection}>
            {visiblePlaces.length > 0 ? (
              visiblePlaces.map((place) => (
                <article
                  key={place.id}
                  className="interactive-card"
                  style={styles.card}
                  onClick={() => openPlaceDetail(place)}
                >
                  <div style={styles.thumbnail}>
                    {getPlaceThumbnailUrl(place) ? (
                      <img
                        src={getPlaceThumbnailUrl(place)}
                        alt={place.name}
                        loading="lazy"
                        onError={(event) => handlePlaceThumbnailError(event, place)}
                        style={styles.thumbnailImage}
                      />
                    ) : null}
                  </div>

                  <div style={styles.cardBody}>
                    <div style={styles.cardTop}>
                      <div>
                        <p style={styles.cardCategory}>{place.category}</p>
                        <h2 style={styles.cardTitle}>{place.name}</h2>
                      </div>
                      <button
                        type="button"
                        style={{
                          ...styles.favoriteButton,
                          ...(favoriteActionIds.includes(place.id)
                            ? styles.favoriteButtonPending
                            : {}),
                        }}
                        onClick={(event: MouseEvent<HTMLButtonElement>) => {
                          event.stopPropagation();
                          void toggleFavorite(place);
                        }}
                        aria-label={`Toggle favorite for ${place.name}`}
                        disabled={favoriteActionIds.includes(place.id)}
                      >
                        <BookmarkIcon filled={place.isFavorite} />
                      </button>
                    </div>

                    <p style={styles.cardDescription}>{place.description}</p>

                    <div style={styles.cardMeta}>
                      <div style={styles.inlineTags}>
                        {place.tags.map((tag) => (
                          <span key={tag} style={styles.inlineTag}>
                            {tag}
                          </span>
                        ))}
                      </div>
                      <div style={styles.metaRight}>
                        <span style={styles.reviewText}>
                          {formatRating(place.rating, place.reviewCount)}
                        </span>
                        <span style={styles.distance}>
                          {formatDistance(place.distanceKm)}
                        </span>
                      </div>
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div style={styles.emptyState}>
                <p style={styles.emptyTitle}>
                  {locationStatus === "detecting"
                    ? "Finding places near you..."
                    : placesError ||
                    (activeSort === "Favorites"
                      ? "No favorite places yet."
                      : "No places available yet.")}
                </p>
                <p style={styles.emptyCopy}>
                  {activeSort === "Favorites"
                    ? "Add a place to favorites and it will appear here in latest-added order."
                    : "Search again or adjust your filters to find nearby places."}
                </p>
              </div>
            )}

            <div ref={observerRef} style={styles.scrollSentinel}>
              {sentinelText}
            </div>
          </section>
        </div>
      </div>

      {selectedPlace ? (
        <div style={styles.modalOverlay} onClick={closePlaceDetail}>
          <div style={styles.modalCard} onClick={(event) => event.stopPropagation()}>
            <div
              style={{
                ...styles.modalHero,
                ...(getPlaceThumbnailUrl(selectedPlace)
                  ? {
                      backgroundImage: `linear-gradient(180deg, rgba(24,26,32,0.16), rgba(24,26,32,0.56)), url(${getPlaceThumbnailUrl(selectedPlace)})`,
                      backgroundSize: "cover",
                      backgroundPosition: "center",
                    }
                  : {}),
              }}
            >
              <div style={styles.modalHeroTop}>
                <span style={styles.modalCategory}>{selectedPlace.category}</span>
                <button
                  type="button"
                  style={styles.modalCloseButton}
                  onClick={closePlaceDetail}
                  aria-label="Close details"
                >
                  x
                </button>
              </div>
              <div>
                <h2
                  style={{
                    ...styles.modalTitle,
                    ...(getPlaceThumbnailUrl(selectedPlace) ? styles.modalTitleOnImage : {}),
                  }}
                >
                  {selectedPlace.name}
                </h2>
                <p
                  style={{
                    ...styles.modalDistance,
                    ...(getPlaceThumbnailUrl(selectedPlace) ? styles.modalDistanceOnImage : {}),
                  }}
                >
                  {locationLabel} / {formatDistance(selectedPlace.distanceKm)}
                </p>
              </div>
            </div>

            <div style={styles.modalBody}>
              <p style={styles.modalDescription}>{selectedPlace.description}</p>

              <div style={styles.detailStack}>
                <DetailRow
                  label="Address"
                  value={selectedPlace.shortAddress || selectedPlace.address}
                />
                <DetailRow
                  label="Rating"
                  value={formatRating(selectedPlace.rating, selectedPlace.reviewCount)}
                />
                <DetailRow
                  label="Price"
                  value={formatPriceRange(
                    selectedPlace.priceLevel,
                    selectedPlace.priceRange
                  )}
                />
                <DetailRow label="Phone" value={selectedPlace.phone} />
                <DetailRow
                  label="International Phone"
                  value={selectedPlace.phoneInternational}
                />
              </div>

              <div style={styles.modalInfoGrid}>
                <div style={styles.modalInfoCard}>
                  <span style={styles.modalInfoLabel}>Reviews</span>
                  <strong style={styles.modalInfoValue}>
                    {selectedPlace.reviewCount.toLocaleString()}
                  </strong>
                </div>
                <div style={styles.modalInfoCard}>
                  <span style={styles.modalInfoLabel}>Opening Hours</span>
                  <strong style={styles.modalInfoValue}>
                    {selectedPlace.openingHours[0] || "Not available"}
                  </strong>
                </div>
              </div>

              {selectedPlace.services.length > 0 ? (
                <DetailChipSection label="Services" items={selectedPlace.services} />
              ) : null}

              {selectedPlace.payment.length > 0 ? (
                <DetailChipSection label="Payment" items={selectedPlace.payment} />
              ) : null}

              {selectedPlace.accessibility.length > 0 ? (
                <DetailChipSection label="Accessibility" items={selectedPlace.accessibility} />
              ) : null}

              {selectedPlace.parking.length > 0 ? (
                <DetailChipSection label="Parking" items={selectedPlace.parking} />
              ) : null}

              <div style={styles.detailLinkRow}>
                {selectedPlace.website ? (
                  <a
                    href={selectedPlace.website}
                    target="_blank"
                    rel="noreferrer"
                    style={styles.detailLink}
                  >
                    Website
                  </a>
                ) : null}
                {selectedPlace.googleMapsUrl ? (
                  <a
                    href={selectedPlace.googleMapsUrl}
                    target="_blank"
                    rel="noreferrer"
                    style={styles.detailLink}
                  >
                    Open Map
                  </a>
                ) : null}
                {selectedPlace.googleMapReviewLink ? (
                  <a
                    href={selectedPlace.googleMapReviewLink}
                    target="_blank"
                    rel="noreferrer"
                    style={styles.detailLink}
                  >
                    View Reviews
                  </a>
                ) : null}
              </div>

              {selectedPlace.reviews.length > 0 ? (
                <div style={styles.reviewSection}>
                  <p style={styles.sectionLabel}>Reviews</p>
                  {selectedPlace.reviews.slice(0, 3).map((review, index) => (
                    <div key={`${review.author}-${index}`} style={styles.reviewCard}>
                      <div style={styles.reviewHeader}>
                        <strong>{review.author}</strong>
                        <span>
                          {[review.rating ? `${review.rating}` : null, review.relativeTime]
                            .filter(Boolean)
                            .join(" / ")}
                        </span>
                      </div>
                      <p style={styles.reviewBody}>
                        {review.text || "No review text"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}

              <button
                type="button"
                style={{
                  ...styles.modalFavoriteButton,
                  ...(favoriteActionIds.includes(selectedPlace.id)
                    ? styles.favoriteButtonPending
                    : {}),
                }}
                onClick={() => void toggleFavorite(selectedPlace)}
                disabled={favoriteActionIds.includes(selectedPlace.id)}
              >
                {selectedPlace.isFavorite ? "Remove Favorite" : "Add to Favorites"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {isSearchOpen ? (
        <div style={styles.modalOverlay} onClick={closeSearchSheet}>
          <div style={styles.searchSheet} onClick={(event) => event.stopPropagation()}>
            <div style={styles.searchSheetHandle} />
            <div style={styles.searchSheetHeader}>
              <label style={styles.searchSheetInputWrap}>
                <SearchIcon />
                <input
                  autoFocus
                  value={searchDraft}
                  onChange={(event) => setSearchDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      submitSearch();
                    }
                  }}
                  placeholder="Search places by name or keyword"
                  style={styles.searchSheetInput}
                />
              </label>
              <button
                type="button"
                style={styles.searchSheetClose}
                onClick={closeSearchSheet}
              >
                Cancel
              </button>
            </div>

            <div style={styles.searchSheetSection}>
              <div style={styles.searchSheetLabelRow}>
                <p style={styles.searchSheetTitle}>Suggested Searches</p>
                <button
                  type="button"
                  style={styles.linkButton}
                  onClick={() => submitSearch()}
                >
                  Search
                </button>
              </div>
              <div style={styles.searchSuggestionGrid}>
                {relatedSuggestions.length > 0 ? (
                  relatedSuggestions.map((keyword) => (
                    <button
                      key={keyword}
                      type="button"
                      style={styles.searchKeywordChip}
                      onClick={() => submitSearch(keyword)}
                    >
                      {keyword}
                    </button>
                  ))
                ) : (
                  <p style={styles.searchEmpty}>No suggestions yet.</p>
                )}
              </div>
            </div>

            <div style={styles.searchSheetSection}>
              <div style={styles.searchSheetLabelRow}>
                <p style={styles.searchSheetTitle}>Recent Searches</p>
              </div>
              {recentSearches.length > 0 ? (
                <div style={styles.recentList}>
                  {recentSearchKeywords.map((keyword) => (
                    <div key={keyword} style={styles.recentItem}>
                      <button
                        type="button"
                        style={styles.recentKeywordButton}
                        onClick={() => submitSearch(keyword)}
                      >
                        {keyword}
                      </button>
                      <button
                        type="button"
                        style={styles.recentDeleteButton}
                        onClick={() => void removeRecentSearch(keyword)}
                        aria-label={`Delete ${keyword}`}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={styles.searchEmpty}>No recent searches yet.</p>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {showScrollTop ? (
        <button
          type="button"
          style={styles.scrollTopButton}
          onClick={scrollToTop}
          aria-label="Scroll to top"
        >
          ↑
        </button>
      ) : null}

    </div>
  );
}

function SearchIcon() {
  return (
    <img
      src="/SearchIcon.svg"
      alt="search"
      width={20}
      height={20}
      style={{ display: "block", objectFit: "contain" }}
    />
  );
}

function HomeHeader({
  searchInput,
  onOpenSearch,
  isHidden,
}: {
  searchInput: string;
  onOpenSearch: () => void;
  isHidden: boolean;
}) {
  return (
    <header
      style={{
        ...styles.homeHeader,
        opacity: isHidden ? 0 : 1,
        pointerEvents: isHidden ? "none" : "auto",
        transform: isHidden
          ? "translate3d(0, calc(-100% - 8px), 0)"
          : "translate3d(0, 0, 0)",
      }}
    >
      <div style={styles.header}>
        <div style={styles.headerLogoWrap}>
          <img
            src="/kripInAppLogo.svg"
            alt="KRIP"
            style={styles.headerLogo}
          />
        </div>
        <div style={styles.headerActions}>
          <NotificationBell buttonStyle={styles.myPageButton} />
        </div>
      </div>

      <div style={styles.searchPanel}>
        <div style={styles.searchRow}>
          <label style={styles.searchWrap}>
            <input
              value={searchInput}
              onClick={onOpenSearch}
              onFocus={(event) => {
                event.target.blur();
                onOpenSearch();
              }}
              placeholder="Search places by name or keyword"
              className="search-input"
              style={styles.searchInput}
              readOnly
            />
            <button
              type="button"
              style={styles.searchAction}
              aria-label="Search"
              onClick={onOpenSearch}
            >
              <SearchIcon />
            </button>
          </label>
        </div>
      </div>
    </header>
  );
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <img
      src={filled ? "/FavoriteIcon_active.svg" : "/FavoriteIcon.svg"}
      alt=""
      aria-hidden="true"
      width={24}
      height={24}
      style={{ display: "block" }}
    />
  );
}

function DetailRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;

  return (
    <div style={styles.detailRow}>
      <span style={styles.detailLabel}>{label}</span>
      <span style={styles.detailValue}>{value}</span>
    </div>
  );
}

function DetailChipSection({
  label,
  items,
}: {
  label: string;
  items: string[];
}) {
  return (
    <div style={styles.detailSection}>
      <p style={styles.sectionLabel}>{label}</p>
      <div style={styles.inlineTags}>
        {items.map((item) => (
          <span key={item} style={styles.inlineTag}>
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  loading: {
    minHeight: "var(--app-viewport-height)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "transparent",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  loadingShell: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 16,
    color: "var(--text-secondary)",
  },
  loadingText: {
    margin: 0,
    fontSize: "0.95rem",
    color: "var(--neutral-700)",
  },
  spinner: {
    display: "block",
    width: 42,
    height: 42,
    borderRadius: "50%",
    border: "4px solid rgba(5, 181, 187, 0.16)",
    borderTop: "4px solid var(--brand-primary)",
    animation: "spin 0.8s linear infinite",
  },
  page: {
    height: "calc(var(--app-viewport-height) - var(--app-bottom-nav-reserved))",
    minHeight: "calc(var(--app-viewport-height) - var(--app-bottom-nav-reserved))",
    overflow: "visible",
    background: "#f5f5f5",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  shell: {
    position: "relative",
    width: "100%",
    maxWidth: 760,
    height: "100%",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    overflow: "visible",
  },
  bodyScroller: {
    flex: 1,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    overflowY: "auto",
    overflowX: "hidden",
    overscrollBehavior: "contain",
    WebkitOverflowScrolling: "touch",
    paddingBottom: 40,
    background: "#f5f5f5",
    transition: "padding-top 220ms ease",
  },

  /* ── Header ─────────────────────────────── */
  homeHeader: {
    position: "sticky",
    top: 0,
    zIndex: 20,
    flexShrink: 0,
    display: "flex",
    flexDirection: "column",
    gap: 6,
    paddingTop: "calc(12px + var(--app-safe-top))",
    paddingBottom: 14,
    boxSizing: "border-box",
    marginBottom: -1,
    background: "#f5f5f5",
    transition:
      "transform 240ms ease, opacity 180ms ease",
    willChange: "transform, opacity",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 16px 0",
  },
  headerLogoWrap: {
    display: "flex",
    alignItems: "center",
    alignSelf: "flex-start",
  },
  headerLogo: {
    height: "clamp(28px, 6vw, 40px)",
    width: "auto",
    objectFit: "contain",
    display: "block",
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexShrink: 0,
    alignSelf: "flex-start",
    marginRight: 8,
    marginTop: -8,
  },
  notificationButton: {
    position: "relative",
    width: 40,
    height: 40,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "rgba(255,255,255,0.94)",
    color: "var(--brand-primary-deep)",
    boxShadow: "var(--shadow-soft)",
    cursor: "pointer",
  },
  notificationBadge: {
    position: "absolute",
    top: -4,
    right: -4,
    minWidth: 20,
    height: 20,
    padding: "0 6px",
    borderRadius: 999,
    display: "grid",
    placeItems: "center",
    background: "#ef4444",
    color: "#ffffff",
    border: "2px solid rgba(255,255,255,0.96)",
    fontSize: "0.64rem",
    fontWeight: 900,
    lineHeight: 1,
  },
  myPageButton: {
    position: "relative",
    width: 40,
    height: 40,
    border: "none",
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "transparent",
    color: "var(--brand-primary-deep)",
    boxShadow: "none",
    cursor: "pointer",
    flexShrink: 0,
    fontWeight: 900,
  },
  searchPanel: {
    padding: "0 16px",
    borderRadius: 28,
    background: "transparent",
  },
  locationSection: {
    padding: "0 16px",
    background: "transparent",
  },
  searchRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },
  searchWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    padding: "0 1rem 0 1.7rem",
    minHeight: "2.75rem",
    borderRadius: "3rem",
    background: "#fff",
    color: "var(--neutral-600)",
  },
  searchInput: {
    width: "100%",
    border: "none",
    outline: "none",
    background: "transparent",
    fontSize: "0.9rem",
    color: "var(--text-primary)",
    fontFamily: "inherit",
  },
  searchAction: {
    width: 34,
    border: "transparent",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "transparent",
    color: "#848484",
    cursor: "pointer",
  },
  locationBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    alignItems: "center",
  },
  locationButton: {
    border: "transparent",
    borderRadius: 999,
    padding: "7px 12px",
    background: "#fff",
    color: "var(--brand-primary-deep)",
    fontSize: "0.7rem",
    fontWeight: 800,
    cursor: "pointer",
  },
  locationHint: {
    color: "var(--neutral-700)",
    fontSize: "0.86rem",
  },
  filtersSection: {
    display: "flex",
    flexDirection: "column",
    margin: "0",
    padding: "0 16px 0.4rem",
    gap: 6,
    minHeight: 54,
    overflow: "visible",
  },
  filterGroup: {
    display: "flex",
    flexWrap: "nowrap",
    gap: "0.3rem",
    justifyContent: "center",
    alignItems: "center",
    overflowX: "auto",
    overflowY: "hidden",
    scrollbarWidth: "none",
    msOverflowStyle: "none",
    width: "100%",
    minWidth: 0,
    minHeight: 23,
  },
  categoryFilterContent: {
    display: "flex",
    flexWrap: "nowrap",
    gap: "0.3rem",
    justifyContent: "center",
    alignItems: "center",
    minWidth: "100%",
    width: "max-content",
    flexShrink: 0,
  },
  filterChip: {
    border: "transparent",
    borderRadius: 999,
    padding: "0.3rem 0.7rem 0.35rem",
    lineHeight: 1.4,
    background: "#fff",
    color: "var(--neutral-500)",
    fontWeight: 500,
    fontSize: "0.7rem",
    cursor: "pointer",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  filterChipActive: {
    background: "#01C0C0",
    color: "#fff",
  },
  secondaryChip: {
    border: "transparent",
    borderRadius: 999,
    padding: "0.3rem 0.7rem 0.35rem",
    lineHeight: 1.4,
    background: "#fff",
    color: "var(--neutral-500)",
    fontWeight: 500,
    fontSize: "0.7rem",
    cursor: "pointer",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  secondaryChipActive: {
    background: "#01C0C0",
    color: "#fff",
  },
  listSection: {
    display: "flex",
    flexDirection: "column",
    background: "#fff",
    borderRadius: "1.8rem",
    boxShadow: "var(--shadow-soft)",
    paddingTop: 6,
  },
  emptyListSection: {
    display: "flex",
    flexDirection: "column",
    minHeight: 220,
  },
  card: {
    display: "grid",
    gridTemplateColumns: "minmax(3.8rem, 4.4rem) minmax(0, 1fr)",
    gap: 14,
    padding: "0.35rem 16px",
    minHeight: "6rem",
    cursor: "pointer",
  },
  thumbnail: {
    width: "100%",
    aspectRatio: "1 / 1.24",
    minHeight: 68,
    maxHeight: 84,
    borderRadius: 14,
    overflow: "hidden",
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "flex-start",
    padding: 6,
    boxSizing: "border-box",
    background: "linear-gradient(160deg, rgba(5,181,187,0.18), rgba(248,180,0,0.14))",
  },
  thumbnailImage: {
    width: "calc(100% + 16px)",
    height: "calc(100% + 16px)",
    margin: -8,
    display: "block",
    objectFit: "cover",
  },
  cardBody: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    minWidth: 0,
    minHeight: 0,
  },
  cardTop: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-start",
  },
  cardCategory: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.68rem",
    fontWeight: 700,
    lineHeight: 1.25,
  },
  cardTitle: {
    margin: "1px 0 0",
    color: "var(--text-primary)",
    fontSize: "0.92rem",
    fontWeight: 700,
    lineHeight: 1.3,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  favoriteButton: {
    border: "transparent",
    display: "grid",
    placeItems: "center",
    background: "transparent",
    cursor: "pointer",
    flexShrink: 0,
    opacity: 0.65,
  },
  favoriteButtonPending: {
    opacity: 0.4,
    cursor: "wait",
  },
  cardDescription: {
    margin: 0,
    color: "var(--neutral-500)",
    lineHeight: 1.4,
    fontSize: "0.68rem",
    display: "-webkit-box",
    WebkitLineClamp: 1,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  cardMeta: {
    marginTop: "auto",
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-end",
    flexWrap: "nowrap",
    minWidth: 0,
  },
  inlineTags: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  inlineTag: {
    padding: "7px 10px",
    borderRadius: 999,
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 700,
  },
  metaRight: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    gap: 2,
    marginLeft: "auto",
    flexShrink: 0,
  },
  distance: {
    color: "var(--neutral-500)",
    fontWeight: 500,
    fontSize: "0.82rem",
    whiteSpace: "nowrap",
  },
  reviewText: {
    color: "var(--neutral-400)",
    textAlign: "right",
    fontSize: "0.62rem",
    whiteSpace: "nowrap",
  },
  emptyState: {
    padding: "48px 20px",
    margin: 16,
    textAlign: "center",
    borderRadius: 28,
    background: "rgba(255,255,255,0.88)",
    color: "var(--neutral-700)",
    border: "1px solid var(--border-soft)",
  },
  emptyTitle: {
    margin: 0,
    fontSize: "1.05rem",
    fontWeight: 800,
    color: "var(--text-primary)",
  },
  emptyCopy: {
    margin: "8px 0 0",
    lineHeight: 1.5,
  },
  scrollSentinel: {
    minHeight: 28,
    padding: "12px 0 4px",
    textAlign: "center",
    color: "var(--neutral-700)",
    fontSize: "0.9rem",
    fontWeight: 700,
  },
  modalOverlay: {
    position: "fixed",
    inset: 0,
    padding: "calc(16px + var(--app-safe-top)) 16px 0",
    background: "rgba(24, 26, 32, 0.42)",
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "center",
    zIndex: 20,
    animation: "fadeInOverlay 220ms ease-out",
  },
  modalCard: {
    width: "100%",
    maxWidth: 760,
    minHeight: "78dvh",
    maxHeight: "88dvh",
    overflowY: "auto",
    borderRadius: "32px 32px 0 0",
    background: "var(--surface-panel)",
    boxShadow: "0 28px 72px rgba(24, 26, 32, 0.18)",
    animation: "slideUpModal 280ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  modalHero: {
    padding: 22,
    minHeight: 220,
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    borderRadius: "32px 32px 0 0",
    background: "linear-gradient(160deg, rgba(5,181,187,0.2), rgba(248,180,0,0.18))",
  },
  modalHeroTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  modalCategory: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.7)",
    fontSize: "0.8rem",
    fontWeight: 800,
    color: "var(--text-secondary)",
  },
  modalCloseButton: {
    width: 38,
    height: 38,
    border: "1px solid rgba(255,255,255,0.6)",
    borderRadius: "50%",
    background: "rgba(255,255,255,0.82)",
    color: "var(--text-secondary)",
    fontSize: "1.5rem",
    lineHeight: 1,
    cursor: "pointer",
  },
  modalTitle: {
    margin: 0,
    fontSize: "2rem",
    fontWeight: 800,
    lineHeight: 1.05,
    color: "var(--text-primary)",
  },
  modalTitleOnImage: {
    color: "#fff",
    textShadow: "0 2px 14px rgba(0,0,0,0.32)",
  },
  modalDistance: {
    marginTop: 10,
    fontSize: "0.92rem",
    color: "var(--text-secondary)",
  },
  modalDistanceOnImage: {
    color: "rgba(255,255,255,0.9)",
    textShadow: "0 1px 8px rgba(0,0,0,0.32)",
  },
  modalBody: {
    padding: 22,
    display: "flex",
    flexDirection: "column",
    gap: 18,
  },
  modalDescription: {
    margin: 0,
    color: "var(--text-secondary)",
    lineHeight: 1.65,
    fontSize: "0.98rem",
  },
  detailStack: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  detailRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "flex-start",
  },
  detailLabel: {
    flexShrink: 0,
    color: "#7a7a7a",
    fontSize: "0.85rem",
    fontWeight: 700,
  },
  detailValue: {
    color: "#333333",
    fontSize: "0.9rem",
    textAlign: "right",
    lineHeight: 1.5,
  },
  modalInfoGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
  },
  modalInfoCard: {
    padding: 16,
    borderRadius: 20,
    background: "var(--surface-muted)",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  modalInfoLabel: {
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
    fontWeight: 700,
  },
  modalInfoValue: {
    color: "var(--text-primary)",
    fontSize: "0.98rem",
  },
  detailSection: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  sectionLabel: {
    margin: 0,
    color: "var(--text-secondary)",
    fontSize: "0.86rem",
    fontWeight: 800,
  },
  detailLinkRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
  },
  detailLink: {
    color: "var(--brand-primary-deep)",
    textDecoration: "none",
    fontWeight: 700,
    fontSize: "0.92rem",
  },
  reviewSection: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  reviewCard: {
    padding: "14px 16px",
    borderRadius: 18,
    background: "var(--surface-muted)",
  },
  reviewHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 8,
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
  },
  reviewBody: {
    margin: 0,
    color: "var(--text-secondary)",
    lineHeight: 1.6,
    fontSize: "0.9rem",
  },
  modalFavoriteButton: {
    width: "100%",
    border: "1px solid rgba(248,180,0,0.26)",
    borderRadius: 18,
    padding: "15px 18px",
    background: "linear-gradient(135deg, var(--brand-secondary), #ffc730)",
    color: "var(--text-primary)",
    fontWeight: 800,
    fontSize: "1rem",
    cursor: "pointer",
  },
  notificationOverlay: {
    position: "fixed",
    inset: 0,
    zIndex: 90,
    background: "rgba(24,26,32,0.26)",
    display: "flex",
    justifyContent: "flex-end",
  },
  notificationPanel: {
    width: "min(390px, 92vw)",
    minHeight: "var(--app-viewport-height)",
    padding: "calc(22px + var(--app-safe-top)) 18px calc(28px + var(--app-safe-bottom))",
    background: "rgba(255,255,255,0.98)",
    boxShadow: "-24px 0 54px rgba(24,26,32,0.18)",
    borderLeft: "1px solid var(--border-soft)",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    animation: "slideInFromRight 260ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  notificationHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 14,
  },
  notificationTitle: {
    margin: "4px 0 0",
    color: "var(--text-primary)",
    fontSize: "1.45rem",
    lineHeight: 1.1,
  },
  notificationCloseButton: {
    width: 38,
    height: 38,
    border: "1px solid rgba(5,181,187,0.16)",
    borderRadius: "50%",
    background: "rgba(255,255,255,0.9)",
    color: "var(--text-secondary)",
    fontWeight: 900,
    cursor: "pointer",
  },
  notificationTabs: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 8,
    padding: 6,
    borderRadius: 18,
    background: "var(--surface-muted)",
  },
  notificationTab: {
    minHeight: 42,
    border: "none",
    borderRadius: 14,
    background: "transparent",
    color: "var(--neutral-700)",
    fontWeight: 900,
    cursor: "pointer",
  },
  notificationTabActive: {
    background: "#ffffff",
    color: "var(--text-primary)",
    boxShadow: "0 8px 20px rgba(24,26,32,0.08)",
  },
  notificationTabBadge: {
    display: "inline-grid",
    placeItems: "center",
    minWidth: 18,
    height: 18,
    marginLeft: 6,
    padding: "0 5px",
    borderRadius: 999,
    background: "var(--brand-secondary)",
    color: "var(--text-primary)",
    fontSize: "0.68rem",
  },
  notificationList: {
    minHeight: 0,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    paddingRight: 2,
  },
  notificationItem: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: 12,
    border: "1px solid var(--border-soft)",
    borderRadius: 18,
    background: "rgba(255,255,255,0.9)",
    color: "var(--text-primary)",
    textAlign: "left",
    cursor: "pointer",
  },
  notificationItemIcon: {
    width: 42,
    height: 42,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    flexShrink: 0,
    background: "rgba(248,180,0,0.18)",
    color: "var(--text-primary)",
    fontWeight: 900,
  },
  notificationAvatar: {
    width: 42,
    height: 42,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  notificationItemText: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 3,
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
  },
  notificationEmpty: {
    minHeight: 180,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 22,
    borderRadius: 20,
    background: "var(--surface-muted)",
    textAlign: "center",
  },
  searchSheet: {
    width: "100%",
    maxWidth: 760,
    minHeight: "56dvh",
    borderRadius: "30px 30px 0 0",
    background: "var(--surface-panel)",
    boxShadow: "0 28px 72px rgba(24, 26, 32, 0.18)",
    padding: "10px 18px 26px",
    animation: "slideUpModal 280ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  searchSheetHandle: {
    width: 56,
    height: 6,
    borderRadius: 999,
    background: "rgba(5,181,187,0.24)",
    margin: "4px auto 16px",
  },
  searchSheetHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  searchSheetInputWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "0 14px",
    minHeight: 54,
    borderRadius: 18,
    background: "var(--surface-muted)",
    color: "var(--neutral-700)",
  },
  searchSheetInput: {
    width: "100%",
    border: "none",
    outline: "none",
    background: "transparent",
    color: "var(--text-primary)",
    fontSize: "1rem",
  },
  searchSheetClose: {
    border: "none",
    background: "transparent",
    color: "var(--neutral-700)",
    fontWeight: 700,
    cursor: "pointer",
    padding: "10px 4px",
  },
  searchSheetSection: {
    marginTop: 24,
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  searchSheetLabelRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  searchSheetTitle: {
    margin: 0,
    color: "var(--text-secondary)",
    fontWeight: 800,
    fontSize: "0.96rem",
  },
  linkButton: {
    border: "none",
    background: "transparent",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
    cursor: "pointer",
    padding: 0,
  },
  searchSuggestionGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
  },
  searchKeywordChip: {
    border: "1px solid #dfdfdf",
    borderRadius: 999,
    padding: "11px 14px",
    background: "rgba(248,180,0,0.12)",
    color: "var(--text-secondary)",
    fontWeight: 700,
    cursor: "pointer",
  },
  recentList: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  recentItem: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    padding: "12px 14px",
    borderRadius: 16,
    background: "rgba(255,255,255,0.82)",
    border: "1px solid var(--border-soft)",
  },
  recentKeywordButton: {
    border: "none",
    background: "transparent",
    color: "var(--text-primary)",
    fontWeight: 700,
    padding: 0,
    cursor: "pointer",
  },
  recentDeleteButton: {
    border: "none",
    borderRadius: "25rem",
    background: "rgba(248,180,0,0.5)",
    color: "var(--text-secondary)",
    fontSize: "1rem",
    lineHeight: 1,
    cursor: "pointer",
    padding: "0.4rem 1rem",
  },
  searchEmpty: {
    margin: 0,
    color: "var(--neutral-700)",
    lineHeight: 1.5,
  },
  scrollTopButton: {
    position: "fixed",
    bottom: "calc(24px + var(--app-bottom-nav-reserved, 0px))",
    right: 20,
    width: 44,
    height: 44,
    borderRadius: "50%",
    border: "none",
    background: "var(--brand-primary)",
    color: "#fff",
    fontSize: "1.2rem",
    fontWeight: 900,
    display: "grid",
    placeItems: "center",
    boxShadow: "0 4px 16px rgba(1,192,192,0.35)",
    cursor: "pointer",
    zIndex: 30,
    animation: "fadeInOverlay 200ms ease-out",
  },
};
