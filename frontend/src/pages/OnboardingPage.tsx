import type { ReactNode } from "react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { registerUser } from "../api/auth/auth";

const MINT = "#01c0c0";
const DARK_MINT = "#008888";
const GOLD = "#936b00";
const PURPLE = "#6b4fa8";
const GRAY1 = "#f6f6f6";
const GRAY2 = "#eaeaea";
const GRAY4 = "#848484";
const GRAY5 = "#4d4d4d";
const GRAY6 = "#222";
const GRAY_AAA = "#aaa";

const imgPlane = "/krip_register_plane.png";
const imgLogo = "/krip_register_logo.png";

// LoginPage sends { email, name } — RegisterPage (legacy) sent { registerForm }
type RegisterLocationState = {
  email?: string;
  name?: string;
  registerForm?: Record<string, unknown>;
} | null;

export interface OnboardingData {
  nickname: string;
  age: string;
  gender: string;
  travelStyles: string[];
  foodPrefs: string[];
  budget: string;
  walking: string;
  schedule: string;
  transport: string[];
  activeTime: string[];
  companion: string;
  communication: string;
  planning: string;
}

// ─── Value → API key maps ────────────────────────────────────────────────────

const TRAVEL_STYLE_KEY: Record<string, string> = {
  Activity: "activity",
  "Famous Attractions": "famous_attractions",
  Healing: "healing",
  "Culture & History": "culture_history",
  Shopping: "shopping",
  "Food Tour": "food_tour",
  "Photo Aesthetic": "photo_aesthetic",
  "Festival & Event": "festival_event",
  Nature: "nature",
  Traditional: "traditional",
  Trekking: "trekking",
  "Hidden Gems": "hidden_gems",
  "Art Exhibition": "art_exhibition",
  "Theme Park": "theme_park",
};

const FOOD_KEY: Record<string, string> = {
  Halal: "food_halal",
  Vegetarian: "food_vegetarian",
  Foodie: "foodie",
  "Cafe Lover": "cafe_lover",
  "No Preference": "food_no_preference",
};

const SCHEDULE_KEY: Record<string, string> = {
  Relaxed: "density_relaxed",
  Packed: "density_packed",
};

const BUDGET_KEY: Record<string, string> = {
  Saving: "budget_saving",
  Moderate: "budget_moderate",
  Premium: "budget_premium",
};

const WALKING_KEY: Record<string, string> = {
  Low: "walking_low",
  Medium: "walking_medium",
  High: "walking_high",
};

const TRANSPORT_KEY: Record<string, string> = {
  "Public Transit": "transport_public",
  Car: "transport_car",
  Taxi: "transport_taxi",
  Walking: "transport_walking",
  Bicycle: "transport_bicycle",
};

const ACTIVE_TIME_KEY: Record<string, string> = {
  Daytime: "daytime",
  Nightlife: "nightlife",
  "Night View": "night_view",
};

const COMPANION_KEY: Record<string, string> = {
  Independent: "companion_independent",
  Together: "companion_together",
  Flexible: "companion_flexible",
};

const COMMUNICATION_KEY: Record<string, string> = {
  "High Communication": "communication_high",
  "Low Communication": "communication_low",
};

const PLANNING_KEY: Record<string, string> = {
  Planner: "planner",
  Spontaneous: "spontaneous",
  Follower: "follower",
};

function mapArray(values: string[], map: Record<string, string>): string[] {
  return values.map((v) => map[v] ?? v);
}

function toOnboardingPayload(data: OnboardingData) {
  return {
    travel_styles: mapArray(data.travelStyles, TRAVEL_STYLE_KEY),
    food_preferences: mapArray(data.foodPrefs, FOOD_KEY),
    density_preference: SCHEDULE_KEY[data.schedule] ?? data.schedule,
    budget_preference: BUDGET_KEY[data.budget] ?? data.budget,
    walking_preference: WALKING_KEY[data.walking] ?? data.walking,
    transport_preferences: mapArray(data.transport, TRANSPORT_KEY),
    companion_preference: COMPANION_KEY[data.companion] ?? data.companion,
    time_preferences: mapArray(data.activeTime, ACTIVE_TIME_KEY),
    communication_preference: COMMUNICATION_KEY[data.communication] ?? data.communication,
    planning_preference: PLANNING_KEY[data.planning] ?? data.planning,
  };
}

// ─── Shared UI components ────────────────────────────────────────────────────

