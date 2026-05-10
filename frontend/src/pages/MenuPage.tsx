import type { CSSProperties } from "react";

export default function MenuPage() {
  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <p style={styles.eyebrow}>Menu OCR</p>
        <h1 style={styles.title}>Menu Translation</h1>
        <p style={styles.copy}>Capture a menu and review the translated result in one simple flow.</p>
      </div>

      <section style={styles.heroCard}>
        <div style={styles.cameraFrame}>
          <div style={styles.cameraIcon}>+</div>
          <p style={styles.cameraTitle}>Upload a Menu Image</p>
          <p style={styles.cameraCopy}>Take a photo or choose one from your gallery</p>
        </div>
        <button type="button" style={styles.primaryButton}>Choose Menu Image</button>
      </section>

      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <h2 style={styles.sectionTitle}>Translation History</h2>
        </div>

        <div style={styles.emptyCard}>
          <p style={styles.emptyTitle}>No translated menus yet</p>
          <p style={styles.emptyCopy}>Once you upload a menu image, the result will appear here.</p>
        </div>
      </section>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(24px + var(--app-safe-top)) 16px 0",
    background: "transparent",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  header: {
    maxWidth: 720,
    margin: "0 auto 18px",
  },
  eyebrow: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 800,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
  },
  title: {
    margin: "8px 0 8px",
    color: "var(--text-primary)",
    fontSize: "2rem",
    lineHeight: 1.05,
  },
  copy: {
    margin: 0,
    color: "var(--neutral-700)",
    lineHeight: 1.55,
  },
  heroCard: {
    maxWidth: 720,
    margin: "0 auto",
    padding: 18,
    borderRadius: 30,
    background:
      "linear-gradient(180deg, rgba(5,181,187,0.12), rgba(255,255,255,0.98) 35%)",
    boxShadow: "var(--shadow-soft)",
    border: "1px solid rgba(5,181,187,0.16)",
  },
  cameraFrame: {
    minHeight: 280,
    borderRadius: 24,
    border: "2px dashed rgba(5,181,187,0.28)",
    background: "rgba(255,255,255,0.92)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  cameraIcon: {
    width: 64,
    height: 64,
    borderRadius: 20,
    display: "grid",
    placeItems: "center",
    background: "linear-gradient(135deg, var(--brand-primary), var(--brand-primary-deep))",
    color: "#ffffff",
    fontSize: "2rem",
  },
  cameraTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontWeight: 800,
    fontSize: "1rem",
  },
  cameraCopy: {
    margin: 0,
    color: "var(--neutral-700)",
    fontSize: "0.88rem",
  },
  primaryButton: {
    width: "100%",
    marginTop: 16,
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 18,
    padding: "15px 16px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(5,181,187,0.22)",
  },
  section: {
    maxWidth: 720,
    margin: "18px auto 0",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 10,
  },
  sectionTitle: {
    margin: 0,
    color: "#333333",
    fontSize: "1rem",
    fontWeight: 800,
  },
  emptyCard: {
    padding: 20,
    borderRadius: 22,
    background: "rgba(255,255,255,0.88)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  emptyTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1rem",
    fontWeight: 800,
  },
  emptyCopy: {
    margin: "8px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.9rem",
    lineHeight: 1.5,
  },
};
