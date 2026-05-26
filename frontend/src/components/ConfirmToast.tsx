import type { CSSProperties } from "react";

export default function ConfirmToast({
  title,
  message,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  message?: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div style={styles.overlay}>
      <div style={styles.scrim} />
      <div style={styles.slot} role="alertdialog" aria-modal="true" aria-label={title}>
        <div style={styles.toast}>
          <span style={styles.text}>
            <strong style={styles.title}>{title}</strong>
            {message ? <span style={styles.message}>{message}</span> : null}
          </span>
          <span style={styles.actions}>
            <button
              type="button"
              style={styles.cancelButton}
              onClick={onCancel}
              disabled={busy}
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              style={{
                ...styles.confirmButton,
                ...(destructive ? styles.destructiveButton : {}),
              }}
              onClick={onConfirm}
              disabled={busy}
            >
              {busy ? "Working..." : confirmLabel}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    zIndex: 2147483647,
    pointerEvents: "none",
  },
  scrim: {
    position: "absolute",
    inset: 0,
    background: "rgba(24,26,32,0.28)",
    backdropFilter: "blur(2px)",
  },
  slot: {
    position: "absolute",
    left: "50%",
    top: "50%",
    width: "min(calc(100% - 32px), 380px)",
    transform: "translate(-50%, -50%)",
    pointerEvents: "none",
  },
  toast: {
    minHeight: 86,
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: 14,
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 18,
    background: "rgba(255,255,255,0.98)",
    boxShadow:
      "0 28px 72px rgba(15,23,42,0.32), 0 10px 24px rgba(15,23,42,0.18)",
    backdropFilter: "blur(16px)",
    pointerEvents: "auto",
  },
  text: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  title: {
    color: "var(--text-primary)",
    fontSize: "0.94rem",
    lineHeight: 1.25,
  },
  message: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 700,
    lineHeight: 1.35,
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  cancelButton: {
    minHeight: 38,
    border: "1px solid var(--border-soft)",
    borderRadius: 12,
    padding: "0 12px",
    background: "#ffffff",
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  confirmButton: {
    minHeight: 38,
    border: "none",
    borderRadius: 12,
    padding: "0 12px",
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontSize: "0.78rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  destructiveButton: {
    background: "#dc2626",
  },
};