function StepDots({ current, total }: { current: number; total: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 16px" }}>
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          style={{
            width: i === current ? 12 : 8,
            height: i === current ? 12 : 8,
            borderRadius: "50%",
            background: i === current ? MINT : GRAY2,
            transition: "all 0.25s",
            flexShrink: 0,
          }}
        />
      ))}
    </div>
  );
}

function QuestionTitle({ text }: { text: string }) {
  return (
    <div style={{ padding: "0 16px" }}>
      <p
        style={{
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 700,
          fontSize: 24,
          color: GRAY6,
          lineHeight: "32px",
          margin: 0,
          whiteSpace: "pre-line",
        }}
      >
        {text}
      </p>
    </div>
  );
}

function SectionLabel({ text, color = DARK_MINT }: { text: string; color?: string }) {
  return (
    <div style={{ padding: "0 16px" }}>
      <p
        style={{
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 700,
          fontSize: 13,
          color,
          margin: 0,
          lineHeight: "16px",
        }}
      >
        {text}
      </p>
    </div>
  );
}

function Chip({
  label,
  selected,
  onClick,
  accentColor = MINT,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
  accentColor?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        height: 36,
        padding: "0 14px",
        borderRadius: 100,
        cursor: "pointer",
        border: selected ? `1.5px solid ${accentColor}` : `1px solid ${GRAY2}`,
        background: selected ? `${accentColor}18` : "#fff",
        fontFamily: "Pretendard Variable,sans-serif",
        fontWeight: 600,
        fontSize: 13,
        color: selected ? accentColor : GRAY5,
        whiteSpace: "nowrap",
        transition: "all 0.15s",
        flexShrink: 0,
      }}
    >
      {label}
    </button>
  );
}

function BudgetCard({
  title,
  sub,
  selected,
  onClick,
}: {
  title: string;
  sub: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        border: selected ? `1.5px solid ${MINT}` : `1px solid ${GRAY2}`,
        background: selected ? `${MINT}14` : "#fff",
        borderRadius: 16,
        padding: "10px 8px",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        transition: "all 0.15s",
        gap: 2,
      }}
    >
      <span
        style={{
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 700,
          fontSize: 13,
          color: selected ? MINT : GRAY5,
        }}
      >
        {title}
      </span>
      <span
        style={{
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 400,
          fontSize: 11,
          color: GRAY4,
        }}
      >
        {sub}
      </span>
    </button>
  );
}

function NextButton({
  onNext,
  canProceed,
  label = "Next",
}: {
  onNext: () => void;
  canProceed: boolean;
  label?: string;
}) {
  return (
    <div style={{ padding: "0 17px 32px", flexShrink: 0 }}>
      <button
        type="button"
        onClick={canProceed ? onNext : undefined}
        style={{
          width: "100%",
          height: 56,
          borderRadius: 50,
          border: "none",
          background: canProceed ? MINT : GRAY2,
          cursor: canProceed ? "pointer" : "default",
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 700,
          fontSize: 17,
          color: canProceed ? "#fff" : GRAY_AAA,
          transition: "all 0.2s",
        }}
      >
        {label}
      </button>
    </div>
  );
}

function ChipRow({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "0 16px" }}>
      {children}
    </div>
  );
}

function TextInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "0 16px" }}>
      <label
        style={{
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 700,
          fontSize: 13,
          color: DARK_MINT,
        }}
      >
        {label}
      </label>
      <input
        type={type}
        value={value}
        name={label.toLowerCase().replace(/[^a-z0-9]+/g, "_")}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          height: 48,
          borderRadius: 50,
          border: `1px solid ${GRAY2}`,
          background: GRAY1,
          outline: "none",
          padding: "0 18px",
          fontFamily: "Pretendard Variable,sans-serif",
          fontSize: 15,
          color: GRAY6,
        }}
      />
    </div>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "0 16px" }}>
      <label
        style={{
          fontFamily: "Pretendard Variable,sans-serif",
          fontWeight: 700,
          fontSize: 13,
          color: DARK_MINT,
        }}
      >
        {label}
      </label>
      <div
        style={{
          height: 48,
          borderRadius: 50,
          border: `1px solid ${GRAY2}`,
          background: GRAY2,
          padding: "0 18px",
          display: "flex",
          alignItems: "center",
          fontFamily: "Pretendard Variable,sans-serif",
          fontSize: 15,
          color: GRAY4,
          userSelect: "none",
        }}
      >
        {value}
      </div>
    </div>
  );
}

