import type { CSSProperties } from "react";
import React, { useState } from "react";
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
        <section style={styles.termsFrame} aria-label="Account deletion terms">
          <DeletionTermsContent />
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

function DeletionTermsContent() {
  const h: CSSProperties = {
    fontSize: 13,
    fontWeight: 700,
    color: "#111827",
    margin: "16px 0 6px",
    lineHeight: "18px",
    display: "flex",
    alignItems: "center",
    gap: 6,
  };
  const p: CSSProperties = {
    fontSize: 12,
    lineHeight: "19px",
    color: "#374151",
    margin: "0 0 6px",
  };
  const li: CSSProperties = {
    fontSize: 12,
    lineHeight: "19px",
    color: "#374151",
    marginBottom: 4,
  };
  const ul: CSSProperties = { paddingLeft: 16, margin: "4px 0 6px" };
  const dot: CSSProperties = {
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: MINT,
    flexShrink: 0,
    display: "inline-block",
  };

  const sections: { title: string; body: React.ReactNode }[] = [
    {
      title: "Account Deactivation and Grace Period",
      body: (
        <ul style={ul}>
          <li style={li}>When you request account deletion, the account is immediately deactivated and access to the service is restricted.</li>
          <li style={li}>A <b>one-month grace period</b> is provided to prevent accidental deletion and allow account recovery.</li>
          <li style={li}>During the grace period, you may request account restoration.</li>
        </ul>
      ),
    },
    {
      title: "Deletion of Personal Information",
      body: (
        <>
          <p style={p}>After the grace period, personal information and service usage data will be deleted. However, the following information may be retained as required by law:</p>
          <ul style={ul}>
            {[
              "Contracts or subscription withdrawal records: 5 years",
              "Payment and supply of goods/services records: 5 years",
              "Consumer complaints or dispute resolution records: 3 years",
              "Advertising and labeling records: 6 months",
              "Access log records: 3 months",
            ].map((item, i) => <li key={i} style={li}>{item}</li>)}
          </ul>
        </>
      ),
    },
    {
      title: "Posts and Chat Data",
      body: (
        <p style={p}>
          Posts, comments, chat messages, and other content may not be immediately deleted or may be anonymized to maintain service operation and protect other users. Personal information included in such content will be processed in accordance with applicable laws.
        </p>
      ),
    },
    {
      title: "Fraud Prevention",
      body: (
        <p style={p}>
          Minimum necessary records may be retained for up to <b>one year</b> after account deletion for the prevention of fraudulent registration, abuse, or abnormal activities.
        </p>
      ),
    },
    {
      title: "Withdrawal Cancellation and Account Recovery",
      body: (
        <ul style={ul}>
          <li style={li}>You may request account recovery through customer support during the grace period.</li>
          <li style={li}>After the grace period expires, account and personal information <b>cannot be recovered</b>.</li>
        </ul>
      ),
    },
    {
      title: "Important Notice",
      body: (
        <>
          <p style={p}>After account deletion is completed, the following information may not be recoverable:</p>
          <ul style={ul}>
            {[
              "Profile information",
              "Travel itinerary information",
              "Travel mate posts",
              "Chat history",
              "Saved settings",
              "Notification settings",
            ].map((item, i) => <li key={i} style={{ ...li, color: "#ef4444" }}>{item}</li>)}
          </ul>
        </>
      ),
    },
  ];

  return (
    <div style={{ padding: "2px 0 8px" }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: MINT, margin: "0 0 14px" }}>
        KRIP Account Deletion Notice
      </p>
      <p style={p}>Please read the following information carefully before requesting account deletion.</p>
      {sections.map((s, i) => (
        <div key={i}>
          <p style={h}>
            <span style={dot} />
            {s.title}
          </p>
          {s.body}
        </div>
      ))}
      <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 14, lineHeight: "16px" }}>
        By proceeding with account deletion, you are deemed to have read and agreed to the above terms.
      </p>
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
  termsFrame: {
    height: "min(62vh, 620px)",
    minHeight: 360,
    border: "1px solid #e5e7eb",
    borderRadius: 12,
    overflowY: "auto",
    background: "#f9fafb",
    padding: "16px 18px",
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
