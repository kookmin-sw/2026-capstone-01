import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  ACCENT,
  BRAND,
  KRW_PER_BUDGET_UNIT,
  buildPlanTitle,
  budgetCategoryLabel,
  createTourPlan,
  flattenRecommendedPlacesV2,
  formatKrw,
  getAiPlanDayInputs,
  getTourPlan,
  getTourRecommendationsV2,
  tourPlanToCreateItems,
  tourPlanV2ToRouteStops,
  type AiPreferenceState,
  type MovementHopV2,
  type PlanDetailResponse,
  type PlaceDetailV2,
  type TimelineSlotV2,
  type TourDayResponseV2,
  type TourRecommendResponseV2,
} from "../../api/aiPlanShared";

interface AiPlanResultPageProps {
  preferences: AiPreferenceState;
  onBack: () => void;
  onEdit: () => void;
}

function readPlanId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("planId");
}

function buildRouteTitle(preferences: AiPreferenceState): string {
  const days = getAiPlanDayInputs(preferences);
  return buildPlanTitle(
    "ai",
    `${days[0]?.departureCluster || "Seoul"} to ${days[days.length - 1]?.arrivalCluster || "Seoul"}`
  );
}

function getTimelineSlotsByPlace(day: TourDayResponseV2): Map<string, TimelineSlotV2[]> {
  const slotsByPlace = new Map<string, TimelineSlotV2[]>();
  day.timeline.forEach((slot) => {
    const currentSlots = slotsByPlace.get(slot.place_id) || [];
    slotsByPlace.set(slot.place_id, [...currentSlots, slot]);
  });
  return slotsByPlace;
}

function getMovementAfterPlace(
  day: TourDayResponseV2,
  place: PlaceDetailV2 | undefined
): MovementHopV2 | null {
  if (!place) return null;

  const placeIndex = day.places.findIndex(
    (item) => item.place_id === place.place_id
  );
  const nextPlace = day.places[placeIndex + 1];
  if (!nextPlace) return null;

  return (
    day.movements.find(
      (movement) =>
        movement.from_place === place.display_name &&
        movement.to_place === nextPlace.display_name
    ) || null
  );
}

function savedPlanToRecommendation(plan: PlanDetailResponse): TourRecommendResponseV2 {
  const dayNumbers = Array.from(
    new Set(plan.items.map((item) => item.day_number))
  ).sort((left, right) => left - right);

  return {
    tour_plan: dayNumbers.map((dayNumber) => {
      const items = plan.items.filter((item) => item.day_number === dayNumber);
      return {
        day: dayNumber,
        timeline: items.map((item) => ({
          time: item.visit_time || "--:--",
          place_id: item.place_id,
          title: item.display_name,
        })),
        places: items.map((item) => ({
          place_id: item.place_id,
          display_name: item.display_name,
          category: "Saved place",
          address: item.address,
          location: { lat: 0, lng: 0 },
          rating: item.rating,
          reason: "Saved in your trip plan.",
          estimated_cost_krw: 0,
          stay_minutes: 60,
          photos: item.photos ?? [],
        })),
        movements: [],
        budget_breakdown: [],
        budget_total_krw: 0,
        summary: plan.title || "Saved trip plan",
      };
    }),
  };
}