function PageShell({
  children,
  onBack,
  showBack = true,
}: {
  children: ReactNode;
  onBack?: () => void;
  showBack?: boolean;
}) {
  return (
    <div
      style={{
        minHeight: "var(--app-viewport-height, 100vh)",
        width: "100%",
        background: "#fff",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {showBack && (
        <div style={{ padding: "16px 6px 4px", flexShrink: 0 }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "10px 10px",
            }}
          >
            <svg width="11" height="20" viewBox="0 0 11 20" fill="none">
              <path
                d="M9.5 1.5L1.5 10l8 8.5"
                stroke={GRAY6}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      )}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          scrollbarWidth: "none",
          paddingTop: showBack ? 0 : 28,
        }}
      >
        {children}
      </div>
    </div>
  );
}

// ─── Page components ─────────────────────────────────────────────────────────

type PageProps = {
  data: OnboardingData;
  setData: (d: Partial<OnboardingData>) => void;
  onNext: () => void;
  onBack: () => void;
  email?: string;
};

function Page1({ data, setData, onNext, onBack, email }: PageProps) {
  const canProceed =
    data.nickname.trim().length > 0 &&
    data.age.trim().length > 0 &&
    data.gender.length > 0;

  return (
    <PageShell onBack={onBack} showBack={false}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 4 }}>
        <StepDots current={0} total={5} />
        <QuestionTitle text={"Tell us a little\nabout yourself!"} />
        <div style={{ padding: "0 16px" }}>
          <span style={{ fontFamily: "Pretendard Variable,sans-serif", fontWeight: 700, fontSize: 11, color: MINT, letterSpacing: 1.2 }}>
            ONBOARDING
          </span>
        </div>
        {email ? <ReadOnlyField label="Email" value={email} /> : null}
        <TextInput label="Nickname *" value={data.nickname} onChange={(v) => setData({ nickname: v })} placeholder="What should we call you?" />
        <TextInput label="Age *" value={data.age} onChange={(v) => setData({ age: v })} placeholder="Enter your age" type="number" />
        <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "0 16px" }}>
          <span style={{ fontFamily: "Pretendard Variable,sans-serif", fontWeight: 700, fontSize: 13, color: DARK_MINT }}>
            Gender *
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            {["Male", "Female"].map((g) => (
              <Chip key={g} label={g} selected={data.gender === g} onClick={() => setData({ gender: g })} />
            ))}
          </div>
        </div>
        <div style={{ height: 20 }} />
      </div>
      <NextButton onNext={onNext} canProceed={canProceed} />
    </PageShell>
  );
}

const TRAVEL_STYLES = [
  "Activity", "Famous Attractions", "Healing", "Culture & History", "Shopping",
  "Food Tour", "Photo Aesthetic", "Festival & Event", "Nature", "Traditional",
  "Trekking", "Hidden Gems", "Art Exhibition", "Theme Park",
];

function Page2({ data, setData, onNext, onBack }: PageProps) {
  const toggle = (s: string) => {
    const arr = data.travelStyles;
    setData({ travelStyles: arr.includes(s) ? arr.filter((x) => x !== s) : [...arr, s] });
  };
  return (
    <PageShell onBack={onBack}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 4, paddingBottom: 24 }}>
        <StepDots current={1} total={5} />
        <QuestionTitle text={"What is your preferred\ntravel style?"} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Travel Styles" color={DARK_MINT} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Multiple choice</div>
          <ChipRow>
            {TRAVEL_STYLES.map((s) => (
              <Chip key={s} label={s} selected={data.travelStyles.includes(s)} onClick={() => toggle(s)} />
            ))}
          </ChipRow>
        </div>
      </div>
      <NextButton onNext={onNext} canProceed={data.travelStyles.length > 0} />
    </PageShell>
  );
}

const FOOD_PREFS = ["Halal", "Vegetarian", "Foodie", "Cafe Lover", "No Preference"];
const WALKING_OPTS = ["Low", "Medium", "High"];
const BUDGET_OPTS = [
  { title: "Saving", sub: "$40-$70 / day" },
  { title: "Moderate", sub: "$100-$200 / day" },
  { title: "Premium", sub: "$250+ / day" },
];

