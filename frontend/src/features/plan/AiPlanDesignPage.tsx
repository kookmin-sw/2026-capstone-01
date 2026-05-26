import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { getTourPlaces, type TourPlaceApiItem } from "../../api/auth/auth";
import {
  BRAND,
  BUDGET_SLIDER_MAX,
  BUDGET_SLIDER_MIN,
  BUDGET_SLIDER_STEP,
  budgetCategoryFromValue,
  budgetCategoryIcon,
  budgetCategoryLabel,
  companionOptions,
  durationOptions,
  foodNeeds,
  formatBudgetValue,
  getAiPlanDayInputs,
  seoulClusterKeys,
  styleTokens,
  type AiPlanDayInput,
  type AiPreferenceState,
} from "../../api/aiPlanShared";

interface AiPlanDesignPageProps {
  value: AiPreferenceState;
  onBack: () => void;
  onChange: (next: AiPreferenceState) => void;
  onSubmit: () => void;
  isGenerating: boolean;
}

type AiStep = 1 | 2 | 3 | 4 | 5;
type AiPreferenceStateV2 = AiPreferenceState & {
  days?: AiPlanDayInput[];
  additionalPlaceId?: string | null;
  additionalPlaceName?: string;
};

interface ExtraPlaceOption {
  placeId: string;
  name: string;
  address: string;
  category: string;
}

const TOTAL_STEPS = 5;
const BUDGET_EXCHANGE_FALLBACK = 1350;
const MERIDIEM_OPTIONS = ["AM", "PM"] as const;
const HOUR_OPTIONS = Array.from({ length: 12 }, (_, index) => index + 1);
const MINUTE_OPTIONS = ["00", "10", "20", "30", "40", "50"];
const paceOptions = [
  { value: "Slow", label: "Relaxed" },
  { value: "Packed", label: "Packed" },
] as const;

function toPlanValue(value: AiPreferenceState): AiPreferenceStateV2 {
  return value as AiPreferenceStateV2;
}

function getDayInputs(value: AiPreferenceStateV2): AiPlanDayInput[] {
  return getAiPlanDayInputs(value);
}

function normalizePlace(item: TourPlaceApiItem): ExtraPlaceOption | null {
  const placeId = String(item.place_id || item.id || "");
  const name = String(item.display_name || item.name || item.title || "");
  if (!placeId || !name) return null;

  return {
    placeId,
    name,
    address: String(item.short_address || item.address || ""),
    category: String(item.category || item.type || item.place_type || "Place"),
  };
}

