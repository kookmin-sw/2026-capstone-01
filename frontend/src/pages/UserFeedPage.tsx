import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMyProfile } from "../api/auth/auth";
import {
  createFeedComment,
  deleteFeedComment,
  getFeedComments,
  getFeedPopup,
  getFeedPostLikes,
  getUserFeedPosts,
  likeFeedPost,
  unlikeFeedPost,
  type FeedComment,
  type FeedLikeUser,
  type FeedPost,
  type FeedPopupResponse,
} from "../api/feed";

const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

export default function UserFeedPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<FeedPopupResponse | null>(null);
  const [posts, setPosts] = useState<FeedPost[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [selectedPost, setSelectedPost] = useState<FeedPost | null>(null);
  const [selectedLikes, setSelectedLikes] = useState<FeedLikeUser[]>([]);
  const [selectedComments, setSelectedComments] = useState<FeedComment[]>([]);
  const [commentInput, setCommentInput] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [viewerUserId, setViewerUserId] = useState("");

  useEffect(() => {
    let mounted = true;
    if (!id) return undefined;

    setLoading(true);
    setError("");
    getFeedPopup(id)
      .then((response) => {
        if (!mounted) return;
        setProfile(response);
        setPosts(response.feed.items);
        setNextCursor(response.feed.items.at(-1)?.post_id ?? null);
      })
      .catch((loadError) => {
        if (mounted) setError(toErrorMessage(loadError, "Feed could not be loaded."));
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [id]);

  useEffect(() => {
    let mounted = true;
    getMyProfile()
      .then((viewer) => {
        if (mounted) setViewerUserId(viewer?.user_id ?? "");
      })
      .catch(() => {
        if (mounted) setViewerUserId("");
      });

    return () => {
      mounted = false;
    };
  }, []);

  async function loadMore(): Promise<void> {
    if (!id || !nextCursor || loadingMore) return;

    setLoadingMore(true);
    try {
      const response = await getUserFeedPosts(id, nextCursor);
      setPosts((current) => {
        const existing = new Set(current.map((post) => post.post_id));
        return [...current, ...response.posts.filter((post) => !existing.has(post.post_id))];
      });
      setNextCursor(response.next_cursor);
    } catch (loadError) {
      setError(toErrorMessage(loadError, "More feed photos could not be loaded."));
    } finally {
      setLoadingMore(false);
    }
  }

  async function openPost(post: FeedPost): Promise<void> {
    setSelectedPost(post);
    setSelectedLikes([]);
    setSelectedComments([]);
    setCommentInput("");
    setDetailError("");
    setDetailLoading(true);

    try {
      const [likes, comments] = await Promise.all([
        getFeedPostLikes(post.post_id),
        getFeedComments(post.post_id),
      ]);
      setSelectedLikes(likes.users);
      setSelectedComments(comments.comments);
    } catch (loadError) {
      setDetailError(toErrorMessage(loadError, "Likes and comments could not be loaded."));
    } finally {
      setDetailLoading(false);
    }
  }

  function updatePostState(post: FeedPost): void {
    setPosts((current) =>
      current.map((item) => (item.post_id === post.post_id ? post : item))
    );
    setSelectedPost((current) => (current?.post_id === post.post_id ? post : current));
  }

  async function handleLike(): Promise<void> {
    if (!selectedPost || detailBusy) return;

    setDetailBusy(true);
    setDetailError("");
    try {
      const response = await likeFeedPost(selectedPost.post_id);
      updatePostState({ ...selectedPost, like_count: response.like_count });
      setSelectedLikes((await getFeedPostLikes(selectedPost.post_id)).users);
    } catch (likeError) {
      if (getApiStatus(likeError) === 400) {
        try {
          const response = await unlikeFeedPost(selectedPost.post_id);
          updatePostState({ ...selectedPost, like_count: response.like_count });
          setSelectedLikes((await getFeedPostLikes(selectedPost.post_id)).users);
        } catch (unlikeError) {
          setDetailError(toErrorMessage(unlikeError, "Failed to update like."));
        }
      } else {
        setDetailError(toErrorMessage(likeError, "Failed to update like."));
      }
    } finally {
      setDetailBusy(false);
    }
  }

  async function handleCommentSubmit(): Promise<void> {
    const content = commentInput.trim();
    if (!selectedPost || !content || detailBusy) return;

    setDetailBusy(true);
    setDetailError("");
    try {
      const comment = await createFeedComment(selectedPost.post_id, content);
      setSelectedComments((current) => [comment, ...current]);
      updatePostState({
        ...selectedPost,
        comment_count: selectedPost.comment_count + 1,
      });
      setCommentInput("");
    } catch (commentError) {
      setDetailError(toErrorMessage(commentError, "Failed to add comment."));
    } finally {
      setDetailBusy(false);
    }
  }

  async function handleCommentDelete(comment: FeedComment): Promise<void> {
    if (!selectedPost || detailBusy) return;

    setDetailBusy(true);
    setDetailError("");
    try {
      await deleteFeedComment(selectedPost.post_id, comment.comment_id);
      setSelectedComments((current) =>
        current.filter((item) => item.comment_id !== comment.comment_id)
      );
      updatePostState({
        ...selectedPost,
        comment_count: Math.max(0, selectedPost.comment_count - 1),
      });
    } catch (deleteError) {
      setDetailError(toErrorMessage(deleteError, "Failed to delete comment."));
    } finally {
      setDetailBusy(false);
    }
  }

  const profileMeta = [profile?.nationality, ...(profile?.travel_styles ?? [])]
    .filter((value): value is string => Boolean(value))
    .map(formatMeta)
    .join(" · ");

  return (
    <div style={styles.page}>
      <header style={styles.topBar}>
        <button type="button" style={styles.backButton} onClick={() => navigate(-1)}>
          ‹
        </button>
        <strong style={styles.topTitle}>{profile?.user_name || "Feed"}</strong>
        <span style={styles.topSpacer} />
      </header>

      {loading ? (
        <div style={styles.statePanel}>Loading feed...</div>
      ) : error ? (
        <div style={styles.statePanel}>{error}</div>
      ) : profile ? (
        <>
          <section style={styles.profileHeader}>
            <img
              src={profile.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
              alt=""
              style={styles.avatar}
            />
            <div style={styles.profileText}>
              <h1 style={styles.name}>{profile.user_name || "Unknown"}</h1>
              {profileMeta ? <p style={styles.meta}>{profileMeta}</p> : null}
              <p style={styles.count}>{posts.length} posts</p>
            </div>
          </section>

          {posts.length > 0 ? (
            <section style={styles.grid}>
              {posts.map((post) => (
                <button
                  key={post.post_id}
                  type="button"
                  style={styles.tile}
                  onClick={() => void openPost(post)}
                >
                  <img src={getFeedImageUrl(post)} alt="" style={styles.tileImage} />
                </button>
              ))}
            </section>
          ) : (
            <div style={styles.statePanel}>No visible feed photos.</div>
          )}

          {nextCursor ? (
            <button
              type="button"
              style={styles.loadMoreButton}
              onClick={() => void loadMore()}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading..." : "More"}
            </button>
          ) : null}
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
            <div style={styles.detailImagePane}>
              <img src={selectedPost.original_url} alt="" style={styles.detailImage} />
            </div>
            <aside style={styles.detailSidePane}>
              <header style={styles.postHeader}>
                <img
                  src={profile?.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                  alt=""
                  style={styles.postAvatar}
                />
                <div>
                  <strong style={styles.postAuthor}>{profile?.user_name || "Unknown"}</strong>
                  <p style={styles.postVisibility}>
                    {getVisibilityLabel(selectedPost.visibility)}
                  </p>
                </div>
              </header>

              {detailError ? <div style={styles.detailError}>{detailError}</div> : null}
              {detailLoading ? (
                <div style={styles.commentsState}>Loading comments...</div>
              ) : (
                <div style={styles.commentsList}>
                  {selectedPost.caption ? (
                    <article style={styles.commentItem}>
                      <img
                        src={profile?.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                        alt=""
                        style={styles.commentAvatar}
                      />
                      <div style={styles.commentBody}>
                        <strong style={styles.commentAuthor}>
                          {profile?.user_name || "Unknown"}
                        </strong>
                        <p style={styles.commentText}>{selectedPost.caption}</p>
                      </div>
                    </article>
                  ) : null}
                  {selectedComments.map((comment) => (
                    <article key={comment.comment_id} style={styles.commentItem}>
                      <img
                        src={comment.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                        alt=""
                        style={styles.commentAvatar}
                      />
                      <div style={styles.commentBody}>
                        <strong style={styles.commentAuthor}>
                          {comment.user_name || "Unknown"}
                        </strong>
                        <p style={styles.commentText}>{comment.content}</p>
                      </div>
                      {comment.user_id === viewerUserId ? (
                        <button
                          type="button"
                          style={styles.commentDeleteButton}
                          disabled={detailBusy}
                          onClick={() => void handleCommentDelete(comment)}
                        >
                          Delete
                        </button>
                      ) : null}
                    </article>
                  ))}
                  {!selectedPost.caption && selectedComments.length === 0 ? (
                    <div style={styles.commentsState}>No comments yet.</div>
                  ) : null}
                </div>
              )}

              <footer style={styles.postFooter}>
                <div style={styles.actionSummary}>
                  <button
                    type="button"
                    style={styles.likeIconButton}
                    disabled={detailBusy}
                    onClick={() => void handleLike()}
                    aria-label="Like"
                  >
                    <span style={styles.actionCount}>{selectedPost.like_count}</span>
                    <HeartIcon />
                  </button>
                  <span style={styles.commentSummary}>
                    <span style={styles.actionCount}>{selectedPost.comment_count}</span>
                    <CommentIcon />
                  </span>
                </div>
                <form
                  style={styles.commentForm}
                  onSubmit={(event) => {
                    event.preventDefault();
                    void handleCommentSubmit();
                  }}
                >
                  <input
                    value={commentInput}
                    maxLength={500}
                    placeholder="Add a comment..."
                    style={styles.commentInput}
                    onChange={(event) => setCommentInput(event.target.value)}
                  />
                  <button
                    type="submit"
                    style={styles.commentSubmit}
                    disabled={!commentInput.trim() || detailBusy}
                  >
                    Post
                  </button>
                </form>
              </footer>
            </aside>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function getFeedImageUrl(post: FeedPost): string {
  return post.thumbnail_medium_url || post.thumbnail_small_url || post.original_url;
}

function formatMeta(value: string): string {
  return value
    .trim()
    .replace(/[\s-]+/g, "_")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as {
    response?: { data?: { detail?: string; message?: string } };
    message?: string;
  };
  return apiError.response?.data?.detail || apiError.response?.data?.message || apiError.message || fallback;
}

function getApiStatus(error: unknown): number | undefined {
  const apiError = error as { status?: number; response?: { status?: number } };
  return apiError.status || apiError.response?.status;
}

function getVisibilityLabel(value: string): string {
  if (value === "private") return "Private";
  if (value === "friends") return "Friends";
  return "Public";
}

function HeartIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 20.2s-7.4-4.6-9.2-9.4C1.6 7.5 3.6 4.5 6.8 4.5c1.8 0 3.2.9 4.1 2.2.9-1.3 2.3-2.2 4.1-2.2 3.2 0 5.2 3 4 6.3-1.7 4.8-9 9.4-9 9.4Z"
        fill="currentColor"
      />
    </svg>
  );
}

function CommentIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5.2 18.4c-1.7-1.4-2.7-3.4-2.7-5.7 0-4.6 4.1-8.2 9.5-8.2s9.5 3.6 9.5 8.2-4.1 8.2-9.5 8.2c-1.2 0-2.3-.2-3.4-.5L4.5 21.5c-.7.2-1.2-.5-.9-1.1l1.6-2Z"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100dvh",
    padding: "18px 0 112px",
    background: "#ffffff",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  topBar: {
    width: "min(430px, 100%)",
    margin: "0 auto",
    minHeight: 48,
    display: "grid",
    gridTemplateColumns: "48px minmax(0, 1fr) 48px",
    alignItems: "center",
    padding: "0 10px",
  },
  backButton: {
    border: "none",
    background: "transparent",
    color: "#8d8d8d",
    fontSize: "2.4rem",
    lineHeight: 1,
    cursor: "pointer",
  },
  topTitle: {
    color: "#171717",
    textAlign: "center",
    fontSize: "1.05rem",
  },
  topSpacer: {
    width: 48,
  },
  profileHeader: {
    width: "min(430px, 100%)",
    margin: "8px auto 18px",
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "0 18px",
  },
  avatar: {
    width: 84,
    height: 84,
    borderRadius: "50%",
    objectFit: "cover",
    background: "var(--surface-muted)",
  },
  profileText: {
    minWidth: 0,
  },
  name: {
    margin: 0,
    color: "#171717",
    fontSize: "1.3rem",
    lineHeight: 1.15,
  },
  meta: {
    margin: "6px 0 0",
    color: "var(--brand-primary-deep)",
    fontSize: "0.84rem",
    fontWeight: 900,
    overflowWrap: "anywhere",
  },
  count: {
    margin: "6px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.86rem",
    fontWeight: 800,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 3,
    width: "min(430px, 100%)",
    margin: "0 auto",
  },
  tile: {
    width: "100%",
    aspectRatio: "1 / 1",
    padding: 0,
    border: "none",
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
    width: "min(394px, calc(100% - 32px))",
    margin: "18px auto",
    padding: 22,
    borderRadius: 18,
    background: "var(--surface-muted)",
    color: "var(--neutral-700)",
    fontWeight: 800,
    textAlign: "center",
  },
  loadMoreButton: {
    display: "block",
    width: "min(394px, calc(100% - 32px))",
    minHeight: 44,
    margin: "16px auto 0",
    border: "none",
    borderRadius: 14,
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  detailBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 72,
    display: "grid",
    placeItems: "center",
    padding: 10,
    background: "rgba(8,12,16,0.74)",
  },
  detailCard: {
    position: "relative",
    width: "min(430px, calc(100% - 8px))",
    maxHeight: "94dvh",
    overflowY: "auto",
    borderRadius: 18,
    background: "#ffffff",
    boxShadow: "0 24px 70px rgba(0,0,0,0.28)",
    display: "grid",
    gridTemplateColumns: "1fr",
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
    height: "100%",
    maxHeight: "58dvh",
    objectFit: "contain",
    display: "block",
    background: "#050608",
  },
  detailImagePane: {
    minHeight: "min(58dvh, 520px)",
    background: "#050608",
  },
  detailSidePane: {
    minHeight: 260,
    display: "flex",
    flexDirection: "column",
    borderTop: "1px solid var(--border-soft)",
    background: "#ffffff",
  },
  postHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "14px 16px",
    borderBottom: "1px solid var(--border-soft)",
  },
  postAvatar: {
    width: 36,
    height: 36,
    borderRadius: "50%",
    objectFit: "cover",
  },
  postAuthor: {
    color: "var(--text-primary)",
    fontSize: "0.92rem",
  },
  postVisibility: {
    margin: "2px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.72rem",
    fontWeight: 800,
  },
  detailError: {
    margin: "10px 14px 0",
    padding: "10px 12px",
    borderRadius: 12,
    background: "rgba(220,38,38,0.1)",
    color: "#b91c1c",
    fontSize: "0.82rem",
    fontWeight: 800,
  },
  commentsList: {
    flex: 1,
    minHeight: 0,
    maxHeight: "42dvh",
    overflowY: "auto",
    padding: "12px 14px",
  },
  commentsState: {
    padding: 16,
    color: "var(--neutral-700)",
    fontWeight: 800,
    textAlign: "center",
  },
  commentItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    padding: "8px 0",
  },
  commentAvatar: {
    width: 30,
    height: 30,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  commentBody: {
    minWidth: 0,
    flex: 1,
  },
  commentAuthor: {
    color: "var(--text-primary)",
    fontSize: "0.84rem",
  },
  commentText: {
    margin: "2px 0 0",
    color: "var(--text-secondary)",
    fontSize: "0.86rem",
    lineHeight: 1.4,
    overflowWrap: "anywhere",
  },
  commentDeleteButton: {
    border: "none",
    background: "transparent",
    color: "#ef4444",
    fontSize: "0.72rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  postFooter: {
    padding: "10px 14px 12px",
    borderTop: "1px solid var(--border-soft)",
  },
  actionSummary: {
    display: "flex",
    alignItems: "center",
    gap: 18,
  },
  likeIconButton: {
    border: "none",
    padding: 0,
    background: "transparent",
    color: "#ef4444",
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    fontWeight: 900,
    cursor: "pointer",
  },
  commentSummary: {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    color: "var(--text-primary)",
    fontWeight: 900,
  },
  actionCount: {
    minWidth: 10,
    color: "var(--text-primary)",
    fontSize: "0.94rem",
    fontWeight: 900,
  },
  likesList: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
    marginTop: 8,
  },
  likeUser: {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    padding: "5px 8px",
    borderRadius: 999,
    background: "var(--surface-muted)",
    color: "var(--text-secondary)",
    fontSize: "0.75rem",
    fontWeight: 800,
  },
  likeAvatar: {
    width: 18,
    height: 18,
    borderRadius: "50%",
    objectFit: "cover",
  },
  commentForm: {
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 8,
    marginTop: 12,
  },
  commentInput: {
    minHeight: 38,
    minWidth: 0,
    border: "1px solid var(--border-soft)",
    borderRadius: 999,
    padding: "0 12px",
    color: "var(--text-primary)",
    outline: "none",
  },
  commentSubmit: {
    border: "none",
    borderRadius: 999,
    padding: "0 14px",
    background: "var(--text-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  caption: {
    margin: "14px 16px 0",
    color: "var(--text-secondary)",
    fontWeight: 800,
    lineHeight: 1.45,
  },
};
