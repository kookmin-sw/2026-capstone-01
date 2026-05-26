import type { CSSProperties, ReactNode } from "react";
import React from "react";
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

const MIN_AGE = 20;
const MAX_AGE = 100;
const KOREAN_NICKNAME_MAX_LENGTH = 10;
const ENGLISH_NICKNAME_MAX_LENGTH = 20;

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
  const allowed = new Set(Object.values(map));
  return values
    .map((value) => map[value] ?? value.trim().toLowerCase())
    .filter((value) => allowed.has(value));
}

function toOnboardingPayload(data: OnboardingData) {
  return {
    travel_styles: Array.from(
      new Set(
        [
          ...mapArray(data.travelStyles, TRAVEL_STYLE_KEY),
          ...mapArray(data.foodPrefs, FOOD_KEY),
          SCHEDULE_KEY[data.schedule] ?? data.schedule,
          BUDGET_KEY[data.budget] ?? data.budget,
          WALKING_KEY[data.walking] ?? data.walking,
          ...mapArray(data.transport, TRANSPORT_KEY),
          COMPANION_KEY[data.companion] ?? data.companion,
          ...mapArray(data.activeTime, ACTIVE_TIME_KEY),
          COMMUNICATION_KEY[data.communication] ?? data.communication,
          PLANNING_KEY[data.planning] ?? data.planning,
        ]
          .map((value) => value.trim().toLowerCase())
          .filter(Boolean)
      )
    ),
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
  min,
  max,
  inputMode,
  error,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  min?: number;
  max?: number;
  inputMode?: "numeric" | "text" | "search" | "tel" | "url" | "email" | "decimal";
  error?: string;
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
        min={min}
        max={max}
        inputMode={inputMode}
        style={{
          height: 48,
          borderRadius: 50,
          border: `1px solid ${error ? "#ef4444" : GRAY2}`,
          background: error ? "rgba(239,68,68,0.06)" : GRAY1,
          outline: "none",
          padding: "0 18px",
          fontFamily: "Pretendard Variable,sans-serif",
          fontSize: 15,
          color: GRAY6,
        }}
      />
      {error ? (
        <p
          style={{
            margin: "0 4px",
            color: "#ef4444",
            fontFamily: "Pretendard Variable,sans-serif",
            fontSize: 12,
            fontWeight: 700,
            lineHeight: "16px",
          }}
        >
          {error}
        </p>
      ) : null}
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

function normalizeSignupNickname(value: string): string {
  const maxLength = getSignupNicknameMaxLength(value);
  return Array.from(value).slice(0, maxLength).join("");
}

function getSignupNicknameMaxLength(value: string): number {
  return /[가-힣]/.test(value) ? KOREAN_NICKNAME_MAX_LENGTH : ENGLISH_NICKNAME_MAX_LENGTH;
}

function getSignupNicknameError(value: string): string {
  const maxLength = getSignupNicknameMaxLength(value);
  if (Array.from(value.trim()).length <= maxLength) return "";

  return /[가-힣]/.test(value)
    ? `Nickname must be ${KOREAN_NICKNAME_MAX_LENGTH} Korean characters or fewer.`
    : `Nickname must be ${ENGLISH_NICKNAME_MAX_LENGTH} English characters or fewer.`;
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

function PrivacyPolicyContent() {
  const h2: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 700,
    color: "#111827",
    margin: "18px 0 6px",
    lineHeight: "18px",
  };
  const p: React.CSSProperties = {
    fontSize: 12,
    lineHeight: "19px",
    color: "#374151",
    margin: "0 0 6px",
  };
  const li: React.CSSProperties = {
    fontSize: 12,
    lineHeight: "19px",
    color: "#374151",
    marginBottom: 4,
  };
  const ul: React.CSSProperties = {
    paddingLeft: 16,
    margin: "4px 0 8px",
  };
  const indent: React.CSSProperties = {
    paddingLeft: 12,
    margin: "4px 0 6px",
  };
  const label: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: "#6b7280",
    display: "block",
    marginTop: 4,
  };

  return (
    <div style={{ padding: "4px 2px 8px" }}>
      <p style={{ ...p, fontWeight: 700, fontSize: 13, color: "#01c0c0", marginBottom: 12 }}>
        KRIP Privacy Policy
      </p>
      <p style={p}>
        KRIP (hereinafter, the "Company") values users' personal information and
        complies with the Personal Information Protection Act and other applicable laws.
        Through this Privacy Policy, the Company explains the purposes for which it
        processes users' personal information and how it protects and destroys such information.
      </p>

      <p style={h2}>Article 1 — Purpose of Processing Personal Information</p>
      <ul style={ul}>
        {[
          "User identification, confirmation of intent to sign up, login, and account management",
          "Service provision and delivery of personalized features",
          "Provision of menu OCR translation, travel mate matching, and AI travel itinerary planning",
          "Provision of community features such as posts and chats",
          "Responding to inquiries, delivering notices, and operating and improving the service",
          "Statistical analysis of service usage",
          "Prevention and sanctions against abnormal use such as fraudulent use and identity theft",
          "Sending push notifications (advertising only with separate consent)",
        ].map((item, i) => <li key={i} style={li}>{item}</li>)}
      </ul>

      <p style={h2}>Article 2 — Items of Personal Information Processed</p>
      <div style={indent}>
        <span style={label}>Sign-up and login</span>
        <p style={p}>Required: Email address, name, nickname, unique Google account identifier<br />
          Collection method: User input or Google OAuth authentication</p>
        <span style={label}>Automatically generated information</span>
        <p style={p}>Service usage records, access logs, IP address, device information, app version, error records</p>
        <span style={label}>Push notifications (optional)</span>
        <p style={p}>FCM device token — processed only when the user has consented</p>
        <span style={label}>Menu OCR translation</span>
        <p style={p}>Menu board images — deleted immediately after OCR processing</p>
        <span style={label}>Travel mate matching & AI planning</span>
        <p style={p}>Travel region, schedule, companion type, preferred gender, age group, search keywords, post content, chat messages</p>
      </div>

      <p style={h2}>Article 3 — Retention and Use Period</p>
      <div style={indent}>
        <span style={label}>Member information</span>
        <p style={p}>After withdrawal request: 1-month grace period (account deactivated, restoration possible). After grace period: deleted without delay.</p>
        <span style={label}>Menu board images</span>
        <p style={p}>Deleted immediately after OCR processing.</p>
        <span style={label}>Fraud prevention records</span>
        <p style={p}>Minimum necessary records retained up to 1 year after withdrawal.</p>
        <span style={label}>Retention required by law</span>
        <ul style={ul}>
          {[
            "Contracts or withdrawal records: 5 years",
            "Payment and supply records: 5 years",
            "Consumer complaints / dispute resolution: 3 years",
            "Labeling / advertising records: 6 months",
            "Website access logs: 3 months",
          ].map((item, i) => <li key={i} style={li}>{item}</li>)}
        </ul>
      </div>

      <p style={h2}>Article 4 — Procedures and Methods for Destruction</p>
      <ul style={ul}>
        <li style={li}>Electronic files: deleted using methods that prevent recovery or reproduction</li>
        <li style={li}>Paper documents: shredded or incinerated</li>
        <li style={li}>Legally required information: stored separately from other personal information</li>
      </ul>

      <p style={h2}>Article 5 — Provision of Personal Information to Third Parties</p>
      <p style={p}>
        In principle, the Company does not provide users' personal information to external parties,
        except when the user has consented, when required by law, or when investigative authorities
        request information through lawful procedures. Google OAuth authentication does not constitute
        provision to a third party.
      </p>

      <p style={h2}>Article 6 — Outsourcing of Personal Information Processing</p>
      <div style={indent}>
        <span style={label}>Google LLC</span>
        <p style={p}>Tasks: Google social login; Firebase Cloud Messaging push notifications<br />
          Items: Email, name, Google account identifier, FCM device token<br />
          Retention: Until 1 month after withdrawal or until purpose is achieved</p>
      </div>

      <p style={h2}>Article 7 — Overseas Transfer of Personal Information</p>
      <div style={indent}>
        <p style={p}>
          <b>Recipient:</b> Google LLC<br />
          <b>Country:</b> United States and other countries where Google processes data<br />
          <b>Items:</b> Email, name, Google account identifier, FCM device token<br />
          <b>Purpose:</b> Social login authentication; push notifications<br />
          <b>Retention:</b> Until 1 month after withdrawal or purpose is achieved
        </p>
      </div>

      <p style={h2}>Article 8 — Rights of Data Subjects</p>
      <p style={p}>
        Users may request access, correction, deletion, suspension of processing, or withdrawal
        of consent at any time via in-app features or by emailing the Chief Privacy Officer.
      </p>

      <p style={h2}>Article 9 — Children Under 14</p>
      <p style={p}>
        The Company does not allow children under 14 to sign up. If such information is
        inadvertently collected, it will be deleted without delay.
      </p>

      <p style={h2}>Article 10 — Advertising Information</p>
      <p style={p}>
        Advertising information is transmitted only with explicit prior consent.
        Users may withdraw consent at any time.
      </p>

      <p style={h2}>Article 11 — Cookies</p>
      <p style={p}>
        The Company may use cookies for web-based services. Users may refuse cookies
        via browser settings, though some features may be restricted as a result.
      </p>

      <p style={h2}>Article 12 — Security Measures</p>
      <ul style={ul}>
        {[
          "Minimization of access rights to personal information",
          "Training for personnel handling personal information",
          "Encryption and secure storage",
          "Technical measures against hacking and malware",
          "Retention of access records and prevention of forgery",
          "Access control for personal information processing systems",
        ].map((item, i) => <li key={i} style={li}>{item}</li>)}
      </ul>

      <p style={h2}>Article 13 — Data Breach Response</p>
      <p style={p}>
        In the event of loss, theft, or leakage of personal information, the Company will
        notify users without delay and report to the Personal Information Protection Commission
        and other relevant authorities.
      </p>

      <p style={h2}>Article 14 — Chief Privacy Officer</p>
      <div style={indent}>
        <p style={p}>
          <b>Name:</b> Wonjun Choi<br />
          <b>Title:</b> Team Lead<br />
          <b>Email:</b> gwg0813@gmail.com
        </p>
      </div>

      <p style={h2}>Article 15 — Remedies for Rights Infringement</p>
      <ul style={ul}>
        {[
          "Personal Information Dispute Mediation Committee: 1833-6972, www.kopico.go.kr",
          "Personal Information Infringement Report Center: 118, privacy.kisa.or.kr",
          "Supreme Prosecutors' Office: 1301, www.spo.go.kr",
          "National Police Agency: 182, ecrm.cyber.go.kr",
        ].map((item, i) => <li key={i} style={li}>{item}</li>)}
      </ul>

      <p style={h2}>Article 16 — Changes to the Privacy Policy</p>
      <p style={p}>
        The Company may revise this Policy due to changes in laws, service contents, or
        internal policies. Changes will be announced at least 7 days prior to the effective date
        (30 days for material changes affecting users' rights).
      </p>

      <p style={{ ...p, color: "#9ca3af", marginTop: 16, fontSize: 11 }}>
        This Privacy Policy is effective as of May 25, 2026.
      </p>
    </div>
  );
}

function PrivacyConsentPage({
  agreed,
  onAgreeChange,
  onNext,
  onBack,
}: {
  agreed: boolean;
  onAgreeChange: (value: boolean) => void;
  onNext: () => void;
  onBack: () => void;
}) {
  return (
    <PageShell onBack={onBack} showBack={false}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 4 }}>
        <QuestionTitle text={"Privacy Policy"} />
        <div style={{ padding: "0 16px" }}>
          <div
            style={{
              height: "min(58vh, 520px)",
              overflowY: "auto",
              border: `1px solid ${GRAY2}`,
              borderRadius: 18,
              background: GRAY1,
              padding: 16,
            }}
          >
            <PrivacyPolicyContent />
          </div>
        </div>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "0 18px",
            fontFamily: "Pretendard Variable,sans-serif",
            fontWeight: 700,
            fontSize: 14,
            color: GRAY6,
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={agreed}
            onChange={(event) => onAgreeChange(event.target.checked)}
            style={{ width: 18, height: 18, accentColor: MINT }}
          />
          <span>I agree to the Privacy Policy.</span>
        </label>
      </div>
      <NextButton onNext={onNext} canProceed={agreed} />
    </PageShell>
  );
}

