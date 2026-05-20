import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { BRAND } from "../../api/aiPlanShared";

interface PlanSelectionPageProps {
  onSelectAI?: () => void;
  onSelectManual?: () => void;
}

export default function PlanSelectionPage({
  onSelectAI,
  onSelectManual,
}: PlanSelectionPageProps) {
  const navigate = useNavigate();

  const handleAiSelect = () => {
    if (onSelectAI) { onSelectAI(); return; }
    navigate("/plan/ai");
  };

  const handleManualSelect = () => {
    if (onSelectManual) { onSelectManual(); return; }
    navigate("/plan/manual");
  };

  return (
    <div style={styles.page}>
      <div style={styles.container}>

        <div style={styles.header}>
          <h1 style={styles.headline}>How would<br />you like to plan?</h1>
          <p style={styles.byline}>Pick your style — AI builds it, or craft every step yourself.</p>
        </div>

        {/* ── AI Ticket ── */}
        <button type="button" onClick={handleAiSelect} style={styles.ticketDark}>
          <div style={styles.ticketTop}>
            <div>
              <span style={{ ...styles.routeTag, color: BRAND }}>AI ROUTE</span>
              <p style={{ ...styles.dest, color: "#ffffff" }}>Smart Travel Plan</p>
            </div>
            <span style={{ fontSize: "1.8rem", color: "rgba(255,255,255,0.35)", lineHeight: 1, flexShrink: 0 }}>→</span>
          </div>

          <div style={styles.fields}>
            <BoardingField label="FROM" value="Your Style" dark />
            <BoardingField label="TO" value="Seoul, KR" dark />
            <BoardingField label="TYPE" value="AI-Generated" dark />
          </div>

          <div style={styles.perf}>
            <div style={styles.notchL} />
            <div style={{ ...styles.perfLine, borderColor: "rgba(255,255,255,0.12)" }} />
            <div style={styles.notchR} />
          </div>

          <div style={styles.stub}>
            {["Budget friendly", "Personalized route", "Auto-saved"].map((t) => (
              <span key={t} style={styles.tagDark}>{t}</span>
            ))}
          </div>
        </button>

        {/* ── Manual Ticket ── */}
        <button type="button" onClick={handleManualSelect} style={styles.ticketLight}>
          <div style={styles.ticketTop}>
            <div>
              <span style={{ ...styles.routeTag, color: "#b45309" }}>MANUAL ROUTE</span>
              <p style={{ ...styles.dest, color: "#0f172a" }}>Custom Itinerary</p>
            </div>
            <span style={{ fontSize: "1.8rem", color: BRAND, lineHeight: 1, flexShrink: 0 }}>→</span>
          </div>

          <div style={styles.fields}>
            <BoardingField label="FROM" value="Your Search" />
            <BoardingField label="TO" value="Anywhere" />
            <BoardingField label="TYPE" value="Full Control" />
          </div>

          <div style={styles.perf}>
            <div style={{ ...styles.notchL, background: "#f5f0eb" }} />
            <div style={{ ...styles.perfLine, borderColor: "#e5e7eb" }} />
            <div style={{ ...styles.notchR, background: "#f5f0eb" }} />
          </div>

          <div style={styles.stub}>
            {["Search Places", "Editable plan", "Invite friends"].map((t) => (
              <span key={t} style={styles.tagLight}>{t}</span>
            ))}
          </div>
        </button>

      </div>
    </div>
  );
}

function BoardingField({
  label,
  value,
  dark,
}: {
  label: string;
  value: string;
  dark?: boolean;
}) {
  return (
    <div style={{ flex: 1 }}>
      <span style={{
        display: "block",
        fontSize: "0.52rem",
        fontWeight: 900,
        letterSpacing: "0.12em",
        color: dark ? "rgba(255,255,255,0.38)" : "#9ca3af",
        marginBottom: 3,
      }}>
        {label}
      </span>
      <span style={{
        fontSize: "0.82rem",
        fontWeight: 700,
        color: dark ? "#ffffff" : "#0f172a",
      }}>
        {value}
      </span>
    </div>
  );
}

const PAGE_BG = "#f5f0eb";

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(20px + var(--app-safe-top)) 20px calc(28px + var(--app-bottom-nav-reserved))",
    background: PAGE_BG,
    fontFamily: '"Satoshi Variable", "Satoshi", "Apple SD Gothic Neo", sans-serif',
  },
  container: {
    maxWidth: 430,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  header: {
    padding: "8px 0 14px",
  },
  headline: {
    margin: "0 0 8px",
    fontSize: "2rem",
    fontWeight: 900,
    color: "#0f172a",
    lineHeight: 1.1,
    letterSpacing: "-0.03em",
  },
  byline: {
    margin: 0,
    fontSize: "0.83rem",
    color: "#9ca3af",
    lineHeight: 1.55,
  },

  /* ── Tickets ── */
  ticketDark: {
    border: "none",
    borderRadius: 20,
    background: "#1a2537",
    textAlign: "left",
    cursor: "pointer",
    padding: 0,
    width: "100%",
    position: "relative",
    overflow: "hidden",
  },
  ticketLight: {
    border: "1.5px solid #e5e7eb",
    borderRadius: 20,
    background: "#ffffff",
    textAlign: "left",
    cursor: "pointer",
    padding: 0,
    width: "100%",
    position: "relative",
    overflow: "hidden",
  },
  ticketTop: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    padding: "22px 22px 14px",
  },
  routeTag: {
    display: "block",
    fontSize: "0.58rem",
    fontWeight: 900,
    letterSpacing: "0.14em",
    marginBottom: 7,
  },
  dest: {
    margin: 0,
    fontSize: "1.55rem",
    fontWeight: 900,
    lineHeight: 1.15,
    letterSpacing: "-0.025em",
  },
  fields: {
    display: "flex",
    gap: 6,
    padding: "0 22px 16px",
  },

  /* Perforation row */
  perf: {
    position: "relative",
    height: 22,
    display: "flex",
    alignItems: "center",
  },
  notchL: {
    flexShrink: 0,
    width: 22,
    height: 22,
    borderRadius: "50%",
    background: PAGE_BG,
    marginLeft: -11,
    zIndex: 1,
  },
  notchR: {
    flexShrink: 0,
    width: 22,
    height: 22,
    borderRadius: "50%",
    background: PAGE_BG,
    marginRight: -11,
    zIndex: 1,
  },
  perfLine: {
    flex: 1,
    height: 0,
    borderTop: "1.5px dashed rgba(255,255,255,0.15)",
  },

  /* Stub */
  stub: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    padding: "12px 22px 20px",
  },
  tagDark: {
    padding: "5px 10px",
    borderRadius: 6,
    background: "rgba(255,255,255,0.1)",
    color: "rgba(255,255,255,0.82)",
    fontSize: "0.72rem",
    fontWeight: 700,
  },
  tagLight: {
    padding: "5px 10px",
    borderRadius: 6,
    background: "#f0fdfc",
    color: BRAND,
    fontSize: "0.72rem",
    fontWeight: 700,
  },
};
