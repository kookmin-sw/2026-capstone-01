import type { CSSProperties, ReactNode } from "react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

interface RegisterLocationState {
  email?: string;
  name?: string;
  registerForm?: RegisterFormState;
}

export interface RegisterFormState {
  email: string;
  user_name: string;
  phone_number: string;
  age: string;
  gender: string;
  nationality: string;
}

const MIN_AGE = 0;
const MAX_AGE = 149;
const KOREAN_NAME_MAX_LENGTH = 10;
const ENGLISH_NAME_MAX_LENGTH = 20;

export default function RegisterPage() {
  const navigate = useNavigate();
  const { state } = useLocation() as { state: RegisterLocationState | null };
  const [loading] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState<RegisterFormState>({
    email: state?.registerForm?.email || state?.email || "",
    user_name: normalizeSignupName(state?.registerForm?.user_name || state?.name || ""),
    phone_number: state?.registerForm?.phone_number || "",
    age: state?.registerForm?.age || "",
    gender: state?.registerForm?.gender || "",
    nationality: state?.registerForm?.nationality || "korea",
  });

  function setField<Key extends keyof RegisterFormState>(
    key: Key,
    value: RegisterFormState[Key]
  ): void {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function handleNext(): void {
    setError("");
    if (!form.email || !form.user_name || !form.phone_number || !form.age || !form.gender || !form.nationality) {
      setError("Please fill in all required fields.");
      return;
    }

    const nameError = getSignupNameError(form.user_name);
    if (nameError) {
      setError(nameError);
      return;
    }

    const age = Number(form.age);
    if (!Number.isInteger(age) || age < MIN_AGE || age > MAX_AGE) {
      setError(`Age must be between ${MIN_AGE} and ${MAX_AGE}.`);
      return;
    }

    navigate("/register/onboarding", { state: { registerForm: form } });
  }

  return (
    <div style={s.wrapper}>
      <div style={s.card}>
        <div style={s.header}>
          <Progress current={1} total={2} />
          <span style={s.step}>Sign Up</span>
          <h2 style={s.title}>Traveler Details</h2>
          <p style={s.sub}>Tell us a little about yourself to personalize your trip.</p>
        </div>

        <div style={s.fields}>
          <Field label="Email *">
            <input
              style={s.input}
              type="email"
              value={form.email}
              onChange={(e) => setField("email", e.target.value)}
              placeholder="example@gmail.com"
            />
          </Field>

          <Field label="Name *">
            <input
              style={s.input}
              value={form.user_name}
              onChange={(e) => setField("user_name", normalizeSignupName(e.target.value))}
              placeholder="Your name"
            />
          </Field>

          <Field label="Phone Number *">
            <input
              style={s.input}
              type="tel"
              value={form.phone_number}
              onChange={(e) => setField("phone_number", e.target.value)}
              placeholder="+82 10-1234-5678"
            />
          </Field>

          <div style={s.twoColumn}>
            <Field label="Age *">
              <input
                style={s.input}
                type="number"
                value={form.age}
                onChange={(e) => setField("age", normalizeAgeInput(e.target.value))}
                placeholder="25"
                min={MIN_AGE}
                max={MAX_AGE}
                inputMode="numeric"
              />
            </Field>

            <Field label="Gender *">
              <div style={s.segmentRow}>
                {[
                  ["male", "Male"],
                  ["female", "Female"],
                ].map(([val, label]) => (
                  <button
                    type="button"
                    key={val}
                    style={{ ...s.genderBtn, ...(form.gender === val ? s.genderBtnActive : {}) }}
                    onClick={() => setField("gender", val)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </Field>
          </div>

          <Field label="Nationality *">
            <select
              style={s.input}
              value={form.nationality}
              onChange={(e) => setField("nationality", e.target.value)}
            >
              <option value="korea">Korea</option>
              <option value="japan">Japan</option>
              <option value="china">China</option>
              <option value="usa">United States</option>
              <option value="other">Other</option>
            </select>
          </Field>
        </div>

        {error && <p style={s.error}>{error}</p>}

        <button style={{ ...s.submitBtn, opacity: loading ? 0.7 : 1 }} onClick={handleNext} disabled={loading}>
          Next Page
        </button>
      </div>
    </div>
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

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div style={s.field}>
      <label style={s.label}>{label}</label>
      {children}
    </div>
  );
}

function normalizeAgeInput(value: string): string {
  const digitsOnly = value.replace(/\D/g, "");
  if (!digitsOnly) return "";

  const age = Number(digitsOnly);
  if (!Number.isFinite(age)) return "";

  return String(Math.min(Math.max(age, MIN_AGE), MAX_AGE));
}

function normalizeSignupName(value: string): string {
  const maxLength = getSignupNameMaxLength(value);
  return Array.from(value).slice(0, maxLength).join("");
}

function getSignupNameMaxLength(value: string): number {
  return /[가-힣]/.test(value) ? KOREAN_NAME_MAX_LENGTH : ENGLISH_NAME_MAX_LENGTH;
}

function getSignupNameError(value: string): string {
  const maxLength = getSignupNameMaxLength(value);
  if (Array.from(value.trim()).length <= maxLength) return "";

  return /[가-힣]/.test(value)
    ? `Name must be ${KOREAN_NAME_MAX_LENGTH} Korean characters or fewer.`
    : `Name must be ${ENGLISH_NAME_MAX_LENGTH} English characters or fewer.`;
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
    maxWidth: 420,
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
  fields: { display: "flex", flexDirection: "column", gap: 16 },
  field: { display: "flex", flexDirection: "column", gap: 6 },
  label: {
    fontSize: "0.8rem",
    fontWeight: 600,
    color: "var(--neutral-700)",
    letterSpacing: "0.03em",
  },
  input: {
    width: "100%",
    padding: "11px 14px",
    borderRadius: 10,
    border: "1.5px solid rgba(5,181,187,0.16)",
    fontSize: "0.95rem",
    outline: "none",
    background: "var(--surface-muted)",
    color: "var(--text-primary)",
    boxSizing: "border-box",
  },
  twoColumn: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 12,
  },
  segmentRow: { display: "flex", gap: 8 },
  genderBtn: {
    flex: 1,
    padding: "11px 0",
    borderRadius: 10,
    border: "1.5px solid rgba(5,181,187,0.14)",
    background: "rgba(255,255,255,0.86)",
    color: "var(--neutral-700)",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: "0.9rem",
  },
  genderBtnActive: {
    background: "linear-gradient(135deg, rgba(5,181,187,0.2), rgba(228,247,247,0.96))",
    border: "1.5px solid rgba(5,181,187,0.12)",
    color: "var(--text-primary)",
  },
  error: { margin: "12px 0 0", color: "#e05555", fontSize: "0.85rem", textAlign: "center" },
  submitBtn: {
    marginTop: 24,
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
