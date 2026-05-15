import type { CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { navigateBackOrFallback } from "../utils/navigation";

export default function PlaceholderPage() {
  const navigate = useNavigate();
  const params = useParams();

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>Detail Screen Coming Soon</h1>
        <p style={styles.copy}>Current route params: {JSON.stringify(params)}</p>
        <button
          type="button"
          style={styles.button}
          onClick={() => navigateBackOrFallback(navigate, "/home")}
        >
          Go Back
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "calc(24px + var(--app-safe-top)) 16px 24px",
    background: "#ffffff",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  card: {
    width: "100%",
    maxWidth: 420,
    padding: 24,
    borderRadius: 24,
    background: "#f7f7f7",
    border: "1px solid #ececec",
    textAlign: "center",
  },
  title: {
    margin: 0,
    color: "#222222",
  },
  copy: {
    margin: "12px 0 0",
    color: "#777777",
  },
  button: {
    marginTop: 18,
    border: "1px solid #d8d8d8",
    borderRadius: 14,
    padding: "12px 16px",
    background: "#d9d9d9",
    color: "#222222",
    fontWeight: 800,
    cursor: "pointer",
  },
};