function Page1({ data, setData, onNext, onBack, email }: PageProps) {
  const isAgeValid = Boolean(data.age);
  const ageError = "";
  const canProceed =
    data.nickname.trim().length > 0 &&
    isAgeValid &&
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
        <TextInput
          label="Nickname *"
          value={data.nickname}
          onChange={(v) => setData({ nickname: normalizeSignupNickname(v) })}
          placeholder="What should we call you?"
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "0 16px" }}>
          <label
            style={{
              fontFamily: "Pretendard Variable,sans-serif",
              fontWeight: 700,
              fontSize: 13,
              color: DARK_MINT,
            }}
          >
            Age *
          </label>
          <select
            value={data.age}
            onChange={(e) => setData({ age: e.target.value })}
            style={{
              height: 48,
              borderRadius: 50,
              border: `1px solid ${ageError ? "#ef4444" : GRAY2}`,
              background: ageError ? "rgba(239,68,68,0.06)" : GRAY1,
              outline: "none",
              padding: "0 18px",
              fontFamily: "Pretendard Variable,sans-serif",
              fontSize: 15,
              color: data.age ? GRAY6 : GRAY_AAA,
              appearance: "none",
              WebkitAppearance: "none",
              cursor: "pointer",
            }}
          >
            <option value="" disabled hidden>Select your age</option>
            {Array.from({ length: MAX_AGE - MIN_AGE + 1 }, (_, i) => {
              const age = MIN_AGE + i;
              return (
                <option key={age} value={String(age)} style={{ color: GRAY6 }}>
                  {age}
                </option>
              );
            })}
          </select>
          {ageError ? (
            <p
              style={{
                margin: "0 4px",
                color: "#ef4444",
                fontFamily: "Pretendard Variable,sans-serif",
                fontSize: 12,
                fontWeight: 700,
                lineHeight: "16px",
              }}
            >
              {ageError}
            </p>
          ) : null}
        </div>
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

