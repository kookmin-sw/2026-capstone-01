import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMyProfile } from "../api/auth/auth";
import { createDirectChatRoom } from "../api/chat";
import {
  getFeedPopup,
  getUserFeedPosts,
  type FeedPost,
  type FeedPopupResponse,
} from "../api/feed";
import { getFriendDetail, sendFriendRequest, type FriendshipStatus } from "../api/friend";

const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

export default function FeedPopup({
  userId,
  onClose,
}: {
  userId: string;
  onClose: () => void;
  side?: "left" | "right";
}) {
  const navigate = useNavigate();
  const [popup, setPopup] = useState<FeedPopupResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPost, setSelectedPost] = useState<FeedPost | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMoreFeed, setHasMoreFeed] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [viewerUserId, setViewerUserId] = useState("");
  const [friendshipStatus, setFriendshipStatus] = useState<FriendshipStatus | null>(null);
  const [isRequester, setIsRequester] = useState<boolean | null>(null);
  const [relationshipBusy, setRelationshipBusy] = useState(false);
  const [sheetState, setSheetState] = useState<"collapsed" | "expanded">("collapsed");

  const sheetRef = useRef<HTMLDivElement>(null);
  const dragPointerIdRef = useRef<number | null>(null);
  const dragStartYRef = useRef(0);
  const dragRafRef = useRef<number | null>(null);
  const dragBaseRef = useRef(0);

  function getCollapsedY(): number {
    return Math.round(window.innerHeight * 0.45);
  }
  function applyTransform(state: "collapsed" | "expanded", withTransition = true): void {
    const el = sheetRef.current;
    if (!el) return;
    el.style.transition = withTransition ? "transform 300ms cubic-bezier(0.22,1,0.36,1)" : "none";
    el.style.transform = state === "expanded" ? "translate3d(0,0,0)" : `translate3d(0,${getCollapsedY()}px,0)`;
  }

  useEffect(() => {
    requestAnimationFrame(() => {
      const el = sheetRef.current;
      if (!el) return;
      el.style.transition = "none";
      el.style.transform = `translate3d(0,${getCollapsedY()}px,0)`;
      requestAnimationFrame(() => {
        if (sheetRef.current) sheetRef.current.style.transition = "transform 300ms cubic-bezier(0.22,1,0.36,1)";
      });
    });
  }, []);

  useEffect(() => {
    let isMounted = true;
    getFeedPopup(userId)
      .then((response) => {
        if (isMounted) {
          setPopup(response);
          setNextCursor(response.feed.items[response.feed.items.length - 1]?.post_id ?? null);
          setHasMoreFeed(response.feed.items.length >= 9);
        }
      })
      .catch((loadError) => { if (isMounted) setError(toErrorMessage(loadError, "Feed could not be loaded.")); })
      .finally(() => { if (isMounted) setLoading(false); });
    return () => { isMounted = false; };
  }, [userId]);

  useEffect(() => {
    let mounted = true;
    getMyProfile()
      .then((viewer) => { if (mounted) setViewerUserId(viewer?.user_id ?? ""); })
      .catch(() => { if (mounted) setViewerUserId(""); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    if (!viewerUserId || viewerUserId === userId) return undefined;
    getFriendDetail(userId)
      .then((detail) => {
        if (!mounted) return;
        setFriendshipStatus(detail.friendship_status);
        setIsRequester(detail.is_requester);
      })
      .catch(() => { if (!mounted) return; setFriendshipStatus(null); setIsRequester(null); });
    return () => { mounted = false; };
  }, [userId, viewerUserId]);

  const profileMetaItems = [popup?.nationality, ...(popup?.travel_styles ?? [])]
    .filter((value): value is string => Boolean(value))
    .map(formatProfileMeta)
    .slice(0, 3);
  const canShowProfileActions = Boolean(viewerUserId && viewerUserId !== userId);
  const totalLikes = popup?.feed.items.reduce((sum, post) => sum + post.like_count, 0) ?? 0;

  async function handleAddFriend(): Promise<void> {
    if (relationshipBusy || !canShowProfileActions) return;
    setRelationshipBusy(true);
    try {
      const friendship = await sendFriendRequest(userId);
      setFriendshipStatus(friendship.status);
      setIsRequester(friendship.is_requester);
    } catch (requestError) {
      setError(toErrorMessage(requestError, "Failed to send friend request."));
    } finally { setRelationshipBusy(false); }
  }

  async function handleOpenChat(): Promise<void> {
    if (relationshipBusy || !canShowProfileActions) return;
    setRelationshipBusy(true);
    try {
      const room = await createDirectChatRoom(userId);
      if (!room?.chat_room_id) throw new Error("Failed to open chat room.");
      onClose();
      navigate(`/chat/${room.chat_room_id}`);
    } catch (chatError) {
      setError(toErrorMessage(chatError, "Failed to open chat."));
    } finally { setRelationshipBusy(false); }
  }

  async function handleLoadMore(): Promise<void> {
    if (!popup || loadingMore || !hasMoreFeed) return;
    const cursor = nextCursor || popup.feed.items[popup.feed.items.length - 1]?.post_id;
    if (!cursor) return;
    setLoadingMore(true); setError("");
    try {
      const response = await getUserFeedPosts(userId, cursor);
      setPopup((current) => {
        if (!current) return current;
        const existingIds = new Set(current.feed.items.map((post) => post.post_id));
        const nextItems = response.posts.filter((post) => !existingIds.has(post.post_id));
        return { ...current, feed: { items: [...current.feed.items, ...nextItems] } };
      });
      setNextCursor(response.next_cursor);
      setHasMoreFeed(Boolean(response.next_cursor));
    } catch (loadError) {
      setError(toErrorMessage(loadError, "More feed photos could not be loaded."));
    } finally { setLoadingMore(false); }
  }

  function onHandleDown(e: React.PointerEvent<HTMLButtonElement>): void {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragPointerIdRef.current = e.pointerId;
    dragStartYRef.current = e.clientY;
    dragBaseRef.current = sheetState === "expanded" ? 0 : getCollapsedY();
    const el = sheetRef.current;
    if (el) el.style.transition = "none";
  }
  function onHandleMove(e: React.PointerEvent<HTMLButtonElement>): void {
    if (dragPointerIdRef.current !== e.pointerId) return;
    const y = Math.max(0, dragBaseRef.current + (e.clientY - dragStartYRef.current));
    if (dragRafRef.current !== null) cancelAnimationFrame(dragRafRef.current);
    dragRafRef.current = requestAnimationFrame(() => {
      if (sheetRef.current) sheetRef.current.style.transform = `translate3d(0,${y}px,0)`;
      dragRafRef.current = null;
    });
  }
  function onHandleUp(e: React.PointerEvent<HTMLButtonElement>): void {
    if (dragPointerIdRef.current !== e.pointerId) return;
    dragPointerIdRef.current = null;
    if (dragRafRef.current !== null) { cancelAnimationFrame(dragRafRef.current); dragRafRef.current = null; }
    const deltaY = e.clientY - dragStartYRef.current;
    const vh = window.innerHeight;
    if (deltaY > Math.max(150, vh * 0.22)) { onClose(); return; }
    if (sheetState === "collapsed" && deltaY < -80) {
      setSheetState("expanded"); applyTransform("expanded");
    } else if (sheetState === "expanded" && deltaY > 80) {
      setSheetState("collapsed"); applyTransform("collapsed");
    } else {
      applyTransform(sheetState);
    }
  }

  return (
    <>
      <div style={styles.backdrop} onClick={onClose} />
      <div ref={sheetRef} style={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          style={styles.handleBtn}
          onPointerDown={onHandleDown}
          onPointerMove={onHandleMove}
          onPointerUp={onHandleUp}
          onPointerCancel={onHandleUp}
          aria-label="Drag to expand or close"
        >
          <span style={styles.handle} />
        </button>

        {loading ? (
          <div style={styles.statePanel}>Loading feed...</div>
        ) : error ? (
          <div style={styles.statePanel}>{error}</div>
        ) : popup ? (
          <>
            {/* Profile — MyPage 동일 구조 */}
            <section style={styles.socialProfile}>
              <div style={styles.avatarWrap}>
                <img src={popup.profile_image_url || DEFAULT_PROFILE_IMAGE_URL} alt="" style={styles.avatarImage} />
              </div>
              <div style={styles.socialProfileBody}>
                <div style={styles.socialNameRow}>
                  <h2 style={styles.name}>{popup.user_name || "Unknown"}</h2>
                </div>
                <div style={styles.profileStatsRow}>
                  <span style={styles.profileStat}>
                    <strong style={styles.profileStatNumber}>{popup.feed.items.length}</strong>
                    <span>Posts</span>
                  </span>
                  <span style={styles.profileStat}>
                    <strong style={styles.profileStatNumber}>{totalLikes}</strong>
                    <span>Likes</span>
                  </span>
                </div>
                {profileMetaItems.length ? (
                  <div style={styles.profileChipRow}>
                    {profileMetaItems.map((chip) => (
                      <span key={chip} style={styles.profileChip}>{chip}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            </section>

            {canShowProfileActions ? (
              <section style={styles.profileActionBar}>
                <button type="button" style={styles.profileActionButton} onClick={() => void handleOpenChat()} disabled={relationshipBusy}>
                  <ChatIcon />
                  <span>Chat</span>
                </button>
                <span style={styles.profileActionDivider} />
                <button
                  type="button"
                  style={{ ...styles.profileActionButton, ...(friendshipStatus === "accepted" || friendshipStatus === "pending" ? styles.profileActionButtonDone : {}) }}
                  onClick={() => void handleAddFriend()}
                  disabled={relationshipBusy || friendshipStatus === "pending" || friendshipStatus === "accepted"}
                >
                  <AddFriendIcon />
                  <span>{friendshipStatus === "accepted" ? "Friends" : friendshipStatus === "pending" ? (isRequester ? "Requested" : "Pending") : "Add Friend"}</span>
                </button>
              </section>
            ) : null}
            <div style={styles.profileActionDividerLine} />

            <section style={styles.section}>
              {popup.feed.items.length ? (
                <div style={styles.feedGrid}>
                  {popup.feed.items.map((post) => (
                    <button key={post.post_id} type="button" style={styles.feedTile} onClick={() => setSelectedPost(post)}>
                      <img src={getFeedImageUrl(post)} alt="" style={styles.feedTileImage} />
                      <span style={styles.feedTileMeta}>{post.like_count} likes · {post.comment_count} comments</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div style={styles.statePanel}>No visible feed photos.</div>
              )}
              {hasMoreFeed ? (
                <button type="button" style={styles.loadMoreButton} onClick={() => void handleLoadMore()} disabled={loadingMore}>
                  {loadingMore ? "Loading..." : "More"}
                </button>
              ) : null}
            </section>
          </>
        ) : null}

        {selectedPost ? (
          <div style={styles.detailBackdrop} onClick={() => setSelectedPost(null)}>
            <div style={styles.detailCard} onClick={(e) => e.stopPropagation()}>
              <div style={styles.sheetHandle} />
              <button type="button" style={styles.detailClose} onClick={() => setSelectedPost(null)}>x</button>
              <img src={selectedPost.original_url} alt="" style={styles.detailImage} />
              {selectedPost.caption ? <p style={styles.caption}>{selectedPost.caption}</p> : null}
              <p style={styles.meta}>{selectedPost.like_count} likes · {selectedPost.comment_count} comments</p>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

function ChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}
function AddFriendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <line x1="19" y1="8" x2="19" y2="14" />
      <line x1="22" y1="11" x2="16" y2="11" />
    </svg>
  );
}
function getFeedImageUrl(post: FeedPost): string {
  return post.thumbnail_medium_url || post.thumbnail_small_url || post.original_url;
}
function formatProfileMeta(value: string): string {
  return value.trim().replace(/[\s-]+/g, "_").replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}
function toErrorMessage(error: unknown, fallback: string): string {
  const e = error as { response?: { data?: { detail?: string; message?: string } }; message?: string };
  return e.response?.data?.detail || e.response?.data?.message || e.message || fallback;
}

const styles: Record<string, CSSProperties> = {
  backdrop: { position: "fixed", inset: 0, zIndex: 70, background: "rgba(24,26,32,0.42)" },
  sheet: {
    position: "fixed", inset: 0, zIndex: 71,
    background: "var(--surface-panel, #fff)",
    height: "100dvh", overflowY: "auto",
    willChange: "transform", transform: "translate3d(0,100vh,0)",
    padding: "0 12px calc(24px + var(--app-safe-bottom, 0px))",
  },
  handleBtn: {
    width: "100%", minHeight: 32, padding: "8px 0 4px",
    border: "none", background: "transparent",
    display: "grid", placeItems: "center",
    cursor: "grab", touchAction: "none", userSelect: "none",
  },
  handle: { display: "block", width: 48, height: 5, borderRadius: 999, background: "#dadada" },
  /* ── MyPage와 동일한 값 ── */
  socialProfile: { maxWidth: 540, margin: "0 auto", display: "grid", gridTemplateColumns: "132px minmax(0,1fr)", gap: 14, alignItems: "center", padding: "16px 6px 20px" },
  avatarWrap: { position: "relative" },
  avatarImage: { width: 108, height: 108, borderRadius: "50%", objectFit: "cover", border: "4px solid #ffffff", boxShadow: "0 8px 18px rgba(33,33,33,0.1)", display: "block" },
  socialProfileBody: { minWidth: 0 },
  socialNameRow: { display: "flex", alignItems: "center", minHeight: 32 },
  name: { margin: 0, color: "#1a1a1a", fontSize: "1.25rem", fontWeight: 400, lineHeight: 1.15, letterSpacing: "-0.02em" },
  profileStatsRow: { display: "flex", alignItems: "center", gap: 26, marginTop: 6, marginBottom: 12 },
  profileStat: { minWidth: 56, color: "#323232", fontSize: "0.98rem", fontWeight: 400, lineHeight: 1.28, letterSpacing: "-0.02em", display: "flex", flexDirection: "column", alignItems: "flex-start" },
  profileStatNumber: { fontWeight: 400 },
  profileChipRow: { display: "flex", alignItems: "center", gap: 6, overflow: "hidden" },
  profileChip: { height: 22, maxWidth: 116, padding: "0 10px", border: "0.7px solid #d7d7d7", borderRadius: 24, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#606060", fontSize: "0.68rem", fontWeight: 400, lineHeight: 1, letterSpacing: "-0.02em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  profileActionBar: { maxWidth: 525, minHeight: 50, margin: "6px auto 0", border: "1px solid #bebebe", borderRadius: 12, background: "#ffffff", boxShadow: "0 1px 8px rgba(0,0,0,0.04)", display: "grid", gridTemplateColumns: "1fr 1px 1fr", alignItems: "center" },
  profileActionButton: { height: 50, border: "none", padding: 0, background: "transparent", color: "#606060", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 16, fontSize: "1rem", fontWeight: 400, letterSpacing: "-0.02em", cursor: "pointer" },
  profileActionButtonDone: { color: "var(--neutral-500, #aaa)" },
  profileActionDivider: { width: 1, height: 31, background: "#bebebe" },
  profileActionDividerLine: { height: 1, background: "#d7d7d7", margin: "16px 0 10px" },
  section: { width: "calc(100% + 24px)", maxWidth: "none", margin: "0 -12px" },
  feedGrid: { display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 2 },
  feedTile: { position: "relative", padding: 0, border: "none", borderRadius: 0, overflow: "hidden", background: "#050608", aspectRatio: "1 / 1", cursor: "pointer" },
  feedTileImage: { width: "100%", height: "100%", objectFit: "cover", display: "block" },
  feedTileMeta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: "18px 8px 8px", background: "linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,0.62))", color: "#ffffff", fontSize: "0.72rem", fontWeight: 900, textAlign: "left" },
  statePanel: { margin: "16px 18px", padding: 22, borderRadius: 20, background: "rgba(255,255,255,0.9)", border: "1px solid var(--border-soft)", color: "var(--neutral-700)", fontWeight: 800 },
  loadMoreButton: { width: "calc(100% - 36px)", minHeight: 44, margin: "14px 18px 0", border: "none", borderRadius: 14, background: "var(--brand-primary)", color: "#ffffff", fontWeight: 900, cursor: "pointer" },
  detailBackdrop: { position: "fixed", inset: 0, zIndex: 72, display: "grid", placeItems: "center", padding: "calc(18px + var(--app-safe-top)) 18px calc(18px + var(--app-safe-bottom))", background: "rgba(8,12,16,0.74)" },
  detailCard: { position: "relative", width: "min(560px, 100%)", maxHeight: "88dvh", overflowY: "auto", borderRadius: 22, background: "#ffffff", boxShadow: "0 24px 70px rgba(0,0,0,0.28)" },
  sheetHandle: { position: "absolute", top: 8, left: "50%", transform: "translateX(-50%)", width: 48, height: 4, borderRadius: 999, background: "rgba(255,255,255,0.64)", zIndex: 3 },
  detailClose: { position: "absolute", top: 12, right: 12, width: 34, height: 34, border: "none", borderRadius: "50%", background: "rgba(16,34,35,0.72)", color: "#ffffff", fontWeight: 900, cursor: "pointer" },
  detailImage: { width: "100%", maxHeight: "70dvh", objectFit: "contain", display: "block", background: "#050608" },
  caption: { margin: "14px 16px 0", color: "var(--text-secondary)", fontWeight: 800, lineHeight: 1.45 },
  meta: { margin: "8px 16px 16px", color: "var(--neutral-700)", fontSize: "0.86rem", fontWeight: 800 },
};
