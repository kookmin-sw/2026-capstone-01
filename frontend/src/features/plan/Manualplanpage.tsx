import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { getTourPlaces, type TourPlaceApiItem } from "../../api/auth/auth";
import {
  ACCENT,
  BRAND,
  DEFAULT_MAP_CENTER,
  addTourPlanDay,
  buildPlanTitle,
  createTourPlanItem,
  createTourPlan,
  createPlanId,
  deleteTourPlanItem,
  getTourPlan,
  hydratePlanItemCoordinates,
  moveTourPlanItem,
  updateTourPlanItem,
  updateTourPlanTitle,
  type PlanDetailResponse,
} from "../../api/aiPlanShared";

type ShareTarget = "kakao" | "link" | "mail" | "message";

interface ManualPlanPageProps {
  onBack?: () => void;
  onHome?: () => void;
  onMyPage?: () => void;
}

interface TourPlace {
  id: string;
  name: string;
  category: string;
  summary: string;
  address: string;
  rating?: number;
  latitude?: number;
  longitude?: number;
}

interface PlannedStop extends TourPlace {
  plannedId: string;
  visitDate: string;
  visitTime: string;
  backendItemId?: string;
  backendDayNumber?: number;
}

type ManualStep = 1 | 2 | 3 | 4 | 5;

declare global {
  interface Window {
    Kakao?: {
      isInitialized?: () => boolean;
      init: (key: string) => void;
      Share?: {
        sendDefault: (options: unknown) => void;
      };
    };
  }
}


const MANUAL_PLAN_DATE_METADATA_KEY = "krip-manual-plan-date-metadata";

function formatDateOnly(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDefaultStartDate(): string {
  return formatDateOnly(new Date());
}

function parseDateOnly(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(year, month - 1, day);

  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return null;
  }

  return parsed;
}

function readPlanId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("planId");
}

