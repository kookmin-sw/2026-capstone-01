import type { CSSProperties } from "react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { registerUser } from "../api/auth/auth";
import type { RegisterFormState } from "./RegisterPage";

type Option = {
  key: string;
  label: string;
  note?: string;
};

interface OnboardingLocationState {
  registerForm?: RegisterFormState;
}

interface OnboardingFormState {
  travel_styles: string[];
  food_preferences: string[];
  density_preference: string;
  budget_preference: string;
  walking_preference: string;
  transport_preferences: string[];
  companion_preference: string;
  time_preferences: string[];
  communication_preference: string;
  planning_preference: string;
}

const TRAVEL_STYLE_OPTIONS: Option[] = [
  { key: "activity", label: "Activity" },
  { key: "famous_attractions", label: "Famous Attractions" },
  { key: "healing", label: "Healing" },
  { key: "culture_history", label: "Culture & History" },
  { key: "shopping", label: "Shopping" },
  { key: "food_tour", label: "Food Tour" },
  { key: "photo_aesthetic", label: "Photo Aesthetic" },
  { key: "festival_event", label: "Festival & Event" },
  { key: "nature", label: "Nature" },
  { key: "traditional", label: "Traditional" },
  { key: "trekking", label: "Trekking" },
  { key: "hidden_gems", label: "Hidden Gems" },
  { key: "art_exhibition", label: "Art Exhibition" },
  { key: "theme_park", label: "Theme Park" },
];

const FOOD_OPTIONS: Option[] = [
  { key: "food_halal", label: "Halal" },
  { key: "food_vegetarian", label: "Vegetarian" },
  { key: "foodie", label: "Foodie" },
  { key: "cafe_lover", label: "Cafe Lover" },
];

const DENSITY_OPTIONS: Option[] = [
  { key: "density_relaxed", label: "Relaxed" },
  { key: "density_packed", label: "Packed" },
];

const BUDGET_OPTIONS: Option[] = [
  { key: "budget_saving", label: "Saving", note: "$40-$70 / day" },
  { key: "budget_moderate", label: "Moderate", note: "$100-$200 / day" },
  { key: "budget_premium", label: "Premium", note: "$250+ / day" },
];

const WALKING_OPTIONS: Option[] = [
  { key: "walking_low", label: "Low" },
  { key: "walking_medium", label: "Medium" },
  { key: "walking_high", label: "High" },
];

const TRANSPORT_OPTIONS: Option[] = [
  { key: "transport_public", label: "Public Transit" },
  { key: "transport_car", label: "Car" },
  { key: "transport_taxi", label: "Taxi" },
];

const COMPANION_OPTIONS: Option[] = [
  { key: "companion_independent", label: "Independent" },
  { key: "companion_together", label: "Together" },
  { key: "companion_flexible", label: "Flexible" },
];

const TIME_OPTIONS: Option[] = [
  { key: "daytime", label: "Daytime" },
  { key: "nightlife", label: "Nightlife" },
  { key: "night_view", label: "Night View" },
];

const COMMUNICATION_OPTIONS: Option[] = [
  { key: "communication_high", label: "High Communication" },
  { key: "communication_low", label: "Low Communication" },
];

const PLANNING_OPTIONS: Option[] = [
  { key: "planner", label: "Planner" },
  { key: "spontaneous", label: "Spontaneous" },
  { key: "follower", label: "Follower" },
];

