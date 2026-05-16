import type { CSSProperties } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { withdrawUser } from "../api/auth/auth";
import { showAppToast } from "../utils/appToast";

export default function DeleteAccountTermsPage() {
  const navigate = useNavigate();
  const [agreed, setAgreed] = useState(false);
  const [isWithdrawing, setIsWithdrawing] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  async function handleWithdraw(): Promise<void> {
    if (isWithdrawing) return;

    setIsWithdrawing(true);
    try {
      await withdrawUser();
      showAppToast({ title: "Account deleted", variant: "success" });
      navigate("/login", { replace: true });
    } catch (error) {
      showAppToast({
        title: "Account withdrawal failed",
        message: toErrorMessage(error, "Please try again."),
        variant: "error",
      });
      setIsWithdrawing(false);
    }
  }

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <button
          type="button"
          style={styles.backButton}
          onClick={() => navigate(-1)}
          aria-label="Go back"
        >
          ‹
        </button>
        <h1 style={styles.title}>Delete Account</h1>
      </header>

      <main style={styles.content}>
        <p style={styles.description}>
          Please review the account deletion terms before continuing.
        </p>
        <section style={styles.pdfFrame} aria-label="Account deletion terms PDF">
          <iframe
            src="/docs/deletion.pdf#zoom=44"
            title="Account Deletion Terms"
            style={styles.pdf}
          />
        </section>
        <label style={styles.checkboxRow}>
          <input
            type="checkbox"
            checked={agreed}
            onChange={(event) => setAgreed(event.target.checked)}
            style={styles.checkbox}
          />
          <span>I agree to the Account Deletion Terms.</span>
        </label>
        <button
          type="button"
          style={{
            ...styles.deleteButton,
            ...(!agreed || isWithdrawing ? styles.deleteButtonDisabled : {}),
          }}
          disabled={!agreed || isWithdrawing}
          onClick={() => setShowConfirm(true)}
        >
          {isWithdrawing ? "Deleting..." : "Delete Account"}
        </button>
      </main>

      {showConfirm ? (
        <AccountDeletionConfirmDialog
          busy={isWithdrawing}
          onCancel={() => setShowConfirm(false)}
          onConfirm={() => {
            setShowConfirm(false);
            void handleWithdraw();
          }}
        />
      ) : null}
    </div>
  );
}

function AccountDeletionConfirmDialog({
  busy,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div style={styles.confirmBackdrop} onClick={onCancel}>
      <div style={styles.confirmCard} onClick={(event) => event.stopPropagation()}>
        <h2 style={styles.confirmTitle}>Delete account?</h2>
        <p style={styles.confirmCopy}>
          Your account deletion request will start immediately.
        </p>
        <div style={styles.confirmActions}>
          <button
            type="button"
            style={styles.confirmSecondary}
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            style={{ ...styles.confirmPrimary, ...styles.confirmDanger }}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

const MINT = "#01c0c0";

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height, 100vh)",
    background: "#fff",
    color: "#111827",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "18px 18px 10px",
    flexShrink: 0,
  },
  backButton: {
    width: 36,
    height: 36,
    border: "none",
    background: "transparent",
    fontSize: 30,
    lineHeight: "30px",
    cursor: "pointer",
    color: "#111827",
  },
  title: {
    margin: 0,
    fontSize: 22,
    fontWeight: 800,
  },
  content: {
    flex: 1,
    overflowY: "auto",
    padding: "0 18px 28px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  description: {
    margin: 0,
    fontSize: 14,
    lineHeight: "20px",
    color: "#4b5563",
  },
  pdfFrame: {
    height: "min(62vh, 620px)",
    minHeight: 360,
    border: "1px solid #e5e7eb",
    borderRadius: 12,
    overflow: "hidden",
    background: "#f9fafb",
  },
  pdf: {
    width: "100%",
    height: "100%",
    border: "none",
    display: "block",
  },
  checkboxRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    fontSize: 14,
    fontWeight: 700,
    lineHeight: "20px",
    cursor: "pointer",
  },
  checkbox: {
    width: 18,
    height: 18,
    accentColor: MINT,
    flexShrink: 0,
  },
  deleteButton: {
    width: "100%",
    height: 54,
    border: "none",
    borderRadius: 27,
    background: "#ef4444",
    color: "#fff",
    fontSize: 16,
    fontWeight: 800,
    cursor: "pointer",
    flexShrink: 0,
  },
  deleteButtonDisabled: {
    background: "#e5e7eb",
    color: "#9ca3af",
    cursor: "default",
  },
  confirmBackdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(15, 23, 42, 0.35)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    zIndex: 1000,
  },
  confirmCard: {
    width: "min(360px, 100%)",
    borderRadius: 20,
    background: "#fff",
    padding: 22,
    boxShadow: "0 20px 60px rgba(15, 23, 42, 0.24)",
  },
  confirmTitle: {
    margin: "0 0 8px",
    fontSize: 20,
    fontWeight: 800,
  },
  confirmCopy: {
    margin: 0,
    fontSize: 14,
    lineHeight: "20px",
    color: "#4b5563",
  },
  confirmActions: {
    display: "flex",
    gap: 10,
    marginTop: 20,
  },
  confirmSecondary: {
    flex: 1,
    height: 44,
    borderRadius: 22,
    border: "1px solid #e5e7eb",
    background: "#fff",
    color: "#374151",
    fontWeight: 800,
    cursor: "pointer",
  },
  confirmPrimary: {
    flex: 1,
    height: 44,
    borderRadius: 22,
    border: "none",
    background: MINT,
    color: "#fff",
    fontWeight: 800,
    cursor: "pointer",
  },
  confirmDanger: {
    background: "#ef4444",
  },
};
