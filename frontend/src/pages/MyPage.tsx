import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  deleteMyProfileImage,
  getMyProfile,
  getMyProfileStats,
  logoutUser,
  replaceMyProfileImage,
  updateMyProfile,
  uploadMyProfileImage,
  type MyProfileStats,
  type ProfilePreferencesPayload,
  type ProfileUpdatePayload,
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
  getFeedPost,
  getFeedPostLikes,
  getMyFeedPosts,
  isPossiblyCommittedFeedMutationError,
  likeFeedPost,
  unlikeFeedPost,
  updateFeedPostCaption,
  updateFeedPostVisibility,
  type FeedComment,
  type FeedLikeUser,
  type FeedPost,
  type FeedVisibility,
} from "../api/feed";
import { setGlobalNotificationMuted } from "../api/notification";
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

const TRAVEL_STYLE_KEYS = new Set(TRAVEL_STYLE_OPTIONS.map((option) => option.key));
const FOOD_KEYS = new Set(FOOD_OPTIONS.map((option) => option.key));
const DENSITY_KEYS = new Set(DENSITY_OPTIONS.map((option) => option.key));
const BUDGET_KEYS = new Set(BUDGET_OPTIONS.map((option) => option.key));
const WALKING_KEYS = new Set(WALKING_OPTIONS.map((option) => option.key));
const TRANSPORT_KEYS = new Set(TRANSPORT_OPTIONS.map((option) => option.key));
const COMPANION_KEYS = new Set(COMPANION_OPTIONS.map((option) => option.key));
const TIME_KEYS = new Set(TIME_OPTIONS.map((option) => option.key));
const COMMUNICATION_KEYS = new Set(COMMUNICATION_OPTIONS.map((option) => option.key));
const PLANNING_KEYS = new Set(PLANNING_OPTIONS.map((option) => option.key));

const MIN_AGE = 20;
const MAX_AGE = 100;
const EMPTY_PROFILE_STATS: MyProfileStats = {
  total_feed_likes: 0,
  total_friends: 0,
};

type ProfileInfoDraft = {
  user_name: string;
  email: string;
  phone_number: string;
  age: string;
  gender: string;
  nationality: string;
  travel_styles: string[];
};

function toInfoDraft(profile: UserProfile | null): ProfileInfoDraft {
  return {
    user_name: profile?.user_name ?? "",
    email: profile?.email ?? "",
    phone_number: profile?.phone_number ?? "",
    age: profile?.age != null ? String(profile.age) : "",
    gender: profile?.gender ?? "",
    nationality: profile?.nationality ?? "",
    travel_styles: profile?.travel_styles ?? [],
  };
}

type FeedUploadStatus = "uploading" | "failed";

type FeedPostItem = FeedPost & {
  uploadStatus?: FeedUploadStatus;
  uploadProgress?: number;
  uploadFile?: File;
  uploadPreviewUrl?: string;
  uploadCaption?: string;
  uploadVisibility?: FeedVisibility;
  uploadError?: string;
};