function Page3({ data, setData, onNext, onBack }: PageProps) {
  const toggleFood = (s: string) => {
    const arr = data.foodPrefs;
    setData({ foodPrefs: arr.includes(s) ? arr.filter((x) => x !== s) : [...arr, s] });
  };
  const canProceed = data.foodPrefs.length > 0 && data.budget.length > 0 && data.walking.length > 0;
  return (
    <PageShell onBack={onBack}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 4, paddingBottom: 24 }}>
        <StepDots current={2} total={5} />
        <QuestionTitle text={"What are your food\nand budget preferences?"} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Food Preferences" color={DARK_MINT} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Multiple choice</div>
          <ChipRow>
            {FOOD_PREFS.map((f) => (
              <Chip key={f} label={f} selected={data.foodPrefs.includes(f)} onClick={() => toggleFood(f)} />
            ))}
          </ChipRow>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Budget" color={GOLD} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Choose one</div>
          <div style={{ display: "flex", gap: 8, padding: "0 16px" }}>
            {BUDGET_OPTS.map((b) => (
              <BudgetCard key={b.title} title={b.title} sub={b.sub} selected={data.budget === b.title} onClick={() => setData({ budget: b.title })} />
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Walking Preference" color={DARK_MINT} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Choose one</div>
          <ChipRow>
            {WALKING_OPTS.map((w) => (
              <Chip key={w} label={w} selected={data.walking === w} onClick={() => setData({ walking: w })} />
            ))}
          </ChipRow>
        </div>
      </div>
      <NextButton onNext={onNext} canProceed={canProceed} />
    </PageShell>
  );
}

const SCHEDULE_OPTS = ["Relaxed", "Packed"];
const TRANSPORT_OPTS = ["Public Transit", "Car", "Taxi", "Walking", "Bicycle"];
const ACTIVE_TIME_OPTS = ["Daytime", "Nightlife", "Night View"];

function Page4({ data, setData, onNext, onBack }: PageProps) {
  const toggleTransport = (s: string) => {
    const arr = data.transport;
    setData({ transport: arr.includes(s) ? arr.filter((x) => x !== s) : [...arr, s] });
  };
  const toggleActive = (s: string) => {
    const arr = data.activeTime;
    setData({ activeTime: arr.includes(s) ? arr.filter((x) => x !== s) : [...arr, s] });
  };
  const canProceed = data.schedule.length > 0 && data.transport.length > 0 && data.activeTime.length > 0;
  return (
    <PageShell onBack={onBack}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 4, paddingBottom: 24 }}>
        <StepDots current={3} total={5} />
        <QuestionTitle text={"How do you travel\nday to day?"} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Schedule Density" color={GOLD} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Choose one</div>
          <ChipRow>
            {SCHEDULE_OPTS.map((s) => (
              <Chip key={s} label={s} selected={data.schedule === s} onClick={() => setData({ schedule: s })} accentColor={GOLD} />
            ))}
          </ChipRow>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Transportation" color={DARK_MINT} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Multiple choice</div>
          <ChipRow>
            {TRANSPORT_OPTS.map((t) => (
              <Chip key={t} label={t} selected={data.transport.includes(t)} onClick={() => toggleTransport(t)} />
            ))}
          </ChipRow>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Active Time" color={PURPLE} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Multiple choice</div>
          <ChipRow>
            {ACTIVE_TIME_OPTS.map((a) => (
              <Chip key={a} label={a} selected={data.activeTime.includes(a)} onClick={() => toggleActive(a)} accentColor={PURPLE} />
            ))}
          </ChipRow>
        </div>
      </div>
      <NextButton onNext={onNext} canProceed={canProceed} />
    </PageShell>
  );
}

const COMPANION_OPTS = ["Independent", "Together", "Flexible"];
const COMMUNICATION_OPTS = ["High Communication", "Low Communication"];
const PLANNING_OPTS = ["Planner", "Spontaneous", "Follower"];

function Page5({ data, setData, onNext, onBack }: PageProps) {
  const canProceed = data.companion.length > 0 && data.communication.length > 0 && data.planning.length > 0;
  return (
    <PageShell onBack={onBack}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 4, paddingBottom: 24 }}>
        <StepDots current={4} total={5} />
        <QuestionTitle text={"Last step! How do\nyou like to travel?"} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Companion Style" color={DARK_MINT} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Choose one</div>
          <ChipRow>
            {COMPANION_OPTS.map((c) => (
              <Chip key={c} label={c} selected={data.companion === c} onClick={() => setData({ companion: c })} />
            ))}
          </ChipRow>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Communication Style" color={GOLD} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Choose one</div>
          <ChipRow>
            {COMMUNICATION_OPTS.map((c) => (
              <Chip key={c} label={c} selected={data.communication === c} onClick={() => setData({ communication: c })} accentColor={GOLD} />
            ))}
          </ChipRow>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SectionLabel text="Planning Style" color={PURPLE} />
          <div style={{ padding: "0 16px 4px", fontFamily: "Pretendard Variable,sans-serif", fontSize: 12, color: GRAY4 }}>Choose one</div>
          <ChipRow>
            {PLANNING_OPTS.map((p) => (
              <Chip key={p} label={p} selected={data.planning === p} onClick={() => setData({ planning: p })} accentColor={PURPLE} />
            ))}
          </ChipRow>
        </div>
      </div>
      <NextButton onNext={onNext} canProceed={canProceed} label="Finish" />
    </PageShell>
  );
}