const FOOD_PREFS = ["Halal", "Vegetarian", "Foodie", "Cafe Lover"];
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
const TRANSPORT_OPTS = ["Public Transit", "Car", "Taxi"];
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
  const [privacyAgreed, setPrivacyAgreed] = useState(false);
  const [data, setDataState] = useState<OnboardingData>({
    ...EMPTY,
    nickname: normalizeSignupNickname(initialNickname),
  });

  const setData = (patch: Partial<OnboardingData>) =>
    setDataState((prev) => ({ ...prev, ...patch }));
  const next = () => setStep((s) => Math.min(s + 1, 4));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  async function handleComplete(): Promise<void> {
    if (!email) { setError("Email is missing. Please log in again."); return; }
    const nicknameError = getSignupNicknameError(data.nickname);
    if (nicknameError) {
      setError(nicknameError);
      setDone(false);
      setStep(0);
      return;
    }
    const age = Number(data.age);
    if (!Number.isInteger(age) || age < MIN_AGE || age > MAX_AGE) {
      setError(`Age must be between ${MIN_AGE} and ${MAX_AGE}.`);
      setDone(false);
      setStep(0);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await registerUser({
        email,
        user_name: normalizeSignupNickname(data.nickname),
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

  if (!privacyAgreed) {
    return (
      <PrivacyConsentPage
        agreed={privacyAgreed}
        onAgreeChange={setPrivacyAgreed}
        onNext={() => setPrivacyAgreed(true)}
        onBack={() => navigate("/login")}
      />
    );
  }

  const pages = [
    <Page1 key={0} data={data} setData={setData} onNext={next} onBack={back} email={email} />,
    <Page2 key={1} data={data} setData={setData} onNext={next} onBack={back} />,
    <Page3 key={2} data={data} setData={setData} onNext={next} onBack={back} />,
    <Page4 key={3} data={data} setData={setData} onNext={next} onBack={back} />,
    <Page5 key={4} data={data} setData={setData} onNext={() => setDone(true)} onBack={back} />,
  ];

  return <>{pages[step]}</>;
}