type FeedConfirmState =
  | { type: "delete-post" }
  | { type: "delete-comment"; comment: FeedComment };

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
  const location = useLocation();
  const profileImageInputRef = useRef<HTMLInputElement>(null);
  const feedImageInputRef = useRef<HTMLInputElement>(null);
  const openedNotificationPostIdRef = useRef("");

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileStats, setProfileStats] =
    useState<MyProfileStats>(EMPTY_PROFILE_STATS);
  const [profileImagePreview, setProfileImagePreview] = useState("");
  const [isUploadingProfileImage, setIsUploadingProfileImage] = useState(false);
  const [isDeletingProfileImage, setIsDeletingProfileImage] = useState(false);
  const [isProfileImageMenuOpen, setIsProfileImageMenuOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isNotificationMuteSaving, setIsNotificationMuteSaving] = useState(false);
  const [isProfileChipsExpanded, setIsProfileChipsExpanded] = useState(false);
  const [preferenceDraft, setPreferenceDraft] =
    useState<ProfilePreferencesPayload>(EMPTY_PREFERENCES);
  const [isPreferenceEditing, setIsPreferenceEditing] = useState(false);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);

  const [isInfoEditing, setIsInfoEditing] = useState(false);
  const [infoDraft, setInfoDraft] = useState<ProfileInfoDraft>(toInfoDraft(null));
  const [isSavingInfo, setIsSavingInfo] = useState(false);
  const [infoError, setInfoError] = useState("");

  const [feedPosts, setFeedPosts] = useState<FeedPostItem[]>([]);
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
  const [feedConfirm, setFeedConfirm] = useState<FeedConfirmState | null>(null);
  const [pendingAccountAction, setPendingAccountAction] = useState<"logout" | null>(
    null
  );
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
          setPreferenceDraft(toPreferencePayload(data));
        }
      })
      .catch(() => setProfile(null));
  }, []);

  useEffect(() => {
    getMyProfileStats()
      .then((stats) => setProfileStats(sanitizeProfileStats(stats)))
      .catch((error) => {
        console.warn("Failed to load profile stats", error);
        setProfileStats(EMPTY_PROFILE_STATS);
      });
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

  useEffect(() => {
    const targetPostId = new URLSearchParams(location.search).get("feedPost") || "";
    if (!targetPostId || openedNotificationPostIdRef.current === targetPostId) return;

    const existingPost = feedPosts.find((post) => post.post_id === targetPostId);
    if (existingPost) {
      openedNotificationPostIdRef.current = targetPostId;
      void openFeedPost(existingPost);
      return;
    }

    if (isFeedLoading) return;

    openedNotificationPostIdRef.current = targetPostId;
    void getFeedPost(targetPostId)
      .then((post) => {
        setFeedPosts((current) =>
          current.some((item) => item.post_id === post.post_id)
            ? current
            : [post, ...current]
        );
        void openFeedPost(post);
      })
      .catch((error) => {
        openedNotificationPostIdRef.current = "";
        setFeedError(toErrorMessage(error, "Failed to open feed photo."));
      });
  }, [location.search, feedPosts, isFeedLoading]);

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

  async function refreshFeedPosts(options: { minCount?: number } = {}): Promise<FeedPost[]> {
    const posts: FeedPost[] = [];
    let cursor: string | undefined;
    let nextCursor: string | null = null;

    do {
      const response = await getMyFeedPosts(cursor);
      posts.push(...response.posts);
      nextCursor = response.next_cursor;
      cursor = nextCursor || undefined;
    } while (nextCursor && options.minCount && posts.length < options.minCount);

    setFeedPosts(posts);
    setFeedNextCursor(nextCursor);
    return posts;
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
      showAppToast({
        title: "Unsupported file type.",
        message: "Please upload a JPG, PNG, or WEBP image.",
        variant: "error",
        placement: "center",
      });
      event.target.value = "";
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      showAppToast({
        title: "File too large.",
        message: "Please upload an image smaller than 10MB.",
        variant: "error",
        placement: "center",
      });
      event.target.value = "";
      return;
    }

    if (await isAnimatedFeedImage(file)) {
      showAppToast({
        title: "Unsupported image file.",
        message: "Animated WEBP/APNG images are not supported.",
        variant: "error",
        placement: "center",
      });
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

    const uploadFile = feedFile;
    const uploadCaption = feedCaption;
    const uploadVisibility = feedVisibility;
    const uploadPreviewUrl = URL.createObjectURL(uploadFile);
    const temporaryPostId = `upload-${Date.now()}`;
    const uploadStartedAt = Date.now();

    setFeedPosts((current) =>
      [
        createOptimisticFeedPost({
          postId: temporaryPostId,
          file: uploadFile,
          previewUrl: uploadPreviewUrl,
          caption: uploadCaption,
          visibility: uploadVisibility,
        }),
        ...current,
      ].slice(0, 100)
    );

    closeFeedComposer();
    setIsFeedUploading(true);
    setFeedError("");

    try {
      const post = await createFeedPost({
        file: uploadFile,
        visibility: uploadVisibility,
        caption: uploadCaption,
        onUploadProgress: (progress) =>
          updateOptimisticFeedPost(temporaryPostId, { uploadProgress: progress }),
      });
      URL.revokeObjectURL(uploadPreviewUrl);
      setFeedPosts((current) =>
        current.map((item) => (item.post_id === temporaryPostId ? post : item))
      );
    } catch (error) {
      if (isPossiblyCommittedFeedMutationError(error)) {
        try {
          const refreshedPosts = await refreshFeedPosts();
          const createdPost = findLikelyUploadedPost(refreshedPosts, {
            caption: uploadCaption,
            visibility: uploadVisibility,
            startedAt: uploadStartedAt,
          });

          URL.revokeObjectURL(uploadPreviewUrl);

          if (createdPost) {
            setFeedError("");
          } else {
            setFeedError("");
          }
          return;
        } catch (refreshError) {
          updateOptimisticFeedPost(temporaryPostId, {
            uploadStatus: "failed",
            uploadError: toErrorMessage(
              refreshError,
              "Upload response was delayed and feed status could not be checked."
            ),
          });
          return;
        }
      }

      updateOptimisticFeedPost(temporaryPostId, {
        uploadStatus: "failed",
        uploadError: toErrorMessage(error, "Feed upload failed. Please try again."),
      });
    } finally {
      setIsFeedUploading(false);
    }
  }

  function updateOptimisticFeedPost(
    postId: string,
    patch: Partial<FeedPostItem>
  ): void {
    setFeedPosts((current) =>
      current.map((item) => (item.post_id === postId ? { ...item, ...patch } : item))
    );
  }

  async function retryFeedUpload(post: FeedPostItem): Promise<void> {
    if (!post.uploadFile || isFeedUploading) return;

    const uploadStartedAt = Date.now();

    updateOptimisticFeedPost(post.post_id, {
      uploadStatus: "uploading",
      uploadProgress: 0,
      uploadError: "",
    });
    setIsFeedUploading(true);

    try {
      const createdPost = await createFeedPost({
        file: post.uploadFile,
        visibility: post.uploadVisibility ?? "public",
        caption: post.uploadCaption ?? "",
        onUploadProgress: (progress) =>
          updateOptimisticFeedPost(post.post_id, { uploadProgress: progress }),
      });
      if (post.uploadPreviewUrl) URL.revokeObjectURL(post.uploadPreviewUrl);
      setFeedPosts((current) =>
        current.map((item) => (item.post_id === post.post_id ? createdPost : item))
      );
    } catch (error) {
      if (isPossiblyCommittedFeedMutationError(error)) {
        try {
          const refreshedPosts = await refreshFeedPosts();
          const createdPost = findLikelyUploadedPost(refreshedPosts, {
            caption: post.uploadCaption ?? "",
            visibility: post.uploadVisibility ?? "public",
            startedAt: uploadStartedAt,
          });

          if (post.uploadPreviewUrl) URL.revokeObjectURL(post.uploadPreviewUrl);

          if (createdPost) {
            setFeedError("");
          } else {
            setFeedError("");
          }
          return;
        } catch (refreshError) {
          updateOptimisticFeedPost(post.post_id, {
            uploadStatus: "failed",
            uploadError: toErrorMessage(
              refreshError,
              "Upload response was delayed and feed status could not be checked."
            ),
          });
          return;
        }
      }

      updateOptimisticFeedPost(post.post_id, {
        uploadStatus: "failed",
        uploadError: toErrorMessage(error, "Feed upload failed. Please try again."),
      });
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
    setFeedError("");
    if (feedImageInputRef.current) feedImageInputRef.current.value = "";
  }

  async function openFeedPost(post: FeedPostItem): Promise<void> {
    if (post.uploadStatus) return;
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
      current.map((item) => (item.post_id === post.post_id ? mergeFeedPost(item, post) : item))
    );
    setSelectedFeedPost((current) =>
      current?.post_id === post.post_id ? mergeFeedPost(current, post) : current
    );
  }

  async function handleSelectedVisibilityChange(visibility: FeedVisibility): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

    setIsFeedActionRunning(true);
    try {
      updateFeedPostState(
        mergeFeedPost(
          selectedFeedPost,
          await updateFeedPostVisibility(selectedFeedPost.post_id, visibility)
        )
      );
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
        mergeFeedPost(
          selectedFeedPost,
          await updateFeedPostCaption(
            selectedFeedPost.post_id,
            selectedCaptionDraft.trim() || null
          )
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
    setFeedConfirm({ type: "delete-post" });
  }

  async function confirmSelectedDelete(): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

    const postToDelete = selectedFeedPost;
    const previousPosts = feedPosts;
    const previousStats = profileStats;

    setIsFeedActionRunning(true);
    setFeedPosts((current) =>
      current.filter((item) => item.post_id !== postToDelete.post_id)
    );
    setProfileStats((current) => ({
      ...current,
      total_feed_likes: Math.max(
        0,
        current.total_feed_likes - safeCount(postToDelete.like_count)
      ),
    }));
    setSelectedFeedPost(null);
    setFeedConfirm(null);
    setIsFeedPostMenuOpen(false);
    setIsFeedPostEditing(false);

    try {
      await deleteFeedPost(postToDelete.post_id);
    } catch (error) {
      if (isPossiblyCommittedFeedMutationError(error)) {
        try {
          const refreshedPosts = await refreshFeedPosts({ minCount: previousPosts.length });
          const stillExists = refreshedPosts.some(
            (post) => post.post_id === postToDelete.post_id
          );

          if (!stillExists) {
            setFeedError("");
            return;
          }
        } catch {
          // Fall through to the delayed-response message below.
        }

        window.alert(
          "The delete response was delayed and the post is still visible. Please try again."
        );
        return;
      }

      setFeedPosts(previousPosts);
      setProfileStats(previousStats);
      setSelectedFeedPost(postToDelete);
      window.alert(toErrorMessage(error, "Failed to delete feed photo."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  async function handleSelectedLike(): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

    const previousPost = selectedFeedPost;
    const nextLiked = !previousPost.is_liked;
    const optimisticPost = {
      ...previousPost,
      is_liked: nextLiked,
      like_count: Math.max(0, previousPost.like_count + (nextLiked ? 1 : -1)),
    };

    setIsFeedActionRunning(true);
    updateFeedPostState(optimisticPost);
    updateTotalFeedLikes(nextLiked ? 1 : -1);
    try {
      const response = nextLiked
        ? await likeFeedPost(previousPost.post_id)
        : await unlikeFeedPost(previousPost.post_id);
      const nextPost = {
        ...optimisticPost,
        like_count: response.like_count,
        is_liked: nextLiked,
      };
      updateFeedPostState(nextPost);
      updateTotalFeedLikes(safeCount(response.like_count) - safeCount(optimisticPost.like_count));
      setSelectedFeedLikes((await getFeedPostLikes(previousPost.post_id)).users);
    } catch (error) {
      updateFeedPostState(previousPost);
      updateTotalFeedLikes(nextLiked ? -1 : 1);
      window.alert(toErrorMessage(error, "Failed to update like."));
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
    setFeedConfirm({ type: "delete-comment", comment });
  }

  async function confirmCommentDelete(comment: FeedComment): Promise<void> {
    if (!selectedFeedPost || isFeedActionRunning) return;

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
      setFeedConfirm(null);
    } catch (error) {
      window.alert(toErrorMessage(error, "Failed to delete comment."));
    } finally {
      setIsFeedActionRunning(false);
    }
  }

  function confirmFeedAction(): void {
    if (!feedConfirm) return;

    if (feedConfirm.type === "delete-post") {
      void confirmSelectedDelete();
      return;
    }

    void confirmCommentDelete(feedConfirm.comment);
  }

  function updateTotalFeedLikes(delta: number): void {
    if (!Number.isFinite(delta) || delta === 0) return;

    setProfileStats((current) => ({
      ...current,
      total_feed_likes: Math.max(0, current.total_feed_likes + Math.trunc(delta)),
    }));
  }

  async function handleLogout(): Promise<void> {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logoutUser();
    } catch {
      // The session may already be invalid locally; still leave the app shell.
    } finally {
      showAppToast({ title: "Logged out", variant: "success" });
      navigate("/login");
      setIsLoggingOut(false);
    }
  }

  function handleConfirmAccountAction(): void {
    const action = pendingAccountAction;
    if (action === "logout" && isLoggingOut) return;
    setPendingAccountAction(null);

    if (action === "logout") {
      void handleLogout();
    }
  }

  async function handleProfileImageChange(
    event: React.ChangeEvent<HTMLInputElement>
  ): Promise<void> {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsProfileImageMenuOpen(false);

    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type)) {
      showAppToast({
        title: "Unsupported file type.",
        message: "Please upload a JPG, PNG, WEBP, or GIF image.",
        variant: "error",
        placement: "center",
      });
      event.target.value = "";
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      showAppToast({
        title: "File too large.",
        message: "Please upload an image smaller than 5MB.",
        variant: "error",
        placement: "center",
      });
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
      const normalizedPreferences = sanitizePreferencePayload(preferenceDraft);
      const updatePayload = toTravelStylesOnlyPayload(normalizedPreferences);
      const updatedProfile = await updateMyProfile(updatePayload);
      const refreshedProfile = await getMyProfile();
      const nextProfile = {
        ...(profile ?? {}),
        ...(updatedProfile ?? {}),
        ...(refreshedProfile ?? {}),
        ...updatePayload,
      } as UserProfile;
      const nextPreferences = toPreferencePayload(nextProfile);
      setProfile((current) => ({
        ...(current ?? {}),
        ...nextProfile,
      }) as UserProfile);
      setPreferenceDraft(nextPreferences);
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

  async function handleProfileInfoSave(): Promise<void> {
    if (!profile || isSavingInfo) return;

    const ageStr = infoDraft.age.trim();
    let ageNum: number | undefined;
    if (ageStr !== "") {
      const parsed = parseInt(ageStr, 10);
      if (isNaN(parsed) || String(parsed) !== ageStr) {
        setInfoError("Age must be a valid whole number.");
        return;
      }
      if (parsed < MIN_AGE || parsed > MAX_AGE) {
        setInfoError(`Age must be between ${MIN_AGE} and ${MAX_AGE}.`);
        return;
      }
      ageNum = parsed;
    }

    const payload: ProfileUpdatePayload = {};
    const trimName = infoDraft.user_name.trim();
    if (trimName !== (profile.user_name ?? "")) payload.user_name = trimName;
    // email은 수정 불가 — payload에서 제외
    const trimPhone = infoDraft.phone_number.trim();
    if (trimPhone !== (profile.phone_number ?? "")) payload.phone_number = trimPhone;
    if (ageStr === "" && profile.age != null) {
      // cleared — not sent (age cannot be null in PATCH)
    } else if (ageNum !== undefined && ageNum !== profile.age) {
      payload.age = ageNum;
    }
    if (infoDraft.gender !== (profile.gender ?? "")) payload.gender = infoDraft.gender;
    const trimNationality = infoDraft.nationality.trim();
    if (trimNationality !== (profile.nationality ?? "")) payload.nationality = trimNationality;
    const sortedDraft = [...infoDraft.travel_styles].sort().join(",");
    const sortedOrig = [...(profile.travel_styles ?? [])].sort().join(",");
    if (sortedDraft !== sortedOrig) payload.travel_styles = infoDraft.travel_styles;

    if (Object.keys(payload).length === 0) {
      setIsInfoEditing(false);
      return;
    }

    setIsSavingInfo(true);
    setInfoError("");
    try {
      const updated = await updateMyProfile(payload);
      const refreshed = await getMyProfile();
      setProfile(
        (current) =>
          ({
            ...(current ?? {}),
            ...(updated ?? {}),
            ...(refreshed ?? {}),
          }) as UserProfile
      );
      setIsInfoEditing(false);
      showAppToast({ title: "Profile updated successfully.", variant: "success" });
    } catch (error) {
      setInfoError(toErrorMessage(error, "Failed to save profile."));
    } finally {
      setIsSavingInfo(false);
    }
  }

  async function handleGlobalNotificationMuteToggle(): Promise<void> {
    if (isNotificationMuteSaving) return;

    const nextMuted = profile?.notification_muted !== true;
    setIsNotificationMuteSaving(true);
    try {
      await setGlobalNotificationMuted(nextMuted);
      setProfile((current) =>
        current ? { ...current, notification_muted: nextMuted } : current
      );
      showAppToast({
        title: nextMuted ? "Notifications muted" : "Notifications enabled",
        variant: "success",
      });
    } catch (error) {
      showAppToast({
        title: "Failed to update notifications",
        message: toErrorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setIsNotificationMuteSaving(false);
    }
  }

  const profileImageUrl =
    profileImagePreview || getProfileImageUrl(profile) || DEFAULT_PROFILE_IMAGE_URL;
  const canDeleteProfileImage =
    Boolean(getProfileImageUrl(profile)) && !profileImagePreview;
  const nameText = profile?.user_name ?? "";
  const isNotificationMuted = profile?.notification_muted === true;
  const allProfileChips = [
    profile?.nationality,
    ...(profile?.travel_styles ?? []),
  ].filter((value): value is string => Boolean(value));
  const previewProfileChips = allProfileChips.slice(0, 3);
  const expandedProfileChips = allProfileChips.slice(3);
  const canExpandProfileChips = allProfileChips.length > 3;
  const infoItems = [
    { label: "Name", value: profile?.user_name ?? "" },
    { label: "Email", value: profile?.email ?? "" },
    { label: "Phone", value: profile?.phone_number ?? "" },
    { label: "Age", value: profile?.age != null ? String(profile.age) : "" },
    { label: "Gender", value: formatGender(profile?.gender) },
    { label: "Nationality", value: profile?.nationality ?? "" },
  ].filter((item) => item.value);
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
            ) : null}
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
          </div>
          <div style={styles.profileStatsRow}>
            <span style={styles.profileStat}>
              <strong style={styles.profileStatNumber}>{safeCount(feedPosts.length)}</strong>
              <span>Posts</span>
            </span>
            <span style={styles.profileStat}>
              <strong style={styles.profileStatNumber}>{safeCount(profileStats.total_feed_likes)}</strong>
              <span>Likes</span>
            </span>
            <span style={styles.profileStat}>
              <strong style={styles.profileStatNumber}>{safeCount(profileStats.total_friends)}</strong>
              <span>Friends</span>
            </span>
          </div>
          {previewProfileChips.length ? (
            <div style={styles.profileChipBlock}>
              <div style={styles.profileChipPreviewRow}>
                {previewProfileChips.map((chip) => (
                  <span key={chip} style={styles.profileChip}>
                    {formatProfileChip(chip)}
                  </span>
                ))}
                {canExpandProfileChips ? (
                  <button
                    type="button"
                    style={styles.profileChipToggle}
                    onClick={() => setIsProfileChipsExpanded((current) => !current)}
                    aria-label={
                      isProfileChipsExpanded
                        ? "Show fewer travel styles"
                        : "Show all travel styles"
                    }
                    aria-expanded={isProfileChipsExpanded}
                  >
                    <ChevronDownIcon flipped={isProfileChipsExpanded} />
                  </button>
                ) : null}
              </div>
              {canExpandProfileChips ? (
                <div
                  style={{
                    ...styles.profileChipExpandedRow,
                    ...(isProfileChipsExpanded ? styles.profileChipExpandedRowOpen : {}),
                  }}
                >
                  {expandedProfileChips.map((chip) => (
                    <span key={chip} style={styles.profileChip}>
                      {formatProfileChip(chip)}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <section style={styles.profileActionBar}>
        <button
          type="button"
          style={styles.profileActionButton}
          onClick={() => setIsSettingsOpen(true)}
        >
          <img src="/SettingsIcon.svg" alt="" style={styles.profileActionIcon} />
          <span>settings</span>
        </button>
        <span style={styles.profileActionDivider} />
        <button
          type="button"
          style={{
            ...styles.profileActionButton,
            ...(isFeedUploading ? styles.buttonDisabled : {}),
          }}
          onClick={() => {
            if (isFeedUploading) return;
            if (feedPosts.length >= 100) {
              window.alert("The maximum feed photo limit is 100.");
              return;
            }
            feedImageInputRef.current?.click();
          }}
          disabled={isFeedUploading}
        >
          <img src="/PostIcon.svg" alt="" style={styles.profileActionIcon} />
          <span>new post</span>
        </button>
      </section>
      <div style={styles.profileActionDividerLine} />

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
                style={{
                  ...styles.feedTile,
                  ...(post.uploadStatus === "failed" ? styles.feedTilePending : {}),
                }}
                onClick={() => {
                  if (post.uploadStatus === "failed") return;
                  void openFeedPost(post);
                }}
                disabled={post.uploadStatus === "uploading"}
              >
                <img src={getFeedImageUrl(post)} alt="" style={styles.feedTileImage} />
                {post.uploadStatus === "failed" ? (
                  <span style={styles.feedUploadOverlay}>
                    <span style={styles.feedFailedBadge}>Failed</span>
                    <span style={styles.feedUploadError}>
                      {post.uploadError || "Upload failed."}
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      style={styles.feedRetryButton}
                      onClick={(event) => {
                        event.stopPropagation();
                        void retryFeedUpload(post);
                      }}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter" && event.key !== " ") return;
                        event.preventDefault();
                        event.stopPropagation();
                        void retryFeedUpload(post);
                      }}
                    >
                      Retry
                    </span>
                  </span>
                ) : null}
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
              onClick={() => setIsPreferenceEditing((current) => !current)}
            >
              Edit Travel Preferences
            </button>
            <div style={styles.settingsToggleRow}>
              <span style={styles.settingsToggleText}>
                <strong style={styles.settingsToggleTitle}>Notification</strong>
                <span style={styles.settingsToggleCopy}>
                  {isNotificationMuted ? "All push notifications are muted." : "Push notifications are enabled."}
                </span>
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={!isNotificationMuted}
                style={{
                  ...styles.settingsSwitch,
                  ...(!isNotificationMuted ? styles.settingsSwitchOn : {}),
                }}
                onClick={() => void handleGlobalNotificationMuteToggle()}
                disabled={isNotificationMuteSaving}
              >
                <span
                  style={{
                    ...styles.settingsSwitchThumb,
                    ...(!isNotificationMuted ? styles.settingsSwitchThumbOn : {}),
                  }}
                />
              </button>
            </div>
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
              <div style={styles.infoTitleRow}>
                <strong style={styles.settingsInfoTitle}>My Information</strong>
                {!isInfoEditing ? (
                  <button
                    type="button"
                    style={styles.infoEditButton}
                    onClick={() => {
                      setInfoDraft(toInfoDraft(profile));
                      setInfoError("");
                      setIsInfoEditing(true);
                    }}
                  >
                    Edit Profile
                  </button>
                ) : null}
              </div>
              {isInfoEditing ? (
                <InfoEditor
                  draft={infoDraft}
                  isSaving={isSavingInfo}
                  error={infoError}
                  onChangeField={(key, value) =>
                    setInfoDraft((d) => ({ ...d, [key]: value }))
                  }
                  onSave={() => void handleProfileInfoSave()}
                  onCancel={() => {
                    setIsInfoEditing(false);
                    setInfoError("");
                  }}
                />
              ) : (
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
              )}
            </div>
            <button
              type="button"
              style={styles.settingsActionButton}
              onClick={() => {
                if (!isLoggingOut) setPendingAccountAction("logout");
              }}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? "Logging out..." : "Log Out"}
            </button>
            <button
              type="button"
              style={{ ...styles.settingsActionButton, ...styles.settingsDangerButton }}
              onClick={() => navigate("/account/delete")}
            >
              Delete Account
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
          errorMessage={feedError}
          disabled={!feedFile || feedPosts.length >= 100 || isFeedUploading}
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
          busy={isLoggingOut}
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

      {feedConfirm ? (
        <FeedConfirmToast
          title={
            feedConfirm.type === "delete-post"
              ? "Delete this feed?"
              : "Delete this comment?"
          }
          message="This action cannot be undone."
          confirmLabel="Delete"
          busy={isFeedActionRunning}
          onCancel={() => setFeedConfirm(null)}
          onConfirm={confirmFeedAction}
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

function InfoEditor({
  draft,
  isSaving,
  error,
  onChangeField,
  onSave,
  onCancel,
}: {
  draft: ProfileInfoDraft;
  isSaving: boolean;
  error: string;
  onChangeField: (
    key: keyof Omit<ProfileInfoDraft, "travel_styles">,
    value: string
  ) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div style={styles.infoEditor}>
      {error ? <p style={styles.infoEditorError}>{error}</p> : null}

      <div style={styles.infoEditField}>
        <label style={styles.infoEditLabel}>Name</label>
        <input
          type="text"
          value={draft.user_name}
          placeholder="Your name"
          style={styles.infoEditInput}
          disabled={isSaving}
          onChange={(e) => onChangeField("user_name", e.target.value)}
        />
      </div>

      <div style={styles.infoEditField}>
        <label style={styles.infoEditLabel}>Email (cannot be changed)</label>
        <input
          type="email"
          value={draft.email}
          style={{ ...styles.infoEditInput, ...styles.infoEditInputReadonly }}
          readOnly
          disabled
          tabIndex={-1}
        />
      </div>

      <div style={styles.infoEditField}>
        <label style={styles.infoEditLabel}>Phone</label>
        <input
          type="tel"
          value={draft.phone_number}
          placeholder="Phone number"
          style={styles.infoEditInput}
          disabled={isSaving}
          onChange={(e) => onChangeField("phone_number", e.target.value)}
        />
      </div>

      <div style={styles.infoEditField}>
        <label style={styles.infoEditLabel}>
          Age ({MIN_AGE}–{MAX_AGE})
        </label>
        <input
          type="text"
          inputMode="numeric"
          value={draft.age}
          placeholder={`${MIN_AGE}–${MAX_AGE}`}
          style={styles.infoEditInput}
          disabled={isSaving}
          onChange={(e) => {
            const val = e.target.value.replace(/[^0-9]/g, "");
            onChangeField("age", val);
          }}
        />
      </div>

      <div style={styles.infoEditField}>
        <label style={styles.infoEditLabel}>Gender</label>
        <div style={styles.infoEditChipList}>
          {(["male", "female", "other"] as const).map((g) => (
            <button
              key={g}
              type="button"
              style={{
                ...styles.preferenceChoice,
                ...(draft.gender === g ? styles.preferenceChoiceActive : {}),
              }}
              disabled={isSaving}
              onClick={() => onChangeField("gender", draft.gender === g ? "" : g)}
            >
              {g.charAt(0).toUpperCase() + g.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div style={styles.infoEditField}>
        <label style={styles.infoEditLabel}>Nationality</label>
        <input
          type="text"
          value={draft.nationality}
          placeholder="e.g. Korean"
          style={styles.infoEditInput}
          disabled={isSaving}
          onChange={(e) => onChangeField("nationality", e.target.value)}
        />
      </div>

      <div style={styles.infoEditorActions}>
        <button
          type="button"
          style={styles.secondaryButton}
          disabled={isSaving}
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          type="button"
          style={{
            ...styles.primaryButton,
            ...(isSaving ? styles.buttonDisabled : {}),
          }}
          disabled={isSaving}
          onClick={onSave}
        >
          {isSaving ? "Saving..." : "Save"}
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
            {isWithdraw ? (busy ? "Deleting..." : "Delete") : busy ? "Logging out..." : "Log Out"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FeedConfirmToast({
  title,
  message,
  confirmLabel,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  message: string;
  confirmLabel: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div style={styles.feedConfirmBackdrop} onClick={busy ? undefined : onCancel}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="feed-confirm-title"
        style={styles.feedConfirmCard}
        onClick={(event) => event.stopPropagation()}
      >
        <strong id="feed-confirm-title" style={styles.feedConfirmTitle}>
          {title}
        </strong>
        <p style={styles.feedConfirmMessage}>{message}</p>
        <div style={styles.feedConfirmActions}>
          <button
            type="button"
            style={styles.feedConfirmCancel}
            disabled={busy}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            style={{
              ...styles.feedConfirmDelete,
              ...(busy ? styles.buttonDisabled : {}),
            }}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Deleting..." : confirmLabel}
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
  errorMessage,
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
  errorMessage: string;
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
        {!isUploading && errorMessage ? (
          <p style={styles.createPostErrorText}>{errorMessage}</p>
        ) : null}
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
  const [commentsExpanded, setCommentsExpanded] = useState(false);

  return (
    <div style={styles.modalBackdrop} onClick={onClose}>
      <div
        style={{
          ...styles.feedModal,
          ...(commentsExpanded ? styles.feedModalCommentsExpanded : {}),
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" style={styles.modalCloseButton} onClick={onClose}>
          x
        </button>
        <div
          style={{
            ...styles.feedModalImagePane,
            ...(commentsExpanded ? styles.feedModalImagePaneCompact : {}),
          }}
        >
          <img src={post.original_url} alt="" style={styles.feedModalImage} />
        </div>
        <aside style={styles.feedModalSidePane}>
          <button
            type="button"
            style={styles.feedCommentHandleButton}
            onClick={() => setCommentsExpanded((current) => !current)}
            aria-label={commentsExpanded ? "Collapse comments" : "Expand comments"}
          >
            <span style={styles.feedCommentHandle} />
          </button>
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

          <div
            style={{
              ...styles.feedDiscussion,
              ...(commentsExpanded ? styles.feedDiscussionExpanded : {}),
            }}
          >
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
                <HeartIcon filled={post.is_liked} />
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
                onFocus={() => setCommentsExpanded(true)}
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

function ChevronDownIcon({ flipped }: { flipped: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      stroke="#606060"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        transform: flipped ? "rotate(180deg)" : "none",
        transition: "transform 200ms",
      }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(42px + var(--app-safe-top)) 12px calc(110px + var(--app-safe-bottom))",
    background: "#f5f5f5",
    fontFamily: "'Apple SD Gothic Neo', 'Pretendard Variable', 'Nunito', sans-serif",
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
  statusMessage: {
    margin: "10px 0 12px",
    color: "var(--text-secondary)",
    lineHeight: 1.5,
    overflowWrap: "anywhere",
  },
  profileStat: {
    minWidth: 56,
    color: "#323232",
    fontSize: "0.862rem",
    fontWeight: 400,
    lineHeight: 1.28,
    letterSpacing: "-0.02em",
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
  },
  profileStatNumber: {
    fontWeight: 400,
  },
  profileStatsRow: {
    display: "flex",
    alignItems: "center",
    gap: 22,
    marginTop: 6,
    marginBottom: 12,
  },
  profileChipBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    maxWidth: 360,
  },
  profileChipPreviewRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "nowrap",
    maxWidth: "100%",
    overflow: "hidden",
  },
  profileChipExpandedRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "wrap",
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
    whiteSpace: "nowrap",
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
  avatarButton: {
    width: 108,
    height: 108,
    position: "relative",
    padding: 0,
    border: "4px solid #ffffff",
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "var(--neutral-100)",
    overflow: "hidden",
    cursor: "pointer",
    boxShadow: "0 8px 18px rgba(33,33,33,0.1)",
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
    top: 118,
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
    color: "#1a1a1a",
    fontSize: "1.25rem",
    fontWeight: 400,
    lineHeight: 1.15,
    letterSpacing: "-0.02em",
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
  profileActionDividerLine: {
    width: "calc(100% + 24px)",
    height: 1,
    margin: "16px -12px 10px",
    background: "#d7d7d7",
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
  profileActionIcon: {
    width: 26,
    height: 26,
    objectFit: "contain",
    display: "block",
    opacity: 0.72,
  },
  profileActionDivider: {
    width: 1,
    height: 31,
    background: "#bebebe",
  },
  section: {
    width: "calc(100% + 24px)",
    maxWidth: "none",
    margin: "0 -12px",
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
  feedTilePending: {
    cursor: "default",
  },
  feedTileImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
    display: "block",
  },
  feedUploadOverlay: {
    position: "absolute",
    inset: 0,
    zIndex: 2,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    padding: 12,
    background: "rgba(5,6,8,0.42)",
    color: "#ffffff",
    textAlign: "center",
    backdropFilter: "blur(1.5px)",
  },
  feedUploadSpinner: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    border: "3px solid rgba(255,255,255,0.36)",
    borderTopColor: "#ffffff",
    animation: "spin 820ms linear infinite",
  },
  feedUploadBadge: {
    borderRadius: 999,
    padding: "5px 10px",
    background: "rgba(5,181,187,0.92)",
    color: "#ffffff",
    fontSize: "0.72rem",
    fontWeight: 900,
  },
  feedUploadPercent: {
    color: "rgba(255,255,255,0.9)",
    fontSize: "0.78rem",
    fontWeight: 900,
  },
  feedFailedBadge: {
    borderRadius: 999,
    padding: "5px 10px",
    background: "rgba(220,38,38,0.94)",
    color: "#ffffff",
    fontSize: "0.72rem",
    fontWeight: 900,
  },
  feedUploadError: {
    maxWidth: "100%",
    color: "rgba(255,255,255,0.92)",
    fontSize: "0.72rem",
    fontWeight: 800,
    lineHeight: 1.25,
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
  },
  feedRetryButton: {
    borderRadius: 999,
    padding: "6px 12px",
    background: "#ffffff",
    color: "#dc2626",
    fontSize: "0.72rem",
    fontWeight: 900,
    cursor: "pointer",
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
  feedTileMetaHidden: {
    display: "none",
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
  settingsToggleRow: {
    minHeight: 58,
    border: "1px solid var(--neutral-200)",
    borderRadius: 14,
    padding: "10px 12px 10px 14px",
    background: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  settingsToggleText: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 3,
  },
  settingsToggleTitle: {
    color: "var(--text-primary)",
    fontSize: "0.92rem",
  },
  settingsToggleCopy: {
    color: "var(--neutral-500)",
    fontSize: "0.74rem",
    fontWeight: 800,
  },
  settingsSwitch: {
    width: 54,
    height: 30,
    border: "none",
    borderRadius: 9999,
    padding: 3,
    background: "#d7dce0",
    cursor: "pointer",
    flexShrink: 0,
    transition: "background-color 180ms ease",
  },
  settingsSwitchOn: {
    background: "#7ee3e7",
  },
  settingsSwitchThumb: {
    display: "block",
    width: 24,
    height: 24,
    borderRadius: 9999,
    background: "#ffffff",
    transform: "translateX(0)",
    transition: "transform 180ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  settingsSwitchThumbOn: {
    transform: "translateX(24px)",
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
    border: "1px solid rgba(5,181,187,0.38)",
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
  infoTitleRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  infoEditButton: {
    minHeight: 32,
    border: "1px solid rgba(5,181,187,0.28)",
    borderRadius: 999,
    padding: "0 14px",
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap" as const,
  },
  infoEditor: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 14,
    borderRadius: 16,
    background: "rgba(5,181,187,0.06)",
    border: "1px solid rgba(5,181,187,0.14)",
  },
  infoEditorError: {
    margin: 0,
    padding: "8px 12px",
    borderRadius: 10,
    background: "rgba(220,38,38,0.08)",
    color: "#dc2626",
    fontSize: "0.82rem",
    fontWeight: 800,
  },
  infoEditField: {
    display: "flex",
    flexDirection: "column",
    gap: 5,
  },
  infoEditLabel: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  infoEditInput: {
    width: "100%",
    minHeight: 40,
    border: "1px solid var(--neutral-200)",
    borderRadius: 10,
    padding: "0 12px",
    background: "#ffffff",
    color: "var(--text-primary)",
    fontSize: "0.9rem",
    fontFamily: "inherit",
    outline: "none",
    boxSizing: "border-box" as const,
  },
  infoEditInputReadonly: {
    background: "var(--neutral-100)",
    color: "var(--neutral-700)",
    cursor: "not-allowed",
    opacity: 0.7,
  },
  infoEditChipList: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 8,
  },
  infoEditorActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    paddingTop: 4,
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
  createPostErrorText: {
    margin: 0,
    padding: "10px 18px",
    color: "#fecaca",
    background: "rgba(220,38,38,0.14)",
    borderBottom: "1px solid rgba(220,38,38,0.2)",
    fontSize: "0.82rem",
    fontWeight: 800,
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
  feedConfirmBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 140,
    display: "grid",
    placeItems: "center",
    padding: 24,
    background: "rgba(15,23,42,0.34)",
    backdropFilter: "blur(2px)",
  },
  feedConfirmCard: {
    width: "min(336px, 100%)",
    borderRadius: 20,
    padding: 20,
    background: "rgba(255,255,255,0.98)",
    border: "1px solid rgba(255,255,255,0.82)",
    boxShadow:
      "0 32px 86px rgba(15,23,42,0.38), 0 14px 32px rgba(15,23,42,0.22)",
    color: "var(--text-primary)",
    textAlign: "center",
  },
  feedConfirmTitle: {
    display: "block",
    fontSize: "1.08rem",
    lineHeight: 1.25,
  },
  feedConfirmMessage: {
    margin: "8px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.88rem",
    lineHeight: 1.45,
  },
  feedConfirmActions: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 10,
    marginTop: 18,
  },
  feedConfirmCancel: {
    minHeight: 42,
    border: "1px solid var(--border-soft)",
    borderRadius: 14,
    background: "#ffffff",
    color: "var(--text-secondary)",
    fontWeight: 900,
    cursor: "pointer",
  },
  feedConfirmDelete: {
    minHeight: 42,
    border: "none",
    borderRadius: 14,
    background: "#dc2626",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(220,38,38,0.24)",
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
    transition: "max-height 260ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  feedModalCommentsExpanded: {
    maxHeight: "98dvh",
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
    transition: "min-height 260ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  feedModalImagePaneCompact: {
    minHeight: "min(28dvh, 260px)",
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
  feedCommentHandleButton: {
    width: "100%",
    minHeight: 20,
    border: "none",
    background: "#ffffff",
    display: "grid",
    placeItems: "center",
    padding: "7px 0 0",
    cursor: "pointer",
    touchAction: "manipulation",
  },
  feedCommentHandle: {
    width: 46,
    height: 5,
    borderRadius: 999,
    background: "#d8d8d8",
    display: "block",
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
    transition: "max-height 260ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  feedDiscussionExpanded: {
    maxHeight: "64dvh",
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
  commentItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    padding: "8px 0",
  },
  feedCommentAvatar: {
    width: 30,
    height: 30,
    borderRadius: "50%",
    objectFit: "cover" as const,
    flexShrink: 0,
    background: "#3a3d45",
  },
  feedPostCommentMain: {
    minWidth: 0,
    flex: 1,
  },
  commentAuthor: {
    display: "block",
    color: "var(--text-primary)",
    fontSize: "0.84rem",
    fontWeight: 900,
  },
  commentText: {
    margin: "2px 0 0",
    color: "var(--text-secondary)",
    fontSize: "0.86rem",
    lineHeight: 1.4,
    overflowWrap: "anywhere" as const,
  },
  commentDeleteButton: {
    border: "none",
    background: "transparent",
    color: "#ef4444",
    fontSize: "0.72rem",
    fontWeight: 900,
    cursor: "pointer",
    flexShrink: 0,
  },
  likesList: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  likeUser: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "4px 8px",
    borderRadius: 999,
    background: "var(--neutral-100)",
    color: "var(--text-secondary)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  commentForm: {
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 8,
    marginTop: 4,
  },
  feedCommentInput: {
    minHeight: 38,
    minWidth: 0,
    border: "1px solid var(--border-soft)",
    borderRadius: 999,
    padding: "0 12px",
    color: "var(--text-primary)",
    outline: "none",
    fontFamily: "inherit",
  },
  feedPostSubmitButton: {
    border: "none",
    borderRadius: 999,
    padding: "0 14px",
    background: "var(--text-primary)",
    color: "#ffffff",
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

function createOptimisticFeedPost({
  postId,
  file,
  previewUrl,
  caption,
  visibility,
}: {
  postId: string;
  file: File;
  previewUrl: string;
  caption: string;
  visibility: FeedVisibility;
}): FeedPostItem {
  const now = new Date().toISOString();
  return {
    post_id: postId,
    user_id: "",
    original_url: previewUrl,
    thumbnail_small_url: previewUrl,
    thumbnail_medium_url: previewUrl,
    caption,
    visibility,
    like_count: 0,
    comment_count: 0,
    is_liked: false,
    created_at: now,
    updated_at: now,
    uploadStatus: "uploading",
    uploadProgress: 0,
    uploadFile: file,
    uploadPreviewUrl: previewUrl,
    uploadCaption: caption,
    uploadVisibility: visibility,
  };
}

function getFeedImageUrl(post: FeedPostItem): string {
  return post.uploadPreviewUrl || post.thumbnail_medium_url || post.thumbnail_small_url || post.original_url || "";
}

function mergeFeedPost<T extends FeedPost>(current: T, next: FeedPost): T {
  return {
    ...current,
    ...next,
    is_liked:
      typeof next.is_liked === "boolean" ? next.is_liked : current.is_liked,
  };
}

function findLikelyUploadedPost(
  posts: FeedPost[],
  upload: { caption: string; visibility: FeedVisibility; startedAt: number }
): FeedPost | null {
  const normalizedCaption = upload.caption.trim();
  const uploadWindowStart = upload.startedAt - 10000;

  return (
    posts.find((post) => {
      const createdAt = Date.parse(post.created_at);
      const postCaption = (post.caption || "").trim();

      return (
        post.visibility === upload.visibility &&
        postCaption === normalizedCaption &&
        Number.isFinite(createdAt) &&
        createdAt >= uploadWindowStart
      );
    }) || null
  );
}

async function isAnimatedFeedImage(file: File): Promise<boolean> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  if (file.type === "image/png" || file.type === "image/apng") {
    return isAnimatedPng(bytes);
  }
  if (file.type === "image/webp") {
    return isAnimatedWebp(bytes);
  }
  return false;
}

function isAnimatedPng(bytes: Uint8Array): boolean {
  const sig = [137, 80, 78, 71, 13, 10, 26, 10];
  for (let i = 0; i < sig.length; i++) {
    if (bytes[i] !== sig[i]) return false;
  }
  let offset = 8;
  while (offset + 12 <= bytes.length) {
    const len =
      (bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3];
    const type = String.fromCharCode(
      bytes[offset + 4],
      bytes[offset + 5],
      bytes[offset + 6],
      bytes[offset + 7]
    );
    if (type === "acTL") return true;
    if (type === "IDAT") break;
    offset += 12 + len;
  }
  return false;
}

function isAnimatedWebp(bytes: Uint8Array): boolean {
  if (bytes.length < 12) return false;
  const riff = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
  const webp = String.fromCharCode(bytes[8], bytes[9], bytes[10], bytes[11]);
  if (riff !== "RIFF" || webp !== "WEBP") return false;
  let offset = 12;
  while (offset + 8 <= bytes.length) {
    const fourcc = String.fromCharCode(
      bytes[offset],
      bytes[offset + 1],
      bytes[offset + 2],
      bytes[offset + 3]
    );
    if (fourcc === "ANIM") return true;
    const size =
      bytes[offset + 4] |
      (bytes[offset + 5] << 8) |
      (bytes[offset + 6] << 16) |
      (bytes[offset + 7] << 24);
    offset += 8 + size + (size & 1);
  }
  return false;
}

function toPreferencePayload(
  profile: UserProfile | null
): ProfilePreferencesPayload {
  if (!profile) return EMPTY_PREFERENCES;
  if (Array.isArray(profile.travel_styles)) {
    return splitTravelStyles(profile.travel_styles);
  }

  return {
    travel_styles: [],
    food_preferences: normalizePreferenceList(profile.food_preferences),
    density_preference: normalizePreferenceValue(profile.density_preference),
    budget_preference: normalizePreferenceValue(profile.budget_preference),
    walking_preference: normalizePreferenceValue(profile.walking_preference),
    transport_preferences: normalizePreferenceList(profile.transport_preferences),
    companion_preference: normalizePreferenceValue(profile.companion_preference),
    time_preferences: normalizePreferenceList(profile.time_preferences),
    communication_preference: normalizePreferenceValue(profile.communication_preference),
    planning_preference: normalizePreferenceValue(profile.planning_preference),
  };
}

function sanitizePreferencePayload(
  payload: ProfilePreferencesPayload
): ProfilePreferencesPayload {
  return {
    travel_styles: normalizePreferenceList(payload.travel_styles),
    food_preferences: normalizePreferenceList(payload.food_preferences),
    density_preference: normalizePreferenceValue(payload.density_preference),
    budget_preference: normalizePreferenceValue(payload.budget_preference),
    walking_preference: normalizePreferenceValue(payload.walking_preference),
    transport_preferences: normalizePreferenceList(payload.transport_preferences),
    companion_preference: normalizePreferenceValue(payload.companion_preference),
    time_preferences: normalizePreferenceList(payload.time_preferences),
    communication_preference: normalizePreferenceValue(payload.communication_preference),
    planning_preference: normalizePreferenceValue(payload.planning_preference),
  };
}

function toTravelStylesOnlyPayload(
  preferences: ProfilePreferencesPayload
): ProfileUpdatePayload {
  return {
    travel_styles: mergeUnique(
      preferences.travel_styles,
      preferences.food_preferences,
      [
        preferences.density_preference,
        preferences.budget_preference,
        preferences.walking_preference,
      ],
      preferences.transport_preferences,
      [preferences.companion_preference],
      preferences.time_preferences,
      [preferences.communication_preference, preferences.planning_preference]
    ),
  };
}

function splitTravelStyles(values: string[]): ProfilePreferencesPayload {
  const result: ProfilePreferencesPayload = {
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

  normalizePreferenceList(values).forEach((value) => {
    if (TRAVEL_STYLE_KEYS.has(value)) result.travel_styles.push(value);
    else if (FOOD_KEYS.has(value)) result.food_preferences?.push(value);
    else if (DENSITY_KEYS.has(value)) result.density_preference = value;
    else if (BUDGET_KEYS.has(value)) result.budget_preference = value;
    else if (WALKING_KEYS.has(value)) result.walking_preference = value;
    else if (TRANSPORT_KEYS.has(value)) result.transport_preferences?.push(value);
    else if (COMPANION_KEYS.has(value)) result.companion_preference = value;
    else if (TIME_KEYS.has(value)) result.time_preferences?.push(value);
    else if (COMMUNICATION_KEYS.has(value)) result.communication_preference = value;
    else if (PLANNING_KEYS.has(value)) result.planning_preference = value;
    else result.travel_styles.push(value);
  });

  return result;
}

function normalizePreferenceList(values?: string[]): string[] {
  return mergeUnique(values);
}

function normalizePreferenceValue(value?: string): string {
  return (value ?? "").trim().toLowerCase();
}

function mergeUnique(...groups: Array<Array<string | undefined> | undefined>): string[] {
  return Array.from(
    new Set(
      groups
        .flatMap((group) => group ?? [])
        .map(normalizePreferenceValue)
        .filter(Boolean)
    )
  );
}

function getVisibilityLabel(visibility: FeedVisibility): string {
  if (visibility === "public") return "Public";
  if (visibility === "friends") return "Friends";
  return "Private";
}

function formatGender(gender?: string): string {
  if (gender === "male") return "Male";
  if (gender === "female") return "Female";
  return gender || "";
}

function formatProfileChip(value: string): string {
  return value.trim().replace(/[_-]+/g, " ");
}

function sanitizeProfileStats(stats: MyProfileStats | null | undefined): MyProfileStats {
  return {
    total_feed_likes: safeCount(stats?.total_feed_likes),
    total_friends: safeCount(stats?.total_friends),
  };
}

function safeCount(value: unknown): number {
  const numberValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numberValue) || numberValue < 0) return 0;

  return Math.trunc(numberValue);
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as { message?: string };
  return apiError.message || fallback;
}

function getApiStatus(error: unknown): number | undefined {
  const apiError = error as { status?: number; response?: { status?: number } };
  return apiError.status || apiError.response?.status;
}