function GoogleMapPreview({ places }: { places: PlaceDetailV2[] }) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const naverMapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const polylineRef = useRef<any>(null);

  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");

  const positionedPlaces = useMemo(
    () =>
      places.filter(
        (place) =>
          typeof place.location?.lat === "number" &&
          typeof place.location?.lng === "number"
      ),
    [places]
  );

  useEffect(() => {
    if (!mapRef.current || positionedPlaces.length === 0) {
      setMapReady(false);
      setMapError("");
      return;
    }

    const clientId = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID;

    if (!clientId) {
      setMapError("Add VITE_NAVER_MAPS_CLIENT_ID to render the map.");
      return;
    }

    const scriptId = "naver-maps-sdk-ai";

    const load = () => {
      setTimeout(() => {
        initMap();
      }, 100);
    };

    if (!document.getElementById(scriptId)) {
      const script = document.createElement("script");

      script.id = scriptId;
      script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}&submodules=gl`;

      script.onload = load;
      script.onerror = () => {
        setMapError("Naver Maps SDK failed to load.");
      };

      document.head.appendChild(script);
    } else if ((window as any).naver?.maps) {
      load();
    } else {
      document
        .getElementById(scriptId)
        ?.addEventListener("load", load, { once: true });
    }

    function initMap() {
      const naver = (window as any).naver;

      if (!naver?.maps || !mapRef.current) return;

      let map = naverMapRef.current;

      if (!map) {
        map = new naver.maps.Map(mapRef.current, {
          center: new naver.maps.LatLng(
            positionedPlaces[0].location.lat,
            positionedPlaces[0].location.lng
          ),
          zoom: 11,
          gl: true,
          scaleControl: false,
          mapDataControl: false,
          customStyleId: import.meta.env.VITE_NAVER_MAPS_STYLE_ID,
        });

        naverMapRef.current = map;
      } else {
        map.refresh();
      }

      markersRef.current.forEach((marker) => marker.setMap(null));
      markersRef.current = [];

      if (polylineRef.current) {
        polylineRef.current.setMap(null);
        polylineRef.current = null;
      }

      const bounds = new naver.maps.LatLngBounds();

      positionedPlaces.forEach((place, index) => {
        const position = new naver.maps.LatLng(
          place.location.lat,
          place.location.lng
        );

        bounds.extend(position);

        const marker = new naver.maps.Marker({
          position,
          map,
          title: place.display_name,

          icon: {
            content: `
              <svg width="24" height="32" viewBox="0 0 36 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M18 0C8.06 0 0 8.06 0 18C0 31.5 18 48 18 48C18 48 36 31.5 36 18C36 8.06 27.94 0 18 0Z" fill="#58C9D4"/>
                <text x="18" y="22" text-anchor="middle" dominant-baseline="middle" fill="white" font-size="14" font-weight="800" font-family="sans-serif">
                  ${index + 1}
                </text>
              </svg>
            `,
            anchor: new naver.maps.Point(12, 32),
          },
        });

        markersRef.current.push(marker);
      });

      if (positionedPlaces.length > 1) {
        polylineRef.current = new naver.maps.Polyline({
          path: positionedPlaces.map(
            (place) =>
              new naver.maps.LatLng(
                place.location.lat,
                place.location.lng
              )
          ),

          strokeColor: "#58C9D4",
          strokeOpacity: 0.9,
          strokeWeight: 4,
          map,
        });
      }

      map.fitBounds(bounds, {
        top: 60,
        right: 60,
        bottom: 60,
        left: 60,
      });

      setMapReady(true);
      setMapError("");
    }
  }, [positionedPlaces]);

  const hasApiKey = Boolean(import.meta.env.VITE_NAVER_MAPS_CLIENT_ID);

  return (
    <div style={styles.mapCard}>
      <div style={styles.mapViewport}>
        <div style={styles.mapCanvasGoogle} ref={mapRef} />

        {positionedPlaces.length === 0 ? (
          <div style={styles.mapEmpty}>
            Location coordinates will appear here when the API returns them.
          </div>
        ) : !hasApiKey ? (
          <div style={styles.mapEmpty}>
            Add `VITE_NAVER_MAPS_CLIENT_ID` to render the live map.
          </div>
        ) : mapError ? (
          <div style={styles.mapEmpty}>{mapError}</div>
        ) : !mapReady ? (
          <div style={styles.mapEmpty}>Loading Naver Map...</div>
        ) : null}
      </div>

      <div style={styles.mapLegend}>
        {positionedPlaces.map((place, index) => (
          <div key={place.place_id} style={styles.mapLegendItem}>
            <span style={styles.mapLegendIndex}>{index + 1}</span>
            <span style={styles.mapLegendText}>
              {place.display_name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LoadingPlanScreen() {
  return (
    <section style={styles.loadingSection}>
      <div style={styles.loadingDots}>
        <span style={{ ...styles.loadingDot, animationDelay: "0s" }} />
        <span style={{ ...styles.loadingDot, animationDelay: "0.15s" }} />
        <span style={{ ...styles.loadingDot, animationDelay: "0.3s" }} />
        <span style={{ ...styles.loadingDot, animationDelay: "0.45s" }} />
      </div>
      <p style={styles.loadingText}>Creating your itinerary</p>
    </section>
  );
}
export default function AiPlanResultPage({
  preferences,
  onBack,
}: AiPlanResultPageProps) {
  const [plan, setPlan] = useState<TourRecommendResponseV2 | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [saveMessage, setSaveMessage] = useState("");

  const planId = useMemo(() => readPlanId(), []);
  
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setErrorMessage("");

    const request = planId
      ? getTourPlan(planId).then(savedPlanToRecommendation)
      : getTourRecommendationsV2(preferences);

    void request
      .then((result) => {
        if (cancelled) return;
        setPlan(result);
      })
      .catch((error) => {
        if (cancelled) return;
        setPlan(null);
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load recommended plan."
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [planId, preferences]);

  const allPlaces = useMemo(() => flattenRecommendedPlacesV2(plan), [plan]);
  const routeStops = useMemo(() => tourPlanV2ToRouteStops(plan), [plan]);
  const budgetTotal = plan?.tour_plan.reduce(
    (sum, day) => sum + day.budget_total_krw,
    0
  ) || 0;
  const dailyBudgetLimit = Math.max(0, preferences.budgetValue * KRW_PER_BUDGET_UNIT);
  const tripBudgetLimit = dailyBudgetLimit * Math.max(1, preferences.durationDays || 1);
  const hasDailyBudgetOverrun = Boolean(
    plan?.tour_plan.some((day) => day.budget_total_krw > dailyBudgetLimit)
  );
  const isOverBudget =
    dailyBudgetLimit > 0 &&
    (budgetTotal > tripBudgetLimit || hasDailyBudgetOverrun);
  const summary = plan?.tour_plan.map((day) => day.summary).filter(Boolean).join(" ") ||
    `This itinerary uses ${routeStops.length} places returned by the recommendation API.`;


  if (isLoading) {
    return (
      <div style={styles.page}>
        <style>{`
          @keyframes menuBounce {
            0%, 80%, 100% { transform: translateY(0); opacity: 0.35; }
            40% { transform: translateY(-7px); opacity: 1; }
          }
        `}</style>

        <div style={styles.phoneFrame}>
          <div style={styles.headerRow}>
            <button type="button" onClick={onBack} style={styles.iconButton}>
            <img src="/icon-back.svg" alt="Back" style={styles.backIcon} />
            </button>
            <h1 style={styles.headerLogo}>
              AI Plan
            </h1>
          </div>
          <LoadingPlanScreen />
        </div>
      </div>
    );
  }
  const handleSave = () => {
    const items = tourPlanToCreateItems(plan);
    if (items.length === 0) {
      setSaveMessage("There are no places to save yet.");
      return;
    }

    void createTourPlan({
      title: buildRouteTitle(preferences),
      travel_days: Math.max(1, plan?.tour_plan.length || preferences.durationDays || 1),
      items,
    })
      .then((saved) => {
        setSaveMessage(`Saved to My Page (${saved.title || "Untitled plan"})`);
      })
      .catch((error) => {
        setSaveMessage(
          error instanceof Error ? error.message : "Failed to save plan."
        );
      });
  };

  return (
    <div style={styles.page}>
      <div style={styles.phoneFrame}>
        <div style={styles.headerRow}>
          <button type="button" onClick={onBack} style={styles.iconButton}>
            <img src="/icon-back.svg" alt="Back" style={styles.backIcon} />
            </button>
            <h1 style={styles.headerLogo}>
              AI Plan
            </h1>
          </div>

        <div style={styles.titleBlock}>
          <h1 style={styles.title}>{buildRouteTitle(preferences)}</h1>
          <p style={styles.copy}>{summary}</p>
        </div>

        <div style={styles.summaryTagGroup}>
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>Budget</span>
              <strong style={styles.summaryValue}>
                {budgetCategoryLabel(preferences.budgetCategory)}
              </strong>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>Companion</span>
              <strong style={styles.summaryValue}>
                {preferences.companion || "Not selected"}
              </strong>
            </div>
          </div>
          <div style={{ ...styles.summaryCard, ...styles.styleSummaryCard }}>
            <span style={styles.summaryLabel}>Travel Style</span>
            <strong style={{ ...styles.summaryValue, ...styles.styleSummaryValue }}>
              {preferences.styles.length > 0
                ? preferences.styles.join(" + ")
                : "No style selected"}
            </strong>
          </div>
        </div>

        <GoogleMapPreview places={allPlaces} />

        <section style={styles.timelineSection}>
          <div style={styles.timelineHeader}>
            <div>
              <h2 style={styles.timelineTitle}>Timeline</h2>
            </div>
            <span style={styles.timelineBadge}>Public Transit</span>
          </div>

          {errorMessage ? (
            <div style={styles.stateCard}>{errorMessage}</div>
          ) : !plan || plan.tour_plan.length === 0 ? (
            <div style={styles.stateCard}>No plan has been returned yet.</div>
          ) : (
            <div style={styles.timelineList}>
              {plan.tour_plan.map((day) => {
                const slotsByPlace = getTimelineSlotsByPlace(day);
                const dayOverBudget =
                  dailyBudgetLimit > 0 && day.budget_total_krw > dailyBudgetLimit;
                return (
                  <section key={day.day} style={styles.dayRouteBlock}>
                    <div style={styles.dayRouteHeader}>
                      <strong style={styles.dayRouteTitle}>Day {day.day}</strong>
                      <span style={styles.dayRouteCluster}>
                        {formatKrw(day.budget_total_krw)}
                        {dayOverBudget ? " - Over budget" : ""}
                      </span>
                    </div>
                    {day.places.map((place, index) => {
                      const placeSlots = slotsByPlace.get(place.place_id) || [];
                      const primarySlot = placeSlots[0];
                      const movement = getMovementAfterPlace(day, place);
                      return (
                        <div key={`${day.day}-${place.place_id}-${index}`}>
                          <div style={styles.timelineItem}>
                            <div style={styles.timelineTime}>
                              {primarySlot?.time || "--:--"}
                            </div>
                            <div style={styles.timelineDot}>{index + 1}</div>
                            <div style={styles.timelineCard}>
                              <div style={styles.timelineTitleRow}>
                                <strong style={styles.timelineItemTitle}>
                                  {primarySlot?.title || place.display_name}
                                </strong>
                                {typeof place.rating === "number" ? (
                                  <span style={styles.ratingBadge}>{place.rating.toFixed(1)}</span>
                                ) : null}
                              </div>
                              {placeSlots.length > 1 ? (
                                <div style={styles.slotList}>
                                  {placeSlots.slice(1).map((slot) => (
                                    <span key={`${slot.time}-${slot.title}`}>
                                      {slot.time} {slot.title}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                              {place.reason ? (
                                <p style={styles.timelineCopy}>{place.reason}</p>
                              ) : null}
                              {place.address ? (
                                <p style={styles.poiAddress}>{place.address}</p>
                              ) : null}
                              <div style={styles.poiMetaRow}>
                                <span>{place.category}</span>
                                <span>{place.stay_minutes} min</span>
                                <span>{formatKrw(place.estimated_cost_krw)}</span>
                              </div>
                            </div>
                          </div>
                          {movement ? (
                            <div style={styles.movementCard}>
                              {movement.from_place} to {movement.to_place}: {movement.method}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                    {day.summary ? <p style={styles.daySummary}>{day.summary}</p> : null}
                    {day.budget_breakdown.length > 0 ? (
                      <div style={styles.budgetList}>
                        {day.budget_breakdown.map((item) => (
                          <div key={`${day.day}-${item.label}`} style={styles.budgetItem}>
                            <span>{item.label}</span>
                            <strong>{formatKrw(item.amount_krw)}</strong>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </section>
                );
              })}
            </div>
          )}
        </section>

        {plan ? (
          <div style={{ ...styles.stateCard, ...(isOverBudget ? styles.warningCard : {}) }}>
            Total budget: {formatKrw(budgetTotal)}
            {isOverBudget ? " - Budget may be exceeded." : ""}
            {preferences.foodNeed
              ? ` ${preferences.foodNeed} dining data can be sparse, so meal slots may be missing in some areas.`
              : ""}
          </div>
        ) : null}

        <button
          type="button"
          onClick={handleSave}
          style={styles.primaryAction}
          disabled={!plan || routeStops.length === 0}
        >
          Save plan to My Page
        </button>

        {saveMessage ? <p style={styles.saveMessage}>{saveMessage}</p> : null}
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(20px + var(--app-safe-top)) 16px 20px",
    background: "#fff",
    fontFamily: '"Pretendard Variable", sans-serif',
  },
  phoneFrame: {
    maxWidth: 430,
    width: "100%",
    minHeight: "calc(var(--app-viewport-height) - 40px - var(--app-safe-top))",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 18,
    paddingBottom: 28,
  },
  headerRow: {
    display: "grid",
    gridTemplateColumns: "42px 1fr 42px",
    alignItems: "center",
  },
  iconButton: {
    width: 42,
    height: 42,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 14,
    border: "none",
    background: "transparent",
    padding: 0,
    outline: "none",
    cursor: "pointer",
  },
  backIcon: {
    width: 20,
    height: 20,
    display: "block",
  },
  headerLogo: {
    fontSize: "1.1rem",
    height: "auto",
    display: "flex",
    color: "#212121",
    alignItems: "center",
    justifyContent: "center",
  },
  titleBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  title: {
    margin: 0,
    fontSize: "1.15rem",
    lineHeight: "1.5rem",
    color: "#102223",
    fontWeight: 800,
  },
  copy: {
    margin: 0,
    color: "#8b8b8b",
    fontSize: "0.65rem",
    lineHeight: 1.45,
  },
  summaryTagGroup: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    gap: 8,
  },
  summaryGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  summaryCard: {
    display: "inline-flex",
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    width: "fit-content",
    padding: "7px 10px",
    borderRadius: 999,
    background: "#ecfbfb",
    border: "none",
  },
  styleSummaryCard: {
    background: "#FFF5D9",
  },
  summaryLabel: {
    display: "none",
  },
  summaryValue: {
    color: "#05AEAE",
    fontSize: "0.6rem",
    lineHeight: 1,
    fontWeight: 800,
  },
  styleSummaryValue: {
    color: "#936B00",
  },
  mapCard: {
    margin: "0.8rem 0"
  },
  mapViewport: {
    position: "relative",
    minHeight: 220,
    borderRadius: 18,
    overflow: "hidden",
    background: "#eef7f7",
    marginBottom: 20,
  },
  mapCanvasGoogle: {
    position: "absolute",
    inset: 0,
  },
  mapEmpty: {
    position: "absolute",
    inset: 0,
    display: "grid",
    placeItems: "center",
    textAlign: "center",
    color: "#537070",
    padding: "0 20px",
    lineHeight: 1.6,
    background: "#eef7f7",
    zIndex: 1,
  },
  mapLegend: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  mapLegendItem: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  mapLegendIndex: {
    width: 22,
    height: 22,
    borderRadius: "50%",
    background: BRAND,
    color: "#fff",
    display: "grid",
    placeItems: "center",
    fontSize: 12,
    fontWeight: 800,
  },
  mapLegendText: {
    color: "#204444",
    fontSize: 13,
    fontWeight: 700,
  },
  timelineSection: {
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  timelineHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  timelineTitle: {
    margin: 0,
    color: "#102223",
    fontSize: 16,
  },
  timelineBadge: {
    padding: "8px 10px",
    borderRadius: 999,
    background: "rgba(255,190,15,0.18)",
    color: "#7a5400",
    fontSize: 8,
    fontWeight: 800,
  },
  timelineList: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  timelineItem: {
    display: "grid",
    gridTemplateColumns: "56px 26px 1fr",
    gap: 10,
    alignItems: "start",
  },
  timelineTime: {
    color: BRAND,
    fontSize: 12,
    fontWeight: 900,
    paddingTop: 14,
  },
  timelineDot: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    background: BRAND,
    color: "#fff",
    display: "grid",
    placeItems: "center",
    marginTop: 10,
    fontSize: 12,
    fontWeight: 900,
  },
  timelineCard: {
    padding: "14px 16px",
    borderRadius: 18,
    background: "#ffffff",
    border: "1px solid #eaeaea",
  },
  timelineTitleRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  timelineItemTitle: {
    color: "#222",
    fontSize: "0.8rem",
  },
  ratingBadge: {
    padding: "5px 8px",
    borderRadius: 999,
    background: "rgba(255,190,15,0.2)",
    color: "#7a5400",
    fontSize: 11,
    fontWeight: 900,
  },
  timelineCopy: {
    margin: "8px 0 0",
    color: "#888",
    lineHeight: 1.4,
    fontSize: "0.7rem",
  },
  slotList: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    marginTop: 8,
    color: "#5d7576",
    fontSize: 12,
    fontWeight: 700,
  },
  dayRouteBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  dayRouteHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    padding: "0 2px",
  },
  dayRouteTitle: {
    color: "#102223",
    fontSize: 16,
  },
  dayRouteCluster: {
    color: BRAND,
    fontSize: "0.75rem",
    fontWeight: 700,
  },
  loadingSection: {
    flex: 1,
    minHeight: 360,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 18,
  },

  loadingDots: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  loadingDot: {
    width: 10,
    height: 10,
    borderRadius: "50%",
    background: BRAND,
    display: "block",
    animation: "menuBounce 1s infinite ease-in-out",
  },
  loadingText: {
    margin: 0,
    color: "#537070",
    fontSize: 13,
    fontWeight: 800,
  },
  stateCard: {
    padding: 18,
    borderRadius: 18,
    background: "#ffffff",
    border: "1px solid #eaeaea",
    color: "#58C9D4",
    lineHeight: 1.6,
    fontSize: 13,
    fontWeight: 800,
  },
  warningCard: {
    border: "1px solid rgba(255,190,15,0.65)",
    background: "rgba(255,190,15,0.12)",
    color: "#7a5400",
    fontWeight: 800,
  },
  poiAddress: {
    margin: "8px 0 0",
    color: BRAND,
    fontSize: "0.65rem",
    fontWeight: 800,
  },
  poiMetaRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
    color: "#888",
    fontSize: 12,
    fontWeight: 700,
  },
  movementCard: {
    margin: "8px 0 8px 102px",
    padding: "10px 12px",
    borderRadius: 14,
    background: "#f6f6f6",
    color: "#555",
    fontSize: 10,
    fontWeight: 500,
    lineHeight: 1.4,
  },
  daySummary: {
    margin: 0,
    padding: 14,
    borderRadius: 16,
    background: "#f5f5f5",
    color: "#333",
    lineHeight: 1.6,
    fontSize: 12,
  },
  budgetList: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: 14,
    borderRadius: 16,
    background: "#ffffff",
    border: "1px solid #eaeaea",
  },
  budgetItem: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    color: "#204444",
    fontSize: 13,
  },
  primaryAction: {
    minHeight: 56,
    border: "none",
    borderRadius: "3rem",
    background: "#58C9D4",
    color: "#ffffff",
    fontSize: 15,
    fontWeight: 800,
    cursor: "pointer",
  },
  saveMessage: {
    margin: 0,
    textAlign: "center",
    color: BRAND,
    fontSize: 13,
    fontWeight: 800,
  },
};