const INITIAL_ONBOARDING_FORM: OnboardingFormState = {
  travel_styles: [],
  food_preferences: [],
  density_preference: "",
  budget_preference: "",
  walking_preference: "",
  transport_preferences: [],
  companion_preference: "",
  time_preferences: [],
  communication_preference: "",
  planning_preference: "",
};

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { state } = useLocation() as { state: OnboardingLocationState | null };
  const registerForm = state?.registerForm;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<OnboardingFormState>(INITIAL_ONBOARDING_FORM);

  function toggleMulti(key: keyof OnboardingFormState, value: string): void {
    setForm((current) => {
      const selected = current[key] as string[];
      return {
        ...current,
        [key]: selected.includes(value)
          ? selected.filter((item) => item !== value)
          : [...selected, value],
      };
    });
  }

  function setSingle(key: keyof OnboardingFormState, value: string): void {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function validate(): boolean {
    if (!registerForm) {
      setError("Please complete traveler details first.");
      return false;
    }

    if (
      form.travel_styles.length === 0 ||
      form.food_preferences.length === 0 ||
      !form.density_preference ||
      !form.budget_preference ||
      !form.walking_preference ||
      form.transport_preferences.length === 0 ||
      !form.companion_preference ||
      form.time_preferences.length === 0 ||
      !form.communication_preference ||
      !form.planning_preference
    ) {
      setError("Please complete every onboarding section.");
      return false;
    }

    return true;
  }

  async function handleSubmit(): Promise<void> {
    setError("");
    if (!validate() || !registerForm) return;

    setLoading(true);
    try {
      await registerUser({
        ...registerForm,
        age: Number(registerForm.age),
        ...form,
      });
      navigate("/home");
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "Something went wrong while completing sign up.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.wrapper}>
      <div style={s.card}>
        <div style={s.header}>
          <Progress current={2} total={2} />
          <span style={s.step}>Onboarding</span>
          <h2 style={s.title}>Travel Preferences</h2>
          <p style={s.sub}>Choose what fits your trip style so KRIP can personalize recommendations.</p>
        </div>

        <div style={s.sections}>
          <ChoiceSection
            label="Travel Styles (multiple choice) *"
            options={TRAVEL_STYLE_OPTIONS}
            selected={form.travel_styles}
            onToggle={(key) => toggleMulti("travel_styles", key)}
          />
          <ChoiceSection
            label="Food Preferences (multiple choice) *"
            options={FOOD_OPTIONS}
            selected={form.food_preferences}
            onToggle={(key) => toggleMulti("food_preferences", key)}
          />
          <ChoiceSection
            label="Schedule Density (choose one) *"
            options={DENSITY_OPTIONS}
            selected={form.density_preference}
            onToggle={(key) => setSingle("density_preference", key)}
          />
          <ChoiceSection
            label="Budget Preference (choose one) *"
            options={BUDGET_OPTIONS}
            selected={form.budget_preference}
            onToggle={(key) => setSingle("budget_preference", key)}
          />
          <ChoiceSection
            label="Walking Preference (choose one) *"
            options={WALKING_OPTIONS}
            selected={form.walking_preference}
            onToggle={(key) => setSingle("walking_preference", key)}
          />
          <ChoiceSection
            label="Transportation (multiple choice) *"
            options={TRANSPORT_OPTIONS}
            selected={form.transport_preferences}
            onToggle={(key) => toggleMulti("transport_preferences", key)}
          />
          <ChoiceSection
            label="Companion Style (choose one) *"
            options={COMPANION_OPTIONS}
            selected={form.companion_preference}
            onToggle={(key) => setSingle("companion_preference", key)}
          />
          <ChoiceSection
            label="Active Time (multiple choice) *"
            options={TIME_OPTIONS}
            selected={form.time_preferences}
            onToggle={(key) => toggleMulti("time_preferences", key)}
          />
          <ChoiceSection
            label="Communication Style (choose one) *"
            options={COMMUNICATION_OPTIONS}
            selected={form.communication_preference}
            onToggle={(key) => setSingle("communication_preference", key)}
          />
          <ChoiceSection
            label="Planning Style (choose one) *"
            options={PLANNING_OPTIONS}
            selected={form.planning_preference}
            onToggle={(key) => setSingle("planning_preference", key)}
          />
        </div>

        {error && <p style={s.error}>{error}</p>}

        <div style={s.actions}>
          <button
            type="button"
            style={s.backBtn}
            onClick={() => navigate("/register", { state: registerForm })}
            disabled={loading}
          >
            Back
          </button>
          <button
            type="button"
            style={{ ...s.submitBtn, opacity: loading ? 0.7 : 1 }}
            onClick={() => void handleSubmit()}
            disabled={loading}
          >
            {loading ? "Submitting..." : "Complete Sign Up"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ChoiceSection({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: Option[];
  selected: string[] | string;
  onToggle: (key: string) => void;
}) {
  return (
    <section style={s.choiceSection}>
      <h3 style={s.sectionTitle}>{label}</h3>
      <div style={s.styleGrid}>
        {options.map(({ key, label: optionLabel, note }) => {
          const isSelected = Array.isArray(selected)
            ? selected.includes(key)
            : selected === key;
          return (
            <button
              key={key}
              type="button"
              style={{ ...s.styleBtn, ...(isSelected ? s.styleBtnActive : {}) }}
              onClick={() => onToggle(key)}
            >
              <span>{optionLabel}</span>
              {note && <small style={s.note}>{note}</small>}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Progress({ current, total }: { current: number; total: number }) {
  return (
    <div style={s.progressWrap}>
      <div style={s.progressText}>Step {current} of {total}</div>
      <div style={s.progressTrack}>
        <div style={{ ...s.progressFill, width: `${(current / total) * 100}%` }} />
      </div>
    </div>
  );
}

const s: Record<string, CSSProperties> = {
  wrapper: {
    minHeight: "var(--app-viewport-height)",
    background:
      "radial-gradient(circle at top left, rgba(5,181,187,0.16), transparent 32%), radial-gradient(circle at top right, rgba(5,181,187,0.1), transparent 34%), linear-gradient(180deg, rgba(228,247,247,0.68), transparent 28%), var(--surface-base)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "calc(24px + var(--app-safe-top)) 16px 24px",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  card: {
    background: "rgba(255,255,255,0.94)",
    borderRadius: 24,
    padding: "32px 28px",
    width: "100%",
    maxWidth: 560,
    boxShadow: "var(--shadow-soft)",
    border: "1px solid var(--border-soft)",
  },
  header: { marginBottom: 24 },
  progressWrap: { display: "flex", flexDirection: "column", gap: 8, marginBottom: 18 },
  progressText: { color: "var(--brand-primary-deep)", fontSize: "0.78rem", fontWeight: 800 },
  progressTrack: { width: "100%", height: 8, borderRadius: 999, background: "rgba(5,181,187,0.12)", overflow: "hidden" },
  progressFill: { height: "100%", borderRadius: 999, background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)" },
  step: { fontSize: "0.75rem", fontWeight: 700, color: "var(--brand-primary-deep)", textTransform: "uppercase", letterSpacing: "0.1em" },
  title: { margin: "6px 0 4px", fontSize: "1.5rem", fontWeight: 800, color: "var(--text-primary)" },
  sub: { margin: 0, fontSize: "0.85rem", color: "var(--neutral-700)" },
  sections: { display: "flex", flexDirection: "column", gap: 18 },
  choiceSection: { display: "flex", flexDirection: "column", gap: 8 },
  sectionTitle: {
    margin: 0,
    fontSize: "0.82rem",
    fontWeight: 700,
    color: "var(--neutral-700)",
  },
  styleGrid: { display: "flex", flexWrap: "wrap", gap: 8 },
  styleBtn: {
    minHeight: 38,
    display: "inline-flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
    padding: "8px 14px",
    borderRadius: 20,
    border: "1.5px solid rgba(5,181,187,0.14)",
    background: "rgba(255,255,255,0.86)",
    color: "var(--neutral-700)",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: "0.85rem",
  },
  styleBtnActive: {
    background: "linear-gradient(135deg, rgba(5,181,187,0.18), rgba(228,247,247,0.96))",
    border: "1.5px solid rgba(5,181,187,0.12)",
    color: "var(--text-primary)",
  },
  note: { color: "var(--brand-primary-deep)", fontSize: "0.72rem", fontWeight: 800 },
  error: { margin: "12px 0 0", color: "#e05555", fontSize: "0.85rem", textAlign: "center" },
  actions: { display: "grid", gridTemplateColumns: "0.45fr 1fr", gap: 10, marginTop: 24 },
  backBtn: {
    width: "100%",
    padding: "14px 0",
    borderRadius: 14,
    border: "1.5px solid rgba(5,181,187,0.16)",
    background: "rgba(255,255,255,0.86)",
    color: "var(--neutral-700)",
    fontSize: "1rem",
    fontWeight: 800,
    cursor: "pointer",
  },
  submitBtn: {
    width: "100%",
    padding: "14px 0",
    borderRadius: 14,
    border: "1px solid rgba(5,181,187,0.18)",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontSize: "1rem",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(5,181,187,0.22)",
  },
};
