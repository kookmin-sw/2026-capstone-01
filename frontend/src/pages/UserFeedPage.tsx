import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMyProfile } from "../api/auth/auth";
import { navigateBackOrFallback } from "../utils/navigation";
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
import { createDirectChatRoom } from "../api/chat";
import {
  getFriendDetail,
  sendFriendRequest,
  type FriendshipStatus,
} from "../api/friend";
import ConfirmToast from "../components/ConfirmToast";

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
  const [isMetaExpanded, setIsMetaExpanded] = useState(false);
  const [friendshipStatus, setFriendshipStatus] = useState<FriendshipStatus | null>(null);
  const [isRequester, setIsRequester] = useState<boolean | null>(null);
  const [relationshipBusy, setRelationshipBusy] = useState(false);
  const [commentDeleteTarget, setCommentDeleteTarget] = useState<FeedComment | null>(null);

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
        setNextCursor(response.feed.items[response.feed.items.length - 1]?.post_id ?? null);
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

  useEffect(() => {
    let mounted = true;
    if (!id || !viewerUserId || id === viewerUserId) {
      setFriendshipStatus(null);
      setIsRequester(null);
      return undefined;
    }

    getFriendDetail(id)
      .then((detail) => {
        if (!mounted) return;
        setFriendshipStatus(detail.friendship_status);
        setIsRequester(detail.is_requester);
      })
      .catch(() => {
        if (!mounted) return;
        setFriendshipStatus(null);
        setIsRequester(null);
      });

    return () => {
      mounted = false;
    };
  }, [id, viewerUserId]);

  async function handleAddFriend(): Promise<void> {
    if (!id || relationshipBusy || id === viewerUserId) return;

    setRelationshipBusy(true);
    try {
      const friendship = await sendFriendRequest(id);
      setFriendshipStatus(friendship.status);
      setIsRequester(friendship.is_requester);
    } catch (requestError) {
      setError(toErrorMessage(requestError, "Failed to send friend request."));
    } finally {
      setRelationshipBusy(false);
    }
  }

  async function handleOpenChat(): Promise<void> {
    if (!id || relationshipBusy || id === viewerUserId) return;

    setRelationshipBusy(true);
    try {
      const room = await createDirectChatRoom(id);
      if (!room?.chat_room_id) {
        throw new Error("Failed to open chat room.");
      }
      navigate(`/chat/${room.chat_room_id}`);
    } catch (chatError) {
      setError(toErrorMessage(chatError, "Failed to open chat."));
    } finally {
      setRelationshipBusy(false);
    }
  }

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
      current.map((item) => (item.post_id === post.post_id ? mergeFeedPost(item, post) : item))
    );
    setSelectedPost((current) =>
      current?.post_id === post.post_id ? mergeFeedPost(current, post) : current
    );
  }

  async function handleLike(): Promise<void> {
    if (!selectedPost || detailBusy) return;

    const previousPost = selectedPost;
    const nextLiked = !previousPost.is_liked;
    const optimisticPost = {
      ...previousPost,
      is_liked: nextLiked,
      like_count: Math.max(0, previousPost.like_count + (nextLiked ? 1 : -1)),
    };

    setDetailBusy(true);
    setDetailError("");
    updatePostState(optimisticPost);
    try {
      const response = nextLiked
        ? await likeFeedPost(previousPost.post_id)
        : await unlikeFeedPost(previousPost.post_id);
      updatePostState({
        ...optimisticPost,
        like_count: response.like_count,
        is_liked: nextLiked,
      });
      setSelectedLikes((await getFeedPostLikes(previousPost.post_id)).users);
    } catch (likeError) {
      updatePostState(previousPost);
      setDetailError(toErrorMessage(likeError, "Failed to update like."));
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
    setCommentDeleteTarget(comment);
  }

  async function confirmCommentDelete(): Promise<void> {
    if (!selectedPost || !commentDeleteTarget || detailBusy) return;

    setDetailBusy(true);
    setDetailError("");
    try {
      await deleteFeedComment(selectedPost.post_id, commentDeleteTarget.comment_id);
      setSelectedComments((current) =>
        current.filter((item) => item.comment_id !== commentDeleteTarget.comment_id)
      );
      updatePostState({
        ...selectedPost,
        comment_count: Math.max(0, selectedPost.comment_count - 1),
      });
      setCommentDeleteTarget(null);
    } catch (deleteError) {
      setDetailError(toErrorMessage(deleteError, "Failed to delete comment."));
    } finally {
      setDetailBusy(false);
    }
  }

  const profileMetaItems = [profile?.nationality, ...(profile?.travel_styles ?? [])]
    .filter((value): value is string => Boolean(value))
    .map(formatMeta);
  const previewChips = profileMetaItems.slice(0, 3);
  const expandedChips = profileMetaItems.slice(3);
  const canExpandChips = profileMetaItems.length > 3;
  const canShowProfileActions = Boolean(id && viewerUserId && id !== viewerUserId);

  return (
    <div style={styles.page}>
      <header style={styles.topBar}>
        <button
          type="button"
          style={styles.backButton}
          onClick={() => navigateBackOrFallback(navigate, "/my")}
        >
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
          <section style={styles.socialProfile}>
            <div style={styles.avatarWrap}>
              <img
                src={profile.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                alt=""
                style={styles.avatarImage}
              />
            </div>
            <div style={styles.socialProfileBody}>
              <div style={styles.socialNameRow}>
                <h1 style={styles.name}>{profile.user_name || "Unknown"}</h1>
              </div>
              <div style={styles.profileStatsRow}>
                <span style={styles.profileStat}>
                  <strong style={styles.profileStatNumber}>{posts.length}</strong>
                  <span>Posts</span>
                </span>
                <span style={styles.profileStat}>
                  <strong style={styles.profileStatNumber}>
                    {posts.reduce((sum, p) => sum + p.like_count, 0)}
                  </strong>
                  <span>Likes</span>
                </span>
              </div>
              {previewChips.length ? (
                <div style={styles.profileChipBlock}>
                  <div style={styles.profileChipPreviewRow}>
                    {previewChips.map((item) => (
                      <span key={item} style={styles.profileChip}>{item}</span>
                    ))}
                    {canExpandChips ? (
                      <button
                        type="button"
                        style={styles.profileChipToggle}
                        onClick={() => setIsMetaExpanded((current) => !current)}
                        aria-label={isMetaExpanded ? "Show fewer" : "Show all travel styles"}
                        aria-expanded={isMetaExpanded}
                      >
                        <ChevronDownIcon flipped={isMetaExpanded} />
                      </button>
                    ) : null}
                  </div>
                  {canExpandChips ? (
                    <div
                      style={{
                        ...styles.profileChipExpandedRow,
                        ...(isMetaExpanded ? styles.profileChipExpandedRowOpen : {}),
                      }}
                    >
                      {expandedChips.map((item) => (
                        <span key={item} style={styles.profileChip}>{item}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </section>

          {canShowProfileActions ? (
            <section style={styles.profileActionBar}>
              <button
                type="button"
                style={styles.profileActionButton}
                onClick={() => void handleOpenChat()}
                disabled={relationshipBusy}
              >
                <ChatSvg />
                <span>Chat</span>
              </button>
              <span style={styles.profileActionDivider} />
              <button
                type="button"
                style={styles.profileActionButton}
                onClick={() => void handleAddFriend()}
                disabled={relationshipBusy || friendshipStatus === "accepted" || friendshipStatus === "pending"}
              >
                <AddFriendSvg />
                <span>
                  {friendshipStatus === "accepted"
                    ? "Friends"
                    : friendshipStatus === "pending"
                      ? isRequester ? "Requested" : "Pending"
                      : "Add Friend"}
                </span>
              </button>
            </section>
          ) : null}
          <div style={styles.profileActionDividerLine} />

          <section style={styles.section}>
            {posts.length > 0 ? (
              <div style={styles.feedGrid}>
                {posts.map((post) => (
                  <button
                    key={post.post_id}
                    type="button"
                    style={styles.feedTile}
                    onClick={() => void openPost(post)}
                  >
                    <img src={getFeedImageUrl(post)} alt="" style={styles.feedTileImage} />
                    <span style={styles.feedTileMeta}>
                      {post.like_count} likes · {post.comment_count} comments
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </section>

        </>
      ) : null}

      {selectedPost ? (
        <div style={styles.detailBackdrop} onClick={() => setSelectedPost(null)}>
          <div style={styles.detailCard} onClick={(event) => event.stopPropagation()}>
            <div style={styles.sheetHandle} />
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
                    <HeartIcon filled={selectedPost.is_liked} />
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

      {commentDeleteTarget ? (
        <ConfirmToast
          title="Delete this comment?"
          message="This action cannot be undone."
          confirmLabel="Delete"
          destructive
          busy={detailBusy}
          onCancel={() => setCommentDeleteTarget(null)}
          onConfirm={() => void confirmCommentDelete()}
        />
      ) : null}
    </div>
  );
}

function getFeedImageUrl(post: FeedPost): string {
  return post.thumbnail_medium_url || post.thumbnail_small_url || post.original_url;
}

function mergeFeedPost(current: FeedPost, next: FeedPost): FeedPost {
  return {
    ...current,
    ...next,
    is_liked:
      typeof next.is_liked === "boolean" ? next.is_liked : current.is_liked,
  };
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

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 20.2s-7.4-4.6-9.2-9.4C1.6 7.5 3.6 4.5 6.8 4.5c1.8 0 3.2.9 4.1 2.2.9-1.3 2.3-2.2 4.1-2.2 3.2 0 5.2 3 4 6.3-1.7 4.8-9 9.4-9 9.4Z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
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

function ChatSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function AddFriendSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <line x1="19" y1="8" x2="19" y2="14" />
      <line x1="22" y1="11" x2="16" y2="11" />
    </svg>
  );
}

function ChevronDownIcon({ flipped }: { flipped: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true" stroke="#606060" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: flipped ? "rotate(180deg)" : "none", transition: "transform 200ms" }}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(18px + var(--app-safe-top)) 12px calc(78px + var(--app-bottom-nav-reserved))",
    background: "#f5f5f5",
    fontFamily: "'Apple SD Gothic Neo', 'Pretendard Variable', 'Nunito', sans-serif",
  },
  topBar: {
    width: "min(500px, 100%)",
    margin: "0 auto",
    minHeight: 48,
    display: "grid",
    gridTemplateColumns: "48px minmax(0, 1fr) 48px",
    alignItems: "center",
    padding: "0 4px",
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
  socialProfile: {
    maxWidth: 500,
    margin: "0 auto",
    display: "grid",
    gridTemplateColumns: "116px minmax(0, 1fr)",
    gap: 8,
    alignItems: "center",
    padding: "0 4px 20px",
  },
  socialProfileBody: {
    minWidth: 0,
  },
  socialNameRow: {
    display: "flex",
    alignItems: "center",
    minHeight: 32,
  },
  name: {
    margin: 0,
    color: "#1a1a1a",
    fontSize: "1.25rem",
    fontWeight: 400,
    lineHeight: 1.15,
    letterSpacing: "-0.02em",
  },
  profileStatsRow: {
    display: "flex",
    alignItems: "center",
    gap: 22,
    marginTop: 6,
    marginBottom: 12,
  },
  profileStat: {
    minWidth: 56,
    color: "#323232",
    fontSize: "0.862rem",
    fontWeight: 400,
    lineHeight: 1.28,
    letterSpacing: "-0.02em",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "flex-start",
  },
  profileStatNumber: {
    fontWeight: 400,
  },
  profileChipBlock: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 6,
    maxWidth: 360,
  },
  profileChipPreviewRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "nowrap" as const,
    maxWidth: "100%",
    overflow: "hidden",
  },
  profileChipExpandedRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "wrap" as const,
    maxHeight: 0,
    opacity: 0,
    overflow: "hidden",
    transform: "translateY(-6px)",
    transition: "max-height 260ms ease, opacity 220ms ease, transform 260ms ease",
  },
  profileChipExpandedRowOpen: {
    maxHeight: 120,
    opacity: 1,
    transform: "translateY(0)",
  },
  profileChip: {
    height: 22,
    maxWidth: 116,
    minWidth: 0,
    padding: "0 10px",
    border: "0.7px solid #d7d7d7",
    borderRadius: 24,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#606060",
    fontSize: "0.68rem",
    fontWeight: 400,
    lineHeight: 1,
    letterSpacing: "-0.02em",
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  profileChipToggle: {
    width: 24,
    height: 24,
    flex: "0 0 24px",
    border: "none",
    borderRadius: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    background: "transparent",
    cursor: "pointer",
    padding: 0,
  },
  avatarWrap: {
    position: "relative",
  },
  avatarImage: {
    width: 108,
    height: 108,
    borderRadius: "50%",
    objectFit: "cover" as const,
    border: "4px solid #ffffff",
    background: "var(--neutral-100)",
    boxShadow: "0 8px 18px rgba(33,33,33,0.1)",
    display: "block",
  },
  profileActionBar: {
    maxWidth: 525,
    minHeight: 50,
    margin: "6px auto 0",
    border: "1px solid #bebebe",
    borderRadius: 12,
    background: "#ffffff",
    boxShadow: "0 1px 8px rgba(0,0,0,0.04)",
    display: "grid",
    gridTemplateColumns: "1fr 1px 1fr",
    alignItems: "center",
  },
  profileActionButton: {
    height: 50,
    border: "none",
    padding: 0,
    background: "transparent",
    color: "#606060",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    fontSize: "1rem",
    fontWeight: 400,
    letterSpacing: "-0.02em",
    cursor: "pointer",
  },
  profileActionDivider: {
    width: 1,
    height: 31,
    background: "#bebebe",
  },
  profileActionDividerLine: {
    width: "calc(100% + 24px)",
    height: 1,
    margin: "16px -12px 10px",
    background: "#d7d7d7",
  },
  section: {
    width: "calc(100% + 24px)",
    maxWidth: "none",
    margin: "0 -12px",
  },
  feedGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 2,
  },
  feedTile: {
    position: "relative",
    padding: 0,
    border: "none",
    borderRadius: 0,
    overflow: "hidden",
    background: "#050608",
    aspectRatio: "1 / 1",
    cursor: "pointer",
  },
  feedTileImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    display: "block",
  },
  feedTileMeta: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: "18px 8px 8px",
    background: "linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,0.62))",
    color: "#ffffff",
    fontSize: "0.72rem",
    fontWeight: 900,
    textAlign: "left",
  },
  statePanel: {
    width: "min(394px, calc(100% - 32px))",
    margin: "18px auto",
    padding: 22,
    borderRadius: 18,
    background: "#f3f3f3",
    color: "#555555",
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
  sheetHandle: {
    position: "absolute",
    top: 8,
    left: "50%",
    transform: "translateX(-50%)",
    width: 48,
    height: 4,
    borderRadius: 999,
    background: "rgba(255,255,255,0.64)",
    zIndex: 3,
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
    display: "grid",
    placeItems: "center",
    background: "#050608",
    overflow: "hidden",
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
    color: "#555555",
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