function StepDots({ step }: { step: AiStep }) {
  return (
    <div style={styles.stepDots}>
      {Array.from({ length: TOTAL_STEPS }, (_, index) => {
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

function QuestionTitle({ children }: { children: string }) {
  return <h1 style={styles.questionTitle}>{children}</h1>;
}

function SectionLabel({ children, accent = BRAND }: { children: string; accent?: string }) {
  return (
    <span style={{ ...styles.sectionLabel, color: accent }}>
      {children}
    </span>
  );
}

function ChipButton({
  active,
  label,
  onClick,
  accent = BRAND,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  accent?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        ...styles.chip,

        border: active
          ? `1px solid ${accent}`
          : "1px solid #eaeaea",

        background: active ? `${accent}1f` : "#fafafa",

        color: active ? accent : "#555",
      }}
    >
      {label}
    </button>
  );
}

function formatUsd(krwValue: number, krwPerUsd: number | null): string {
  if (!krwPerUsd || krwPerUsd <= 0) return "";
  return `$${(krwValue / krwPerUsd).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function parseTimeParts(value: string): {
  meridiem: "AM" | "PM";
  hour: number;
  minute: string;
} {
  const [rawHour, rawMinute] = value.split(":").map(Number);
  const hour24 = Number.isFinite(rawHour) ? rawHour : 10;
  const minute = Number.isFinite(rawMinute) ? rawMinute : 0;
  const meridiem = hour24 >= 12 ? "PM" : "AM";
  const hour = hour24 % 12 || 12;

  return {
    meridiem,
    hour,
    minute: String(Math.round(minute / 10) * 10).padStart(2, "0"),
  };
}

function composeTime(
  baseValue: string,
  patch: Partial<{ meridiem: "AM" | "PM"; hour: number; minute: string }>
): string {
  const current = parseTimeParts(baseValue);
  const meridiem = patch.meridiem || current.meridiem;
  const hour = patch.hour || current.hour;
  const minute = patch.minute || current.minute;
  const hour24 =
    meridiem === "AM"
      ? hour === 12
        ? 0
        : hour
      : hour === 12
        ? 12
        : hour + 12;

  return `${String(hour24).padStart(2, "0")}:${minute}`;
}

export default function AiPlanDesignPage({
  value,
  onBack,
  onChange,
  onSubmit,
  isGenerating,
}: AiPlanDesignPageProps) {
  const [step, setStep] = useState<AiStep>(1);
  const [extraResults, setExtraResults] = useState<ExtraPlaceOption[]>([]);
  const [isSearchingExtra, setIsSearchingExtra] = useState(false);
  const [extraSearchMessage, setExtraSearchMessage] = useState("");
  const [extraPlaceDayIndex, setExtraPlaceDayIndex] = useState(0);
  const [extraPlaceQueries, setExtraPlaceQueries] = useState<Record<number, string>>({});
  const [activeRouteDayIndex, setActiveRouteDayIndex] = useState(0);
  const [routePicker, setRoutePicker] = useState<{
    dayIndex: number;
    field: "departureCluster" | "arrivalCluster";
  } | null>(null);
  const [timePicker, setTimePicker] = useState<{
    dayIndex: number;
    field: "startTime" | "endTime";
  } | null>(null);
  const [krwPerUsd, setKrwPerUsd] = useState<number | null>(BUDGET_EXCHANGE_FALLBACK);

  const planValue = toPlanValue(value);
  const dayInputs = useMemo(() => getDayInputs(planValue), [planValue]);
  const activeRouteDay = dayInputs[activeRouteDayIndex] || dayInputs[0];
  const selectedExtraPlaceQuery =
    extraPlaceQueries[extraPlaceDayIndex] ??
    dayInputs[extraPlaceDayIndex]?.additionalPlaceName ??
    (dayInputs.some((day) => day.additionalPlaceId) ? "" : value.extraPlace);
  const hasInvalidTime = dayInputs.some((day) => day.startTime >= day.endTime);
  const budgetKrw = value.budgetValue * 10000;
  const canGenerate = Boolean(
    dayInputs.length === value.durationDays &&
      dayInputs.every(
        (day) =>
          day.departureCluster &&
          day.arrivalCluster &&
          day.startTime &&
          day.endTime &&
          day.startTime < day.endTime
      ) &&
      value.styles.length > 0 &&
      value.pace &&
      value.companion
  );
  const canGoNext =
    step === 1
      ? value.durationDays > 0
      : step === 2
        ? !hasInvalidTime &&
          dayInputs.every(
            (day) =>
              day.departureCluster &&
              day.arrivalCluster &&
              day.startTime &&
              day.endTime
          )
        : step === 3
          ? value.styles.length > 0 && Boolean(value.pace)
          : step === 4
            ? Boolean(value.companion)
            : canGenerate;

  useEffect(() => {
    let cancelled = false;
    fetch("https://open.er-api.com/v6/latest/USD")
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        const nextRate = Number(payload?.rates?.KRW);
        if (!cancelled && Number.isFinite(nextRate) && nextRate > 0) {
          setKrwPerUsd(nextRate);
        }
      })
      .catch(() => {
        if (!cancelled) setKrwPerUsd(BUDGET_EXCHANGE_FALLBACK);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const emitChange = (next: AiPreferenceStateV2) => {
    onChange(next as AiPreferenceState);
  };

  const setField = <K extends keyof AiPreferenceState>(
    field: K,
    fieldValue: AiPreferenceState[K]
  ) => {
    emitChange({ ...planValue, [field]: fieldValue });
  };

  const setDayField = <K extends keyof AiPlanDayInput>(
    index: number,
    field: K,
    fieldValue: AiPlanDayInput[K]
  ) => {
    const nextDays = dayInputs.map((day, dayIndex) =>
      dayIndex === index ? { ...day, [field]: fieldValue } : day
    );

    emitChange({
      ...planValue,
      departure: nextDays[0]?.departureCluster || "",
      arrival: nextDays[nextDays.length - 1]?.arrivalCluster || "",
      startTime: nextDays[0]?.startTime || planValue.startTime,
      endTime: nextDays[nextDays.length - 1]?.endTime || planValue.endTime,
      days: nextDays,
    });
  };

  const setDuration = (durationDays: number) => {
    const currentDays = getDayInputs({ ...planValue, durationDays });
    setExtraPlaceDayIndex((current) => Math.min(current, durationDays - 1));
    setActiveRouteDayIndex((current) => Math.min(current, durationDays - 1));
    emitChange({
      ...planValue,
      durationDays,
      days: currentDays,
      departure: currentDays[0]?.departureCluster || "",
      arrival: currentDays[currentDays.length - 1]?.arrivalCluster || "",
    });
  };

  const toggleStyle = (token: string) => {
    const nextStyles = value.styles.includes(token)
      ? value.styles.filter((item) => item !== token)
      : [...value.styles, token];

    emitChange({
      ...planValue,
      styles: nextStyles,
    });
  };

  const handleBudgetChange = (nextValue: number) => {
    emitChange({
      ...planValue,
      budgetValue: nextValue,
      budgetCategory: budgetCategoryFromValue(nextValue),
    });
  };

  const searchExtraPlace = () => {
    const keyword = selectedExtraPlaceQuery.trim();
    setExtraResults([]);
    setExtraSearchMessage("");

    if (!keyword) {
      setExtraSearchMessage(`Enter a place keyword for Day ${extraPlaceDayIndex + 1}.`);
      return;
    }

    setIsSearchingExtra(true);
    void getTourPlaces({ keyword })
      .then((response) => {
        const places = response.items
          .map(normalizePlace)
          .filter((item): item is ExtraPlaceOption => Boolean(item));
        setExtraResults(places);
        setExtraSearchMessage(
          places.length > 0 ? "Select one result to include it in the itinerary." : "No matching place was found."
        );
      })
      .catch((error) => {
        setExtraResults([]);
        setExtraSearchMessage(error instanceof Error ? error.message : "Failed to search places.");
      })
      .finally(() => setIsSearchingExtra(false));
  };

  const selectExtraPlace = (place: ExtraPlaceOption) => {
    const nextDays = dayInputs.map((day, index) =>
      index === extraPlaceDayIndex
        ? {
            ...day,
            additionalPlaceId: place.placeId,
            additionalPlaceName: place.name,
          }
        : day
    );

    emitChange({
      ...planValue,
      extraPlace: place.name,
      additionalPlaceId: nextDays[0]?.additionalPlaceId ?? null,
      additionalPlaceName: nextDays[0]?.additionalPlaceName || "",
      days: nextDays,
    });
    setExtraPlaceQueries((current) => ({
      ...current,
      [extraPlaceDayIndex]: place.name,
    }));
    setExtraSearchMessage(`${place.name} will be included on Day ${extraPlaceDayIndex + 1}.`);
  };

  const clearExtraPlace = (dayIndex: number) => {
    const nextDays = dayInputs.map((day, index) =>
      index === dayIndex
        ? {
            ...day,
            additionalPlaceId: null,
            additionalPlaceName: "",
          }
        : day
    );

    emitChange({
      ...planValue,
      extraPlace: nextDays.find((day) => day.additionalPlaceName)?.additionalPlaceName || "",
      additionalPlaceId: nextDays[0]?.additionalPlaceId ?? null,
      additionalPlaceName: nextDays[0]?.additionalPlaceName || "",
      days: nextDays,
    });
    setExtraPlaceQueries((current) => ({
      ...current,
      [dayIndex]: "",
    }));
  };

  const goBack = () => {
    if (isGenerating) return;
    if (step > 1) {
      setStep((current) => (current - 1) as AiStep);
      return;
    }
    onBack();
  };

  const goNext = () => {
    if (!canGoNext) return;
    if (step < TOTAL_STEPS) {
      setStep((current) => (current + 1) as AiStep);
      return;
    }
    onSubmit();
  };

  return (
    <div style={styles.page}>
      <div style={styles.phoneFrame}>
        <div style={styles.headerRow}>
          <button type="button" onClick={goBack} style={styles.iconButton}>
            <img src="/icon-back.svg" alt="Back" style={styles.backIcon} />
          </button>
          <h1 style={styles.headerLogo}>
            AI Plan
          </h1>
        </div>

        <div style={styles.stepHeader}>
          <StepDots step={step} />
          <span style={styles.stepCount}>Step {step} of {TOTAL_STEPS}</span>
        </div>

        <section
          style={styles.panel}
          onClick={() => {
            if (step === 2) {
              setRoutePicker(null);
              setTimePicker(null);
            }
          }}
        >
          {step === 1 ? (
            <>
              <QuestionTitle>How long is your trip?</QuestionTitle>
              <p style={styles.copy}>Choose the number of days for this Seoul itinerary.</p>
              <div style={styles.durationGrid}>
                {durationOptions.map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => setDuration(days)}
                    style={{
                      ...styles.durationCard,
                      ...(value.durationDays === days ? styles.durationCardActive : {}),
                    }}
                  >
                    <strong>{days}</strong>
                    <span>{days > 1 ? "days" : "day"}</span>
                  </button>
                ))}
              </div>
            </>
          ) : null}

          {step === 2 ? (
            <>
              <QuestionTitle>Where would you like to go?</QuestionTitle>
              <div style={styles.dayTabs}>
                {dayInputs.map((day, index) => (
                  <button
                    key={`route-day-${index + 1}`}
                    type="button"
                    onClick={() => {
                      setActiveRouteDayIndex(index);
                      setRoutePicker(null);
                      setTimePicker(null);
                    }}
                    style={{
                      ...styles.dayTab,
                      ...(activeRouteDayIndex === index ? styles.dayTabActive : {}),
                    }}
                  >
                    <span style={styles.dayTabLabel}>Day {index + 1}</span>
                    <span style={styles.dayTabDate}>
                      {day.startTime} - {day.endTime}
                    </span>
                  </button>
                ))}
              </div>

              {activeRouteDay ? (
                <div style={styles.placeEntryList}>
                  {[
                    {
                      field: "departureCluster" as const,
                      label: "Enter starting point",
                      value: activeRouteDay.departureCluster,
                      dot: styles.placeEntryDotStart,
                    },
                    {
                      field: "arrivalCluster" as const,
                      label: "Enter Destination",
                      value: activeRouteDay.arrivalCluster,
                      dot: styles.placeEntryDotEnd,
                    },
                  ].map((slot, index) => (
                    <div key={slot.field}>
                      <div style={styles.placeEntryRow}>
                        <span style={styles.placeEntryDotWrap}>
                          <span style={{ ...styles.placeEntryDotHalo, ...slot.dot }} />
                          <span style={{ ...styles.placeEntryDot, ...slot.dot }} />
                        </span>
                        <div style={styles.placeEntryInputShell}>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setTimePicker(null);
                              setRoutePicker({
                                dayIndex: activeRouteDayIndex,
                                field: slot.field,
                              });
                            }}
                            style={styles.placeEntryInput}
                          >
                            {slot.value || slot.label}
                          </button>
                        </div>
                      </div>
                      {index === 0 ? <div style={styles.placeEntryConnector} /> : null}
                    </div>
                  ))}
                </div>
              ) : null}

              {routePicker ? (
                <div
                  style={styles.clusterPicker}
                  onClick={(event) => event.stopPropagation()}
                >
                  <span style={styles.fieldLabel}>
                    {routePicker.field === "departureCluster" ? "Starting point" : "Destination"}
                  </span>
                  <div style={styles.clusterGrid}>
                    {seoulClusterKeys.map((cluster) => (
                      <button
                        key={cluster}
                        type="button"
                        onClick={() => {
                          setDayField(routePicker.dayIndex, routePicker.field, cluster);
                          setRoutePicker(null);
                        }}
                        style={{
                          ...styles.clusterChip,
                          ...(dayInputs[routePicker.dayIndex]?.[routePicker.field] === cluster
                            ? styles.clusterChipActive
                            : {}),
                        }}
                      >
                        {cluster}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {activeRouteDay ? (
                <div style={styles.twoColumn}>
                  <label style={styles.fieldLabel}>
                    Start
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setRoutePicker(null);
                        setTimePicker({
                          dayIndex: activeRouteDayIndex,
                          field: "startTime",
                        });
                      }}
                      style={styles.timeInputButton}
                    >
                      {activeRouteDay.startTime}
                    </button>
                  </label>
                  <label style={styles.fieldLabel}>
                    End
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setRoutePicker(null);
                        setTimePicker({
                          dayIndex: activeRouteDayIndex,
                          field: "endTime",
                        });
                      }}
                      style={styles.timeInputButton}
                    >
                      {activeRouteDay.endTime}
                    </button>
                  </label>
                </div>
              ) : null}

              {timePicker ? (
                <div
                  style={styles.timePicker}
                  onClick={(event) => event.stopPropagation()}
                >
                  <span style={styles.fieldLabel}>
                    {timePicker.field === "startTime" ? "Start time" : "End time"}
                  </span>
                  <div style={styles.timeWheelGrid}>
                    <div style={styles.timeScroll}>
                      {MERIDIEM_OPTIONS.map((meridiem) => {
                        const selected =
                          parseTimeParts(dayInputs[timePicker.dayIndex]?.[timePicker.field] || "10:00")
                            .meridiem === meridiem;
                        return (
                          <button
                            key={meridiem}
                            type="button"
                            onClick={() =>
                              setDayField(
                                timePicker.dayIndex,
                                timePicker.field,
                                composeTime(
                                  dayInputs[timePicker.dayIndex]?.[timePicker.field] || "10:00",
                                  { meridiem }
                                )
                              )
                            }
                            style={{
                              ...styles.timeOption,
                              ...(selected ? styles.timeOptionActive : {}),
                            }}
                          >
                            {meridiem}
                          </button>
                        );
                      })}
                    </div>
                    <div style={styles.timeScroll}>
                      {HOUR_OPTIONS.map((hour) => {
                        const selected =
                          parseTimeParts(dayInputs[timePicker.dayIndex]?.[timePicker.field] || "10:00")
                            .hour === hour;
                        return (
                          <button
                            key={hour}
                            type="button"
                            onClick={() =>
                              setDayField(
                                timePicker.dayIndex,
                                timePicker.field,
                                composeTime(
                                  dayInputs[timePicker.dayIndex]?.[timePicker.field] || "10:00",
                                  { hour }
                                )
                              )
                            }
                            style={{
                              ...styles.timeOption,
                              ...(selected ? styles.timeOptionActive : {}),
                            }}
                          >
                            {hour}
                          </button>
                        );
                      })}
                    </div>
                    <div style={styles.timeScroll}>
                      {MINUTE_OPTIONS.map((minute) => {
                        const selected =
                          parseTimeParts(dayInputs[timePicker.dayIndex]?.[timePicker.field] || "10:00")
                            .minute === minute;
                        return (
                          <button
                            key={minute}
                            type="button"
                            onClick={() =>
                              setDayField(
                                timePicker.dayIndex,
                                timePicker.field,
                                composeTime(
                                  dayInputs[timePicker.dayIndex]?.[timePicker.field] || "10:00",
                                  { minute }
                                )
                              )
                            }
                            style={{
                              ...styles.timeOption,
                              ...(selected ? styles.timeOptionActive : {}),
                            }}
                          >
                            {minute}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTimePicker(null)}
                    style={styles.timeDoneButton}
                  >
                    Done
                  </button>
                </div>
              ) : null}

              <div style={styles.routeSummaryList}>
                {dayInputs.map((day, index) => (
                  <span key={`route-summary-${index + 1}`}>
                    Day {index + 1}: {day.departureCluster} to {day.arrivalCluster}
                  </span>
                ))}
              </div>
              {hasInvalidTime ? (
                <p style={styles.errorText}>Each day needs a start time earlier than the end time.</p>
              ) : null}
            </>
          ) : null}

          {step === 3 ? (
            <>
              <QuestionTitle>What kind of route feels right?</QuestionTitle>
              <div style={styles.fieldBlock}>
                <SectionLabel>Travel Style</SectionLabel>
                <p style={styles.mutedText}>Multiple choice</p>
                <div style={styles.chipGrid}>
                  {styleTokens.map((token) => (
                    <ChipButton
                      key={token}
                      active={value.styles.includes(token)}
                      label={token}
                      onClick={() => toggleStyle(token)}
                    />
                  ))}
                </div>
              </div>
              <div style={styles.fieldBlock}>
                <SectionLabel accent="#FFB765">Schedule Density</SectionLabel>
                <p style={styles.mutedText}>Choose one</p>
                <div style={styles.chipGrid}>
                  {paceOptions.map((option) => (
                    <ChipButton
                      key={option.value}
                      active={value.pace === option.value}
                      label={option.label}
                      onClick={() => setField("pace", option.value)}
                      accent="#FFB765"
                    />
                  ))}
                </div>
              </div>
            </>
          ) : null}

          {step === 4 ? (
            <>
              <QuestionTitle>Who is this trip for?</QuestionTitle>
              <div style={styles.fieldBlock}>
                <SectionLabel>Companion</SectionLabel>
                <p style={styles.mutedText}>Choose one</p>
                <div style={styles.chipGrid}>
                  {companionOptions.map((option) => (
                    <ChipButton
                      key={option}
                      active={value.companion === option}
                      label={option}
                      onClick={() => setField("companion", option)}
                    />
                  ))}
                </div>
              </div>

              <div style={styles.fieldBlock}>
                <div style={styles.budgetHeader}>
                  <SectionLabel accent="#FFB765">Budget per person</SectionLabel>
                  <span style={styles.budgetBadge}>
                    <span style={styles.budgetIcon}>{budgetCategoryIcon(value.budgetCategory)}</span>
                    {budgetCategoryLabel(value.budgetCategory)}
                  </span>
                </div>
                <div style={styles.budgetValueRow}>
                  KRW {formatBudgetValue(value.budgetValue)}
                  {krwPerUsd ? <span>{formatUsd(budgetKrw, krwPerUsd)} / day</span> : null}
                </div>
                <input
                  type="range"
                  min={BUDGET_SLIDER_MIN}
                  max={BUDGET_SLIDER_MAX}
                  step={BUDGET_SLIDER_STEP}
                  value={value.budgetValue}
                  onChange={(event) => handleBudgetChange(Number(event.target.value))}
                  style={styles.rangeInput}
                />
                <div style={styles.rangeLabels}>
                  <span>KRW {formatBudgetValue(BUDGET_SLIDER_MIN)}</span>
                  <span>KRW {formatBudgetValue(BUDGET_SLIDER_MAX)}</span>
                </div>
              </div>

              <div style={styles.fieldBlock}>
                <SectionLabel>Food Preference</SectionLabel>
                <p style={styles.mutedText}>Choose one</p>
                <div style={styles.chipGrid}>
                  <ChipButton
                    active={!value.foodNeed}
                    label="Any"
                    onClick={() => setField("foodNeed", "")}
                  />
                  {foodNeeds.map((item) => (
                    <ChipButton
                      key={item}
                      active={value.foodNeed === item}
                      label={item}
                      onClick={() => setField("foodNeed", value.foodNeed === item ? "" : item)}
                    />
                  ))}
                </div>
              </div>
            </>
          ) : null}

          {step === 5 ? (
            <>
              <QuestionTitle>Any must-visit place?</QuestionTitle>
              <p style={styles.copy}>Add an optional extra place for each day.</p>
              <div style={styles.daySelector}>
                {dayInputs.map((day, index) => (
                  <button
                    key={`extra-day-${index + 1}`}
                    type="button"
                    onClick={() => {
                      setExtraPlaceDayIndex(index);
                      setExtraResults([]);
                      setExtraSearchMessage("");
                    }}
                    style={{
                      ...styles.daySelectorButton,
                      ...(extraPlaceDayIndex === index ? styles.daySelectorButtonActive : {}),
                    }}
                  >
                    Day {index + 1}
                    {day.additionalPlaceId ? " added" : ""}
                  </button>
                ))}
              </div>

              <div style={styles.searchRow}>
                <input
                  value={selectedExtraPlaceQuery}
                  onChange={(event) => {
                    const nextQuery = event.target.value;
                    setExtraPlaceQueries((current) => ({
                      ...current,
                      [extraPlaceDayIndex]: nextQuery,
                    }));
                    setExtraResults([]);
                    setExtraSearchMessage("");
                    emitChange({
                      ...planValue,
                      extraPlace: nextQuery,
                    });
                  }}
                  style={styles.searchInput}
                  placeholder={`Search a place for Day ${extraPlaceDayIndex + 1}`}
                />
                <button
                  type="button"
                  onClick={searchExtraPlace}
                  style={styles.searchButton}
                  disabled={isSearchingExtra}
                >
                  {isSearchingExtra ? "..." : "Search"}
                </button>
              </div>

              {dayInputs.some((day) => day.additionalPlaceId) ? (
                <div style={styles.extraResults}>
                  {dayInputs.map((day, index) =>
                    day.additionalPlaceId ? (
                      <div key={`selected-extra-${index + 1}`} style={styles.selectedPlaceRow}>
                        <span>
                          Day {index + 1}: {day.additionalPlaceName || "Selected place"}
                        </span>
                        <button
                          type="button"
                          onClick={() => clearExtraPlace(index)}
                          style={styles.clearButton}
                        >
                          Clear
                        </button>
                      </div>
                    ) : null
                  )}
                </div>
              ) : null}
              {extraSearchMessage ? <p style={styles.mutedText}>{extraSearchMessage}</p> : null}
              {extraResults.length > 0 ? (
                <div style={styles.extraResults}>
                  {extraResults.map((place) => (
                    <button
                      key={place.placeId}
                      type="button"
                      onClick={() => selectExtraPlace(place)}
                      style={styles.placeCard}
                    >
                      <div style={styles.placeBadgeRow}>
                        <span style={styles.placeCategory}>{place.category}</span>
                      </div>
                      <strong>{place.name}</strong>
                      <span>{place.address || place.category}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </section>

        <button
          type="button"
          onClick={goNext}
          style={{
            ...styles.primaryAction,
            ...(canGoNext ? {} : styles.primaryActionDisabled),
          }}
          disabled={!canGoNext}
        >
          {step === TOTAL_STEPS ? "Generate AI itinerary" : "Next"}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    height: "calc(var(--app-viewport-height) - var(--app-bottom-nav-reserved, 0px))",
    padding: "calc(var(--app-safe-top) + 20px) 16px 20px",
    boxSizing: "border-box",
    background: "#fff",
    fontFamily: '"Pretendard Variable", sans-serif',
    overflowY: "auto",
    overflowX: "hidden",
  },
  phoneFrame: {
    maxWidth: 430,
    width: "100%",
    height: "100%",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 18,
    paddingBottom: 0,
    boxSizing: "border-box",
    overflow: "hidden",
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
  stepHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: "0.6rem",
    padding: "0 4px",
  },
  stepDots: {
    display: "flex",
    gap: "0.75rem",
    marginLeft: "-2px",
    alignItems: "center",
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
  stepCount: {
    color: "#888",
    fontSize: 12,
    fontWeight: 700,
  },
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: 20,
    minHeight: 500,
    padding: "6px 0 0",
  },
  questionTitle: {
    margin: "0 0 2rem",
    color: "#212121",
    fontSize: 20,
  },
  copy: {
    marginTop: "-3rem",
    marginBottom: "4rem",
    color: "#777",
    fontSize: 14,
    lineHeight: 1.6,
  },
  durationGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 16,
  },
  durationCard: {
    minHeight: 112,
    border: "1px solid #eaeaea",
    borderRadius: 20,
    background: "#fafafa",
    color: "#444",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    outline: "none",
    cursor: "pointer",
  },
  durationCardActive: {
    border: "1px solid #58C9D4",
    background: "#eaf8fa",
    color: BRAND,
  },
  dayStack: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
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
    outline: "none",
    cursor: "pointer",
    flexShrink: 0,
  },
  dayTabActive: {
    border: "1px solid #58C9D4",
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
  dayPanel: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 14,
    borderRadius: 18,
    background: "#fafafa",
    border: "1px solid #eaeaea",
  },
  dayHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    color: "#212121",
    fontSize: 14,
  },
  dayBadge: {
    color: BRAND,
    fontSize: 12,
    fontWeight: 800,
  },
  fieldBlock: {
    marginBottom: 16,
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  placeEntryList: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  placeEntryRow: {
    display: "grid",
    gridTemplateColumns: "18px 1fr",
    gap: 12,
    alignItems: "center",
  },
  placeEntryDotWrap: {
    position: "relative",
    width: 18,
    height: 18,
    display: "block",
  },
  placeEntryDotHalo: {
    position: "absolute",
    inset: 0,
    borderRadius: "50%",
    opacity: 0.14,
  },
  placeEntryDot: {
    position: "absolute",
    left: "50%",
    top: "50%",
    width: 9,
    height: 9,
    borderRadius: "50%",
    transform: "translate(-50%, -50%)",
  },
  placeEntryDotStart: {
    background: BRAND,
  },
  placeEntryDotEnd: {
    background: "#FFB765",
  },
  placeEntryInputShell: {
    position: "relative",
  },
  placeEntryInput: {
    width: "100%",
    minHeight: 54,
    border: "none",
    borderRadius: 18,
    background: "#f5f5f5",
    color: "#222",
    padding: "0 18px",
    textAlign: "left",
    fontSize: 14,
    fontWeight: 700,
    outline: "none",
    cursor: "pointer",
  },
  placeEntryConnector: {
    minHeight: 24,
    marginLeft: 8,
    borderLeft: "2px dashed #d9d9d9",
  },
  clusterPicker: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    padding: 12,
    borderRadius: 18,
    background: "#fff",
    border: "1px solid #eaeaea",
  },
  clusterGrid: {
    maxHeight: 220,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 0,
    background: "#fff",
  },
  clusterChip: {
    width: "100%",
    minHeight: 46,
    border: "none",
    borderBottom: "1px solid #eeeeee",
    borderRadius: 0,
    background: "#fff",
    color: "#555",
    padding: "0 4px",
    fontSize: 14,
    fontWeight: 700,
    outline: "none",
    textAlign: "left",
    cursor: "pointer",
  },
  clusterChipActive: {
    borderBottom: "1px solid #d8f1f4",
    background: "#f0fbfc",
    color: BRAND,
  },
  routeSummaryList: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    color: "#888",
    fontSize: 12,
    lineHeight: 1.4,
  },
  fieldLabel: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    color: "#444",
    fontSize: 13,
    fontWeight: 700,
  },
  input: {
    width: "100%",
    minHeight: 48,
    borderRadius: 50,
    border: "1px solid #eaeaea",
    background: "#f7f7f7",
    padding: "0 16px",
    fontSize: 14,
    color: "#222",
    boxSizing: "border-box",
    outline: "none",
  },
  timeInputButton: {
    width: "100%",
    minHeight: 48,
    borderRadius: 50,
    border: "1px solid #eaeaea",
    background: "#f7f7f7",
    padding: "0 16px",
    fontSize: 14,
    color: "#222",
    boxSizing: "border-box",
    outline: "none",
    textAlign: "left",
    cursor: "pointer",
  },
  timePicker: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    padding: 12,
    borderRadius: 18,
    background: "#fff",
    border: "1px solid #eaeaea",
  },
  timeWheelGrid: {
    display: "grid",
    gridTemplateColumns: "0.9fr 1fr 1fr",
    gap: 8,
  },
  timeScroll: {
    maxHeight: 190,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 0,
    background: "#fff",
  },
  timeOption: {
    width: "100%",
    minHeight: 44,
    border: "none",
    borderBottom: "1px solid #eeeeee",
    borderRadius: 0,
    background: "#fff",
    color: "#555",
    fontSize: 14,
    fontWeight: 700,
    outline: "none",
    textAlign: "left",
    padding: "0 4px",
    cursor: "pointer",
  },
  timeDoneButton: {
    minHeight: 42,
    border: "none",
    borderRadius: 999,
    background: "#58C9D4",
    color: "#fff",
    fontSize: 13,
    fontWeight: 800,
    outline: "none",
    cursor: "pointer",
  },
  timeOptionActive: {
    borderBottom: "1px solid #d8f1f4",
    background: "#f0fbfc",
    color: "#58C9D4",
  },
  twoColumn: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
  },
  sectionLabel: {
    padding: "0 4px",
    fontSize: 13,
    fontWeight: 800,
  },
  mutedText: {
    margin: "-8px 4px 8px",
    color: "#888",
    fontSize: 10,
    lineHeight: 1.5,
  },
  chipGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    minHeight: 42,
    border: "1px solid #eaeaea",
    borderRadius: 999,
    background: "#fafafa",
    color: "#555",
    padding: "0 14px",
    fontSize: 13,
    fontWeight: 800,
    outline: "none",
    cursor: "pointer",
  },
  budgetHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  budgetBadge: {
    display: "grid",
    gridTemplateColumns: "24px 1fr",
    width: 130,
    height: 28,
    boxSizing: "border-box",
    justifyContent: "center",
    alignItems: "center",
    gap: 4,
    padding: "0 14px",
    borderRadius: 999,
    background: "#fff1dc",
    color: "#8a5200",
    fontSize: 12,
    fontWeight: 800,
  },
  budgetIcon: {
    width: 24,
    textAlign: "center",
    fontSize: 11,
    fontWeight: 900,
  },
  budgetValueRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    padding: "0 4px",
    gap: 10,
    color: "#444444",
    fontSize: 12,
    fontWeight: 600,
  },
  rangeInput: {
    width: "100%",
    accentColor: BRAND,
  },
  rangeLabels: {
    display: "flex",
    justifyContent: "space-between",
    color: "#888",
    fontSize: 12,
    fontWeight: 700,
  },
  daySelector: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 8,
  },
  daySelectorButton: {
    minHeight: 44,
    borderRadius: 999,
    border: "1px solid #eaeaea",
    background: "#fafafa",
    color: "#555",
    fontSize: 12,
    fontWeight: 800,
    outline: "none",
    cursor: "pointer",
  },
  daySelectorButtonActive: {
    border: "1px solid #58C9D4",
    background: "#eaf8fa",
    color: BRAND,
  },
  searchRow: {
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 10,
    alignItems: "center",
    background: "#f7f7f7",
    borderRadius: 50,
  },
  searchInput: {
    width: "100%",
    minHeight: 48,
    border: "none",
    background: "transparent",
    padding: "0 16px",
    fontSize: 14,
    color: "#222",
    outline: "none",
    boxSizing: "border-box",
  },
  searchButton: {
    minWidth: 78,
    minHeight: 48,
    border: "none",
    borderRadius: 50,
    background: "#FFB765",
    color: "#5e3600",
    padding: "0 14px",
    fontSize: 13,
    fontWeight: 900,
    outline: "none",
    cursor: "pointer",
  },
  extraResults: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  selectedPlaceRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    padding: "10px 12px",
    borderRadius: 14,
    background: "#eaf8fa",
    color: "#204444",
    fontSize: 13,
    fontWeight: 800,
  },
  clearButton: {
    border: "none",
    borderRadius: 999,
    background: "#ffffff",
    color: "#688",
    padding: "6px 10px",
    fontSize: 12,
    fontWeight: 800,
    outline: "none",
    cursor: "pointer",
  },
  placeCard: {
    width: "100%",
    padding: 14,
    borderRadius: 18,
    border: "1px solid #eaeaea",
    background: "#fafafa",
    color: "#222",
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    gap: 8,
    textAlign: "left",
    outline: "none",
    cursor: "pointer",
  },
  placeBadgeRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
  },
  placeCategory: {
    padding: "6px 10px",
    borderRadius: 999,
    background: "#e1eef0",
    color: BRAND,
    fontSize: 10,
    fontWeight: 800,
  },
  errorText: {
    margin: 0,
    color: "#d14343",
    fontSize: 12,
    fontWeight: 700,
  },
  primaryAction: {
    width: "100%",
    minHeight: 56,
    border: "none",
    borderRadius: 50,
    background: BRAND,
    color: "#ffffff",
    fontSize: "1rem",
    fontWeight: 800,
    outline: "none",
    cursor: "pointer",
  },
  primaryActionDisabled: {
    background: "#d7d7d7",
    color: "#999",
    cursor: "not-allowed",
  },
};
