import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { getFeedPopup, type FeedPost, type FeedPopupResponse } from "../api/feed";

const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

export default function FeedPopup({
  userId,
  onClose,
}: {
  userId: string;
  onClose: () => void;
}) {
  const [popup, setPopup] = useState<FeedPopupResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPost, setSelectedPost] = useState<FeedPost | null>(null);

  useEffect(() => {
    let isMounted = true;

    getFeedPopup(userId)
      .then((response) => {
        if (isMounted) setPopup(response);
      })
      .catch((loadError) => {
        if (isMounted) {
          setError(toErrorMessage(loadError, "Feed could not be loaded."));
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [userId]);

  const statusText = popup?.status_message || popup?.message || "";

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.sheet} onClick={(event) => event.stopPropagation()}>
        <button type="button" style={styles.closeButton} onClick={onClose}>
          x
        </button>

        {loading ? (
          <div style={styles.statePanel}>Loading feed...</div>
        ) : error ? (
          <div style={styles.statePanel}>{error}</div>
        ) : popup ? (
          <>
            <header style={styles.header}>
              <img
                src={popup.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                alt=""
                style={styles.avatar}
              />
              <div style={styles.headerText}>
                <h2 style={styles.name}>{popup.user_name || "Unknown"}</h2>
                <p style={styles.status}>{statusText || "No status message."}</p>
              </div>
            </header>

            {popup.feed.items.length ? (
              <div style={styles.grid}>
                {popup.feed.items.map((post) => (
                  <button
                    key={post.post_id}
                    type="button"
                    style={styles.tile}
                    onClick={() => setSelectedPost(post)}
                  >
                    <img src={getFeedImageUrl(post)} alt="" style={styles.tileImage} />
                  </button>
                ))}
              </div>
            ) : (
              <div style={styles.statePanel}>No visible feed photos.</div>
            )}
          </>
        ) : null}

        {selectedPost ? (
          <div style={styles.detailBackdrop} onClick={() => setSelectedPost(null)}>
            <div style={styles.detailCard} onClick={(event) => event.stopPropagation()}>
              <button
                type="button"
                style={styles.detailClose}
                onClick={() => setSelectedPost(null)}
              >
                x
              </button>
              <img src={selectedPost.original_url} alt="" style={styles.detailImage} />
              {selectedPost.caption ? (
                <p style={styles.caption}>{selectedPost.caption}</p>
              ) : null}
              <p style={styles.meta}>
                {selectedPost.like_count} likes · {selectedPost.comment_count} comments
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function getFeedImageUrl(post: FeedPost): string {
  return post.thumbnail_medium_url || post.thumbnail_small_url || post.original_url;
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as {
    response?: { data?: { detail?: string; message?: string } };
    message?: string;
  };
  return apiError.response?.data?.detail || apiError.response?.data?.message || apiError.message || fallback;
}

const styles: Record<string, CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 70,
    display: "flex",
    justifyContent: "flex-end",
    background: "rgba(24,26,32,0.42)",
  },
  sheet: {
    position: "relative",
    width: "min(430px, 100%)",
    height: "100%",
    padding: "calc(22px + var(--app-safe-top)) 18px calc(22px + var(--app-safe-bottom))",
    overflowY: "auto",
    background: "var(--surface-panel)",
    boxShadow: "-24px 0 60px rgba(24,26,32,0.18)",
    animation: "slideInFromRight 240ms ease-out",
  },
  closeButton: {
    position: "absolute",
    top: "calc(14px + var(--app-safe-top))",
    right: 14,
    width: 34,
    height: 34,
    border: "1px solid var(--border-soft)",
    borderRadius: "50%",
    background: "#ffffff",
    color: "var(--text-secondary)",
    fontWeight: 900,
    cursor: "pointer",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 14,
    paddingRight: 46,
    marginBottom: 20,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
    border: "3px solid #ffffff",
    boxShadow: "0 12px 24px rgba(5,181,187,0.16)",
  },
  headerText: {
    minWidth: 0,
  },
  name: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.28rem",
    lineHeight: 1.15,
  },
  status: {
    margin: "6px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.9rem",
    lineHeight: 1.45,
    overflowWrap: "anywhere",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 6,
  },
  tile: {
    width: "100%",
    aspectRatio: "1 / 1",
    padding: 0,
    border: "none",
    borderRadius: 8,
    overflow: "hidden",
    background: "#050608",
    cursor: "pointer",
  },
  tileImage: {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    display: "block",
    background: "#050608",
  },
  statePanel: {
    padding: 22,
    borderRadius: 20,
    background: "rgba(255,255,255,0.9)",
    border: "1px solid var(--border-soft)",
    color: "var(--neutral-700)",
    fontWeight: 800,
  },
  detailBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 72,
    display: "grid",
    placeItems: "center",
    padding: "calc(18px + var(--app-safe-top)) 18px calc(18px + var(--app-safe-bottom))",
    background: "rgba(8,12,16,0.74)",
  },
  detailCard: {
    position: "relative",
    width: "min(560px, 100%)",
    maxHeight: "88dvh",
    overflowY: "auto",
    borderRadius: 22,
    background: "#ffffff",
    boxShadow: "0 24px 70px rgba(0,0,0,0.28)",
  },
  detailClose: {
    position: "absolute",
    top: 12,
    right: 12,
    width: 34,
    height: 34,
    border: "none",
    borderRadius: "50%",
    background: "rgba(16,34,35,0.72)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  detailImage: {
    width: "100%",
    maxHeight: "70dvh",
    objectFit: "contain",
    display: "block",
    background: "#050608",
  },
  caption: {
    margin: "14px 16px 0",
    color: "var(--text-secondary)",
    fontWeight: 800,
    lineHeight: 1.45,
  },
  meta: {
    margin: "8px 16px 16px",
    color: "var(--neutral-700)",
    fontSize: "0.86rem",
    fontWeight: 800,
  },
};