// ─── Complete page ────────────────────────────────────────────────────────────

function CompletePage({ onStart, loading, error }: { onStart: () => void; loading: boolean; error: string }) {
  return (
    <div style={{ minHeight: "var(--app-viewport-height, 100vh)", width: "100%", background: "linear-gradient(157deg, rgba(1,192,192,0.55) 0%, rgba(199,245,245,1) 40%, rgba(255,251,239,0.6) 100%)", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "56px 24px 0", flexShrink: 0 }}>
        <p style={{ fontFamily: "Pretendard Variable,sans-serif", fontWeight: 700, fontSize: 32, color: "#fff", lineHeight: "38px", margin: 0 }}>
          {"Let's start traveling"}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
          <p style={{ fontFamily: "Pretendard Variable,sans-serif", fontWeight: 700, fontSize: 32, color: "#fff", lineHeight: "38px", margin: 0 }}>with</p>
          <img src={imgLogo} alt="Krip" style={{ height: 28, objectFit: "contain" }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
        </div>
      </div>
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 24px" }}>
        <img src={imgPlane} alt="" style={{ width: "100%", maxWidth: 340, objectFit: "contain" }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
      </div>
      {error ? (
        <div style={{ margin: "0 24px 12px", padding: "10px 16px", background: "rgba(220,38,38,0.12)", borderRadius: 12, color: "#c00", fontFamily: "Pretendard Variable,sans-serif", fontSize: 13, textAlign: "center" }}>
          {error}
        </div>
      ) : null}
      <div style={{ padding: "0 24px 48px", flexShrink: 0 }}>
        <button type="button" onClick={loading ? undefined : onStart} style={{ width: "100%", height: 56, borderRadius: 50, border: "none", background: loading ? GRAY2 : MINT, cursor: loading ? "default" : "pointer", fontFamily: "Pretendard Variable,sans-serif", fontWeight: 700, fontSize: 17, color: loading ? GRAY_AAA : "#fff", transition: "all 0.2s" }}>
          {loading ? "Signing up…" : "Start Traveling"}
        </button>
      </div>
    </div>
  );
}

// ─── Root ────────────────────────────────────────────────────────────────────

const EMPTY: OnboardingData = {
  nickname: "", age: "", gender: "",
  travelStyles: [], foodPrefs: [], budget: "", walking: "",
  schedule: "", transport: [], activeTime: [],
  companion: "", communication: "", planning: "",
};

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { state } = useLocation() as { state: RegisterLocationState };

  const email =
    state?.email ??
    (state?.registerForm?.email as string | undefined) ??
    "";
  const initialNickname =
    state?.name ??
    (state?.registerForm?.user_name as string | undefined) ??
    "";

  const [step, setStep] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setDataState] = useState<OnboardingData>({ ...EMPTY, nickname: initialNickname });

  const setData = (patch: Partial<OnboardingData>) =>
    setDataState((prev) => ({ ...prev, ...patch }));
  const next = () => setStep((s) => Math.min(s + 1, 4));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  async function handleComplete(): Promise<void> {
    if (!email) { setError("Email is missing. Please log in again."); return; }
    setLoading(true);
    setError("");
    try {
      await registerUser({
        email,
        user_name: data.nickname,
        phone_number: "",
        age: Number(data.age),
        gender: data.gender.toLowerCase(),
        nationality: "korea",
        ...toOnboardingPayload(data),
      });
      navigate("/home");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!email) {
    navigate("/login", { replace: true });
    return null;
  }

  if (done) {
    return <CompletePage onStart={() => void handleComplete()} loading={loading} error={error} />;
  }

  const pages = [
    <Page1 key={0} data={data} setData={setData} onNext={next} onBack={() => navigate("/login")} email={email} />,
    <Page2 key={1} data={data} setData={setData} onNext={next} onBack={back} />,
    <Page3 key={2} data={data} setData={setData} onNext={next} onBack={back} />,
    <Page4 key={3} data={data} setData={setData} onNext={next} onBack={back} />,
    <Page5 key={4} data={data} setData={setData} onNext={() => setDone(true)} onBack={back} />,
  ];

  return <>{pages[step]}</>;
}
