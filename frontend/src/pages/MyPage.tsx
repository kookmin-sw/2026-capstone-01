import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  deleteMyProfileImage,
  getMyProfile,
  logoutUser,
  replaceMyProfileImage,
  updateMyProfilePreferences,
  uploadMyProfileImage,
  withdrawUser,
  type ProfilePreferencesPayload,
  type UserProfile,
} from "../api/auth/auth";
import {
  createTourPlanShareToken,
  deleteTourPlan,
  listTourPlans,
  updateTourPlanTitle,
  type PlanSummaryResponse,
  type SharePlanResponse,
} from "../api/aiPlanShared";
import {
  createFeedComment,
  createFeedPost,
  deleteFeedComment,
  deleteFeedPost,
  getFeedComments,
  getFeedPostLikes,
  getMyFeedPosts,
  likeFeedPost,
  unlikeFeedPost,
  updateFeedPostCaption,
  updateFeedPostVisibility,
  type FeedComment,
  type FeedLikeUser,
  type FeedPost,
  type FeedVisibility,
} from "../api/feed";
import { showAppToast } from "../utils/appToast";

const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

type PreferenceOption = {
  key: string;
  label: string;
};

const TRAVEL_STYLE_OPTIONS: PreferenceOption[] = [
  { key: "activity", label: "Activity" },
  { key: "famous_attractions", label: "Famous Attractions" },
  { key: "healing", label: "Healing" },
  { key: "culture_history", label: "Culture & History" },
  { key: "shopping", label: "Shopping" },
  { key: "food_tour", label: "Food Tour" },
  { key: "photo_aesthetic", label: "Photo Aesthetic" },
  { key: "festival_event", label: "Festival & Event" },
  { key: "nature", label: "Nature" },
  { key: "traditional", label: "Traditional" },
  { key: "trekking", label: "Trekking" },
  { key: "hidden_gems", label: "Hidden Gems" },
  { key: "art_exhibition", label: "Art Exhibition" },
  { key: "theme_park", label: "Theme Park" },
];

const FOOD_OPTIONS: PreferenceOption[] = [
  { key: "food_halal", label: "Halal" },
  { key: "food_vegetarian", label: "Vegetarian" },
  { key: "foodie", label: "Foodie" },
  { key: "cafe_lover", label: "Cafe Lover" },
];

const DENSITY_OPTIONS: PreferenceOption[] = [
  { key: "density_relaxed", label: "Relaxed" },
  { key: "density_packed", label: "Packed" },
];

const BUDGET_OPTIONS: PreferenceOption[] = [
  { key: "budget_saving", label: "Saving" },
  { key: "budget_moderate", label: "Moderate" },
  { key: "budget_premium", label: "Premium" },
];

const WALKING_OPTIONS: PreferenceOption[] = [
  { key: "walking_low", label: "Low" },
  { key: "walking_medium", label: "Medium" },
  { key: "walking_high", label: "High" },
];

const TRANSPORT_OPTIONS: PreferenceOption[] = [
  { key: "transport_public", label: "Public Transit" },
  { key: "transport_car", label: "Car" },
  { key: "transport_taxi", label: "Taxi" },
];

const COMPANION_OPTIONS: PreferenceOption[] = [
  { key: "companion_independent", label: "Independent" },
  { key: "companion_together", label: "Together" },
  { key: "companion_flexible", label: "Flexible" },
];

const TIME_OPTIONS: PreferenceOption[] = [
  { key: "daytime", label: "Daytime" },
  { key: "nightlife", label: "Nightlife" },
  { key: "night_view", label: "Night View" },
];

const COMMUNICATION_OPTIONS: PreferenceOption[] = [
  { key: "communication_high", label: "High Communication" },
  { key: "communication_low", label: "Low Communication" },
];

const PLANNING_OPTIONS: PreferenceOption[] = [
  { key: "planner", label: "Planner" },
  { key: "spontaneous", label: "Spontaneous" },
  { key: "follower", label: "Follower" },
];

const EMPTY_PREFERENCES: ProfilePreferencesPayload = {
  travel_styles: [],
  food_preferences: [],
  density_preference: "",
  budget_preference: "",
  walking_preference: "",
  transport_preferences: [],
  companion_preference: "",
  time_preferences: [],
  communication_preference: "",
  planning_preference: "",
};

