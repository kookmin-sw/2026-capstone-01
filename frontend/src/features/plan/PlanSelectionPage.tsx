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
    if (onSelectAI) {
      onSelectAI();
      return;
    }

    navigate("/plan/ai");
  };

  const handleManualSelect = () => {
    if (onSelectManual) {
      onSelectManual();
      return;
    }

    navigate("/plan/manual");
  };

  return (
    <div style={styles.page}>
      <div style={styles.phoneFrame}>
        <div style={styles.heroBlock}>
          <div style={styles.heroAccent} />
          <span style={styles.headerBadge}>Trip Planning</span>
          <h1 style={styles.heroTitle}>Choose how you want to build your Seoul trip</h1>
          <p style={styles.heroCopy}>
            Use AI to generate a route from your travel tokens, or build every stop manually with your own search and schedule.
          </p>
        </div>

        <div style={styles.cardStack}>
          <button type="button" onClick={handleAiSelect} style={styles.choiceCardPrimary}>
            <div style={styles.choiceTopRow}>
              <span style={styles.choicePill}>AI Travel Plan</span>
              <span style={styles.choiceArrow}>{">"}</span>
            </div>
            <strong style={styles.choiceTitleLight}>Generate from preference tokens</strong>
            <p style={styles.choiceCopyLight}>
              Start with travel style, pace, transport, budget, and food requirements. The result page is prepared to consume backend place APIs.
            </p>
            <div style={styles.tagWrap}>
              <span style={styles.tagLight}>Budget slider</span>
              <span style={styles.tagLight}>API-ready result</span>
              <span style={styles.tagLight}>Save to My Page</span>
            </div>
          </button>

          <button type="button" onClick={handleManualSelect} style={styles.choiceCardSecondary}>
            <div style={styles.choiceTopRow}>
              <span
                style={{
                  ...styles.choicePill,
                  background: "rgba(255,190,15,0.18)",
                  color: "#7a5400",
                }}
              >
                Manual Travel Plan
              </span>
              <span style={{ ...styles.choiceArrow, color: BRAND }}>{">"}</span>
            </div>
            <strong style={styles.choiceTitleDark}>Search and build the itinerary yourself</strong>
            <p style={styles.choiceCopyDark}>
              Select dates, search only when you need places, add stops day by day, invite friends, and save the final itinerary for later editing.
            </p>
            <div style={styles.tagWrap}>
              <span style={styles.tagDark}>Search first</span>
              <span style={styles.tagDark}>Editable plan</span>
              <span style={styles.tagDark}>My Page archive</span>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(20px + var(--app-safe-top)) 16px 20px",
    background: "#f5f5f5",
    fontFamily: '"Nunito", "Apple SD Gothic Neo", sans-serif',
  },
  phoneFrame: {
    maxWidth: 430,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 18,
    paddingBottom: 28,
  },
  heroBlock: {
    position: "relative",
    overflow: "hidden",
    borderRadius: 28,
    padding: "28px 22px",
    background: `linear-gradient(150deg, ${BRAND} 0%, #0aa8a8 100%)`,
    color: "#ffffff",
    boxShadow: "0 18px 40px rgba(1, 192, 192, 0.24)",
  },
  heroAccent: {
    position: "absolute",
    width: 180,
    height: 180,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.12)",
    right: -50,
    top: -70,
  },
  heroTitle: {
    margin: "14px 0 10px",
    fontSize: 30,
    lineHeight: 1.12,
    maxWidth: 280,
  },
  heroCopy: {
    margin: 0,
    maxWidth: 300,
    color: "rgba(255,255,255,0.88)",
    fontSize: 14,
    lineHeight: 1.6,
  },
  headerBadge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.22)",
    color: "#ffffff",
    fontSize: 12,
    fontWeight: 800,
  },
  cardStack: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  choiceCardPrimary: {
    border: "none",
    borderRadius: 24,
    padding: "22px 20px",
    textAlign: "left",
    background: `linear-gradient(160deg, ${BRAND} 0%, #0aa6a6 100%)`,
    color: "#ffffff",
    boxShadow: "0 16px 36px rgba(1, 192, 192, 0.2)",
    cursor: "pointer",
  },
  choiceCardSecondary: {
    border: "1px solid #d7ecec",
    borderRadius: 24,
    padding: "22px 20px",
    textAlign: "left",
    background: "#ffffff",
    color: "#102223",
    boxShadow: "0 12px 30px rgba(16, 34, 35, 0.06)",
    cursor: "pointer",
  },
  choiceTopRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 18,
  },
  choicePill: {
    display: "inline-flex",
    alignItems: "center",
    padding: "7px 11px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.2)",
    color: "inherit",
    fontSize: 12,
    fontWeight: 800,
  },
  choiceArrow: {
    fontSize: 18,
    fontWeight: 900,
    color: "#ffffff",
  },
  choiceTitleLight: {
    display: "block",
    fontSize: 22,
    lineHeight: 1.2,
  },
  choiceCopyLight: {
    margin: "10px 0 18px",
    color: "rgba(255,255,255,0.86)",
    lineHeight: 1.6,
    fontSize: 14,
  },
  choiceTitleDark: {
    display: "block",
    fontSize: 22,
    lineHeight: 1.2,
    color: "#102223",
  },
  choiceCopyDark: {
    margin: "10px 0 18px",
    color: "#526d6d",
    lineHeight: 1.6,
    fontSize: 14,
  },
  tagWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  tagLight: {
    padding: "8px 11px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.18)",
    color: "#ffffff",
    fontSize: 12,
    fontWeight: 700,
  },
  tagDark: {
    padding: "8px 11px",
    borderRadius: 999,
    background: "#f3fbfb",
    color: BRAND,
    fontSize: 12,
    fontWeight: 700,
  },
};
