import type { CSSProperties } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cancelWithdrawUser, logoutUser } from "../api/auth/auth";
import { showAppToast } from "../utils/appToast";

export default function WithdrawalPendingPage() {
  const navigate = useNavigate();
  const [isCancelling, setIsCancelling] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState("");

  async function handleCancelWithdrawal(): Promise<void> {
    if (isCancelling) return;

    setError("");
    setIsCancelling(true);

    try {
      await cancelWithdrawUser();
      navigate("/home", { replace: true });
    } catch (cancelError) {
      setError(toErrorMessage(cancelError, "Failed to cancel account deletion."));
      setIsCancelling(false);
    }
  }

  async function handleKeepWithdrawal(): Promise<void> {
    if (isLoggingOut) return;

    setError("");
    setIsLoggingOut(true);

    try {
      await logoutUser();
    } catch {
      // Even if logout fails, leave the protected session screen.
    } finally {
      showAppToast({ title: "Logged out", variant: "success" });
      navigate("/login", { replace: true });
    }
  }

  return (
    <div style={styles.page}>
      <section style={styles.card}>
        <span style={styles.eyebrow}>Account Recovery</span>
        <h1 style={styles.title}>Account deletion is in progress</h1>
        <p style={styles.description}>
          Your account is currently in the 30-day deletion grace period. You can
          restore it now, or keep the deletion request and sign out.
        </p>

        {error ? <p style={styles.error}>{error}</p> : null}

        <div style={styles.actions}>
          <button
            type="button"
            style={{
              ...styles.primaryButton,
              ...(isCancelling ? styles.buttonDisabled : {}),
            }}
            onClick={() => void handleCancelWithdrawal()}
            disabled={isCancelling || isLoggingOut}
          >
            {isCancelling ? "Restoring..." : "Cancel Deletion"}
          </button>
          <button
            type="button"
            style={{
              ...styles.secondaryButton,
              ...(isLoggingOut ? styles.buttonDisabled : {}),
            }}
            onClick={() => void handleKeepWithdrawal()}
            disabled={isCancelling || isLoggingOut}
          >
            {isLoggingOut ? "Signing out..." : "Keep Deletion"}
          </button>
        </div>
      </section>
    </div>
  );
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as { message?: string };
  return apiError.message || fallback;
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100dvh",
    padding: "24px 16px",
    display: "grid",
    placeItems: "center",
    background:
      "linear-gradient(180deg, rgba(228,247,247,0.72), rgba(255,255,255,0.98))",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  card: {
    width: "min(100%, 430px)",
    padding: "30px 24px",
    borderRadius: 24,
    background: "rgba(255,255,255,0.96)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  eyebrow: {
    display: "block",
    color: "var(--brand-primary-deep)",
    fontSize: "0.76rem",
    fontWeight: 900,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
  },
  title: {
    margin: "10px 0 0",
    color: "var(--text-primary)",
    fontSize: "1.65rem",
    lineHeight: 1.16,
  },
  description: {
    margin: "12px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.96rem",
    lineHeight: 1.62,
  },
  error: {
    margin: "16px 0 0",
    padding: "12px 14px",
    borderRadius: 16,
    background: "rgba(239,68,68,0.1)",
    color: "#dc2626",
    fontSize: "0.88rem",
    fontWeight: 800,
  },
  actions: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    marginTop: 24,
  },
  primaryButton: {
    minHeight: 50,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 16,
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontSize: "0.98rem",
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(5,181,187,0.22)",
  },
  secondaryButton: {
    minHeight: 50,
    border: "1px solid rgba(220,38,38,0.18)",
    borderRadius: 16,
    background: "#ffffff",
    color: "#dc2626",
    fontSize: "0.98rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  buttonDisabled: {
    opacity: 0.62,
    cursor: "not-allowed",
  },
};