export default function MyPage() {
  const navigate = useNavigate();
  const profileImageInputRef = useRef<HTMLInputElement>(null);
  const feedImageInputRef = useRef<HTMLInputElement>(null);

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileImagePreview, setProfileImagePreview] = useState("");
  const [isUploadingProfileImage, setIsUploadingProfileImage] = useState(false);
  const [isDeletingProfileImage, setIsDeletingProfileImage] = useState(false);
  const [isProfileImageMenuOpen, setIsProfileImageMenuOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isStatusEditing, setIsStatusEditing] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusDraft, setStatusDraft] = useState("");
  const [isWithdrawing, setIsWithdrawing] = useState(false);
  const [preferenceDraft, setPreferenceDraft] =
    useState<ProfilePreferencesPayload>(EMPTY_PREFERENCES);
  const [isPreferenceEditing, setIsPreferenceEditing] = useState(false);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);

  const [feedPosts, setFeedPosts] = useState<FeedPost[]>([]);
  const [feedNextCursor, setFeedNextCursor] = useState<string | null>(null);
  const [isFeedLoading, setIsFeedLoading] = useState(false);
  const [isFeedUploading, setIsFeedUploading] = useState(false);
  const [feedError, setFeedError] = useState("");
  const [feedFile, setFeedFile] = useState<File | null>(null);
  const [feedPreviewUrl, setFeedPreviewUrl] = useState("");
  const [feedVisibility, setFeedVisibility] = useState<FeedVisibility>("public");
  const [feedCaption, setFeedCaption] = useState("");

  const [selectedFeedPost, setSelectedFeedPost] = useState<FeedPost | null>(null);
  const [selectedFeedLikes, setSelectedFeedLikes] = useState<FeedLikeUser[]>([]);
  const [selectedFeedComments, setSelectedFeedComments] = useState<FeedComment[]>([]);
  const [selectedCaptionDraft, setSelectedCaptionDraft] = useState("");
  const [isFeedPostEditing, setIsFeedPostEditing] = useState(false);
  const [isFeedPostMenuOpen, setIsFeedPostMenuOpen] = useState(false);
  const [commentInput, setCommentInput] = useState("");
  const [isFeedActionRunning, setIsFeedActionRunning] = useState(false);
  const [pendingAccountAction, setPendingAccountAction] = useState<
    "logout" | "withdraw" | null
  >(null);
  const [savedPlans, setSavedPlans] = useState<PlanSummaryResponse[]>([]);
  const [isLoadingPlans, setIsLoadingPlans] = useState(false);
  const [planMessage, setPlanMessage] = useState("");
  const [shareInfo, setShareInfo] = useState<SharePlanResponse | null>(null);
  const [shareLink, setShareLink] = useState("");

  useEffect(() => {
    getMyProfile()
      .then((data) => {
        setProfile(data);
        if (data) {
          const nextStatus = getInitialStatusMessage(data);
          setStatusMessage(nextStatus);
          setStatusDraft(nextStatus);
          setPreferenceDraft(toPreferencePayload(data));
        }
      })
      .catch(() => setProfile(null));
  }, []);

  useEffect(() => {
    void loadFeedPosts();
  }, []);

  useEffect(() => {
    refreshPlans();
  }, []);

  useEffect(() => {
    return () => {
      if (feedPreviewUrl) URL.revokeObjectURL(feedPreviewUrl);
    };
  }, [feedPreviewUrl]);

  async function loadFeedPosts(cursor?: string): Promise<void> {
    setIsFeedLoading(true);
    setFeedError("");

    try {
      const response = await getMyFeedPosts(cursor);
      setFeedPosts((current) =>
        cursor ? [...current, ...response.posts] : response.posts
      );
      setFeedNextCursor(response.next_cursor);
    } catch (error) {
      setFeedError(toErrorMessage(error, "Failed to load feed."));
      if (!cursor) setFeedPosts([]);
    } finally {
      setIsFeedLoading(false);
    }
  }

  function refreshPlans(): void {
    setIsLoadingPlans(true);
    setPlanMessage("");

    void listTourPlans()
      .then((plans) => setSavedPlans(plans))
      .catch((error) => {
        setSavedPlans([]);
        setPlanMessage(toErrorMessage(error, "Failed to load saved plans."));
      })
      .finally(() => setIsLoadingPlans(false));
  }

  async function handleRenamePlan(plan: PlanSummaryResponse): Promise<void> {
    const nextTitle = window.prompt("Plan title", plan.title || "");
    if (nextTitle === null) return;

    try {
      await updateTourPlanTitle(plan.plan_id, nextTitle.trim() || null);
      refreshPlans();
    } catch (error) {
      setPlanMessage(toErrorMessage(error, "Failed to update plan title."));
    }
  }

  async function handleDeletePlan(plan: PlanSummaryResponse): Promise<void> {
    if (!window.confirm(`Delete ${plan.title || "this plan"}?`)) return;

    try {
      await deleteTourPlan(plan.plan_id);
      setSavedPlans((current) =>
        current.filter((item) => item.plan_id !== plan.plan_id)
      );
      setPlanMessage("Plan deleted.");
      setShareInfo(null);
      setShareLink("");
    } catch (error) {
      setPlanMessage(toErrorMessage(error, "Failed to delete plan."));
    }
  }

  async function handleSharePlan(plan: PlanSummaryResponse): Promise<void> {
    try {
      const share = await createTourPlanShareToken(plan.plan_id);
      const url = `${window.location.origin}/share/plan/${share.share_token}`;
      setShareInfo(share);
      setShareLink(url);
      setPlanMessage(
        `Share link ready. Expires ${new Date(share.expires_at).toLocaleString()}`
      );
    } catch (error) {
      setPlanMessage(toErrorMessage(error, "Failed to create share link."));
    }
  }

  async function handleCopyShareLink(): Promise<void> {
    if (!shareLink) return;

    try {
      await navigator.clipboard.writeText(shareLink);
      setPlanMessage("Share link copied.");
    } catch {
      window.prompt("Copy this share link", shareLink);
    }
  }

  async function handleFeedFileSelect(
    event: React.ChangeEvent<HTMLInputElement>
  ): Promise<void> {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      window.alert("Please choose a JPG, PNG, or WEBP image.");
      event.target.value = "";
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      window.alert("Please choose an image smaller than 10MB.");
      event.target.value = "";
      return;
    }

    if (await isAnimatedFeedImage(file)) {
      window.alert("Animated WEBP/APNG images are not supported.");
      event.target.value = "";
      return;
    }

    if (feedPreviewUrl) URL.revokeObjectURL(feedPreviewUrl);
    setFeedFile(file);
    setFeedPreviewUrl(URL.createObjectURL(file));
  }

  async function handleFeedUpload(): Promise<void> {
    if (!feedFile || isFeedUploading) return;
    if (feedPosts.length >= 100) {
      window.alert("The maximum feed photo limit is 100.");
      return;
    }

    setIsFeedUploading(true);
    setFeedError("");

    try {
      const post = await createFeedPost({
        file: feedFile,
        visibility: feedVisibility,
        caption: feedCaption,
      });
      setFeedPosts((current) => [post, ...current].slice(0, 100));
      closeFeedComposer();
    } catch (error) {
      setFeedError(toErrorMessage(error, "Feed upload failed. Please try again."));
    } finally {
      setIsFeedUploading(false);
    }
  }

  function closeFeedComposer(): void {
    if (feedPreviewUrl) URL.revokeObjectURL(feedPreviewUrl);
    setFeedFile(null);
    setFeedPreviewUrl("");
    setFeedCaption("");
    setFeedVisibility("public");
    if (feedImageInputRef.current) feedImageInputRef.current.value = "";
  }

  async function openFeedPost(post: FeedPost): Promise<void> {
    setSelectedFeedPost(post);
    setSelectedCaptionDraft(post.caption || "");
    setIsFeedPostEditing(false);
    setIsFeedPostMenuOpen(false);
    setCommentInput("");
    setSelectedFeedLikes([]);
    setSelectedFeedComments([]);

    try {
      const [likes, comments] = await Promise.all([
        getFeedPostLikes(post.post_id),
        getFeedComments(post.post_id),
      ]);
      setSelectedFeedLikes(likes.users);
      setSelectedFeedComments(comments.comments);
    } catch {
      // Secondary feed data should not block opening the photo.
    }
  }

  function updateFeedPostState(post: FeedPost): void {
    setFeedPosts((current) =>
      current.map((item) => (item.post_id === post.post_id ? post : item))
    );
    setSelectedFeedPost((current) =>
      current?.post_id === post.post_id ? post : current
    );
  }

  async function handleSelectedVisibilityChange(visibility: FeedVisibility): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

    setIsFeedActionRunning(true);
    try {
      updateFeedPostState(await updateFeedPostVisibility(selectedFeedPost.post_id, visibility));
    } catch (error) {
      window.alert(toErrorMessage(error, "Failed to update visibility."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleSelectedCaptionSave(): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

    setIsFeedActionRunning(true);
    try {
      updateFeedPostState(
        await updateFeedPostCaption(
          selectedFeedPost.post_id,
          selectedCaptionDraft.trim() || null
        )
      );
      setIsFeedPostEditing(false);
      setIsFeedPostMenuOpen(false);
    } catch (error) {
      window.alert(toErrorMessage(error, "Failed to update caption."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleSelectedDelete(): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;
    if (!window.confirm("Delete this post?")) return;

    setIsFeedActionRunning(true);
    try {
      await deleteFeedPost(selectedFeedPost.post_id);
      setFeedPosts((current) =>
        current.filter((item) => item.post_id !== selectedFeedPost.post_id)
      );
      setSelectedFeedPost(null);
    } catch (error) {
      window.alert(toErrorMessage(error, "Failed to delete feed photo."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleSelectedLike(): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

    setIsFeedActionRunning(true);
    try {
      const response = await likeFeedPost(selectedFeedPost.post_id);
      updateFeedPostState({ ...selectedFeedPost, like_count: response.like_count });
      setSelectedFeedLikes((await getFeedPostLikes(selectedFeedPost.post_id)).users);
    } catch (error) {
      if (getApiStatus(error) === 400) {
        try {
          const response = await unlikeFeedPost(selectedFeedPost.post_id);
          updateFeedPostState({ ...selectedFeedPost, like_count: response.like_count });
          setSelectedFeedLikes((await getFeedPostLikes(selectedFeedPost.post_id)).users);
        } catch (unlikeError) {
          window.alert(toErrorMessage(unlikeError, "Failed to update like."));
        }
      } else {
        window.alert(toErrorMessage(error, "Failed to update like."));
      }
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleCommentSubmit(): Promise<void> {
    const content = commentInput.trim();
    if (!selectedFeedPost || !content || isFeedActionRunning) return;

    setIsFeedActionRunning(true);
    try {
      const comment = await createFeedComment(selectedFeedPost.post_id, content);
      setSelectedFeedComments((current) => [comment, ...current]);
      updateFeedPostState({
        ...selectedFeedPost,
        comment_count: selectedFeedPost.comment_count + 1,
      });
      setCommentInput("");
    } catch (error) {
      window.alert(toErrorMessage(error, "Failed to add comment."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleCommentDelete(comment: FeedComment): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;
    if (!window.confirm("Delete this comment?")) return;

    setIsFeedActionRunning(true);
    try {
      await deleteFeedComment(selectedFeedPost.post_id, comment.comment_id);
      setSelectedFeedComments((current) =>
        current.filter((item) => item.comment_id !== comment.comment_id)
      );
      updateFeedPostState({
        ...selectedFeedPost,
        comment_count: Math.max(0, selectedFeedPost.comment_count - 1),
      });
    } catch (error) {
      window.alert(toErrorMessage(error, "Failed to delete comment."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleLogout(): Promise<void> {
    try {
      await logoutUser();
    } catch {
      // The session may already be invalid locally; still leave the app shell.
    } finally {
      showAppToast({ title: "Logged out", variant: "success" });
      navigate("/login");
    }
  }

  async function handleWithdraw(): Promise<void> {
    setIsWithdrawing(true);
    try {
      await withdrawUser();
      showAppToast({ title: "Account deleted", variant: "success" });
      navigate("/login", { replace: true });
    } catch (error) {
      showAppToast({
        title: "Account withdrawal failed",
        message: toErrorMessage(error, "Please try again."),
        variant: "error",
      });
      setIsWithdrawing(false);
    }
  }

  function handleConfirmAccountAction(): void {
    const action = pendingAccountAction;
    setPendingAccountAction(null);

    if (action === "logout") {
      void handleLogout();
    }
    if (action === "withdraw") {
      void handleWithdraw();
    }
  }

  async function handleProfileImageChange(
    event: React.ChangeEvent<HTMLInputElement>
  ): Promise<void> {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsProfileImageMenuOpen(false);

    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type)) {
      window.alert("Please choose a JPG, PNG, WEBP, or GIF image.");
      event.target.value = "";
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      window.alert("Please choose an image smaller than 5MB.");
      event.target.value = "";
      return;
    }

    const previewUrl = URL.createObjectURL(file);
    setProfileImagePreview(previewUrl);
    setIsUploadingProfileImage(true);

    try {
      const updatedImage = getProfileImageUrl(profile)
        ? await replaceMyProfileImage(file)
        : await uploadMyProfileImage(file);

      if (updatedImage) {
        setProfile((current) => ({ ...current, ...updatedImage }) as UserProfile);
      } else {
        const refreshedProfile = await getMyProfile();
        if (refreshedProfile) setProfile(refreshedProfile);
      }
    } catch (error) {
      setProfileImagePreview("");
      window.alert(toErrorMessage(error, "Profile photo upload failed. Please try again."));
    } finally {
      setIsUploadingProfileImage(false);
      event.target.value = "";
      URL.revokeObjectURL(previewUrl);
    }
  }

  async function handleProfileImageDelete(): Promise<void> {
    if (isDeletingProfileImage || isUploadingProfileImage) return;
    if (!window.confirm("Delete your profile photo?")) return;

    setIsDeletingProfileImage(true);
    try {
      await deleteMyProfileImage();
      setProfile((current) =>
        current
          ? {
              ...current,
              profile_image_url: null,
              profileImageUrl: "",
              avatar_url: "",
              image_url: "",
              imageUrl: "",
            }
          : current
      );
      setProfileImagePreview("");
      setIsProfileImageMenuOpen(false);
    } catch (error) {
      window.alert(toErrorMessage(error, "Profile photo delete failed. Please try again."));
    } finally {
      setIsDeletingProfileImage(false);
    }
  }

  function handleStatusSave(): void {
    const nextStatus = statusDraft.trim();
    setStatusMessage(nextStatus);
    setStatusDraft(nextStatus);
    setIsStatusEditing(false);
    if (profile?.user_id) {
      window.localStorage.setItem(getStatusStorageKey(profile.user_id), nextStatus);
    }
  }

  function togglePreferenceList(
    key: "travel_styles" | "food_preferences" | "transport_preferences" | "time_preferences",
    value: string
  ): void {
    setPreferenceDraft((current) => {
      const selected = current[key] ?? [];
      return {
        ...current,
        [key]: selected.includes(value)
          ? selected.filter((item) => item !== value)
          : [...selected, value],
      };
    });
  }

  function setPreferenceValue(
    key:
      | "density_preference"
      | "budget_preference"
      | "walking_preference"
      | "companion_preference"
      | "communication_preference"
      | "planning_preference",
    value: string
  ): void {
    setPreferenceDraft((current) => ({
      ...current,
      [key]: current[key] === value ? "" : value,
    }));
  }

  async function handlePreferenceSave(): Promise<void> {
    if (isSavingPreferences) return;
    if (!profile) {
      showAppToast({
        title: "Profile is still loading",
        message: "Please try again in a moment.",
        variant: "info",
      });
      return;
    }

    setIsSavingPreferences(true);
    try {
      const updatedProfile = await updateMyProfilePreferences(preferenceDraft, profile);
      setProfile((current) => ({
        ...(current ?? {}),
        ...(updatedProfile ?? {}),
        ...preferenceDraft,
      }) as UserProfile);
      setIsPreferenceEditing(false);
      showAppToast({ title: "Preferences saved", variant: "success" });
    } catch (error) {
      showAppToast({
        title: "Failed to save preferences",
        message: toErrorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setIsSavingPreferences(false);
    }
  }

  const profileImageUrl =
    profileImagePreview || getProfileImageUrl(profile) || DEFAULT_PROFILE_IMAGE_URL;
  const canDeleteProfileImage =
    Boolean(getProfileImageUrl(profile)) && !profileImagePreview;
  const nameText = profile?.user_name ?? "";
  const infoItems = [
    { label: "User ID", value: profile?.user_id ?? "" },
    { label: "Email", value: profile?.email ?? "" },
    { label: "Phone", value: profile?.phone_number ?? "" },
    { label: "Gender", value: formatGender(profile?.gender) },
    { label: "Nationality", value: profile?.nationality ?? "" },
  ].filter((item) => item.value);
  const preferenceTags = getPreferenceTags(profile);

  return (
    <div style={styles.page}>
      <section style={styles.socialProfile}>
        <div style={styles.avatarWrap}>
          <button
            type="button"
            style={styles.avatarButton}
            onClick={() => setIsProfileImageMenuOpen((current) => !current)}
            disabled={isUploadingProfileImage || isDeletingProfileImage}
            aria-label="Change profile photo"
          >
            <img src={profileImageUrl} alt="" style={styles.avatarImage} />
            {isUploadingProfileImage ? (
              <span style={styles.avatarOverlay}>Uploading...</span>
            ) : isDeletingProfileImage ? (
              <span style={styles.avatarOverlay}>Deleting...</span>
            ) : (
              <span style={styles.avatarEditBadge}>Change</span>
            )}
          </button>
          {isProfileImageMenuOpen ? (
            <div style={styles.avatarMenu}>
              <button
                type="button"
                style={styles.avatarMenuButton}
                onClick={() => profileImageInputRef.current?.click()}
              >
                Upload Photo
              </button>
              <button
                type="button"
                style={{
                  ...styles.avatarMenuButton,
                  ...styles.avatarMenuDanger,
                  ...(!canDeleteProfileImage ? styles.avatarMenuButtonDisabled : {}),
                }}
                onClick={() => void handleProfileImageDelete()}
                disabled={!canDeleteProfileImage || isDeletingProfileImage}
              >
                Delete Photo
              </button>
            </div>
          ) : null}
          <input
            ref={profileImageInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            style={styles.hiddenInput}
            onChange={(event) => void handleProfileImageChange(event)}
          />
        </div>

        <div style={styles.socialProfileBody}>
          <div style={styles.socialNameRow}>
            <h1 style={styles.name}>{nameText || "Unknown"}</h1>
            <button
              type="button"
              style={styles.settingsButton}
              onClick={() => setIsSettingsOpen(true)}
              aria-label="Open settings"
            >
              ⚙
            </button>
            <button
              type="button"
              style={styles.newPostButton}
              onClick={() => {
                if (feedPosts.length >= 100) {
                  window.alert("The maximum feed photo limit is 100.");
                  return;
                }
                feedImageInputRef.current?.click();
              }}
              aria-label="Create new post"
            >
              +
            </button>
          </div>
          <p style={styles.statusMessage}>
            {statusMessage || "No status message yet."}
          </p>
          {preferenceTags.length > 0 ? (
            <div style={styles.preferenceTags} aria-label="Travel preferences">
              {preferenceTags.map((tag) => (
                <span key={tag} style={styles.preferenceTag}>
                  #{tag}
                </span>
              ))}
            </div>
          ) : null}
          <span style={styles.profileStat}>
            <strong>{feedPosts.length}</strong> posts
          </span>
        </div>
      </section>

      <section style={styles.section}>
        <input
          ref={feedImageInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          style={styles.hiddenInput}
          onChange={handleFeedFileSelect}
        />
        {feedError ? <p style={styles.errorText}>{feedError}</p> : null}

        {feedPosts.length ? (
          <div style={styles.feedGrid}>
            {feedPosts.map((post) => (
              <button
                key={post.post_id}
                type="button"
                style={styles.feedTile}
                onClick={() => void openFeedPost(post)}
              >
                <img src={getFeedImageUrl(post)} alt="" style={styles.feedTileImage} />
                <span style={styles.feedTileMeta}>
                  {post.like_count} likes · {post.comment_count} comments
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div style={styles.emptyPanel}>
            {isFeedLoading ? "Loading feed..." : "No feed photos yet."}
          </div>
        )}

        {feedNextCursor ? (
          <button
            type="button"
            style={styles.loadMoreButton}
            disabled={isFeedLoading}
            onClick={() => void loadFeedPosts(feedNextCursor)}
          >
            {isFeedLoading ? "Loading..." : "Load More"}
          </button>
        ) : null}
      </section>

      {isSettingsOpen ? (
        <div style={styles.settingsBackdrop} onClick={() => setIsSettingsOpen(false)}>
          <div style={styles.settingsPanel} onClick={(event) => event.stopPropagation()}>
            <div style={styles.settingsHeader}>
              <strong>Settings</strong>
              <button
                type="button"
                style={styles.settingsCloseButton}
                onClick={() => setIsSettingsOpen(false)}
              >
                x
              </button>
            </div>
            <button
              type="button"
              style={styles.settingsActionButton}
              onClick={() => setIsStatusEditing((current) => !current)}
            >
              Edit Status Message
            </button>
            {isStatusEditing ? (
              <div style={styles.statusEditor}>
                <textarea
                  value={statusDraft}
                  maxLength={80}
                  style={styles.statusTextarea}
                  placeholder="Write a short status message."
                  onChange={(event) => setStatusDraft(event.target.value)}
                />
                <button type="button" style={styles.primaryButton} onClick={handleStatusSave}>
                  Save Status
                </button>
              </div>
            ) : null}
            <button
              type="button"
              style={styles.settingsActionButton}
              onClick={() => setIsPreferenceEditing((current) => !current)}
            >
              Edit Travel Preferences
            </button>
            {isPreferenceEditing ? (
              <PreferenceEditor
                value={preferenceDraft}
                isSaving={isSavingPreferences}
                onToggleList={togglePreferenceList}
                onSetValue={setPreferenceValue}
                onReset={() => setPreferenceDraft(toPreferencePayload(profile))}
                onSave={() => void handlePreferenceSave()}
              />
            ) : null}
            <SavedPlansPanel
              plans={savedPlans}
              isLoading={isLoadingPlans}
              message={planMessage}
              shareInfo={shareInfo}
              onRefresh={refreshPlans}
              onCopyShareLink={() => void handleCopyShareLink()}
              onEdit={(plan) =>
                navigate(`/plan/manual?planId=${encodeURIComponent(plan.plan_id)}`)
              }
              onRename={(plan) => void handleRenamePlan(plan)}
              onShare={(plan) => void handleSharePlan(plan)}
              onDelete={(plan) => void handleDeletePlan(plan)}
            />
            <div style={styles.settingsInfoBlock}>
              <strong style={styles.settingsInfoTitle}>My Information</strong>
              <div style={styles.infoList}>
                {infoItems.map((item, index) => (
                  <div
                    key={item.label}
                    style={{
                      ...styles.infoRow,
                      ...(index === infoItems.length - 1 ? styles.infoRowLast : {}),
                    }}
                  >
                    <span style={styles.infoLabel}>{item.label}</span>
                    <span style={styles.infoValue}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
            <button
              type="button"
              style={styles.settingsActionButton}
              onClick={() => setPendingAccountAction("logout")}
            >
              Log Out
            </button>
            <button
              type="button"
              style={{ ...styles.settingsActionButton, ...styles.settingsDangerButton }}
              onClick={() => setPendingAccountAction("withdraw")}
              disabled={isWithdrawing}
            >
              {isWithdrawing ? "Deleting Account..." : "Delete Account"}
            </button>
          </div>
        </div>
      ) : null}

      {feedPreviewUrl ? (
        <CreatePostModal
          profileImageUrl={profileImageUrl}
          userName={nameText || "Unknown"}
          caption={feedCaption}
          visibility={feedVisibility}
          isUploading={isFeedUploading}
          disabled={!feedFile || feedPosts.length >= 100}
          previewUrl={feedPreviewUrl}
          onBack={closeFeedComposer}
          onCaptionChange={setFeedCaption}
          onVisibilityChange={setFeedVisibility}
          onShare={() => void handleFeedUpload()}
        />
      ) : null}

      {pendingAccountAction ? (
        <AccountConfirmDialog
          action={pendingAccountAction}
          busy={isWithdrawing}
          onCancel={() => setPendingAccountAction(null)}
          onConfirm={handleConfirmAccountAction}
        />
      ) : null}

      {selectedFeedPost ? (
        <FeedPostModal
          post={selectedFeedPost}
          profileImageUrl={profileImageUrl}
          userName={nameText || "Unknown"}
          currentUserId={profile?.user_id ?? ""}
          likes={selectedFeedLikes}
          comments={selectedFeedComments}
          captionDraft={selectedCaptionDraft}
          commentInput={commentInput}
          isEditing={isFeedPostEditing}
          isMenuOpen={isFeedPostMenuOpen}
          isBusy={isFeedActionRunning}
          onClose={() => setSelectedFeedPost(null)}
          onToggleMenu={() => setIsFeedPostMenuOpen((current) => !current)}
          onToggleEdit={() => {
            setIsFeedPostEditing((current) => !current);
            setIsFeedPostMenuOpen(false);
          }}
          onDelete={() => {
            setIsFeedPostMenuOpen(false);
            void handleSelectedDelete();
          }}
          onCaptionDraftChange={setSelectedCaptionDraft}
          onVisibilityChange={(visibility) => void handleSelectedVisibilityChange(visibility)}
          onSaveCaption={() => void handleSelectedCaptionSave()}
          onLike={() => void handleSelectedLike()}
          onCommentInputChange={setCommentInput}
          onCommentSubmit={() => void handleCommentSubmit()}
          onCommentDelete={(comment) => void handleCommentDelete(comment)}
        />
      ) : null}
    </div>
  );
}

function PreferenceEditor({
  value,
  isSaving,
  onToggleList,
  onSetValue,
  onReset,
  onSave,
}: {
  value: ProfilePreferencesPayload;
  isSaving: boolean;
  onToggleList: (
    key: "travel_styles" | "food_preferences" | "transport_preferences" | "time_preferences",
    value: string
  ) => void;
  onSetValue: (
    key:
      | "density_preference"
      | "budget_preference"
      | "walking_preference"
      | "companion_preference"
      | "communication_preference"
      | "planning_preference",
    value: string
  ) => void;
  onReset: () => void;
  onSave: () => void;
}) {
  return (
    <div style={styles.preferenceEditor}>
      <PreferenceGroup
        title="Travel Styles"
        options={TRAVEL_STYLE_OPTIONS}
        selected={value.travel_styles}
        onToggle={(key) => onToggleList("travel_styles", key)}
      />
      <PreferenceGroup
        title="Food Preferences"
        options={FOOD_OPTIONS}
        selected={value.food_preferences ?? []}
        onToggle={(key) => onToggleList("food_preferences", key)}
      />
      <PreferenceGroup
        title="Schedule Density"
        options={DENSITY_OPTIONS}
        selected={[value.density_preference ?? ""]}
        single
        onToggle={(key) => onSetValue("density_preference", key)}
      />
      <PreferenceGroup
        title="Budget"
        options={BUDGET_OPTIONS}
        selected={[value.budget_preference ?? ""]}
        single
        onToggle={(key) => onSetValue("budget_preference", key)}
      />
      <PreferenceGroup
        title="Walking"
        options={WALKING_OPTIONS}
        selected={[value.walking_preference ?? ""]}
        single
        onToggle={(key) => onSetValue("walking_preference", key)}
      />
      <PreferenceGroup
        title="Transportation"
        options={TRANSPORT_OPTIONS}
        selected={value.transport_preferences ?? []}
        onToggle={(key) => onToggleList("transport_preferences", key)}
      />
      <PreferenceGroup
        title="Companion"
        options={COMPANION_OPTIONS}
        selected={[value.companion_preference ?? ""]}
        single
        onToggle={(key) => onSetValue("companion_preference", key)}
      />
      <PreferenceGroup
        title="Active Time"
        options={TIME_OPTIONS}
        selected={value.time_preferences ?? []}
        onToggle={(key) => onToggleList("time_preferences", key)}
      />
      <PreferenceGroup
        title="Communication"
        options={COMMUNICATION_OPTIONS}
        selected={[value.communication_preference ?? ""]}
        single
        onToggle={(key) => onSetValue("communication_preference", key)}
      />
      <PreferenceGroup
        title="Planning"
        options={PLANNING_OPTIONS}
        selected={[value.planning_preference ?? ""]}
        single
        onToggle={(key) => onSetValue("planning_preference", key)}
      />
      <div style={styles.preferenceEditorActions}>
        <button type="button" style={styles.secondaryButton} onClick={onReset} disabled={isSaving}>
          Reset
        </button>
        <button
          type="button"
          style={{ ...styles.primaryButton, ...(isSaving ? styles.buttonDisabled : {}) }}
          onClick={onSave}
          disabled={isSaving}
        >
          {isSaving ? "Saving..." : "Save Preferences"}
        </button>
      </div>
    </div>
  );
}

function PreferenceGroup({
  title,
  options,
  selected,
  onToggle,
}: {
  title: string;
  options: PreferenceOption[];
  selected: string[];
  single?: boolean;
  onToggle: (key: string) => void;
}) {
  return (
    <div style={styles.preferenceGroup}>
      <strong style={styles.preferenceGroupTitle}>{title}</strong>
      <div style={styles.preferenceChoiceList}>
        {options.map((option) => {
          const active = selected.includes(option.key);
          return (
            <button
              key={option.key}
              type="button"
              style={{
                ...styles.preferenceChoice,
                ...(active ? styles.preferenceChoiceActive : {}),
              }}
              onClick={() => onToggle(option.key)}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SavedPlansPanel({
  plans,
  isLoading,
  message,
  shareInfo,
  onRefresh,
  onCopyShareLink,
  onEdit,
  onRename,
  onShare,
  onDelete,
}: {
  plans: PlanSummaryResponse[];
  isLoading: boolean;
  message: string;
  shareInfo: SharePlanResponse | null;
  onRefresh: () => void;
  onCopyShareLink: () => void;
  onEdit: (plan: PlanSummaryResponse) => void;
  onRename: (plan: PlanSummaryResponse) => void;
  onShare: (plan: PlanSummaryResponse) => void;
  onDelete: (plan: PlanSummaryResponse) => void;
}) {
  return (
    <div style={styles.planPanel}>
      <div style={styles.planHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Saved Plans</h2>
          <p style={styles.planCopy}>AI and manual plans saved to the backend.</p>
        </div>
        <button
          type="button"
          style={styles.planRefreshButton}
          onClick={onRefresh}
          disabled={isLoading}
        >
          {isLoading ? "Loading" : "Refresh"}
        </button>
      </div>

      {message ? <p style={styles.planMessage}>{message}</p> : null}
      {shareInfo ? (
        <div style={styles.shareReadyRow}>
          <span>Public link expires {new Date(shareInfo.expires_at).toLocaleString()}.</span>
          <button type="button" style={styles.planPrimaryButton} onClick={onCopyShareLink}>
            Copy Link
          </button>
        </div>
      ) : null}

      {isLoading ? (
        <div style={styles.emptyPanel}>Loading saved plans...</div>
      ) : plans.length === 0 ? (
        <div style={styles.emptyPanel}>No saved plans yet.</div>
      ) : (
        <div style={styles.planList}>
          {plans.map((plan) => (
            <article key={plan.plan_id} style={styles.planCard}>
              <div style={styles.planCardBody}>
                <strong style={styles.planTitle}>{plan.title || "Untitled plan"}</strong>
                <span style={styles.planMeta}>
                  {plan.travel_days} day max - Updated{" "}
                  {new Date(plan.updated_at).toLocaleString()}
                </span>
              </div>
              <div style={styles.planActions}>
                <button
                  type="button"
                  style={styles.planPrimaryButton}
                  onClick={() => onEdit(plan)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  style={styles.planGhostButton}
                  onClick={() => onRename(plan)}
                >
                  Rename
                </button>
                <button
                  type="button"
                  style={styles.planGhostButton}
                  onClick={() => onShare(plan)}
                >
                  Share
                </button>
                <button
                  type="button"
                  style={styles.planDangerButton}
                  onClick={() => onDelete(plan)}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function AccountConfirmDialog({
  action,
  busy,
  onCancel,
  onConfirm,
}: {
  action: "logout" | "withdraw";
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const isWithdraw = action === "withdraw";

  return (
    <div style={styles.accountConfirmBackdrop} onClick={onCancel}>
      <div style={styles.accountConfirmCard} onClick={(event) => event.stopPropagation()}>
        <h2 style={styles.accountConfirmTitle}>
          {isWithdraw ? "Delete account?" : "Log out?"}
        </h2>
        <p style={styles.accountConfirmCopy}>
          {isWithdraw
            ? "Your account deletion request will start immediately."
            : "You will return to the login screen."}
        </p>
        <div style={styles.accountConfirmActions}>
          <button
            type="button"
            style={styles.secondaryButton}
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            style={{
              ...styles.primaryButton,
              ...(isWithdraw ? styles.accountConfirmDanger : {}),
              ...(busy ? styles.buttonDisabled : {}),
            }}
            onClick={onConfirm}
            disabled={busy}
          >
            {isWithdraw ? (busy ? "Deleting..." : "Delete") : "Log Out"}
          </button>
        </div>
      </div>
    </div>
  );
}

function CreatePostModal({
  profileImageUrl,
  userName,
  caption,
  visibility,
  isUploading,
  disabled,
  previewUrl,
  onBack,
  onCaptionChange,
  onVisibilityChange,
  onShare,
}: {
  profileImageUrl: string;
  userName: string;
  caption: string;
  visibility: FeedVisibility;
  isUploading: boolean;
  disabled: boolean;
  previewUrl: string;
  onBack: () => void;
  onCaptionChange: (value: string) => void;
  onVisibilityChange: (value: FeedVisibility) => void;
  onShare: () => void;
}) {
  return (
    <div style={styles.createPostBackdrop}>
      <div style={styles.createPostModal}>
        <div style={styles.createPostTopBar}>
          <button type="button" style={styles.createPostIconButton} onClick={onBack}>
            ←
          </button>
          <strong style={styles.createPostTitle}>Create New Post</strong>
          <button
            type="button"
            style={{ ...styles.shareButton, ...(disabled ? styles.buttonDisabled : {}) }}
            disabled={disabled}
            onClick={onShare}
          >
            {isUploading ? "Sharing..." : "Share"}
          </button>
        </div>
        <div style={styles.createPostFrame}>
          <div style={styles.createPostImagePane}>
            <img src={previewUrl} alt="" style={styles.createPostImage} />
          </div>
          <aside style={styles.createPostSidePane}>
            <div style={styles.createPostAuthor}>
              <img src={profileImageUrl} alt="" style={styles.createPostAvatar} />
              <strong style={styles.createPostAuthorName}>{userName}</strong>
            </div>
            <textarea
              maxLength={100}
              value={caption}
              placeholder="Write a caption..."
              style={styles.createPostTextarea}
              onChange={(event) => onCaptionChange(event.target.value)}
            />
            <p style={styles.createPostCounter}>{caption.length}/100</p>
            <div style={styles.createPostDivider} />
            <div style={styles.createPostSectionHeader}>
              <strong>Visibility</strong>
            </div>
            <div style={styles.visibilityList}>
              {(["public", "friends", "private"] as FeedVisibility[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  style={{
                    ...styles.visibilityListItem,
                    ...(visibility === item ? styles.visibilityListItemActive : {}),
                  }}
                  onClick={() => onVisibilityChange(item)}
                >
                  <span>{getVisibilityLabel(item)}</span>
                  <span style={styles.visibilityDot} />
                </button>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function FeedPostModal({
  post,
  profileImageUrl,
  userName,
  currentUserId,
  likes,
  comments,
  captionDraft,
  commentInput,
  isEditing,
  isMenuOpen,
  isBusy,
  onClose,
  onToggleMenu,
  onToggleEdit,
  onDelete,
  onCaptionDraftChange,
  onVisibilityChange,
  onSaveCaption,
  onLike,
  onCommentInputChange,
  onCommentSubmit,
  onCommentDelete,
}: {
  post: FeedPost;
  profileImageUrl: string;
  userName: string;
  currentUserId: string;
  likes: FeedLikeUser[];
  comments: FeedComment[];
  captionDraft: string;
  commentInput: string;
  isEditing: boolean;
  isMenuOpen: boolean;
  isBusy: boolean;
  onClose: () => void;
  onToggleMenu: () => void;
  onToggleEdit: () => void;
  onDelete: () => void;
  onCaptionDraftChange: (value: string) => void;
  onVisibilityChange: (value: FeedVisibility) => void;
  onSaveCaption: () => void;
  onLike: () => void;
  onCommentInputChange: (value: string) => void;
  onCommentSubmit: () => void;
  onCommentDelete: (comment: FeedComment) => void;
}) {
  return (
    <div style={styles.modalBackdrop} onClick={onClose}>
      <div style={styles.feedModal} onClick={(event) => event.stopPropagation()}>
        <button type="button" style={styles.modalCloseButton} onClick={onClose}>
          x
        </button>
        <div style={styles.feedModalImagePane}>
          <img src={post.original_url} alt="" style={styles.feedModalImage} />
        </div>
        <aside style={styles.feedModalSidePane}>
          <header style={styles.feedPostHeader}>
            <div style={styles.feedPostAuthor}>
              <img src={profileImageUrl} alt="" style={styles.feedPostAvatar} />
              <div>
                <strong style={styles.feedPostAuthorName}>{userName}</strong>
                <p style={styles.feedPostVisibility}>{getVisibilityLabel(post.visibility)}</p>
              </div>
            </div>
            <div style={styles.feedPostHeaderActions}>
              <button type="button" style={styles.feedPostMoreButton} onClick={onToggleMenu}>
                ...
              </button>
              {isMenuOpen ? (
                <div style={styles.feedPostMenu}>
                  <button type="button" style={styles.feedPostMenuButton} onClick={onToggleEdit}>
                    {isEditing ? "Cancel edit" : "Edit"}
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.feedPostMenuButton, ...styles.feedPostMenuDanger }}
                    disabled={isBusy}
                    onClick={onDelete}
                  >
                    Delete
                  </button>
                </div>
              ) : null}
            </div>
          </header>

          {isEditing ? (
            <section style={styles.feedEditPanel}>
              <textarea
                maxLength={100}
                value={captionDraft}
                placeholder="Caption"
                style={styles.feedEditTextarea}
                onChange={(event) => onCaptionDraftChange(event.target.value)}
              />
              <p style={styles.feedEditCounter}>{captionDraft.length}/100</p>
              <div style={styles.visibilityRow}>
                {(["public", "friends", "private"] as FeedVisibility[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    style={{
                      ...styles.visibilityChip,
                      ...(post.visibility === item ? styles.visibilityChipActive : {}),
                    }}
                    disabled={isBusy}
                    onClick={() => onVisibilityChange(item)}
                  >
                    {getVisibilityLabel(item)}
                  </button>
                ))}
              </div>
              <button type="button" style={styles.primaryButton} disabled={isBusy} onClick={onSaveCaption}>
                Save Changes
              </button>
            </section>
          ) : null}

          <div style={styles.feedDiscussion}>
            {post.caption ? (
              <article style={styles.commentItem}>
                <img src={profileImageUrl} alt="" style={styles.feedCommentAvatar} />
                <div style={styles.feedPostCommentMain}>
                  <strong style={styles.commentAuthor}>{userName}</strong>
                  <p style={styles.commentText}>{post.caption}</p>
                </div>
              </article>
            ) : null}
            {comments.map((comment) => (
              <article key={comment.comment_id} style={styles.commentItem}>
                <img
                  src={comment.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                  alt=""
                  style={styles.feedCommentAvatar}
                />
                <div style={styles.feedPostCommentMain}>
                  <strong style={styles.commentAuthor}>{comment.user_name || "Unknown"}</strong>
                  <p style={styles.commentText}>{comment.content}</p>
                </div>
                {comment.user_id === currentUserId ? (
                  <button
                    type="button"
                    style={styles.commentDeleteButton}
                    disabled={isBusy}
                    onClick={() => onCommentDelete(comment)}
                  >
                    Delete
                  </button>
                ) : null}
              </article>
            ))}
          </div>

          <footer style={styles.feedPostFooter}>
            <div style={styles.feedPostActionButtons}>
              <button
                type="button"
                style={styles.feedLikeIconButton}
                disabled={isBusy}
                onClick={onLike}
                aria-label="Like"
              >
                <span style={styles.feedActionCount}>{post.like_count}</span>
                <HeartIcon />
              </button>
              <span style={styles.feedCommentSummary}>
                <span style={styles.feedActionCount}>{post.comment_count}</span>
                <CommentIcon />
              </span>
            </div>
            <form
              style={styles.commentForm}
              onSubmit={(event) => {
                event.preventDefault();
                onCommentSubmit();
              }}
            >
              <input
                type="text"
                maxLength={500}
                value={commentInput}
                placeholder="Add a comment..."
                style={styles.feedCommentInput}
                onChange={(event) => onCommentInputChange(event.target.value)}
              />
              <button
                type="submit"
                style={styles.feedPostSubmitButton}
                disabled={!commentInput.trim() || isBusy}
              >
                Post
              </button>
            </form>
          </footer>
        </aside>
      </div>
    </div>
  );
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
    minHeight: "var(--app-viewport-height)",
    padding: "calc(28px + var(--app-safe-top)) 16px calc(110px + var(--app-safe-bottom))",
    background: "transparent",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  socialProfile: {
    maxWidth: 880,
    margin: "0 auto",
    display: "grid",
    gridTemplateColumns: "104px minmax(0, 1fr)",
    gap: 60,
    alignItems: "center",
    padding: "8px 0 24px",
    borderBottom: "1px solid var(--neutral-200)",
  },
  socialProfileBody: {
    minWidth: 0,
  },
  socialNameRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
  settingsButton: {
    width: 38,
    height: 38,
    border: "1px solid var(--border-soft)",
    borderRadius: "50%",
    padding: 0,
    background: "#ffffff",
    color: "var(--text-secondary)",
    fontSize: "1.08rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  newPostButton: {
    width: 38,
    height: 38,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: "50%",
    padding: 0,
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontSize: "1.35rem",
    lineHeight: 1,
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: "0 10px 18px rgba(5,181,187,0.18)",
  },
  statusMessage: {
    margin: "10px 0 12px",
    color: "var(--text-secondary)",
    lineHeight: 1.5,
    overflowWrap: "anywhere",
  },
  profileStat: {
    color: "var(--neutral-700)",
    fontWeight: 800,
  },
  preferenceTags: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 10,
    maxWidth: 520,
  },
  preferenceTag: {
    display: "inline-flex",
    alignItems: "center",
    minHeight: 28,
    borderRadius: 999,
    padding: "0 10px",
    background: "rgba(5,181,187,0.12)",
    border: "1px solid rgba(5,181,187,0.18)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.76rem",
    fontWeight: 900,
    lineHeight: 1,
  },
  avatarWrap: {
    position: "relative",
  },
  avatarButton: {
    width: 136,
    height: 136,
    position: "relative",
    padding: 0,
    border: "4px solid #ffffff",
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "var(--neutral-100)",
    overflow: "hidden",
    cursor: "pointer",
    boxShadow: "0 16px 34px rgba(33,33,33,0.14)",
  },
  avatarImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  avatarEditBadge: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: "7px 4px 8px",
    background: "rgba(24,26,32,0.62)",
    color: "#ffffff",
    fontSize: "0.72rem",
    fontWeight: 900,
  },
  avatarOverlay: {
    position: "absolute",
    inset: 0,
    display: "grid",
    placeItems: "center",
    padding: 10,
    background: "rgba(24,26,32,0.58)",
    color: "#ffffff",
    fontSize: "0.74rem",
    fontWeight: 900,
    textAlign: "center",
  },
  avatarMenu: {
    position: "absolute",
    left: 0,
    top: 148,
    zIndex: 6,
    width: 168,
    padding: 8,
    borderRadius: 16,
    background: "#ffffff",
    border: "1px solid var(--border-soft)",
    boxShadow: "0 16px 34px rgba(33,33,33,0.16)",
  },
  avatarMenuButton: {
    width: "100%",
    minHeight: 38,
    border: "none",
    borderRadius: 12,
    padding: "0 12px",
    background: "transparent",
    color: "var(--text-secondary)",
    fontWeight: 900,
    textAlign: "left",
    cursor: "pointer",
  },
  avatarMenuDanger: {
    color: "#dc2626",
  },
  avatarMenuButtonDisabled: {
    color: "var(--neutral-500)",
    cursor: "not-allowed",
    opacity: 0.58,
  },
  hiddenInput: {
    display: "none",
  },
  name: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.8rem",
    lineHeight: 1.15,
  },
  section: {
    maxWidth: 880,
    margin: "20px auto 0",
  },
  sectionTitle: {
    margin: "0 0 8px",
    color: "var(--text-primary)",
    fontSize: "1rem",
    fontWeight: 900,
  },
  feedUploadPanel: {
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.92)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
    marginBottom: 16,
  },
  feedUploadHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  feedHelp: {
    margin: 0,
    color: "var(--neutral-700)",
    fontSize: "0.86rem",
    lineHeight: 1.45,
  },
  secondaryButton: {
    minHeight: 38,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 12,
    padding: "0 14px",
    background: "#ffffff",
    color: "var(--brand-primary-deep)",
    fontWeight: 900,
    cursor: "pointer",
  },
  primaryButton: {
    minHeight: 42,
    border: "none",
    borderRadius: 12,
    padding: "0 14px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
  },
  buttonDisabled: {
    opacity: 0.55,
    cursor: "not-allowed",
  },
  errorText: {
    margin: "12px 0 0",
    color: "#dc2626",
    fontSize: "0.86rem",
    fontWeight: 800,
  },
  feedGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 6,
  },
  feedTile: {
    position: "relative",
    padding: 0,
    border: "none",
    borderRadius: 4,
    overflow: "hidden",
    background: "#050608",
    aspectRatio: "1 / 1",
    cursor: "pointer",
  },
  feedTileImage: {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    display: "block",
    background: "#050608",
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
  emptyPanel: {
    padding: 28,
    borderRadius: 18,
    background: "rgba(255,255,255,0.9)",
    border: "1px solid var(--border-soft)",
    color: "var(--neutral-700)",
    boxShadow: "var(--shadow-soft)",
  },
  loadMoreButton: {
    width: "100%",
    minHeight: 44,
    marginTop: 14,
    border: "1px solid var(--border-soft)",
    borderRadius: 14,
    background: "#ffffff",
    color: "var(--text-secondary)",
    fontWeight: 900,
    cursor: "pointer",
  },
  planPanel: {
    padding: 18,
    borderRadius: 18,
    background: "rgba(255,255,255,0.92)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  planHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  planCopy: {
    margin: "4px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.86rem",
    lineHeight: 1.45,
  },
  planRefreshButton: {
    minHeight: 38,
    border: "none",
    borderRadius: 12,
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    padding: "0 12px",
    fontSize: "0.78rem",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  planMessage: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.82rem",
    fontWeight: 800,
    lineHeight: 1.5,
  },
  shareReadyRow: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    padding: "10px 12px",
    borderRadius: 14,
    background: "rgba(5,181,187,0.1)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.82rem",
    fontWeight: 800,
  },
  planList: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  planCard: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr)",
    gap: 14,
    alignItems: "start",
    padding: 14,
    borderRadius: 14,
    background: "#ffffff",
    border: "1px solid var(--border-soft)",
  },
  planCardBody: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  planTitle: {
    color: "var(--text-primary)",
    fontSize: "0.95rem",
    overflowWrap: "anywhere",
  },
  planMeta: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 700,
  },
  planActions: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "flex-start",
    gap: 8,
  },
  planPrimaryButton: {
    minHeight: 36,
    border: "none",
    borderRadius: 12,
    background: "var(--brand-primary)",
    color: "#ffffff",
    padding: "0 11px",
    fontSize: "0.76rem",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  planGhostButton: {
    minHeight: 36,
    border: "none",
    borderRadius: 12,
    background: "rgba(5,181,187,0.12)",
    color: "var(--brand-primary-deep)",
    padding: "0 11px",
    fontSize: "0.76rem",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  planDangerButton: {
    minHeight: 36,
    border: "none",
    borderRadius: 12,
    background: "rgba(220,38,38,0.1)",
    color: "#dc2626",
    padding: "0 11px",
    fontSize: "0.76rem",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  settingsBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 88,
    display: "grid",
    placeItems: "center",
    padding: "calc(18px + var(--app-safe-top)) 18px calc(18px + var(--app-safe-bottom))",
    background: "rgba(16,34,35,0.42)",
  },
  settingsPanel: {
    width: "min(460px, 100%)",
    maxHeight: "86dvh",
    overflowY: "auto",
    borderRadius: 22,
    background: "#ffffff",
    boxShadow: "0 24px 70px rgba(15,23,42,0.28)",
    padding: 18,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  settingsHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    color: "var(--text-primary)",
    fontSize: "1.1rem",
  },
  settingsCloseButton: {
    width: 34,
    height: 34,
    border: "none",
    borderRadius: "50%",
    background: "var(--neutral-100)",
    color: "var(--text-primary)",
    fontWeight: 900,
    cursor: "pointer",
  },
  settingsActionButton: {
    width: "100%",
    minHeight: 46,
    border: "1px solid var(--neutral-200)",
    borderRadius: 14,
    padding: "0 14px",
    background: "#ffffff",
    color: "var(--text-secondary)",
    textAlign: "left",
    fontWeight: 900,
    cursor: "pointer",
  },
  settingsDangerButton: {
    color: "#dc2626",
  },
  statusEditor: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  statusTextarea: {
    minHeight: 90,
    border: "1px solid var(--neutral-200)",
    borderRadius: 14,
    padding: 12,
    resize: "vertical",
    outline: "none",
    color: "var(--text-primary)",
    fontFamily: "inherit",
  },
  preferenceEditor: {
    display: "flex",
    flexDirection: "column",
    gap: 14,
    padding: 14,
    borderRadius: 16,
    background: "rgba(5,181,187,0.06)",
    border: "1px solid rgba(5,181,187,0.14)",
  },
  preferenceGroup: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  preferenceGroupTitle: {
    color: "var(--text-primary)",
    fontSize: "0.86rem",
  },
  preferenceChoiceList: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  preferenceChoice: {
    minHeight: 34,
    border: "1px solid rgba(5,181,187,0.16)",
    borderRadius: 999,
    padding: "0 12px",
    background: "#ffffff",
    color: "var(--text-secondary)",
    fontSize: "0.78rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  preferenceChoiceActive: {
    background: "var(--brand-primary-soft)",
    borderColor: "rgba(5,181,187,0.38)",
    color: "var(--brand-primary-deep)",
  },
  preferenceEditorActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    paddingTop: 2,
  },
  settingsInfoBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  settingsInfoTitle: {
    color: "var(--text-primary)",
  },
  infoList: {
    borderRadius: 16,
    background: "rgba(255,255,255,0.88)",
    border: "1px solid var(--border-soft)",
    overflow: "hidden",
  },
  infoRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    padding: "12px 14px",
    borderBottom: "1px solid var(--neutral-200)",
  },
  infoRowLast: {
    borderBottom: "none",
  },
  infoLabel: {
    color: "var(--neutral-700)",
    fontSize: "0.88rem",
  },
  infoValue: {
    color: "var(--text-secondary)",
    fontWeight: 800,
    textAlign: "right",
    overflowWrap: "anywhere",
  },
  createPostBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 80,
    display: "grid",
    placeItems: "center",
    padding: "calc(20px + var(--app-safe-top)) 20px calc(20px + var(--app-safe-bottom))",
    background: "rgba(8,12,16,0.74)",
  },
  createPostModal: {
    width: "min(1220px, 100%)",
    maxHeight: "92dvh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    borderRadius: 4,
    background: "#24262d",
    color: "#f5f6f7",
    boxShadow: "0 28px 90px rgba(0,0,0,0.38)",
  },
  createPostTopBar: {
    height: 52,
    display: "grid",
    gridTemplateColumns: "56px minmax(0, 1fr) 82px",
    alignItems: "center",
    borderBottom: "1px solid rgba(255,255,255,0.1)",
  },
  createPostIconButton: {
    width: 44,
    height: 44,
    marginLeft: 10,
    border: "none",
    background: "transparent",
    color: "#ffffff",
    fontSize: "1.65rem",
    cursor: "pointer",
  },
  createPostTitle: {
    justifySelf: "center",
    color: "#ffffff",
    fontSize: "1rem",
    fontWeight: 900,
  },
  shareButton: {
    justifySelf: "end",
    marginRight: 16,
    border: "none",
    background: "transparent",
    color: "#7f9cff",
    fontSize: "0.9rem",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  createPostFrame: {
    minHeight: 0,
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr)",
  },
  createPostImagePane: {
    minHeight: "min(42dvh, 336px)",
    display: "grid",
    placeItems: "center",
    background: "#050608",
    overflow: "hidden",
  },
  createPostImage: {
    width: "100%",
    height: "100%",
    maxHeight: "calc(92dvh - 52px)",
    objectFit: "contain",
    display: "block",
    background: "#050608",
  },
  createPostSidePane: {
    minHeight: 0,
    maxHeight: "calc(92dvh - 52px)",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
    background: "#24262d",
  },
  createPostAuthor: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "18px 18px 8px",
  },
  createPostAvatar: {
    width: 32,
    height: 32,
    borderRadius: "50%",
    objectFit: "cover",
    background: "#3a3d45",
  },
  createPostAuthorName: {
    color: "#ffffff",
    fontSize: "0.9rem",
    fontWeight: 900,
  },
  createPostTextarea: {
    minHeight: 300,
    border: "none",
    padding: "10px 18px",
    background: "transparent",
    color: "#f5f6f7",
    fontSize: "0.95rem",
    lineHeight: 1.5,
    resize: "none",
    outline: "none",
    fontFamily: "inherit",
  },
  createPostCounter: {
    margin: "0 18px 12px",
    color: "#8f939c",
    fontSize: "0.78rem",
    textAlign: "right",
  },
  createPostDivider: {
    height: 1,
    background: "rgba(255,255,255,0.08)",
  },
  createPostSectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 18px 10px",
    color: "#ffffff",
    fontSize: "0.92rem",
  },
  visibilityList: {
    display: "flex",
    flexDirection: "column",
    paddingBottom: 14,
  },
  visibilityListItem: {
    minHeight: 46,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    border: "none",
    padding: "0 18px",
    background: "transparent",
    color: "#d8dbe0",
    fontWeight: 900,
    cursor: "pointer",
  },
  visibilityListItemActive: {
    color: "#ffffff",
    background: "rgba(255,255,255,0.06)",
  },
  visibilityDot: {
    width: 12,
    height: 12,
    borderRadius: "50%",
    border: "2px solid currentColor",
  },
  modalBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 60,
    display: "grid",
    placeItems: "center",
    padding: 10,
    background: "rgba(16,34,35,0.42)",
  },
  accountConfirmBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 120,
    display: "grid",
    placeItems: "center",
    padding: 18,
    background: "rgba(16,34,35,0.42)",
  },
  accountConfirmCard: {
    width: "min(360px, 100%)",
    padding: 22,
    borderRadius: 18,
    background: "#ffffff",
    border: "1px solid var(--border-soft)",
    boxShadow: "0 24px 70px rgba(15,23,42,0.24)",
  },
  accountConfirmTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.2rem",
    lineHeight: 1.25,
  },
  accountConfirmCopy: {
    margin: "10px 0 0",
    color: "var(--neutral-700)",
    lineHeight: 1.5,
    fontSize: "0.92rem",
  },
  accountConfirmActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    marginTop: 20,
  },
  accountConfirmDanger: {
    background: "#dc2626",
  },
  feedModal: {
    position: "relative",
    width: "min(430px, calc(100% - 8px))",
    maxHeight: "94dvh",
    display: "grid",
    gridTemplateColumns: "1fr",
    overflowY: "auto",
    borderRadius: 18,
    background: "#ffffff",
    boxShadow: "0 24px 70px rgba(15,23,42,0.28)",
  },
  modalCloseButton: {
    position: "absolute",
    top: 12,
    right: 12,
    zIndex: 2,
    width: 36,
    height: 36,
    border: "none",
    borderRadius: "50%",
    background: "rgba(16,34,35,0.72)",
    color: "#ffffff",
    fontSize: "1.1rem",
    lineHeight: 1,
    cursor: "pointer",
  },
  feedModalImagePane: {
    minHeight: "min(58dvh, 520px)",
    display: "grid",
    placeItems: "center",
    background: "#050608",
  },
  feedModalImage: {
    width: "100%",
    height: "100%",
    maxHeight: "58dvh",
    objectFit: "contain",
    background: "#050608",
  },
  feedModalSidePane: {
    minHeight: 260,
    display: "flex",
    flexDirection: "column",
    background: "#ffffff",
    color: "var(--text-primary)",
    borderTop: "1px solid var(--neutral-200)",
  },
  feedPostHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    minHeight: 84,
    padding: "12px 16px",
    borderBottom: "1px solid var(--neutral-200)",
  },
  feedPostAuthor: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
  },
  feedPostAvatar: {
    width: 60,
    height: 60,
    borderRadius: "50%",
    objectFit: "cover",
    background: "#3a3d45",
    flexShrink: 0,
  },
  feedPostAuthorName: {
    display: "block",
    color: "var(--text-primary)",
    fontSize: "0.92rem",
    fontWeight: 900,
  },
  feedPostVisibility: {
    margin: "3px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.76rem",
    fontWeight: 800,
  },
  feedPostHeaderActions: {
    position: "relative",
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  feedPostMoreButton: {
    width: 34,
    height: 34,
    border: "none",
    borderRadius: "50%",
    background: "transparent",
    color: "var(--text-primary)",
    fontSize: "1.28rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  feedPostMenu: {
    position: "absolute",
    top: 42,
    right: 0,
    zIndex: 4,
    width: 156,
    overflow: "hidden",
    borderRadius: 14,
    background: "#ffffff",
    border: "1px solid var(--neutral-200)",
    boxShadow: "0 16px 34px rgba(33,33,33,0.16)",
  },
  feedPostMenuButton: {
    width: "100%",
    minHeight: 42,
    border: "none",
    borderBottom: "1px solid var(--neutral-200)",
    padding: "0 14px",
    background: "#ffffff",
    color: "var(--text-secondary)",
    textAlign: "left",
    fontWeight: 900,
    cursor: "pointer",
  },
  feedPostMenuDanger: {
    color: "#dc2626",
    borderBottom: "none",
  },
  feedEditPanel: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    padding: 14,
    borderBottom: "1px solid var(--neutral-200)",
    background: "#f7fbfb",
  },
  feedEditTextarea: {
    minHeight: 112,
    border: "1px solid var(--neutral-200)",
    borderRadius: 12,
    padding: 12,
    background: "#ffffff",
    color: "var(--text-primary)",
    resize: "vertical",
    outline: "none",
    fontFamily: "inherit",
  },
  feedEditCounter: {
    margin: "-4px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.76rem",
    textAlign: "right",
  },
  visibilityRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  visibilityChip: {
    minHeight: 34,
    border: "1px solid var(--border-soft)",
    borderRadius: 999,
    padding: "0 12px",
    background: "#ffffff",
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
    fontWeight: 900,
    cursor: "pointer",
  },
  visibilityChipActive: {
    background: "var(--brand-primary-soft)",
    borderColor: "rgba(5,181,187,0.24)",
    color: "var(--brand-primary-deep)",
  },
  feedDiscussion: {
    flex: 1,
    minHeight: 0,
    maxHeight: "42dvh",
    overflowY: "auto",
    padding: "8px 16px",
  },
  feedPostFooter: {
    borderTop: "1px solid var(--neutral-200)",
    padding: "10px 16px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  feedPostActionButtons: {
    display: "flex",
    alignItems: "center",
    gap: 18,
  },
  feedLikeIconButton: {
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
  feedCommentSummary: {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    color: "var(--text-primary)",
    fontWeight: 900,
  },
  feedActionCount: {
    minWidth: 10,
    color: "var(--text-primary)",
    fontSize: "0.94rem",
    fontWeight: 900,
  },
  likesList: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  likeUser: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 10px",
    borderRadius: 999,
    background: "var(--neutral-100)",
    color: "var(--text-secondary)",
    fontSize: "0.8rem",
    fontWeight: 800,
  },
  likeAvatar: {
    width: 20,
    height: 20,
    borderRadius: "50%",
    objectFit: "cover",
  },
  commentForm: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto",
    gap: 8,
  },
  feedCommentInput: {
    width: "100%",
    minHeight: 40,
    border: "none",
    borderRadius: 0,
    padding: 0,
    background: "transparent",
    color: "var(--text-primary)",
    outline: "none",
    fontWeight: 700,
  },
  feedPostSubmitButton: {
    border: "none",
    background: "transparent",
    color: "var(--brand-primary-deep)",
    fontWeight: 900,
    cursor: "pointer",
  },
  commentItem: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    padding: "10px 0",
    borderTop: "1px solid var(--neutral-200)",
  },
  feedPostCommentMain: {
    minWidth: 0,
    flex: 1,
  },
  feedCommentAvatar: {
    width: 51,
    height: 51,
    borderRadius: "50%",
    objectFit: "cover",
    background: "var(--neutral-100)",
    flexShrink: 0,
  },
  commentAuthor: {
    display: "block",
    color: "var(--text-primary)",
    fontSize: "0.86rem",
  },
  commentText: {
    margin: "4px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.88rem",
    lineHeight: 1.45,
    overflowWrap: "anywhere",
  },
  commentDeleteButton: {
    alignSelf: "flex-start",
    border: "none",
    background: "transparent",
    color: "#dc2626",
    fontSize: "0.78rem",
    fontWeight: 900,
    cursor: "pointer",
  },
};

function getProfileImageUrl(profile: UserProfile | null): string {
  if (!profile) return "";
  return (
    profile.profile_image_url ||
    profile.profileImageUrl ||
    profile.avatar_url ||
    profile.image_url ||
    profile.imageUrl ||
    ""
  );
}

function getFeedImageUrl(post: FeedPost): string {
  return post.thumbnail_medium_url || post.thumbnail_small_url || post.original_url;
}

async function isAnimatedFeedImage(file: File): Promise<boolean> {
  if (file.type === "image/png") {
    return isAnimatedPng(new Uint8Array(await file.arrayBuffer()));
  }

  if (file.type === "image/webp") {
    return isAnimatedWebp(new Uint8Array(await file.arrayBuffer()));
  }

  return false;
}

function isAnimatedPng(bytes: Uint8Array): boolean {
  const pngSignature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (!pngSignature.every((value, index) => bytes[index] === value)) return false;

  let offset = 8;
  while (offset + 12 <= bytes.length) {
    const chunkLength =
      (bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3];
    const chunkType = bytesToAscii(bytes, offset + 4, offset + 8);
    if (chunkType === "acTL") return true;
    if (chunkType === "IDAT" || chunkType === "IEND") return false;
    offset += 12 + chunkLength;
  }

  return false;
}

function isAnimatedWebp(bytes: Uint8Array): boolean {
  if (
    bytesToAscii(bytes, 0, 4) !== "RIFF" ||
    bytesToAscii(bytes, 8, 12) !== "WEBP"
  ) {
    return false;
  }

  const header = bytesToAscii(bytes, 12, 16);
  if (header === "VP8X" && bytes.length > 20 && (bytes[20] & 0b00000010) !== 0) {
    return true;
  }

  return bytesToAscii(bytes, 12, bytes.length).includes("ANIM");
}

function bytesToAscii(bytes: Uint8Array, start: number, end: number): string {
  return Array.from(bytes.slice(start, end))
    .map((byte) => String.fromCharCode(byte))
    .join("");
}

function getPreferenceTags(profile: UserProfile | null): string[] {
  if (!profile) return [];

  const values = [
    ...(profile.travel_styles ?? []),
    ...(profile.food_preferences ?? []),
    profile.density_preference,
    profile.budget_preference,
    profile.walking_preference,
    ...(profile.transport_preferences ?? []),
    profile.companion_preference,
    ...(profile.time_preferences ?? []),
    profile.communication_preference,
    profile.planning_preference,
  ];

  return Array.from(
    new Set(
      values
        .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
        .map(formatPreferenceTag)
    )
  );
}

function toPreferencePayload(profile: UserProfile | null): ProfilePreferencesPayload {
  if (!profile) return EMPTY_PREFERENCES;

  return {
    travel_styles: profile.travel_styles ?? [],
    food_preferences: profile.food_preferences ?? [],
    density_preference: profile.density_preference ?? "",
    budget_preference: profile.budget_preference ?? "",
    walking_preference: profile.walking_preference ?? "",
    transport_preferences: profile.transport_preferences ?? [],
    companion_preference: profile.companion_preference ?? "",
    time_preferences: profile.time_preferences ?? [],
    communication_preference: profile.communication_preference ?? "",
    planning_preference: profile.planning_preference ?? "",
  };
}

function formatPreferenceTag(value: string): string {
  const labelMap: Record<string, string> = {
    activity: "Activity",
    famous_attractions: "Famous Attractions",
    healing: "Healing",
    culture_history: "Culture & History",
    shopping: "Shopping",
    food_tour: "Food Tour",
    photo_aesthetic: "Photo Aesthetic",
    festival_event: "Festival & Event",
    nature: "Nature",
    traditional: "Traditional",
    trekking: "Trekking",
    hidden_gems: "Hidden Gems",
    art_exhibition: "Art Exhibition",
    theme_park: "Theme Park",
    food_halal: "Halal",
    food_vegetarian: "Vegetarian",
    foodie: "Foodie",
    cafe_lover: "Cafe Lover",
    density_relaxed: "Relaxed",
    density_packed: "Packed",
    budget_saving: "Saving",
    budget_moderate: "Moderate",
    budget_premium: "Premium",
    walking_low: "Low Walking",
    walking_medium: "Medium Walking",
    walking_high: "High Walking",
    transport_public: "Public Transit",
    transport_car: "Car",
    transport_taxi: "Taxi",
    companion_independent: "Independent",
    companion_together: "Together",
    companion_flexible: "Flexible",
    daytime: "Daytime",
    nightlife: "Nightlife",
    night_view: "Night View",
    communication_high: "High Communication",
    communication_low: "Low Communication",
    planner: "Planner",
    spontaneous: "Spontaneous",
    follower: "Follower",
  };

  const key = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  return labelMap[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getVisibilityLabel(visibility: FeedVisibility): string {
  if (visibility === "public") return "Public";
  if (visibility === "friends") return "Friends";
  return "Private";
}

function getInitialStatusMessage(profile: UserProfile): string {
  const profileStatus =
    profile.status ||
    (profile as UserProfile & { status_message?: string | null }).status_message ||
    "";
  if (profile.user_id) {
    return window.localStorage.getItem(getStatusStorageKey(profile.user_id)) || profileStatus;
  }
  return profileStatus;
}

function getStatusStorageKey(userId: string): string {
  return `krip:my-page-status:${userId}`;
}

function formatGender(gender?: string): string {
  if (gender === "male") return "Male";
  if (gender === "female") return "Female";
  return gender || "";
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as { message?: string };
  return apiError.message || fallback;
}

function getApiStatus(error: unknown): number | undefined {
  const apiError = error as { status?: number; response?: { status?: number } };
  return apiError.status || apiError.response?.status;
}
