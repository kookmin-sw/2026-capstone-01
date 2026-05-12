import type { CSSProperties } from "react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { createLoginUrl, getMyProfile } from "../api/auth/auth";

type LoginStatus = "complete" | "new" | "in_progress" | "withdrawal_pending";

export default function LoginPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status") as LoginStatus | null;

    if (!status) return;

    const email = decodeURIComponent(params.get("email") || "");
    const name = decodeURIComponent(params.get("name") || "");

    if (status === "complete") {
      navigate("/home");
    } else if (status === "new" || status === "in_progress") {
      navigate("/register", { state: { email, name } });
    } else if (status === "withdrawal_pending") {
      navigate("/withdrawal-pending", { replace: true });
    }
  }, [navigate]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("status")) return;

    getMyProfile()
      .then((profile) => {
        if (profile) {
          navigate("/home", { replace: true });
        }
      })
      .catch(() => {
        // Stay on the login page when there is no valid session.
      });
  }, [navigate]);

  function handleGoogleLogin(): void {
    window.location.href = createLoginUrl();
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.center}>
        <div style={styles.heroFrame}>
          <img src="/krip_logo.png" alt="Krip login" style={styles.heroImage} />
          <div style={styles.bottom}>
            <button style={styles.googleBtn} onClick={handleGoogleLogin}>
              <GoogleIcon />
              Sign in with Google
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 48 48"
      style={{ marginRight: 10, flexShrink: 0 } as CSSProperties}
    >
      <path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.09-6.09C34.46 3.09 29.5 1 24 1 14.82 1 6.97 6.48 3.28 14.38l7.09 5.51C12.12 13.71 17.6 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.52 24.5c0-1.64-.15-3.22-.42-4.74H24v8.98h12.68c-.55 2.94-2.2 5.43-4.68 7.1l7.19 5.59C43.18 37.64 46.52 31.55 46.52 24.5z"/>
      <path fill="#FBBC05" d="M10.37 28.11A14.6 14.6 0 0 1 9.5 24c0-1.42.24-2.8.67-4.11L3.08 14.38A23.94 23.94 0 0 0 0 24c0 3.87.92 7.52 2.54 10.73l7.83-6.62z"/>
      <path fill="#34A853" d="M24 47c5.52 0 10.15-1.83 13.54-4.97l-7.19-5.59c-1.83 1.23-4.17 1.96-6.35 1.96-6.4 0-11.88-4.21-13.63-9.89l-7.83 6.62C6.97 41.52 14.82 47 24 47z"/>
    </svg>
  );
}

const styles: Record<string, CSSProperties> = {
  wrapper: {
    position: "relative",
    width: "100%",
    minHeight: "var(--app-viewport-height)",
    background:
      "#01C0C0",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "space-between",
    overflow: "hidden",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  center: {
    flex: 1,
    width: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "0 20px",
  },
  heroFrame: {
    position: "relative",
    width: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  heroImage: {
    width: "25vw",
    height: "auto",
    objectFit: "contain",
    display: "block",
  },
  bottom: {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: "calc(28px + var(--app-safe-bottom))",
    width: "min(100%, 430px)",
    margin: "0 auto 2.5rem",
    padding: "0 34px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    zIndex: 1,
  },
  googleBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "86%",
    minHeight: 52,
    padding: "0 18px",
    borderRadius: "2.5rem",
    border: "1px solid rgba(255,255,255,0.78)",
    background: "#ffffff",
    color: "#256f72",
    fontSize: "0.95rem",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 18px 36px rgba(14, 90, 93, 0.18)",
  },
};
