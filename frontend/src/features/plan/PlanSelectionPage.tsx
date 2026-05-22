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
        </div>

        {/* ── AI Ticket ── */}
        <button type="button" onClick={handleAiSelect} style={styles.ticket}>
          <div style={styles.ticketTop}>
            <div>
              <span style={{ ...styles.routeTag, color: BRAND }}>AI ROUTE</span>
              <p style={{ ...styles.dest, color: "#212121" }}>AI Travel Plan</p>
            </div>
            <span style={{ fontSize: "1.8rem", color: "#58C9D4", lineHeight: 1, flexShrink: 0 }}>→</span>
          </div>

          <div style={styles.fields}>
            <BoardingField label="FROM" value="Your Style" dark />
            <BoardingField label="TO" value="Seoul, KR" dark />
            <BoardingField label="TYPE" value="AI-Generated" dark />
          </div>

          <div style={styles.perf}>
            <div style={{...styles.notchL, background: "#f5f5f5"}} />
            <div style={{ ...styles.perfLine, borderColor: "#eaeaea" }} />
            <div style={{...styles.notchR, background: "#f5f5f5"}} />
          </div>

          <div style={styles.stub}>
            <p style={styles.ticketSubTitle}>Tailored For Your Style</p>
            <p style={styles.ticketSummary}>Effortless plan with personalization & tailored routes.</p>
          </div>
        </button>

        {/* ── Manual Ticket ── */}
        <button type="button" onClick={handleManualSelect} style={styles.ticket}>
          <div style={styles.ticketTop}>
            <div>
              <span style={{ ...styles.routeTag, color: "#FFB765" }}>MANUAL ROUTE</span>
              <p style={{ ...styles.dest, color: "#212121" }}>Custom Itinerary</p>
            </div>
            <span style={{ fontSize: "1.8rem", color: "#FFB765", lineHeight: 1, flexShrink: 0 }}>→</span>
          </div>

          <div style={styles.fields}>
            <BoardingField label="FROM" value="Your Search" />
            <BoardingField label="TO" value="Anywhere" />
            <BoardingField label="TYPE" value="Full Control" />
          </div>

          <div style={styles.perf}>
            <div style={{ ...styles.notchL, background: "#f5f5f5" }} />
            <div style={{ ...styles.perfLine, borderColor: "#eaeaea" }} />
            <div style={{ ...styles.notchR, background: "#f5f5f5" }} />
          </div>

          <div style={styles.stub}>
            <p style={styles.ticketSubTitle}>Designed By Your Hands</p>
            <p style={styles.ticketSummary}>Full control with place searching & editable plans.</p>
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
        color: "#aaa",
        marginBottom: 3,
      }}>
        {label}
      </span>
      <span style={{
        fontSize: "0.82rem",
        fontWeight: 700,
        color: "#212121",
      }}>
        {value}
      </span>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    height: "calc(var(--app-viewport-height) - var(--app-bottom-nav-reserved))",
    padding: "calc(20px + var(--app-safe-top)) 16px 28px",
    background: "#f5f5f5",
    fontFamily: '"Pretendard Variable", sans-serif',
    boxSizing: "border-box",
    overflow: "hidden",
  },
  container: {
    maxWidth: 430,
    width: "100%",
    height: "100%",
    overflow: "hidden",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    boxSizing: "border-box",
  },
  header: {
    padding: "8px 0 14px",
  },
  headline: {
    margin: "0 0 8px",
    fontSize: "2rem",
    fontWeight: 800,
    color: "var(--font-primary)",
    lineHeight: 1.1,
    letterSpacing: "-0.03em",
  },
  /* ── Tickets ── */
  ticket: {
    border: "none",
    borderRadius: 20,
    background: "#fcfcfc",
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
    background: "var(background)",
    marginLeft: -11,
    zIndex: 1,
  },
  notchR: {
    flexShrink: 0,
    width: 22,
    height: 22,
    borderRadius: "50%",
    background: "var(background)",
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
    gap: 0,
    padding: "12px 22px 20px",
  },
  ticketSubTitle: {
    color: "#444",
    fontSize: "0.8rem",
    fontWeight: 700,
  },
  ticketSummary: {
    marginTop: "-8px",
    color: "#999",
    fontSize: "0.75rem",
  },
};