function formatDateLabel(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function enumerateTripDates(startDate: string, endDate: string): string[] {
  const days: string[] = [];
  const start = parseDateOnly(startDate);
  const end = parseDateOnly(endDate);

  if (!start || !end || start > end) {
    return days;
  }

  const cursor = new Date(start);
  while (cursor <= end) {
    days.push(formatDateOnly(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }

  return days;
}

function readManualPlanDateMetadata(): Record<string, Record<string, string>> {
  if (typeof window === "undefined") return {};

  try {
    const raw = window.localStorage.getItem(MANUAL_PLAN_DATE_METADATA_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Record<string, string>>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveManualPlanDateMetadata(
  planId: string,
  dayNumberByDate: Map<string, number>
): void {
  if (typeof window === "undefined") return;

  const current = readManualPlanDateMetadata();
  const dateByDayNumber = Object.fromEntries(
    Array.from(dayNumberByDate.entries()).map(([date, dayNumber]) => [
      String(dayNumber),
      date,
    ])
  );

  window.localStorage.setItem(
    MANUAL_PLAN_DATE_METADATA_KEY,
    JSON.stringify({ ...current, [planId]: dateByDayNumber })
  );
}

function getStableFallbackDate(plan: PlanDetailResponse): string {
  const parsed = new Date(plan.created_at);
  return Number.isNaN(parsed.getTime())
    ? getDefaultStartDate()
    : formatDateOnly(parsed);
}

function addDays(date: string, days: number): string {
  const parsed = parseDateOnly(date);
  if (!parsed) return getDefaultStartDate();
  parsed.setDate(parsed.getDate() + days);
  return formatDateOnly(parsed);
}

function ensurePlaceSlots(stops: PlannedStop[]): Array<PlannedStop | null> {
  if (stops.length >= 2) return stops;
  return [...stops, ...Array.from({ length: 2 - stops.length }, () => null)];
}

function stopsToSlotsByDate(
  stops: PlannedStop[],
  dates: string[]
): Record<string, Array<PlannedStop | null>> {
  const fallbackDates = dates.length > 0 ? dates : [getDefaultStartDate()];
  return Object.fromEntries(
    fallbackDates.map((date) => [
      date,
      ensurePlaceSlots(stops.filter((stop) => stop.visitDate === date)),
    ])
  );
}

function applySavedStopsToSlots(
  slots: Array<PlannedStop | null>,
  saved: PlanDetailResponse,
  dayNumberByDate: Map<string, number>
): Array<PlannedStop | null> {
  const filledStops = slots.filter((stop): stop is PlannedStop => Boolean(stop));
  const updatedStops = applySavedItemsToCurrentStops(
    filledStops,
    saved,
    dayNumberByDate
  );
  let nextIndex = 0;

  return ensurePlaceSlots(
    slots
      .map((slot) => (slot ? updatedStops[nextIndex++] || slot : null))
      .filter((slot): slot is PlannedStop => Boolean(slot))
  );
}

function getMonthLabel(month: Date): string {
  return month.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

function getMonthDays(month: Date): Array<Date | null> {
  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
  const daysInMonth = new Date(
    month.getFullYear(),
    month.getMonth() + 1,
    0
  ).getDate();
  const leadingDays = firstDay.getDay();
  const days: Array<Date | null> = Array.from({ length: leadingDays }, () => null);

  for (let day = 1; day <= daysInMonth; day++) {
    days.push(new Date(month.getFullYear(), month.getMonth(), day));
  }

  while (days.length % 7 !== 0) {
    days.push(null);
  }

  return days;
}

function isDateInRange(date: string, startDate: string, endDate: string): boolean {
  return date >= startDate && date <= endDate;
}

function savedPlanToStops(
  plan: PlanDetailResponse,
  dateByDayNumber: Record<string, string> = {}
): PlannedStop[] {
  const sortedDays = Array.from(
    new Set(plan.items.map((item) => item.day_number))
  ).sort((left, right) => left - right);
  const fallbackStartDate = getStableFallbackDate(plan);
  const dateByDay = new Map(
    sortedDays.map((dayNumber, index) => [
      dayNumber,
      dateByDayNumber[String(dayNumber)] || addDays(fallbackStartDate, index),
    ] as const)
  );

    return plan.items.map((item) => ({
    plannedId: item.item_id,
    backendItemId: item.item_id,
    backendDayNumber: item.day_number,
    id: item.place_id,
    name: item.display_name,
    category: item.category || "Saved place",
    summary: "",
    address: item.address,
    rating: typeof item.rating === "number" ? item.rating : undefined,
    visitDate: dateByDay.get(item.day_number) || getDefaultStartDate(),
    visitTime: item.visit_time || "10:00",
    latitude: Number.isFinite(Number(item.latitude ?? item.location?.lat))
      ? Number(item.latitude ?? item.location?.lat)
      : undefined,
    longitude: Number.isFinite(Number(item.longitude ?? item.location?.lng))
      ? Number(item.longitude ?? item.location?.lng)
      : undefined,
  }));
}

function applySavedItemsToCurrentStops(
  currentStops: PlannedStop[],
  saved: PlanDetailResponse,
  dayNumberByDate: Map<string, number>
): PlannedStop[] {
  const remainingItems = [...saved.items];

  return currentStops.map((stop) => {
    const dayNumber = dayNumberByDate.get(stop.visitDate) || stop.backendDayNumber || 1;
    const matchedIndex = remainingItems.findIndex(
      (item) =>
        item.day_number === dayNumber &&
        item.place_id === stop.id &&
        (item.visit_time || "10:00") === stop.visitTime
    );
    const matchedItem =
      matchedIndex >= 0 ? remainingItems.splice(matchedIndex, 1)[0] : undefined;

    if (!matchedItem) return stop;

    return {
      ...stop,
      plannedId: matchedItem.item_id,
      backendItemId: matchedItem.item_id,
      backendDayNumber: matchedItem.day_number,
      name: matchedItem.display_name || stop.name,
      address: matchedItem.address || stop.address,
      rating:
        typeof matchedItem.rating === "number" ? matchedItem.rating : stop.rating,
    };
  });
}

function normalizePlaces(payload: TourPlaceApiItem[]): TourPlace[] {
  const normalized: Array<TourPlace | null> = payload.map((item) => {
    const latitude = Number(item.latitude ?? item.lat ?? item.location?.lat);
    const longitude = Number(item.longitude ?? item.lng ?? item.location?.lng);

    const id = String(item.place_id || item.id || "");
    const name = String(item.display_name || item.name || item.title || "");

    if (!id || !name) {
      return null;
    }

    return {
      id,
      name,
      category: String(item.category || item.type || item.place_type || "Place"),
      summary: String(
        item.summary ||
          item.description ||
          item.review_summary ||
          item.generative_summary ||
          item.editorial_summary ||
          ""
      ),
      address: String(item.short_address || item.address || ""),
      rating: Number.isFinite(Number(item.rating)) ? Number(item.rating) : undefined,
      latitude: Number.isFinite(latitude) ? latitude : undefined,
      longitude: Number.isFinite(longitude) ? longitude : undefined,
    };
  });

  return normalized.filter((item): item is TourPlace => Boolean(item));
}

async function fetchPlaces(query: string): Promise<TourPlace[]> {
  if (!query.trim()) return [];

  const response = await getTourPlaces({
    lat: DEFAULT_MAP_CENTER.lat,
    lng: DEFAULT_MAP_CENTER.lng,
    keyword: query.trim(),
  });

  return normalizePlaces(response.items);
}

function getDayNumberByDate(dates: string[]): Map<string, number> {
  return new Map(dates.map((date, index) => [date, index + 1]));
}

function plannedStopsToCreateItems(
  stops: PlannedStop[],
  dayNumberByDate: Map<string, number>
) {
  return stops.map((stop) => ({
    day_number: dayNumberByDate.get(stop.visitDate) || 1,
    place_id: stop.id,
    visit_time: stop.visitTime,
  }));
}

async function updateExistingBackendPlan(
  plan: PlanDetailResponse,
  title: string,
  stops: PlannedStop[],
  tripDates: string[]
): Promise<{ saved: PlanDetailResponse; dayNumberByDate: Map<string, number> }> {

  await updateTourPlanTitle(plan.plan_id, title);

  const activeDayNumbers = Array.from(
    new Set(plan.items.map((item) => item.day_number))
  ).sort((a, b) => a - b);

  const currentActiveDays = activeDayNumbers.length;
  const targetTravelDays = Math.max(1, tripDates.length);

  const extendedDayNumbers = [...activeDayNumbers];
  for (let i = currentActiveDays; i < targetTravelDays; i++) {
    await addTourPlanDay(plan.plan_id);
    extendedDayNumbers.push(plan.travel_days + 1 + (i - currentActiveDays));
  }

  const dayNumberByDate = new Map(
    tripDates.map((date, index) => [
      date,
      extendedDayNumbers[index] ?? index + 1,
    ])
  );
  const activeBackendIds = new Set(
    stops.map((stop) => stop.backendItemId).filter(Boolean)
  );
  await Promise.all(
    plan.items
      .filter((item) => !activeBackendIds.has(item.item_id))
      .map((item) => deleteTourPlanItem(plan.plan_id, item.item_id))
  );

  const sortedStops = [...stops].sort((left, right) => {
    const leftDay = dayNumberByDate.get(left.visitDate) || 1;
    const rightDay = dayNumberByDate.get(right.visitDate) || 1;
    if (leftDay !== rightDay) return leftDay - rightDay;
    return left.visitTime.localeCompare(right.visitTime);
  });

  const backendIdByPlannedId = new Map<string, string>();
  for (const stop of sortedStops) {
    const dayNumber = dayNumberByDate.get(stop.visitDate) || 1;
    if (stop.backendItemId) {
      const updated = await updateTourPlanItem(plan.plan_id, stop.backendItemId, {
        place_id: stop.id,
        visit_time: stop.visitTime,
      });
      backendIdByPlannedId.set(stop.plannedId, updated.item_id);
    } else {
      const created = await createTourPlanItem(plan.plan_id, {
        day_number: dayNumber,
        place_id: stop.id,
        visit_time: stop.visitTime,
      });
      backendIdByPlannedId.set(stop.plannedId, created.item_id);
    }
  }

  for (const [index, stop] of sortedStops.entries()) {
    const itemId = backendIdByPlannedId.get(stop.plannedId);
    if (!itemId) continue;

    const dayNumber = dayNumberByDate.get(stop.visitDate) || 1;
    const previousSameDay = [...sortedStops]
      .slice(0, index)
      .reverse()
      .find((candidate) => candidate.visitDate === stop.visitDate);

    await moveTourPlanItem(plan.plan_id, itemId, {
      target_day_number: dayNumber,
      after_item_id: previousSameDay
        ? backendIdByPlannedId.get(previousSameDay.plannedId) || null
        : null,
    });
  }

  const saved = await getTourPlan(plan.plan_id);
  return { saved, dayNumberByDate };
}

async function loadKakaoSdk(): Promise<typeof window.Kakao | null> {
  if (typeof window === "undefined") return null;
  if (window.Kakao) return window.Kakao;

  await new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[data-kakao-sdk="true"]'
    );

    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("SDK load failed")), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.src = "https://developers.kakao.com/sdk/js/kakao.min.js";
    script.async = true;
    script.dataset.kakaoSdk = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("SDK load failed"));
    document.head.appendChild(script);
  });

  return window.Kakao || null;
}

function createShareLink(): string {
  if (typeof window === "undefined") {
    return "https://example.com/trip/manual";
  }
  return window.location.href;
}

function ShareSheet({ onClose }: { onClose: () => void }) {
  const shareLink = createShareLink();

  const handleShare = async (target: ShareTarget) => {
    if (target === "kakao") {
      const kakao = await loadKakaoSdk().catch(() => null);
      const kakaoKey = import.meta.env.VITE_KAKAO_JS_KEY;

      if (!kakao || !kakaoKey) {
        window.alert("Add VITE_KAKAO_JS_KEY to enable KakaoTalk sharing.");
        onClose();
        return;
      }

      if (!kakao.isInitialized?.()) {
        kakao.init(kakaoKey);
      }

      kakao.Share?.sendDefault({
        objectType: "feed",
        content: {
          title: "Trip plan invite",
          description: "Join my trip plan and edit it together.",
          imageUrl:
            "https://developers.kakao.com/tool/resource/static/img/button/kakaolink_btn_small.png",
          link: {
            mobileWebUrl: shareLink,
            webUrl: shareLink,
          },
        },
        buttons: [
          {
            title: "Open Plan",
            link: {
              mobileWebUrl: shareLink,
              webUrl: shareLink,
            },
          },
        ],
      });
      onClose();
      return;
    }

    if (target === "link") {
      try {
        await navigator.clipboard.writeText(shareLink);
      } catch {
        window.prompt("Copy this link", shareLink);
      }
      onClose();
      return;
    }

    if (target === "mail") {
      window.location.assign(
        `mailto:?subject=Trip plan invite&body=Join my trip plan: ${shareLink}`
      );
      onClose();
      return;
    }

    window.location.assign(`sms:?body=Join my trip plan ${shareLink}`);
    onClose();
  };

  const shareButtons: Array<{
    id: ShareTarget;
    title: string;
    subtitle: string;
    color: string;
  }> = [
    { id: "kakao", title: "KakaoTalk", subtitle: "SDK share", color: "#fee500" },
    { id: "link", title: "Copy Link", subtitle: "Share URL", color: "#dffafa" },
    { id: "mail", title: "Email", subtitle: "Send invite", color: "#eef3ff" },
    { id: "message", title: "Message", subtitle: "Open SMS", color: "#f3fff0" },
  ];

  return (
    <div style={styles.overlay}>
      <button
        type="button"
        onClick={onClose}
        style={styles.overlayBackdrop}
        aria-label="Close share sheet"
      />
      <div style={styles.sheet}>
        <div style={styles.sheetHandle} />
        <h2 style={styles.sheetTitle}>Invite friends</h2>
        <p style={styles.sheetCopy}>
          Share this planning link so your friends can join and work on the itinerary together.
        </p>
        <div style={styles.shareGrid}>
          {shareButtons.map((button) => (
            <button
              key={button.id}
              type="button"
              onClick={() => void handleShare(button.id)}
              style={{ ...styles.shareCard, background: button.color }}
            >
              <strong style={styles.shareTitle}>{button.title}</strong>
              <span style={styles.shareSubtitle}>{button.subtitle}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MapPreview({ stops }: { stops: PlannedStop[] }) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const naverMapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]); 
  const polylineRef = useRef<any>(null);  
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");

  const positionedStops = useMemo(
    () =>
      stops.filter(
        (stop): stop is PlannedStop & { latitude: number; longitude: number } =>
          typeof stop.latitude === "number" && typeof stop.longitude === "number"
      ),
    [stops]
  );

  useEffect(() => {
    if (!mapRef.current || positionedStops.length === 0) return;

    const clientId = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID;
    if (!clientId) {
      setMapError("Add VITE_NAVER_MAPS_CLIENT_ID to render the map.");
      return;
    }

    const scriptId = "naver-maps-sdk-gl";
    
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
      script.onerror = () => setMapError("Naver Maps SDK failed to load.");
      document.head.appendChild(script);
    } else if ((window as any).naver?.maps) {
      load();
    } else {
      document.getElementById(scriptId)?.addEventListener("load", load, { once: true });
    }

    function initMap() {
      const naver = (window as any).naver;
      if (!naver?.maps || !mapRef.current) return;

      let map = naverMapRef.current;

      if (!map) {
        map = new naver.maps.Map(mapRef.current, {
          center: new naver.maps.LatLng(
            positionedStops[0].latitude,
            positionedStops[0].longitude
          ),
          gl: true, 
          zoom: 10,
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

      positionedStops.forEach((stop, index) => {
        const position = new naver.maps.LatLng(stop.latitude, stop.longitude);
        bounds.extend(position);

        const marker = new naver.maps.Marker({
          position,
          map,
          icon: {
            content: `
              <svg width="24" height="32" viewBox="0 0 36 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M18 0C8.06 0 0 8.06 0 18C0 31.5 18 48 18 48C18 48 36 31.5 36 18C36 8.06 27.94 0 18 0Z" fill="#58C9D4"/>
                <text x="18" y="22" text-anchor="middle" dominant-baseline="middle" fill="white" font-size="14" font-weight="800" font-family="sans-serif">${index + 1}</text>
              </svg>
            `,
            anchor: new naver.maps.Point(12, 32),
          },
        });
        markersRef.current.push(marker);
      });

      if (positionedStops.length > 1) {
        polylineRef.current = new naver.maps.Polyline({
          path: positionedStops.map(
            (stop) => new naver.maps.LatLng(stop.latitude, stop.longitude)
          ),
          strokeColor: "#58C9D4",
          strokeOpacity: 0.9,
          strokeWeight: 3,
          map,
        });
      }

      if (positionedStops.length > 0) {
        map.fitBounds(bounds, { top: 60, right: 60, bottom: 60, left: 60 });
      }

      setMapReady(true);
      setMapError("");
    }
  }, [mapRef, positionedStops]);

  const hasApiKey = Boolean(import.meta.env.VITE_NAVER_MAPS_CLIENT_ID);

  return (
    <div style={styles.mapBox}>
      <div style={styles.mapViewport}>
        <div style={styles.mapCanvasGoogle} ref={mapRef} />
        {positionedStops.length === 0 ? (
          <div style={styles.mapEmpty}>
            Search and add places with coordinates to display them on the map.
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
      {positionedStops.length > 0 ? (
        <div style={styles.mapLegendInline}>
          {positionedStops.map((stop, index) => (
            <div key={stop.plannedId} style={styles.mapLegendChip}>
              <span style={styles.mapLegendIndex}>{index + 1}</span>
              <span style={styles.mapLegendLabel}>{stop.name}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StepProgress({ step }: { step: ManualStep }) {
  return (
    <div style={styles.stepProgress} aria-label={`Step ${step} of 5`}>
      {Array.from({ length: 5 }, (_, index) => {
        const isActive = index + 1 === step;
        return (
          <span
            key={index}
            style={{
              ...styles.stepDot,
              ...(isActive ? styles.stepDotActive : {}),
            }}
          />
        );
      })}
    </div>
  );
}

function DateRangeCalendar({
  startDate,
  endDate,
  onSelectDate,
}: {
  startDate: string;
  endDate: string;
  onSelectDate: (date: string) => void;
}) {
  const baseMonth = parseDateOnly(startDate) || new Date();
  const months = Array.from(
    { length: 12 },
    (_, index) => new Date(baseMonth.getFullYear(), baseMonth.getMonth() + index, 1)
  );
  const weekdays = ["S", "M", "T", "W", "T", "F", "S"];
  const todayValue = formatDateOnly(new Date());

  return (
    <div style={styles.calendarScroller}>
      {months.map((month) => (
        <section key={month.toISOString()} style={styles.monthBlock}>
          <h3 style={styles.monthTitle}>{getMonthLabel(month)}</h3>
          <div style={styles.weekdayGrid}>
            {weekdays.map((day, index) => (
              <span key={`${day}-${index}`} style={styles.weekdayLabel}>
                {day}
              </span>
            ))}
          </div>
          <div style={styles.calendarGrid}>
            {getMonthDays(month).map((date, index) => {
              if (!date) {
                return <span key={`empty-${index}`} style={styles.calendarEmptyDay} />;
              }

              const dateValue = formatDateOnly(date);
              const isStart = dateValue === startDate;
              const isEnd = dateValue === endDate;
              const isToday = dateValue === todayValue;
              const isSelectedRange = isDateInRange(dateValue, startDate, endDate);

              const rangeEdgeStyle =
                isStart && isEnd
                  ? styles.calendarDaySingleSelected
                  : isStart
                    ? styles.calendarDayRangeStart
                    : isEnd
                      ? styles.calendarDayRangeEnd
                      : {};

              return (
                <button
                  key={dateValue}
                  type="button"
                  className="manual-step2-calendar-day"
                  onClick={() => onSelectDate(dateValue)}
                  style={{
                    ...styles.calendarDay,
                    ...(isToday ? styles.calendarDayToday : {}),
                    ...(isSelectedRange ? styles.calendarDayInRange : {}),
                    ...(isStart || isEnd ? styles.calendarDaySelected : {}),
                    ...rangeEdgeStyle,
                  }}
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

export default function ManualPlanPage({
  onBack,
  onHome,
  onMyPage,
}: ManualPlanPageProps) {
  const [step, setStep] = useState<ManualStep>(1);
  const [tripTitle, setTripTitle] = useState("Manual Trip Plan");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [isSelectingEndDate, setIsSelectingEndDate] = useState(false);
  const [activeDate, setActiveDate] = useState("");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchResults, setSearchResults] = useState<TourPlace[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [placeSlotsByDate, setPlaceSlotsByDate] = useState<
    Record<string, Array<PlannedStop | null>>
  >({});
  const [selectedPlaceSlotIndex, setSelectedPlaceSlotIndex] = useState(0);
  const [loadedPlan, setLoadedPlan] = useState<PlanDetailResponse | null>(null);
  const [editingStopId, setEditingStopId] = useState<string | null>(null);
  const [draggedStopId, setDraggedStopId] = useState<string | null>(null);
  const [hasSeenStepFiveHint, setHasSeenStepFiveHint] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [showPlaceSearch, setShowPlaceSearch] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [isComplete, setIsComplete] = useState(false);

  const planId = useMemo(() => readPlanId(), []);
  const tripDates = useMemo(
    () => enumerateTripDates(startDate, endDate),
    [startDate, endDate]
  );

  useEffect(() => {
    if (!planId) {
      return;
    }

    let cancelled = false;
    void getTourPlan(planId)
      .then((savedPlan) => hydratePlanItemCoordinates(savedPlan))
      .then((savedPlan) => {
        if (cancelled) return;
        const dateMetadata = readManualPlanDateMetadata()[savedPlan.plan_id] || {};
        const stops = savedPlanToStops(savedPlan, dateMetadata);
        const dates = Array.from(new Set(stops.map((stop) => stop.visitDate))).sort();
        const firstDate = dates[0] || getDefaultStartDate();
        const lastDate = dates[dates.length - 1] || firstDate;

        setLoadedPlan(savedPlan);
        setTripTitle(savedPlan.title || "Manual Trip Plan");
        setStartDate(firstDate);
        setEndDate(lastDate);
        setIsSelectingEndDate(false);
        setActiveDate(firstDate);
        setPlaceSlotsByDate(stopsToSlotsByDate(stops, dates));
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(
            error instanceof Error ? error.message : "Failed to load saved plan."
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, [planId]);

  useEffect(() => {
    if (!tripDates.includes(activeDate) && tripDates.length > 0) {
      setActiveDate(tripDates[0]);
    }
  }, [activeDate, tripDates]);

  useEffect(() => {
    setPlaceSlotsByDate((current) => {
      const next = { ...current };
      tripDates.forEach((date) => {
        if (!next[date]) {
          next[date] = [null, null];
        }
      });
      Object.keys(next).forEach((date) => {
        if (!tripDates.includes(date)) {
          delete next[date];
        }
      });
      return next;
    });
  }, [tripDates]);

  const activePlaceSlots = useMemo(
    () => {
      const slots = placeSlotsByDate[activeDate] || [];
      return slots.length >= 2
        ? slots
        : ensurePlaceSlots(slots.filter((slot): slot is PlannedStop => Boolean(slot)));
    },
    [activeDate, placeSlotsByDate]
  );
  const tripStops = useMemo(
    () =>
      tripDates.flatMap((date) =>
        (placeSlotsByDate[date] || []).filter(
          (stop): stop is PlannedStop => Boolean(stop)
        )
      ),
    [placeSlotsByDate, tripDates]
  );
  const activeScheduledStops = useMemo(
    () =>
      activePlaceSlots
        .map((stop, slotIndex) => ({ stop, slotIndex }))
        .filter(
          (item): item is { stop: PlannedStop; slotIndex: number } =>
            Boolean(item.stop)
        ),
    [activePlaceSlots]
  );
  const showStepFiveHint = step === 5 && !hasSeenStepFiveHint;
  const canGoNext =
    step === 1
      ? tripTitle.trim().length > 0
      : step === 2
        ? tripDates.length > 0
        : step === 3
          ? tripDates.every(
              (date) =>
                (placeSlotsByDate[date] || []).filter(Boolean).length >= 2
            )
          : true;

  useEffect(() => {
    if (step !== 5 || hasSeenStepFiveHint) return undefined;

    const timer = window.setTimeout(() => {
      setHasSeenStepFiveHint(true);
    }, 3000);

    return () => window.clearTimeout(timer);
  }, [hasSeenStepFiveHint, step]);

  const handleSearch = () => {
    const nextQuery = query.trim();
    setSubmittedQuery(nextQuery);
    setErrorMessage("");

    if (!nextQuery) {
      setSearchResults([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    void fetchPlaces(nextQuery)
      .then((places) => {
        setSearchResults(places);
      })
      .catch((error) => {
        setSearchResults([]);
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to search places."
        );
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const handleDateSelect = (date: string) => {
    if (!isSelectingEndDate) {
      setStartDate(date);
      setEndDate(date);
      setActiveDate(date);
      setIsSelectingEndDate(true);
      return;
    }

    if (date < startDate) {
      setStartDate(date);
      setEndDate(startDate);
      setActiveDate(date);
      setIsSelectingEndDate(false);
      return;
    }

    setEndDate(date);
    setIsSelectingEndDate(false);
  };

  const goBack = () => {
    if (isComplete) {
      onBack?.();
      return;
    }

    if (step > 1) {
      if (step === 5) {
        setHasSeenStepFiveHint(true);
      }
      setStep((current) => (current - 1) as ManualStep);
      return;
    }

    onBack?.();
  };

  const goNext = () => {
    if (!canGoNext || step >= 5) return;
    setStep((current) => (current + 1) as ManualStep);
  };

  const addMiddlePlaceSlot = () => {
    setPlaceSlotsByDate((current) => {
      const slots = current[activeDate] || activePlaceSlots;
      const insertIndex = Math.max(1, slots.length - 1);
      const next = [...slots.slice(0, insertIndex), null, ...slots.slice(insertIndex)];
      setSelectedPlaceSlotIndex(insertIndex);
      return { ...current, [activeDate]: next };
    });
  };

  const openPlaceSearch = (slotIndex: number) => {
    const slot = activePlaceSlots[slotIndex];
    setSelectedPlaceSlotIndex(slotIndex);
    setQuery(slot?.name || "");
    setSubmittedQuery("");
    setSearchResults([]);
    setErrorMessage("");
    setShowPlaceSearch(true);
  };

  const getNextVisitTime = (targetDate: string) => {
    const sameDayStops = tripStops
      .filter((stop) => stop.visitDate === targetDate)
      .sort((left, right) => left.visitTime.localeCompare(right.visitTime));

    const lastStop = sameDayStops[sameDayStops.length - 1];
    if (!lastStop) return "10:00";

    const [hours, minutes] = lastStop.visitTime.split(":").map(Number);
    const totalMinutes = hours * 60 + minutes + 60;
    const nextHours = Math.floor(totalMinutes / 60)
      .toString()
      .padStart(2, "0");
    const nextMinutes = (totalMinutes % 60).toString().padStart(2, "0");
    return `${nextHours}:${nextMinutes}`;
  };

  const addPlaceToPlan = (place: TourPlace) => {
    const targetDate = activeDate || startDate;
    setPlaceSlotsByDate((current) => {
      const slots = [...(current[targetDate] || activePlaceSlots)];
      const fallbackIndex = slots.findIndex((slot) => !slot);
      const targetIndex =
        selectedPlaceSlotIndex >= 0 && selectedPlaceSlotIndex < slots.length
          ? selectedPlaceSlotIndex
          : fallbackIndex >= 0
            ? fallbackIndex
            : Math.max(1, slots.length - 1);

      if (targetIndex >= slots.length) {
        slots.push(null);
      }

      const currentStop = slots[targetIndex];
      slots[targetIndex] = {
        ...place,
        plannedId: currentStop?.plannedId || createPlanId("manual"),
        visitDate: targetDate,
        visitTime: currentStop?.visitTime || getNextVisitTime(targetDate),
        backendItemId: currentStop?.backendItemId,
        backendDayNumber: currentStop?.backendDayNumber,
      };

      setShowPlaceSearch(false);
      return {
        ...current,
        [targetDate]: ensurePlaceSlots(
          slots.filter((slot): slot is PlannedStop => Boolean(slot))
        ),
      };
    });
  };

  const updateStop = (plannedId: string, patch: Partial<PlannedStop>) => {
    setPlaceSlotsByDate((current) => {
      const updatedStops = tripDates.flatMap((date) =>
        (current[date] || [])
          .map((stop) =>
            stop?.plannedId === plannedId
              ? {
                  ...stop,
                  ...patch,
                  backendDayNumber:
                    patch.visitDate && patch.visitDate !== stop.visitDate
                      ? undefined
                      : stop.backendDayNumber,
                }
              : stop
          )
          .filter((stop): stop is PlannedStop => Boolean(stop))
      );
      return stopsToSlotsByDate(updatedStops, tripDates);
    });
  };

  const removeStop = (plannedId: string) => {
    setPlaceSlotsByDate((current) => {
      const next = { ...current };
      Object.entries(current).forEach(([date, slots]) => {
        const targetIndex = slots.findIndex((stop) => stop?.plannedId === plannedId);
        if (targetIndex < 0) return;
        const stopCount = slots.filter(Boolean).length;
        if (stopCount <= 2) return;

        next[date] = ensurePlaceSlots(
          slots.filter((stop) => stop?.plannedId !== plannedId).filter(
            (stop): stop is PlannedStop => Boolean(stop)
          )
        );
      });
      return next;
    });
  };

  const removeMiddlePlaceSlot = (slotIndex: number) => {
    setPlaceSlotsByDate((current) => {
      const slots = current[activeDate] || activePlaceSlots;
      if (slotIndex <= 0 || slotIndex >= slots.length - 1) return current;

      const nextSlots = [
        ...slots.slice(0, slotIndex),
        ...slots.slice(slotIndex + 1),
      ];

      while (nextSlots.length < 2) {
        nextSlots.push(null);
      }

      return { ...current, [activeDate]: nextSlots };
    });
  };

  const reorderStop = (sourceId: string, targetId: string) => {
    if (sourceId === targetId) return;
    const slots = placeSlotsByDate[activeDate] || [];
    const sourceIndex = slots.findIndex((stop) => stop?.plannedId === sourceId);
    const targetIndex = slots.findIndex((stop) => stop?.plannedId === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;

    const nextSlots = [...slots];
    const [sourceStop] = nextSlots.splice(sourceIndex, 1);
    nextSlots.splice(targetIndex, 0, sourceStop);
    setPlaceSlotsByDate((current) => ({ ...current, [activeDate]: nextSlots }));
  };

  const handleSave = () => {
    const dayNumberByDate = getDayNumberByDate(tripDates);
    const items = plannedStopsToCreateItems(tripStops, dayNumberByDate);
    if (items.length === 0) {
      setSaveMessage("Add at least one place before saving.");
      return;
    }

    const title = buildPlanTitle("manual", tripTitle);
    if (loadedPlan) {
      void updateExistingBackendPlan(loadedPlan, title, tripStops, tripDates)
        .then(({ saved, dayNumberByDate }) => {
          saveManualPlanDateMetadata(saved.plan_id, dayNumberByDate);
          setLoadedPlan(saved);
          setPlaceSlotsByDate((current) =>
            Object.fromEntries(
              tripDates.map((date) => [
                date,
                applySavedStopsToSlots(
                  current[date] || [null, null],
                  saved,
                  dayNumberByDate
                ),
              ])
            )
          );
          setSaveMessage(`Saved to My Page (${saved.title || "Untitled plan"})`);
          setIsComplete(true);
        })
        .catch((error) => {
          setSaveMessage(
            error instanceof Error ? error.message : "Failed to save plan."
          );
        });
    } else {
      void createTourPlan({
        title,
        travel_days: Math.max(1, tripDates.length),
        items,
      })
        .then((saved) => {
          const actualDayNumbers = Array.from(
            new Set(saved.items.map((item) => item.day_number))
          ).sort((a, b) => a - b);

          const correctedMap = new Map(
            tripDates.map((date, index) => [
              date,
              actualDayNumbers[index] ?? index + 1,
            ])
          );

          saveManualPlanDateMetadata(saved.plan_id, correctedMap);
          setLoadedPlan(saved);
          setPlaceSlotsByDate((current) =>
            Object.fromEntries(
              tripDates.map((date) => [
                date,
                applySavedStopsToSlots(
                  current[date] || [null, null],
                  saved,
                  correctedMap
                ),
              ])
            )
          );
          setSaveMessage(`Saved to My Page (${saved.title || "Untitled plan"})`);
          setIsComplete(true);
        })
        .catch((error) => {
          setSaveMessage(
            error instanceof Error ? error.message : "Failed to save plan."
          );
        });
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.phoneFrame}>
        <div style={styles.topBar}>
          <button type="button" onClick={goBack} style={styles.iconButton}>
            <img src="/icon-back.svg" alt="Back" style={styles.backIcon} />
          </button>
          <h1 style={styles.headerLogo}>
            Manual Plan
          </h1>
          {!isComplete ? (
            <button type="button" onClick={() => setShowShare(true)} style={styles.shareButton}>
              <img src="/UserAddIcon.svg" alt="UserAdd" style={styles.userAddButton}></img>
            </button>
          ) : (
            <span style={styles.headerSpacer} />
          )}
        </div>

        {!isComplete ? <StepProgress step={step} /> : null}

        {isComplete ? (
          <section style={{ ...styles.card, ...styles.completeCard }}>
            <img src="/map_success.svg" alt="" style={styles.completeImage} />
            <h1 style={styles.sectionTitleEnd}>All set!</h1>
            <p style={styles.sectionCopy}>
              {saveMessage || `Saved to My Page (${buildPlanTitle("manual", tripTitle)})`}
            </p>
          </section>
        ) : null}

        {isComplete ? (
          <div style={styles.actionBar}>
            <button type="button" onClick={onMyPage} style={styles.primaryAction}>
              Check My Page
            </button>
          </div>
        ) : null}

        {!isComplete && step === 1 ? (
          <section style={styles.card}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h1 style={styles.sectionTitle}>What’s your trip’s name?</h1>
              </div>
            </div>
            <label style={styles.fieldLabel}>
              Trip Title
              <input
                value={tripTitle}
                onChange={(event) => setTripTitle(event.target.value)}
                style={styles.planInput}
                placeholder="Manual Trip Plan"
              />
            </label>
          </section>
        ) : null}

        {!isComplete && step === 2 ? (
          <section style={styles.card}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h1 style={styles.sectionTitle}>When is your trip?</h1>
              </div>
              <span style={styles.dayCount}>
                {tripDates.length} day{tripDates.length > 1 ? "s" : ""}
              </span>
            </div>
            <DateRangeCalendar
              startDate={startDate}
              endDate={endDate}
              onSelectDate={handleDateSelect}
            />
          </section>
        ) : null}

        {!isComplete && step === 3 ? (
          <section style={{ ...styles.card, ...styles.placeEntryCard }}>
            <h2 style={styles.sectionTitle}>Where would you like to go?</h2>

            <div style={styles.dayTabs}>
              {tripDates.map((date, index) => {
                const stopCount = (placeSlotsByDate[date] || []).filter(Boolean).length;
                return (
                  <button
                    key={date}
                    type="button"
                    onClick={() => setActiveDate(date)}
                    style={{
                      ...styles.dayTab,
                      ...(date === activeDate ? styles.dayTabActive : {}),
                    }}
                  >
                    <span style={styles.dayTabLabel}>Day {index + 1}</span>
                    <span style={styles.dayTabDate}>
                      {formatDateLabel(date)} · {stopCount}/2
                    </span>
                  </button>
                );
              })}
            </div>

            <div style={styles.placeEntryList}>
              {activePlaceSlots.map((slot, index) => {
                const hasMiddleStops = activePlaceSlots.length > 2;
                const isMiddleStop = index > 0 && index < activePlaceSlots.length - 1;
                const label =
                  index === 0
                    ? "Enter starting point"
                    : index === activePlaceSlots.length - 1
                      ? "Enter Destination"
                      : `Enter stop ${index}`;
                const dotStyle =
                  index === 0
                    ? styles.placeEntryDotStart
                    : index === activePlaceSlots.length - 1
                      ? styles.placeEntryDotEnd
                      : styles.placeEntryDotMiddle;

                return (
                  <div key={`slot-${index}-${slot?.plannedId || "empty"}`}>
                    <div style={styles.placeEntryRow}>
                      <span style={styles.placeEntryDotWrap}>
                        <span style={{ ...styles.placeEntryDotHalo, ...dotStyle }} />
                        <span style={{ ...styles.placeEntryDot, ...dotStyle }} />
                      </span>
                      <div style={styles.placeEntryInputShell}>
                        <button
                          type="button"
                          onClick={() => openPlaceSearch(index)}
                          style={styles.placeEntryInput}
                        >
                          {slot?.name || label}
                        </button>
                        {isMiddleStop ? (
                          <div style={styles.placeEntryInlineActions}>
                            <button
                              type="button"
                              onClick={addMiddlePlaceSlot}
                              style={styles.placeEntryCircleButton}
                              aria-label="Add stop"
                            >
                              +
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                slot
                                  ? removeStop(slot.plannedId)
                                  : removeMiddlePlaceSlot(index)
                              }
                              style={styles.placeEntryCircleButton}
                              aria-label={slot ? `Delete ${slot.name}` : "Delete stop"}
                            >
                              -
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                    {!hasMiddleStops && index === 0 ? (
                      <div style={styles.placeEntryConnector}>
                        <button
                          type="button"
                          onClick={addMiddlePlaceSlot}
                          style={styles.placeEntryAddButton}
                          aria-label="Add stop"
                        >
                          +
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>
        ) : null}

        {!isComplete && step === 4 ? (
          <section style={styles.card}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h2 style={styles.sectionTitle}>Route preview</h2>
              </div>
              <span style={styles.dayCount}>
                {tripStops.length} stop{tripStops.length > 1 ? "s" : ""}
              </span>
            </div>
            <MapPreview stops={tripStops} />
          </section>
        ) : null}

        {!isComplete && step === 5 ? (
          <section style={styles.card}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h2 style={styles.sectionTitle}>Change your schedule</h2>
              </div>
              <span style={styles.dayCount}>
                {tripStops.length} stop{tripStops.length > 1 ? "s" : ""}
              </span>
            </div>

            <div style={styles.dayTabs}>
              {tripDates.map((date, index) => {
                const stopCount = (placeSlotsByDate[date] || []).filter(Boolean).length;
                return (
                  <button
                    key={date}
                    type="button"
                    onClick={() => setActiveDate(date)}
                    style={{
                      ...styles.dayTab,
                      ...(date === activeDate ? styles.dayTabActive : {}),
                    }}
                  >
                    <span style={styles.dayTabLabel}>Day {index + 1}</span>
                    <span style={styles.dayTabDate}>
                      {formatDateLabel(date)} · {stopCount}
                    </span>
                  </button>
                );
              })}
            </div>

            {activeScheduledStops.length === 0 ? (
              <div style={styles.emptyState}>No stops added yet.</div>
            ) : (
              <div style={styles.timelineList}>
                {activeScheduledStops.map(({ stop, slotIndex }, index) => {
                  const stopCountForDate = (
                    placeSlotsByDate[stop.visitDate] || []
                  ).filter(Boolean).length;
                  const canDeleteStop = stopCountForDate > 2;

                  return (
                    <article
                      key={stop.plannedId}
                      draggable
                      onDragStart={() => setDraggedStopId(stop.plannedId)}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() => {
                        if (draggedStopId) reorderStop(draggedStopId, stop.plannedId);
                        setDraggedStopId(null);
                      }}
                      onDragEnd={() => setDraggedStopId(null)}
                      style={{
                        ...styles.stopCard,
                        ...(draggedStopId === stop.plannedId ? styles.stopCardDragging : {}),
                      }}
                    >
                      <div style={styles.stopIndex}>{index + 1}</div>
                      <div style={styles.stopBody}>
                        {showStepFiveHint && index === 0 ? (
                          <div className="manual-step5-edit-hint" style={styles.stepFiveHint}>
                            Press and hold a card to move it around
                          </div>
                        ) : null}
                        <div style={styles.placeTopRow}>
                          <button
                            type="button"
                            onClick={() => openPlaceSearch(slotIndex)}
                            style={styles.placeNameButton}
                          >
                            {stop.name}
                          </button>
                          <div style={styles.stopActionRow}>
                            {typeof stop.rating === "number" ? (
                              <span style={styles.ratingBadge}>{stop.rating.toFixed(1)}</span>
                            ) : null}
                            <button
                              type="button"
                              onClick={() =>
                                setEditingStopId((current) =>
                                  current === stop.plannedId ? null : stop.plannedId
                                )
                              }
                              style={styles.editButton}
                            >
                              {editingStopId === stop.plannedId ? (
                                <img width="16" height="16" src="/CheckIcon.svg">
                                </img>
                              ) : (
                                <img width="16" height="16" src="/PostIcon.svg">
                                </img>
                              )}
                            </button>
                            <button
                              type="button"
                              onClick={() => removeStop(stop.plannedId)}
                              style={{
                                ...styles.deleteButton,
                                ...(!canDeleteStop ? styles.deleteButtonDisabled : {}),
                              }}
                              disabled={!canDeleteStop}
                            >
                                <img width="16" height="16" src="/icon-close.svg">
                                </img>
                            </button>
                          </div>
                        </div>
                        {stop.summary ? <p style={styles.placeSummary}>{stop.summary}</p> : null}
                        {stop.address ? <span style={styles.placeAddress}>{stop.address}</span> : null}
                        {editingStopId === stop.plannedId ? (
                          <div style={styles.stopEditors}>
                            <label style={styles.fieldLabel}>
                              Day
                              <select
                                value={stop.visitDate}
                                onChange={(event) =>
                                  updateStop(stop.plannedId, { visitDate: event.target.value })
                                }
                                style={styles.dayinput}
                              >
                                {tripDates.map((date) => (
                                  <option key={date} value={date}>
                                    {formatDateLabel(date)}
                                  </option>
                                ))}
                              </select>
                            </label>

                            <label style={styles.fieldLabel}>
                              Time
                              <input
                                type="time"
                                value={stop.visitTime}
                                onChange={(event) =>
                                  updateStop(stop.plannedId, { visitTime: event.target.value })
                                }
                                style={styles.dayinput}
                              />
                            </label>
                          </div>
                        ) : (
                          <div style={styles.stopMetaRow}>
                            <span>Day {tripDates.indexOf(stop.visitDate) + 1}</span>
                            <span>{formatDateLabel(stop.visitDate)}</span>
                            <span>{stop.visitTime}</span>
                          </div>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        ) : null}

        {!isComplete && saveMessage ? <p style={styles.saveMessage}>{saveMessage}</p> : null}
      </div>

      {!isComplete && step === 2 ? (
        <div style={styles.stepTwoBottomTabs}>
          <div style={styles.dayTabs}>
            {tripDates.map((date, index) => (
              <button
                key={date}
                type="button"
                className="manual-step2-day-tab"
                onClick={() => setActiveDate(date)}
                style={{
                  ...styles.dayTab,
                  ...(date === activeDate ? styles.dayTabActive : {}),
                }}
              >
                <span style={styles.dayTabLabel}>Day {index + 1}</span>
                <span style={styles.dayTabDate}>{formatDateLabel(date)}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {!isComplete && step < 5 ? (
        <div style={styles.actionBar}>
          <button
            type="button"
            onClick={goNext}
            style={{
              ...styles.primaryAction,
              ...(!canGoNext ? styles.primaryActionDisabled : {}),
            }}
            disabled={!canGoNext}
          >
            Next
          </button>
        </div>
      ) : null}

      {!isComplete && step === 5 ? (
        <div style={styles.actionBar}>
          <button
            type="button"
            onClick={handleSave}
            style={{
              ...styles.primaryAction,
              ...(tripStops.length < 2 ? styles.primaryActionDisabled : {}),
            }}
            disabled={tripStops.length < 2}
          >
            Save
          </button>
        </div>
      ) : null}

      {showPlaceSearch ? (
        <div style={styles.overlay}>
          <button
            type="button"
            onClick={() => setShowPlaceSearch(false)}
            style={styles.overlayBackdrop}
            aria-label="Close place search"
          />
          <div style={styles.searchSheet}>
            <div style={styles.sheetHandle} />
            <h2 style={styles.sheetTitle}>Search place</h2>
            <label style={styles.searchWrap}>
              <div style={styles.searchRow}>
                <input
                  value={query}
                  autoFocus
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      handleSearch();
                    }
                  }}
                  style={styles.input}
                  placeholder="Examples: Bukchon, cafe, Myeongdong"
                />
                <button
                  type="button"
                  onClick={handleSearch}
                  style={styles.searchButton}
                  disabled={isLoading}
                >
                  <img src="/SearchIcon.svg" alt="search" style={styles.searchIcon}></img>
                </button>
              </div>
            </label>

            <div style={styles.resultsList}>
              {!submittedQuery ? (
                <div style={styles.emptyState}>Enter a keyword and press Search.</div>
              ) : isLoading ? (
                <div style={styles.emptyState}>Loading places...</div>
              ) : errorMessage ? (
                <div style={styles.emptyState}>{errorMessage}</div>
              ) : searchResults.length === 0 ? (
                <div style={styles.emptyState}>No places found for this keyword.</div>
              ) : (
                searchResults.map((place) => (
                  <article key={place.id} style={styles.placeCard}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={styles.placeBadgeRow}>
                          {typeof place.rating === "number" ? (
                            <span style={styles.ratingBadge}>{place.rating.toFixed(1)}</span>
                          ) : null}
                          <span style={styles.placeCategory}>{place.category}</span>
                      </div>
                      <div style={styles.placeTopRow}>
                        <strong style={styles.placeName}>{place.name}</strong>
                      </div>
                      {place.summary ? <p style={styles.placeSummary}>{place.summary}</p> : null}
                      {place.address ? <span style={styles.placeAddress}>{place.address}</span> : null}
                    </div>
                    <div style={styles.addButtonRow}>   
                      <button type="button" onClick={() => addPlaceToPlan(place)} style={styles.addButton}>
                        Add
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
      {showShare ? <ShareSheet onClose={() => setShowShare(false)} /> : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "calc(var(--app-viewport-height) - var(--app-bottom-nav-reserved))",
    padding: "calc(20px + var(--app-safe-top)) 16px 20px",
    boxSizing: "border-box",
    background: "#fff",
    fontFamily: '"Pretendard Variable", sans-serif',
  },
  phoneFrame: {
    maxWidth: 430,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: "1.5rem",
    paddingBottom: 16,
  },
  actionBar: {
    position: "fixed",
    left: "50%",
    bottom: "calc(var(--app-bottom-nav-reserved) + 2rem)",
    width: "calc(100% - 32px)",
    maxWidth: 430,
    transform: "translateX(-50%)",
    zIndex: 14,
  },
  topBar: {
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
    border: "transparent",
    background: "transparent",
    padding: 0,
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
  headerSpacer: {
    width: 72,
    height: 42,
    display: "block",
  },
  shareButton: {
    width: 42,
    height: 42,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: "transparent",
    background: "transparent",
    padding: 0,
    cursor: "pointer",
  },
  userAddButton: {
    width: "24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    color: "#102223",
    fontSize: "1rem",
  },
  stepProgress: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    paddingLeft: 2,
  },
  stepDot: {
    margin: "1rem 0 0",
    width: "0.5rem",
    height: "0.5rem",
    borderRadius: "50%",
    background: "#eaeaea",
    transition: "background 180ms ease, transform 180ms ease",
  },
  stepDotActive: {
    background: BRAND,
    transform: "scale(1.5)",
  },
  card: {
    borderRadius: 24,
    background: "transparent",
    border: "transparent",
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  sectionHeaderRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  sectionTitle: {
    margin: "0 0 2.5rem",
    color: "#212121",
    fontSize: 20,
  },
  dayCount: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "var(--brand-secondary-soft)",
    color: "#64370d",
    fontSize: 12,
    fontWeight: 600,
  },
  twoColumn: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
  },
  fieldLabel: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    fontSize: 12,
    fontWeight: 800,
    color: "#6b6b6b",
  },
  planInput: {
    width: "100%",
    minHeight: 46,
    borderRadius: "3rem",
    border: "transparent",
    color: "#222",
    padding: "0.5rem 1.2rem",
    fontSize: "0.8rem",
    boxSizing: "border-box",
    fontWeight: 400,
    outline: "none",
    background: "#f5f5f5",
  },
  input: {
    width: "100%",
    minHeight: 46,
    borderRadius: "3rem",
    border: "transparent",
    background: "transparent",
    color: "#222",
    padding: "0.5rem 1.2rem",
    fontSize: "0.8rem",
    boxSizing: "border-box",
    fontWeight: 400,
    outline: "none",
  },
  dayTabs: {
    display: "flex",
    gap: 8,
    overflowX: "auto",
    paddingBottom: 2,
    scrollbarWidth: "none",
    msOverflowStyle: "none",
  },
  dayTab: {
    margin: "0.1rem 0",
    minWidth: 82,
    border: "none",
    borderRadius: 999,
    background: "#f4f4f4",
    padding: "9px 14px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 2,
    cursor: "pointer",
    flexShrink: 0,
  },
  dayTabActive: {
    border: `1px solid ${BRAND}`,
    background: "rgba(1,192,192,0.12)",
  },
  dayTabLabel: {
    color: "#204444",
    fontSize: 12,
    fontWeight: 800,
  },
  dayTabDate: {
    color: BRAND,
    fontSize: 11,
    fontWeight: 700,
  },
  stepTwoCard: {
    gap: 14,
    paddingBottom: 0,
  },
  calendarScroller: {
    maxHeight: 430,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 18,
    paddingRight: 4,
  },
  monthBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  monthTitle: {
    margin: "0 0 4px",
    color: "#202020",
    fontSize: 17,
    textAlign: "center",
  },
  weekdayGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
  },
  weekdayLabel: {
    textAlign: "center",
    color: "#8a8a8a",
    fontSize: 11,
    fontWeight: 500,
  },
  calendarGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
    columnGap: 0,
    rowGap: 6,
  },
  calendarEmptyDay: {
    height: 32,
  },
  calendarDay: {
    height: 36,
    border: "none",
    background: "transparent",
    color: "#204444",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
  },
  calendarDayToday: {
    background: "#ffffff",
    borderRadius: 999,
    color: "#204444",
  },
  calendarDayInRange: {
    background: "#58c9d4",
    color: "#ffffff",
    border: "none",
  },
  calendarDaySelected: {
    background: "#58c9d4",
    color: "#ffffff",
    border: "none",
  },
  calendarDayRangeStart: {
    borderTopLeftRadius: 999,
    borderBottomLeftRadius: 999,
  },

  calendarDayRangeEnd: {
    borderTopRightRadius: 999,
    borderBottomRightRadius: 999,
  },

  calendarDaySingleSelected: {
    borderRadius: 999,
  },
  stepTwoBottomTabs: {
    position: "fixed",
    left: "50%",
    bottom: "calc(var(--app-bottom-nav-reserved) + 2rem + 56px + 10px)",
    width: "calc(100% - 32px)",
    maxWidth: 430,
    transform: "translateX(-50%)",
    zIndex: 14,
    background: "#ffffff",
    padding: "8px 0",
  },
  mapBox: {
    marginTop: "-1rem",
    borderRadius: 20,
    border: "none",
    display: "flex",
    flexDirection: "column",
    gap: 28,
  },
  mapViewport: {
    position: "relative",
    minHeight: 220,
    borderRadius: 16,
    overflow: "hidden",
    background: "#eef7f7",
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
    color: "#577071",
    padding: "0 20px",
    lineHeight: 1.6,
    background: "#eef7f7",
    zIndex: 1,
  },
  mapLegendInline: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  mapLegendChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    marginBottom: "0.4rem",
  },
  mapLegendIndex: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    background: "#58c9d4",
    color: "#fff",
    display: "grid",
    placeItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 800,
    flexShrink: 0,
  },
  mapLegendLabel: {
    color: "#222",
    fontSize: 12,
    fontWeight: 500,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  searchWrap: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  searchRow: {
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 10,
    alignItems: "center",
    background: "var(--surface-muted)",
    borderRadius: "3rem",
  },
  searchButton: {
    minWidth: 46,
    minHeight: 46,
    border: "none",
    background: "transparent",
    borderRadius: 14,
    padding: "0 14px",
    fontSize: 13,
    fontWeight: 900,
    cursor: "pointer",
  },
  searchIcon: {
    width: 18,
    alignItems: "center",
    justifyItems: "center",
  },
  placeEntryCard: {
    minHeight: 360,
    borderRadius: 0,
    border: "none",
    boxShadow: "none",
    background: "#ffffff",
  },
  placeEntryTitle: {
    margin: "0 0 12px",
    color: "#171d23",
    fontSize: 21,
    lineHeight: 1.25,
    fontWeight: 900,
  },
  placeEntryList: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    paddingTop: 8,
  },
  placeEntryRow: {
    width: "100%",
    display: "grid",
    gridTemplateColumns: "18px 1fr",
    alignItems: "center",
    gap: 10,
  },
  placeEntryDotWrap: {
    margin: "0 0 0 0.5rem",
    width: 18,
    height: 18,
    position: "relative",
    display: "grid",
    placeItems: "center",
    justifySelf: "center",
  },
  placeEntryDot: {
    width: "0.4rem",
    height: "0.4rem",
    borderRadius: "50%",
    position: "relative",
    zIndex: 1,
  },
  placeEntryDotHalo: {
    width: "1rem",
    height: "1rem",
    borderRadius: "50%",
    opacity: 0.3,
    position: "absolute",
    left: "50%",
    top: "50%",
    transform: "translate(-50%, -50%)",
  },
  placeEntryDotStart: {
    background: BRAND,
  },
  placeEntryDotMiddle: {
    background: "#aaa",
  },
  placeEntryDotEnd: {
    background: ACCENT,
  },
  placeEntryInputShell: {
    minHeight: 50,
    border: "none",
    borderRadius: 999,
    background: "#f6f6f6",
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto",
    alignItems: "center",
    gap: 8,
    padding: "0 1.2rem",
    margin: "0.4rem 0",
  },
  placeEntryInput: {
    minWidth: 0,
    minHeight: 50,
    border: "none",
    background: "transparent",
    color: "#8a9297",
    padding: 0,
    textAlign: "left",
    fontSize: 13,
    fontWeight: 400,
    cursor: "pointer",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  placeEntryInlineActions: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  placeEntryCircleButton: {
    width: 26,
    height: 26,
    border: "none",
    borderRadius: "50%",
    background: "#ffffff",
    color: "#7b8588",
    display: "grid",
    placeItems: "center",
    padding: 0,
    fontSize: 17,
    lineHeight: 1,
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: "0 1px 5px rgba(16, 34, 35, 0.08)",
  },
  placeEntryConnector: {
    display: "grid",
    gridTemplateColumns: "18px 1fr",
    alignItems: "center",
    gap: 10,
    minHeight: 34,
  },
  placeEntryAddButton: {
    justifySelf: "left",
    width: 26,
    height: 26,
    borderRadius: "50%",
    border: "1px solid #eaeaea",
    background: "#fff",
    color: "#aaa",
    display: "grid",
    placeItems: "center",
    padding: 0,
    fontSize: 17,
    lineHeight: 1,
    fontWeight: 900,
    cursor: "pointer",
  },
  resultsList: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    overflowY: "auto",
    flex: 1,
    paddingBottom: 8,
  },
  placeCard: {
    padding: 14,
    borderRadius: 18,
    border: "0.8px solid #eaeaea",
    background: "#fafafa",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    alignItems: "stretch",
  },
  placeTopRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  placeName: {
    marginTop: 4,
    color: "#222",
    fontSize: "0.85rem",
    lineHeight: "1.1rem"
  },
  placeNameButton: {
    minWidth: 0,
    border: "none",
    background: "transparent",
    color: "#222",
    padding: 0,
    textAlign: "left",
    fontSize: "0.9rem",
    lineHeight: "1.2rem",
    fontWeight: 800,
    cursor: "pointer",
  },
  placeCategory: {
    padding: "6px 10px",
    borderRadius: 999,
    background: "#e1eef0",
    color: BRAND,
    fontSize: 10,
    fontWeight: 700,
  },
  placeBadgeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-start",
    gap: 6,
    flexWrap: "wrap",
  },
  ratingBadge: {
    padding: "6px 9px",
    borderRadius: 999,
    background: "#f8edd0",
    color: "#7a4900",
    fontSize: 10,
    fontWeight: 800,
  },
  placeSummary: {
    margin: 0,
    color: "#444444",
    lineHeight: "1rem",
    fontSize: "0.75rem",
  },
  placeAddress: {
    color: "#848484",
    fontSize: "0.7rem",
    fontWeight: 400,
  },
  addButtonRow: {
    width: "100%",
    display: "flex",
    justifyContent: "flex-end",
  },
  addButton: {
    minWidth: 48,
    minHeight: 36,
    border: "none",
    borderRadius: 12,
    background: BRAND,
    color: "#ffffff",
    fontSize: 12,
    fontWeight: 800,
    cursor: "pointer",
  },
  emptyState: {
    padding: "24px 16px",
    borderRadius: 18,
    background: "transparent",
    color: "#888888",
    textAlign: "center",
    fontSize: 14,
  },
  timelineList: {
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  stopCard: {
    display: "grid",
    gridTemplateColumns: "34px 1fr",
    gap: 12,
    alignItems: "start",
  },
  stopCardDragging: {
    opacity: 0.58,
  },
  stopIndex: {
    width: 28,
    height: 28,
    borderRadius: 999,
    background: BRAND,
    color: "#ffffff",
    display: "grid",
    placeItems: "center",
    fontSize: 13,
    fontWeight: 900,
  },
  stopBody: {
    position: "relative",
    padding: 14,
    borderRadius: 18,
    border: "1px solid #eaeaea",
    background: "#fff",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  stopEditors: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 10,
  },
  stopActionRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  editButton: {
    border: "none",
    background: "transparent",
    color: "#848484",
    fontSize: 12,
    fontWeight: 800,
    cursor: "pointer",
  },
  deleteButton: {
    border: "none",
    background: "transparent",
    color: "#848484",
    fontSize: 12,
    fontWeight: 800,
    cursor: "pointer",
  },
  deleteButtonDisabled: {
    opacity: 0.35,
    cursor: "not-allowed",
  },
  stepFiveHint: {
    position: "absolute",
    left: 0,
    top: -38,
    padding: "8px 16px",
    borderRadius: "16px 16px 16px 4px",
    background: BRAND,
    color: "#ffffff",
    fontSize: 12,
    fontWeight: 400,
    boxShadow: "0 8px 18px rgba(1, 192, 192, 0.2)",
    pointerEvents: "none",
    zIndex: 2,
  },
  stopMetaRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    color: "#666",
    fontSize: 12,
    fontWeight: 700,
  },
  dayinput: {
    border: "none",
    background: "#fff",
    fontWeight: 500,
    color: "#222",
  },
  primaryAction: {
    position: "sticky",
    bottom: "calc(var(--app-bottom-nav-reserved) + 12px)",
    zIndex: 12,
    width: "100%",
    minHeight: 56,
    border: "none",
    borderRadius: "3rem",
    background: "#58c9d4",
    color: "#ffffff",
    fontSize: "1rem",
    fontWeight: 800,
    cursor: "pointer",
  },
  primaryActionDisabled: {
    background: "#c9dddd",
    color: "#6a8182",
    boxShadow: "none",
    cursor: "not-allowed",
  },
  saveMessage: {
    margin: 0,
    textAlign: "center",
    color: BRAND,
    fontSize: 13,
    fontWeight: 800,
  },
  completeCard: {
    alignItems: "center",
    textAlign: "center",
    paddingTop: 180,
    paddingBottom: 32,
  },
  completeImage: {
    width: 118,
    height: 118,
    objectFit: "contain",
    display: "block",
  },
  overlay: {
    position: "fixed",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    justifyContent: "flex-end",
    zIndex: 30,
  },
  overlayBackdrop: {
    position: "fixed",
    inset: 0,
    flex: 1,
    border: "none",
    background: "rgba(16, 34, 35, 0.42)",
    cursor: "pointer",
    zIndex: 0,  
  },
  sheet: {
    zIndex: 1,
    padding: "18px 18px calc(28px + var(--app-safe-bottom))",
    borderRadius: "20px 20px 0 0",
    background: "#fff",
    boxShadow: "0 -16px 36px rgba(16, 34, 35, 0.12)",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    overflow: "hidden",
  },
  searchSheet: {
    position: "relative",
    zIndex: 1,
    maxHeight: "82vh",
    padding: "18px 18px calc(28px + var(--app-safe-bottom))",
    borderRadius: "20px 20px 0 0",
    background: "#ffffff",
    boxShadow: "0 -16px 36px rgba(16, 34, 35, 0.12)",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  sheetHandle: {
    width: 56,
    height: 6,
    borderRadius: 999,
    background: "#eaeaea",
    alignSelf: "center",
  },
  sheetTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: 16,
  },
  sheetCopy: {
    margin: 0,
    color: "#577071",
    lineHeight: 1.6,
    fontSize: 14,
  },
  shareGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 10,
  },
  shareCard: {
    border: "none",
    borderRadius: 18,
    padding: "18px 14px",
    textAlign: "left",
    display: "flex",
    flexDirection: "column",
    gap: 6,
    cursor: "pointer",
  },
  shareTitle: {
    color: "#102223",
    fontSize: 14,
  },
  shareSubtitle: {
    color: "#577071",
    fontSize: 12,
  },
  sectionTitleEnd: {
    margin: "0 0 4px",
    color: "#212121",
    fontSize: 20,
  },
  sectionCopy: {
    margin: "0 0 1rem",
    color: "#577071",
    fontSize: 14,
    lineHeight: 1.6,
    textAlign: "center",
  },
};
