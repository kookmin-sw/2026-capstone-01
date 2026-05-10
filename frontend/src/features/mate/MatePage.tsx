import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  createTripMatePost,
  deleteDraft,
  deleteTripMatePost,
  getDraft,
  getTripMatePosts,
  saveDraft,
  searchTripMatePosts,
  toggleLike,
  updateTripMatePost,
  type CompanionType,
  type PreferredGender,
  type TripMatePost,
} from "../../api/mate";
import {
  deleteSearchHistoryAll,
  deleteSearchHistoryOne,
  getSearchHistory,
} from "../../api/searchHistory";
import { uploadImages } from "../../api/image";
import { getMyProfile } from "../../api/auth";
import { createDirectChatRoom } from "../../api/chat";
import {
  deleteFriendSearchHistoryAll,
  deleteFriendSearchHistoryOne,
  getFriendDetail,
  getFriendSearchHistory,
  searchFriendUsers,
  sendFriendRequest,
  type FriendSearchUser,
  type FriendshipStatus,
} from "../../api/friend";
import { getRecommendationCandidates } from "../../api/recommendation";
import {
  recommendTravelers,
  type MatePreferenceProfile,
  type RecommendationCandidate,
  type RecommendedTraveler,
} from "../../utils/mateRecommendation";
import NotificationBell from "../../components/NotificationBell";
import FeedPopup from "../../components/FeedPopup";

const COMPANION_FILTERS = ["all", "sole", "friend", "couple", "family"] as const;
const COMPANION_OPTIONS: CompanionType[] = ["friend", "family", "couple", "sole"];
const GENDER_OPTIONS: PreferredGender[] = ["any", "male", "female"];

const COMPANION_LABELS: Record<CompanionType | "all", string> = {
  all: "All",
  sole: "Solo",
  friend: "Friends",
  couple: "Couple",
  family: "Family",
};

const GENDER_LABELS: Record<PreferredGender, string> = {
  any: "Any gender",
  male: "Male",
  female: "Female",
};

const DEFAULT_PROFILE_IMAGE_URL = "/default-profile.png";

const EMPTY_FORM = {
  title: "",
  content: "",
  region: "",
  travel_start_date: "",
  travel_end_date: "",
  companion_type: "friend" as CompanionType,
  preferred_gender: "any" as PreferredGender,
  preferred_age_min: 20,
  preferred_age_max: 35,
};

type Tab = "list" | "write";
type MateFriendState = {
  friendship_status: FriendshipStatus | null;
  is_requester: boolean | null;
  i_blocked_peer: boolean;
};

export default function MatePage() {
  const navigate = useNavigate();
  const searchRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const draftTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const draftFormRef = useRef(EMPTY_FORM);
  const draftImageUrlsRef = useRef<string[]>([]);
  const suggestionRequestIdRef = useRef(0);

  const [tab, setTab] = useState<Tab>("list");
  const [posts, setPosts] = useState<TripMatePost[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [userResults, setUserResults] = useState<FriendSearchUser[]>([]);
  const [userNextCursor, setUserNextCursor] = useState<string | null>(null);
  const [userSearchLoading, setUserSearchLoading] = useState(false);
  const [userSearchError, setUserSearchError] = useState("");
  const [filter, setFilter] = useState<CompanionType | "all">("all");
  const [currentRecommendationProfile, setCurrentRecommendationProfile] =
    useState<MatePreferenceProfile>({});
  const [recommendationCandidates, setRecommendationCandidates] = useState<
    RecommendationCandidate[]
  >([]);

  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHistory, setSearchHistory] = useState<string[]>([]);
  const [suggestedUsers, setSuggestedUsers] = useState<FriendSearchUser[]>([]);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const [selectedPost, setSelectedPost] = useState<TripMatePost | null>(null);
  const [selectedRecommendedTraveler, setSelectedRecommendedTraveler] =
    useState<RecommendedTraveler | null>(null);
  const [friendRequested, setFriendRequested] = useState<Set<string>>(new Set());
  const [recommendedFriendRequested, setRecommendedFriendRequested] = useState<
    Set<string>
  >(new Set());
  const [friendStates, setFriendStates] = useState<Record<string, MateFriendState>>({});
  const [friendRequestingUserId, setFriendRequestingUserId] = useState<string | null>(null);
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const [feedPopupUserId, setFeedPopupUserId] = useState<string | null>(null);
  const [chatOpeningPostId, setChatOpeningPostId] = useState<string | null>(null);

  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [menuOpenPostId, setMenuOpenPostId] = useState<string | null>(null);
  const [editingPostId, setEditingPostId] = useState<string | null>(null);

  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const [draftStatus, setDraftStatus] = useState("");
  const [imageUrls, setImageUrls] = useState<string[]>([]);
  const [imagePreviews, setImagePreviews] = useState<string[]>([]);
  const [imageUploading, setImageUploading] = useState(false);

  useEffect(() => {
    draftFormRef.current = form;
    draftImageUrlsRef.current = imageUrls;
  }, [form, imageUrls]);

  async function loadSearchHistory(): Promise<void> {
    try {
      const [postHistory, userHistory] = await Promise.all([
        getSearchHistory(),
        getFriendSearchHistory(),
      ]);
      setSearchHistory(
        dedupeSearchHistory([
          ...postHistory.histories.map((item) => item.search_name),
          ...userHistory.histories.map((item) => item.search_name),
        ])
      );
    } catch {
      setSearchHistory([]);
    }
  }

  async function fetchPosts(cursor?: string): Promise<void> {
    setLoading(true);
    setErrorMessage("");

    try {
      const response = searchQuery
        ? await searchTripMatePosts(searchQuery, cursor)
        : await getTripMatePosts(cursor);

      const newPosts = Array.isArray(response) ? response : response.posts ?? [];
      const newCursor = Array.isArray(response) ? null : response.next_cursor ?? null;

      setPosts((current) => (cursor ? [...current, ...newPosts] : newPosts));
      setNextCursor(newCursor);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to load mate posts.");
      if (!cursor) {
        setPosts([]);
      }
    } finally {
      setLoading(false);
    }
  }

  async function fetchUsers(keyword: string, cursor?: string): Promise<void> {
    const nextKeyword = keyword.trim();
    if (!nextKeyword) {
      setUserResults([]);
      setUserNextCursor(null);
      setUserSearchError("");
      return;
    }

    setUserSearchLoading(true);
    setUserSearchError("");

    try {
      const response = await searchFriendUsers(nextKeyword, cursor);
      setUserResults((current) =>
        cursor ? [...current, ...response.items] : response.items
      );
      setUserNextCursor(response.next_cursor);
    } catch (error) {
      setUserSearchError(
        error instanceof Error ? error.message : "Failed to search users."
      );
      if (!cursor) {
        setUserResults([]);
        setUserNextCursor(null);
      }
    } finally {
      setUserSearchLoading(false);
    }
  }

  useEffect(() => {
    void fetchPosts();
  }, [searchQuery]);

  useEffect(() => {
    if (!searchQuery) {
      setUserResults([]);
      setUserNextCursor(null);
      setUserSearchError("");
      return;
    }

    void fetchUsers(searchQuery);
  }, [searchQuery]);

  useEffect(() => {
    const keyword = searchInput.trim();
    if (!showHistory || !keyword) {
      setSuggestedUsers([]);
      setSuggestionLoading(false);
      return undefined;
    }

    const requestId = suggestionRequestIdRef.current + 1;
    suggestionRequestIdRef.current = requestId;
    setSuggestionLoading(true);

    const timerId = window.setTimeout(() => {
      searchFriendUsers(keyword)
        .then((response) => {
          if (suggestionRequestIdRef.current !== requestId) return;
          setSuggestedUsers(response.items.slice(0, 5));
        })
        .catch(() => {
          if (suggestionRequestIdRef.current !== requestId) return;
          setSuggestedUsers([]);
        })
        .finally(() => {
          if (suggestionRequestIdRef.current !== requestId) return;
          setSuggestionLoading(false);
        });
    }, 250);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [searchInput, showHistory]);

  useEffect(() => {
    if (!selectedPost || selectedPost.user_id === currentUserId || friendStates[selectedPost.user_id]) {
      return;
    }

    getFriendDetail(selectedPost.user_id)
      .then((detail) => {
        setFriendStates((current) => ({
          ...current,
          [selectedPost.user_id]: {
            friendship_status: detail.friendship_status,
            is_requester: detail.is_requester,
            i_blocked_peer: detail.i_blocked_peer,
          },
        }));
      })
      .catch(() => {
        // Relationship metadata is optional for rendering the post itself.
      });
  }, [currentUserId, friendStates, selectedPost]);

  useEffect(() => {
    void loadSearchHistory();
    getMyProfile()
      .then((profile) => {
        setCurrentUserId(profile?.user_id ?? null);
        setCurrentRecommendationProfile({
          user_id: profile?.user_id ?? null,
          travel_styles: profile?.travel_styles ?? [],
          food_preferences: profile?.food_preferences ?? [],
          density_preference: profile?.density_preference,
          budget_preference: profile?.budget_preference,
          walking_preference: profile?.walking_preference,
          transport_preferences: profile?.transport_preferences ?? [],
          companion_preference: profile?.companion_preference,
          time_preferences: profile?.time_preferences ?? [],
          communication_preference: profile?.communication_preference,
          planning_preference: profile?.planning_preference,
          nationality: profile?.nationality,
        });
      })
      .catch((error) => {
        console.warn("Failed to load /api/auth/profile/me", error);
        setCurrentUserId(null);
        setCurrentRecommendationProfile({});
      });
  }, []);

  useEffect(() => {
    getRecommendationCandidates()
      .then((response) => setRecommendationCandidates(response.items ?? []))
      .catch((error) => {
        console.warn("Failed to load recommendation candidates", error);
        setRecommendationCandidates([]);
      });
  }, []);

  useEffect(() => {
    if (tab !== "write") {
      return undefined;
    }

    if (!editingPostId) {
      getDraft()
        .then((draft) => {
          if (!draft) return;

          setForm({
            title: draft.title ?? "",
            content: draft.content ?? "",
            region: draft.region ?? "",
            travel_start_date: draft.travel_start_date ?? "",
            travel_end_date: draft.travel_end_date ?? "",
            companion_type: draft.companion_type ?? "friend",
            preferred_gender: draft.preferred_gender ?? "any",
            preferred_age_min: draft.preferred_age_min ?? 20,
            preferred_age_max: draft.preferred_age_max ?? 35,
          });
          setImageUrls(draft.image_urls ?? []);
          setImagePreviews(draft.image_urls ?? []);
        })
        .catch(() => {
          // Drafts are optional.
        });
    }

    draftTimer.current = setInterval(() => {
      void handleAutoSaveDraft(false);
    }, 30000);

    return () => {
      if (draftTimer.current) {
        clearInterval(draftTimer.current);
      }
    };
  }, [tab, editingPostId]);

  const filteredPosts = useMemo(
    () =>
      filter === "all"
        ? posts
        : posts.filter((post) => post.companion_type === filter),
    [filter, posts]
  );

  const visibleSearchHistory = useMemo(() => {
    const keyword = searchInput.trim().toLowerCase();
    if (!keyword) return searchHistory;

    return searchHistory.filter((item) => item.toLowerCase().includes(keyword));
  }, [searchHistory, searchInput]);

  const hasSearchSuggestions =
    showHistory &&
    (suggestionLoading || suggestedUsers.length > 0 || visibleSearchHistory.length > 0);

  const mateRecommendations = useMemo(
    () => recommendTravelers(currentRecommendationProfile, recommendationCandidates, 10),
    [currentRecommendationProfile, recommendationCandidates]
  );
  const recommendationSourceTags = useMemo(
    () => getMatePreferenceTags(currentRecommendationProfile),
    [currentRecommendationProfile]
  );

  function resetEditor(): void {
    setEditingPostId(null);
    setForm(EMPTY_FORM);
    setImageUrls([]);
    setImagePreviews([]);
  }

  function handleTabChange(nextTab: Tab): void {
    if (nextTab === "list" && editingPostId) {
      resetEditor();
    }

    setTab(nextTab);
  }

  function handleSearch(keyword: string): void {
    const nextKeyword = keyword.trim();
    if (!nextKeyword) return;

    setSearchQuery(nextKeyword);
    setSearchInput(nextKeyword);
    setShowHistory(false);
    window.setTimeout(() => void loadSearchHistory(), 500);
  }

  async function handleDeleteSearchHistory(term: string): Promise<void> {
    await Promise.allSettled([
      deleteSearchHistoryOne(term),
      deleteFriendSearchHistoryOne(term),
    ]);
    setSearchHistory((current) => current.filter((item) => item !== term));
    setShowHistory(true);
    searchRef.current?.focus();
  }

  async function handleClearSearchHistory(): Promise<void> {
    await Promise.allSettled([
      deleteSearchHistoryAll(),
      deleteFriendSearchHistoryAll(),
    ]);
    setSearchHistory([]);
  }

  async function handleImageSelect(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;

    const selectedFiles = files.slice(0, Math.max(0, 10 - imageUrls.length));
    if (selectedFiles.length === 0) return;

    const previews = selectedFiles.map((file) => URL.createObjectURL(file));
    setImagePreviews((current) => [...current, ...previews]);
    setImageUploading(true);

    try {
      const response = await uploadImages(selectedFiles);
      setImageUrls((current) => [
        ...current,
        ...response.images.map((image) => image.image_url),
      ]);
    } catch (uploadError) {
      window.alert(toErrorMessage(uploadError, "Image upload failed. Please try again."));
      setImagePreviews((current) => current.slice(0, current.length - selectedFiles.length));
    } finally {
      setImageUploading(false);
      if (imageInputRef.current) {
        imageInputRef.current.value = "";
      }
    }
  }

  function handleImageRemove(index: number): void {
    setImageUrls((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setImagePreviews((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  async function handleAutoSaveDraft(showError = true): Promise<void> {
    if (editingPostId) return;

    setDraftSaving(true);
    setDraftStatus("Saving draft...");
    try {
      await saveDraft({
        ...draftFormRef.current,
        image_urls: draftImageUrlsRef.current,
      });
      setDraftStatus("Draft saved");
    } catch (draftError) {
      setDraftStatus("");
      if (showError) {
        window.alert(toErrorMessage(draftError, "Failed to save draft. Please try again."));
      }
    } finally {
      window.setTimeout(() => {
        setDraftSaving(false);
        setDraftStatus("");
      }, 900);
    }
  }

  async function handleLike(event: MouseEvent<HTMLButtonElement>, post: TripMatePost): Promise<void> {
    event.stopPropagation();

    const nextLiked = !post.is_liked;
    const nextCount = Math.max(0, post.like_count + (nextLiked ? 1 : -1));
    setPosts((current) =>
      current.map((item) =>
        item.post_id === post.post_id
          ? { ...item, is_liked: nextLiked, like_count: nextCount }
          : item
      )
    );

    try {
      await toggleLike(post.post_id, post.is_liked);
      window.dispatchEvent(new Event("krip:notification-inbox-updated"));
    } catch {
      setPosts((current) =>
        current.map((item) => (item.post_id === post.post_id ? post : item))
      );
    }
  }

  async function handleSendFriendRequest(post: TripMatePost): Promise<void> {
    if (friendRequestingUserId) return;

    setFriendRequestingUserId(post.user_id);
    try {
      const friendship = await sendFriendRequest(post.user_id);
      setFriendRequested((current) => new Set(current).add(post.post_id));
      setFriendStates((current) => ({
        ...current,
        [post.user_id]: {
          friendship_status: friendship.status,
          is_requester: friendship.is_requester,
          i_blocked_peer: false,
        },
      }));
    } catch (friendError) {
      window.alert(toErrorMessage(friendError, "Failed to send friend request. Please try again."));
    } finally {
      setFriendRequestingUserId(null);
    }
  }

  async function handleSendRecommendedFriendRequest(
    traveler: RecommendedTraveler
  ): Promise<void> {
    if (friendRequestingUserId) return;

    setFriendRequestingUserId(traveler.user_id);
    try {
      await sendFriendRequest(traveler.user_id);
      setRecommendedFriendRequested((current) => new Set(current).add(traveler.user_id));
    } catch (friendError) {
      window.alert(toErrorMessage(friendError, "Failed to send friend request. Please try again."));
    } finally {
      setFriendRequestingUserId(null);
    }
  }

  async function handleSendSearchUserFriendRequest(user: FriendSearchUser): Promise<void> {
    if (friendRequestingUserId) return;

    setFriendRequestingUserId(user.user_id);
    try {
      const friendship = await sendFriendRequest(user.user_id);
      setUserResults((current) =>
        current.map((item) =>
          item.user_id === user.user_id
            ? {
                ...item,
                friendship_status: friendship.status,
                is_requester: friendship.is_requester,
              }
            : item
        )
      );
    } catch (friendError) {
      window.alert(toErrorMessage(friendError, "Failed to send friend request. Please try again."));
    } finally {
      setFriendRequestingUserId(null);
    }
  }

  async function handleStartSearchUserChat(user: FriendSearchUser): Promise<void> {
    if (chatOpeningPostId) return;

    setChatOpeningPostId(user.user_id);
    try {
      const room = await createDirectChatRoom(user.user_id);
      navigate(`/chat/${room.chat_room_id}`);
    } catch (chatError) {
      window.alert(toErrorMessage(chatError, "Failed to open chat. Please try again."));
    } finally {
      setChatOpeningPostId(null);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (imageUploading) {
      window.alert("Please wait until the image upload is complete.");
      return;
    }

    if (
      !form.title.trim() ||
      !form.content.trim() ||
      !form.region.trim() ||
      !form.travel_start_date ||
      !form.travel_end_date
    ) {
      window.alert("Please fill in all required fields.");
      return;
    }

    if (form.content.trim().length < 10) {
      window.alert("Please enter at least 10 characters in the intro.");
      return;
    }

    setSubmitting(true);

    try {
      const payload = {
        ...form,
        preferred_age_min: Number(form.preferred_age_min),
        preferred_age_max: Number(form.preferred_age_max),
        image_urls: imageUrls.length > 0 ? imageUrls : null,
      };

      if (editingPostId) {
        const updatedPost = await updateTripMatePost(editingPostId, payload);
        setPosts((current) =>
          current.map((post) => (post.post_id === editingPostId ? updatedPost : post))
        );
      } else {
        await createTripMatePost(payload);
        await deleteDraft();
        await fetchPosts();
      }

      resetEditor();
      setTab("list");
    } catch (error: unknown) {
      const apiError = error as { response?: { status?: number }; message?: string };
      const status = apiError.response?.status ?? "Network Error";
      const message = toErrorMessage(error, "Please try again.");

      window.alert(`${editingPostId ? "Update" : "Create"} failed (${status})\n${message}`);
    } finally {
      setSubmitting(false);
    }
  }

  function handleStartEdit(post: TripMatePost): void {
    setEditingPostId(post.post_id);
    setForm({
      title: post.title,
      content: post.content,
      region: post.region,
      travel_start_date: post.travel_start_date,
      travel_end_date: post.travel_end_date,
      companion_type: post.companion_type,
      preferred_gender: post.preferred_gender,
      preferred_age_min: post.preferred_age_min,
      preferred_age_max: post.preferred_age_max,
    });
    setImageUrls(post.image_urls ?? []);
    setImagePreviews(post.image_urls ?? []);
    setMenuOpenPostId(null);
    setTab("write");
  }

  async function handleDeletePost(post: TripMatePost): Promise<void> {
    setMenuOpenPostId(null);
    if (!window.confirm(`Delete "${post.title}"?`)) return;

    try {
      await deleteTripMatePost(post.post_id);
      setPosts((current) => current.filter((item) => item.post_id !== post.post_id));
    } catch {
      window.alert("Failed to delete the post.");
    }
  }

  async function handleStartChat(post: TripMatePost): Promise<void> {
    if (chatOpeningPostId) return;

    setChatOpeningPostId(post.post_id);
    try {
      const room = await createDirectChatRoom(post.user_id);
      navigate(`/chat/${room.chat_room_id}`);
    } catch (chatError) {
      window.alert(toErrorMessage(chatError, "Failed to open chat. Please try again."));
    } finally {
      setChatOpeningPostId(null);
    }
  }

  async function handleStartRecommendedChat(traveler: RecommendedTraveler): Promise<void> {
    if (chatOpeningPostId) return;

    setChatOpeningPostId(traveler.user_id);
    try {
      const room = await createDirectChatRoom(traveler.user_id);
      setSelectedRecommendedTraveler(null);
      navigate(`/chat/${room.chat_room_id}`);
    } catch (chatError) {
      window.alert(toErrorMessage(chatError, "Failed to open chat. Please try again."));
    } finally {
      setChatOpeningPostId(null);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        <header style={styles.header}>
          <div>
            <p style={styles.eyebrow}>Trip Mate</p>
            <h1 style={styles.headerTitle}>Find Travel Companions</h1>
            <p style={styles.headerCopy}>
              Meet people planning similar routes, dates, and travel styles around Seoul.
            </p>
          </div>
          <div style={styles.headerActions}>
            <NotificationBell />
            <button
              type="button"
              style={styles.headerButton}
              onClick={() => handleTabChange(tab === "list" ? "write" : "list")}
            >
              {tab === "list" ? "Write Post" : "View Posts"}
            </button>
          </div>
        </header>

        <section style={styles.tabPanel}>
          {(["list", "write"] as const).map((item) => (
            <button
              key={item}
              type="button"
              style={{
                ...styles.tabButton,
                ...(tab === item ? styles.tabButtonActive : {}),
              }}
              onClick={() => handleTabChange(item)}
            >
              {item === "list" ? "Browse" : editingPostId ? "Edit Post" : "New Post"}
            </button>
          ))}
        </section>

        {tab === "list" ? (
          <>
            <section style={styles.searchPanel}>
              <div style={styles.searchRow}>
                <label style={styles.searchWrap}>
                  <SearchIcon />
                  <input
                    ref={searchRef}
                    value={searchInput}
                    onChange={(event) => {
                      setSearchInput(event.target.value);
                      setShowHistory(true);
                    }}
                    onFocus={() => {
                      setShowHistory(true);
                      void loadSearchHistory();
                    }}
                    onBlur={() => window.setTimeout(() => setShowHistory(false), 220)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        handleSearch(searchInput);
                      }
                    }}
                    placeholder="Search by region or keyword"
                    style={styles.searchInput}
                  />
                </label>
                <button
                  type="button"
                  style={styles.searchAction}
                  onMouseDown={() => handleSearch(searchInput)}
                >
                  Search
                </button>
              </div>

              {hasSearchSuggestions ? (
                <div style={styles.historyPanel}>
                  <div style={styles.historyHeader}>
                    <span style={styles.historyTitle}>
                      {searchInput.trim() ? "Suggestions" : "Recent Searches"}
                    </span>
                    {visibleSearchHistory.length > 0 ? (
                      <button
                        type="button"
                        style={styles.linkButton}
                        onMouseDown={() => void handleClearSearchHistory()}
                      >
                        Clear
                      </button>
                    ) : null}
                  </div>
                  {suggestionLoading ? (
                    <p style={styles.suggestionHint}>Searching users...</p>
                  ) : null}
                  {suggestedUsers.length > 0 ? (
                    <div style={styles.historyList}>
                      {suggestedUsers.map((user) => (
                        <button
                          key={user.user_id}
                          type="button"
                          style={styles.suggestionUserItem}
                          onMouseDown={() => handleSearch(user.user_name)}
                        >
                          <img
                            src={user.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
                            alt=""
                            style={styles.suggestionAvatar}
                          />
                          <span style={styles.suggestionUserText}>
                            <strong style={styles.suggestionName}>{user.user_name}</strong>
                            <span style={styles.suggestionMeta}>{user.user_id}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <div style={styles.historyList}>
                    {visibleSearchHistory.map((term) => (
                      <div key={term} style={styles.historyItem}>
                        <button
                          type="button"
                          style={styles.historyTerm}
                          onMouseDown={() => handleSearch(term)}
                        >
                          {term}
                        </button>
                        <button
                          type="button"
                          style={styles.iconButton}
                          onMouseDown={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            void handleDeleteSearchHistory(term);
                          }}
                          aria-label={`Delete ${term}`}
                        >
                          x
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>

            {searchQuery ? (
              <section style={styles.userSearchPanel}>
                <div style={styles.userSearchHeader}>
                  <div>
                    <p style={styles.recommendationEyebrow}>Users</p>
                    <h2 style={styles.recommendationTitle}>People matching "{searchQuery}"</h2>
                  </div>
                  {userSearchLoading ? (
                    <span style={styles.userSearchStatus}>Searching...</span>
                  ) : null}
                </div>

                {userSearchError ? (
                  <p style={styles.userSearchError}>{userSearchError}</p>
                ) : userSearchLoading && userResults.length === 0 ? (
                  <div style={styles.loadingState}>
                    <span style={styles.spinner} />
                    <p style={styles.emptyCopy}>Searching users...</p>
                  </div>
                ) : userResults.length === 0 ? (
                  <p style={styles.recommendationEmpty}>No users found.</p>
                ) : (
                  <div style={styles.userResultList}>
                    {userResults.map((user) => (
                      <UserSearchCard
                        key={user.user_id}
                        user={user}
                        busy={
                          friendRequestingUserId === user.user_id ||
                          chatOpeningPostId === user.user_id
                        }
                        onSendRequest={() => void handleSendSearchUserFriendRequest(user)}
                        onChat={() => void handleStartSearchUserChat(user)}
                        onViewFeed={() => setFeedPopupUserId(user.user_id)}
                      />
                    ))}
                  </div>
                )}

                {userNextCursor ? (
                  <button
                    type="button"
                    style={styles.loadMoreButton}
                    onClick={() => void fetchUsers(searchQuery, userNextCursor)}
                    disabled={userSearchLoading}
                  >
                    {userSearchLoading ? "Loading..." : "Load More Users"}
                  </button>
                ) : null}
              </section>
            ) : null}

            <section style={styles.recommendationPanel}>
              <div style={styles.recommendationHeader}>
                <div>
                  <p style={styles.recommendationEyebrow}>Recommended</p>
                  <h2 style={styles.recommendationTitle}>Travelers for you</h2>
                </div>
                <span style={styles.recommendationSource}>
                  {recommendationSourceTags.length
                    ? recommendationSourceTags.slice(0, 4).join(" / ")
                    : "No preferences yet"}
                </span>
              </div>

              <div style={styles.recommendationList}>
                {mateRecommendations.length > 0 ? (
                  mateRecommendations.map((recommendation) => (
                    <button
                      key={recommendation.user_id}
                      type="button"
                      style={styles.recommendationItem}
                      onClick={() => setSelectedRecommendedTraveler(recommendation)}
                    >
                      {recommendation.profile_image_url ? (
                        <img
                          src={recommendation.profile_image_url}
                          alt={recommendation.user_name}
                          style={styles.recommendationPhoto}
                        />
                      ) : (
                        <img
                          src={DEFAULT_PROFILE_IMAGE_URL}
                          alt=""
                          style={styles.recommendationPhoto}
                        />
                      )}
                      <span style={styles.recommendationText}>
                        <strong style={styles.recommendationName}>
                          {recommendation.user_name}
                        </strong>
                        <span style={styles.recommendationScore}>
                          {(recommendation.similarity_score * 100).toFixed(0)}%
                        </span>
                      </span>
                    </button>
                  ))
                ) : (
                  <p style={styles.recommendationEmpty}>No recommended travelers yet.</p>
                )}
              </div>
            </section>

            <section style={styles.filtersSection}>
              <div style={styles.filterGroup}>
                {COMPANION_FILTERS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    style={{
                      ...styles.filterChip,
                      ...(filter === item ? styles.filterChipActive : {}),
                    }}
                    onClick={() => setFilter(item)}
                  >
                    {COMPANION_LABELS[item]}
                  </button>
                ))}
              </div>
            </section>

            <section style={styles.listSection}>
              {errorMessage ? (
                <div style={styles.emptyState}>
                  <p style={styles.emptyTitle}>{errorMessage}</p>
                  <p style={styles.emptyCopy}>Try refreshing the list in a moment.</p>
                </div>
              ) : loading && posts.length === 0 ? (
                <div style={styles.loadingState}>
                  <span style={styles.spinner} />
                  <p style={styles.emptyCopy}>Loading mate posts...</p>
                </div>
              ) : filteredPosts.length === 0 ? (
                <div style={styles.emptyState}>
                  <p style={styles.emptyTitle}>
                    {searchQuery ? `No results for "${searchQuery}".` : "No mate posts yet."}
                  </p>
                  <p style={styles.emptyCopy}>
                    Create the first post and help others find a travel companion.
                  </p>
                </div>
              ) : (
                filteredPosts.map((post) => (
                  <article
                    key={post.post_id}
                    className="interactive-card"
                    style={styles.card}
                    onClick={() => {
                      if (menuOpenPostId === post.post_id) {
                        setMenuOpenPostId(null);
                        return;
                      }
                      setSelectedPost(post);
                    }}
                  >
                    <div style={styles.cardHeader}>
                      <div style={styles.authorBlock}>
                        <AuthorAvatar post={post} />
                        <div>
                          <p style={styles.authorName}>{post.author.user_name}</p>
                          <p style={styles.authorMeta}>
                            {[post.author.nationality, post.author.age, GENDER_LABELS[post.author.gender]]
                              .filter(Boolean)
                              .join(" / ")}
                          </p>
                        </div>
                      </div>

                      <div style={styles.cardActions}>
                        <span style={styles.typeBadge}>{COMPANION_LABELS[post.companion_type]}</span>
                        {currentUserId && post.user_id === currentUserId ? (
                          <button
                            type="button"
                            style={styles.moreButton}
                            onClick={(event) => {
                              event.stopPropagation();
                              setMenuOpenPostId(
                                menuOpenPostId === post.post_id ? null : post.post_id
                              );
                            }}
                            aria-label={`Open options for ${post.title}`}
                          >
                            ...
                          </button>
                        ) : null}
                      </div>
                    </div>

                    {menuOpenPostId === post.post_id ? (
                      <div style={styles.postMenu}>
                        <button
                          type="button"
                          style={styles.menuButton}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleStartEdit(post);
                          }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          style={{ ...styles.menuButton, ...styles.dangerText }}
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleDeletePost(post);
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    ) : null}

                    <div style={styles.cardBody}>
                      <h2 style={styles.cardTitle}>{post.title}</h2>
                      <p style={styles.cardDescription}>{post.content}</p>
                    </div>

                    {post.image_urls?.length ? (
                      <div style={styles.imageStrip}>
                        {post.image_urls.slice(0, 3).map((url, index) => (
                          <button
                            key={`${url}-${index}`}
                            type="button"
                            style={styles.postImageWrap}
                            onClick={(event) => {
                              event.stopPropagation();
                              setExpandedImage(url);
                            }}
                          >
                            <img src={url} alt="" style={styles.postImage} />
                            {index === 2 && post.image_urls.length > 3 ? (
                              <div style={styles.imageCount}>+{post.image_urls.length - 3}</div>
                            ) : null}
                          </button>
                        ))}
                      </div>
                    ) : null}

                    <div style={styles.metaGrid}>
                      <span style={styles.metaChip}>{post.region}</span>
                      <span style={styles.metaChip}>
                        {post.travel_start_date} - {post.travel_end_date}
                      </span>
                      <span style={styles.metaChip}>
                        Ages {post.preferred_age_min}-{post.preferred_age_max}
                      </span>
                      <span style={styles.metaChip}>{GENDER_LABELS[post.preferred_gender]}</span>
                    </div>

                    <div style={styles.cardFooter}>
                      <button
                        type="button"
                        style={{
                          ...styles.likeButton,
                          ...(post.is_liked ? styles.likeButtonActive : {}),
                        }}
                        onClick={(event) => void handleLike(event, post)}
                      >
                        {post.is_liked ? "Liked" : "Like"} {post.like_count}
                      </button>
                      <span style={styles.createdText}>
                        {new Date(post.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </article>
                ))
              )}

              {nextCursor ? (
                <button
                  type="button"
                  style={styles.loadMoreButton}
                  onClick={() => void fetchPosts(nextCursor)}
                  disabled={loading}
                >
                  {loading ? "Loading..." : "Load More"}
                </button>
              ) : null}
            </section>
          </>
        ) : (
          <section style={styles.formPanel}>
            {editingPostId ? (
              <div style={styles.editBanner}>
                <span>Editing this mate post</span>
                <button
                  type="button"
                  style={styles.linkButton}
                  onClick={() => {
                    resetEditor();
                    setTab("list");
                  }}
                >
                  Cancel
                </button>
              </div>
            ) : null}

            {draftStatus ? <p style={styles.saveHint}>{draftStatus}</p> : null}

            <div style={styles.formGrid}>
              <Field label="Title" required>
                <input
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                  maxLength={100}
                  placeholder="Who wants to explore Seoul together?"
                  style={styles.input}
                />
              </Field>

              <Field label="Region" required>
                <input
                  value={form.region}
                  onChange={(event) => setForm({ ...form, region: event.target.value })}
                  maxLength={100}
                  placeholder="Hongdae, Jongno, Gangnam..."
                  style={styles.input}
                />
              </Field>

              <div style={styles.twoColumn}>
                <Field label="Start Date" required>
                  <input
                    type="date"
                    value={form.travel_start_date}
                    onChange={(event) =>
                      setForm({ ...form, travel_start_date: event.target.value })
                    }
                    style={styles.input}
                  />
                </Field>
                <Field label="End Date" required>
                  <input
                    type="date"
                    value={form.travel_end_date}
                    onChange={(event) =>
                      setForm({ ...form, travel_end_date: event.target.value })
                    }
                    style={styles.input}
                  />
                </Field>
              </div>

              <Field label="Companion Type">
                <div style={styles.optionGrid}>
                  {COMPANION_OPTIONS.map((item) => (
                    <button
                      key={item}
                      type="button"
                      style={{
                        ...styles.optionButton,
                        ...(form.companion_type === item ? styles.optionButtonActive : {}),
                      }}
                      onClick={() => setForm({ ...form, companion_type: item })}
                    >
                      {COMPANION_LABELS[item]}
                    </button>
                  ))}
                </div>
              </Field>

              <div style={styles.twoColumn}>
                <Field label="Min Age">
                  <input
                    type="number"
                    min={18}
                    max={99}
                    value={form.preferred_age_min}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        preferred_age_min: Number(event.target.value),
                      })
                    }
                    onBlur={() =>
                      setForm((current) => ({
                        ...current,
                        preferred_age_min: Math.max(
                          18,
                          Math.min(current.preferred_age_min, current.preferred_age_max)
                        ),
                      }))
                    }
                    style={styles.input}
                  />
                </Field>
                <Field label="Max Age">
                  <input
                    type="number"
                    min={18}
                    max={99}
                    value={form.preferred_age_max}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        preferred_age_max: Number(event.target.value),
                      })
                    }
                    onBlur={() =>
                      setForm((current) => ({
                        ...current,
                        preferred_age_max: Math.max(
                          current.preferred_age_min,
                          Math.min(current.preferred_age_max, 99)
                        ),
                      }))
                    }
                    style={styles.input}
                  />
                </Field>
              </div>

              <Field label="Preferred Gender">
                <div style={styles.optionGrid}>
                  {GENDER_OPTIONS.map((item) => (
                    <button
                      key={item}
                      type="button"
                      style={{
                        ...styles.optionButton,
                        ...(form.preferred_gender === item ? styles.optionButtonActive : {}),
                      }}
                      onClick={() => setForm({ ...form, preferred_gender: item })}
                    >
                      {GENDER_LABELS[item]}
                    </button>
                  ))}
                </div>
              </Field>

              <Field label="Intro" required>
                <textarea
                  value={form.content}
                  onChange={(event) => setForm({ ...form, content: event.target.value })}
                  rows={5}
                  maxLength={500}
                  placeholder="Share your itinerary, pace, and what kind of travel mate you are looking for."
                  style={{ ...styles.input, ...styles.textarea }}
                />
                <p style={styles.counterText}>{form.content.length}/500</p>
              </Field>

              <Field label={`Photos (${imageUrls.length}/10)`}>
                <div style={styles.photoGrid}>
                  {imagePreviews.map((src, index) => (
                    <div key={`${src}-${index}`} style={styles.photoPreview}>
                      <img src={src} alt="" style={styles.photoImage} />
                      {imageUploading && index >= imageUrls.length ? (
                        <div style={styles.uploadOverlay}>
                          <span style={styles.smallSpinner} />
                        </div>
                      ) : null}
                      {!imageUploading ? (
                        <button
                          type="button"
                          style={styles.removePhotoButton}
                          onClick={() => handleImageRemove(index)}
                          aria-label="Remove photo"
                        >
                          x
                        </button>
                      ) : null}
                    </div>
                  ))}

                  {imageUrls.length < 10 && !imageUploading ? (
                    <button
                      type="button"
                      style={styles.addPhotoButton}
                      onClick={() => imageInputRef.current?.click()}
                    >
                      Add Photo
                    </button>
                  ) : null}
                </div>
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  multiple
                  onChange={(event) => void handleImageSelect(event)}
                  style={styles.hiddenInput}
                />
              </Field>

              <div style={styles.formActions}>
                {!editingPostId ? (
                  <button
                    type="button"
                    style={styles.secondaryButton}
                    onClick={() => void handleAutoSaveDraft()}
                    disabled={draftSaving || imageUploading}
                  >
                    {draftSaving ? "Saving..." : "Save Draft"}
                  </button>
                ) : null}
                <button
                  type="button"
                  style={styles.primaryButton}
                  onClick={() => void handleSubmit()}
                  disabled={submitting || imageUploading}
                >
                  {imageUploading
                    ? "Uploading..."
                    : submitting
                    ? editingPostId
                      ? "Updating..."
                      : "Posting..."
                    : editingPostId
                      ? "Update Post"
                      : "Publish Post"}
                </button>
              </div>
            </div>
          </section>
        )}
      </div>

      {selectedPost ? (
        <PostModal
          post={selectedPost}
          friendRequested={friendRequested.has(selectedPost.post_id)}
          friendState={friendStates[selectedPost.user_id]}
          isOwnPost={selectedPost.user_id === currentUserId}
          isSendingFriendRequest={friendRequestingUserId === selectedPost.user_id}
          onClose={() => setSelectedPost(null)}
          onImageClick={(url) => setExpandedImage(url)}
          onToggleFriend={() => void handleSendFriendRequest(selectedPost)}
          onEdit={() => {
            handleStartEdit(selectedPost);
            setSelectedPost(null);
          }}
          onViewProfile={() => {
            setFeedPopupUserId(selectedPost.user_id);
            setSelectedPost(null);
          }}
          onChat={() => {
            void handleStartChat(selectedPost);
            setSelectedPost(null);
          }}
        />
      ) : null}

      {selectedRecommendedTraveler ? (
        <RecommendedTravelerModal
          traveler={selectedRecommendedTraveler}
          friendRequested={recommendedFriendRequested.has(
            selectedRecommendedTraveler.user_id
          )}
          isSendingFriendRequest={
            friendRequestingUserId === selectedRecommendedTraveler.user_id
          }
          isOpeningChat={chatOpeningPostId === selectedRecommendedTraveler.user_id}
          onClose={() => setSelectedRecommendedTraveler(null)}
          onAddFriend={() =>
            void handleSendRecommendedFriendRequest(selectedRecommendedTraveler)
          }
          onChat={() => void handleStartRecommendedChat(selectedRecommendedTraveler)}
          onViewFeed={() => setFeedPopupUserId(selectedRecommendedTraveler.user_id)}
        />
      ) : null}

      {feedPopupUserId ? (
        <FeedPopup
          key={feedPopupUserId}
          userId={feedPopupUserId}
          onClose={() => setFeedPopupUserId(null)}
        />
      ) : null}

      {expandedImage ? (
        <ImageLightbox src={expandedImage} onClose={() => setExpandedImage(null)} />
      ) : null}

      {menuOpenPostId !== null ? (
        <div style={styles.menuBackdrop} onClick={() => setMenuOpenPostId(null)} />
      ) : null}

    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label style={styles.field}>
      <span style={styles.fieldLabel}>
        {label}
        {required ? <span style={styles.required}> *</span> : null}
      </span>
      {children}
    </label>
  );
}

function AuthorAvatar({
  post,
  size = "default",
}: {
  post: TripMatePost;
  size?: "default" | "large";
}) {
  const avatarStyle =
    size === "large" ? { ...styles.avatar, ...styles.largeAvatar } : styles.avatar;

  return (
    <div style={avatarStyle}>
      {post.profile_image_url ? (
        <img src={post.profile_image_url} alt="" style={styles.avatarImage} />
      ) : (
        <img src={DEFAULT_PROFILE_IMAGE_URL} alt="" style={styles.avatarImage} />
      )}
    </div>
  );
}

function UserSearchCard({
  user,
  busy,
  onSendRequest,
  onChat,
  onViewFeed,
}: {
  user: FriendSearchUser;
  busy: boolean;
  onSendRequest: () => void;
  onChat: () => void;
  onViewFeed: () => void;
}) {
  const isFriend = user.friendship_status === "accepted";
  const hasPendingRequest = user.friendship_status === "pending";
  const canSendRequest = !user.i_blocked_peer && !isFriend && !hasPendingRequest;

  return (
    <div style={styles.userResultCard}>
      <div style={styles.userResultSummary}>
        <img
          src={user.profile_image_url || DEFAULT_PROFILE_IMAGE_URL}
          alt={user.user_name}
          style={styles.userResultAvatar}
        />
        <div style={styles.userResultText}>
          <strong style={styles.userResultName}>{user.user_name}</strong>
          <span style={styles.userResultMeta}>{user.nationality || "Unknown"}</span>
          <span style={styles.userResultStyles}>
            {user.travel_styles.length > 0 ? user.travel_styles.join(" / ") : "No styles"}
          </span>
          <span style={styles.userResultId}>{user.user_id}</span>
        </div>
      </div>
      <div style={styles.userResultActions}>
        {isFriend ? (
          <button type="button" style={styles.secondaryButton} onClick={onChat} disabled={busy}>
            {busy ? "Opening..." : "Chat"}
          </button>
        ) : (
          <button
            type="button"
            style={canSendRequest ? styles.primaryButton : styles.secondaryButton}
            onClick={onSendRequest}
            disabled={!canSendRequest || busy}
          >
            {busy
              ? "Sending..."
              : hasPendingRequest
                ? user.is_requester
                  ? "Request Sent"
                  : "Pending"
                : user.i_blocked_peer
                  ? "Blocked"
                  : "Add Friend"}
          </button>
        )}
        <button type="button" style={styles.secondaryButton} onClick={onViewFeed}>
          Feed
        </button>
      </div>
    </div>
  );
}

function RecommendedTravelerModal({
  traveler,
  friendRequested,
  isSendingFriendRequest,
  isOpeningChat,
  onClose,
  onAddFriend,
  onChat,
  onViewFeed,
}: {
  traveler: RecommendedTraveler;
  friendRequested: boolean;
  isSendingFriendRequest: boolean;
  isOpeningChat: boolean;
  onClose: () => void;
  onAddFriend: () => void;
  onChat: () => void;
  onViewFeed: () => void;
}) {
  const profileEntries = Object.entries(traveler).filter(
    ([key]) => key !== "similarity_score" && key !== "profile_image_url"
  );

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={styles.recommendedModalCard} onClick={(event) => event.stopPropagation()}>
        <div style={styles.recommendedModalHeader}>
          {traveler.profile_image_url ? (
            <img
              src={traveler.profile_image_url}
              alt={traveler.user_name}
              style={styles.recommendedModalPhoto}
            />
          ) : (
            <img
              src={DEFAULT_PROFILE_IMAGE_URL}
              alt=""
              style={styles.recommendedModalPhoto}
            />
          )}
          <div style={styles.recommendedModalTitleBlock}>
            <p style={styles.recommendationEyebrow}>Recommended Traveler</p>
            <h2 style={styles.recommendedModalTitle}>{traveler.user_name}</h2>
            <p style={styles.recommendedModalScore}>
              Match {(traveler.similarity_score * 100).toFixed(0)}%
            </p>
          </div>
          <button type="button" style={styles.modalCloseButton} onClick={onClose}>
            x
          </button>
        </div>

        <div style={styles.recommendedInfoGrid}>
          {profileEntries.map(([key, value]) => (
            <div key={key} style={styles.recommendedInfoItem}>
              <span style={styles.recommendedInfoLabel}>{formatProfileKey(key)}</span>
              <span style={styles.recommendedInfoValue}>{formatProfileValue(value)}</span>
            </div>
          ))}
        </div>

        <div style={styles.modalButtonGrid}>
          <button
            type="button"
            style={friendRequested ? styles.secondaryButton : styles.primaryButton}
            onClick={onAddFriend}
            disabled={friendRequested || isSendingFriendRequest}
          >
            {isSendingFriendRequest
              ? "Sending..."
              : friendRequested
                ? "Request Sent"
                : "Add Friend"}
          </button>
          <button
            type="button"
            style={styles.secondaryButton}
            onClick={onChat}
            disabled={isOpeningChat}
          >
            {isOpeningChat ? "Opening..." : "Chat"}
          </button>
          <button type="button" style={styles.secondaryButton} onClick={onViewFeed}>
            Feed
          </button>
        </div>
      </div>
    </div>
  );
}

function PostModal({
  post,
  friendRequested,
  friendState,
  isOwnPost,
  isSendingFriendRequest,
  onClose,
  onImageClick,
  onToggleFriend,
  onEdit,
  onViewProfile,
  onChat,
}: {
  post: TripMatePost;
  friendRequested: boolean;
  friendState?: MateFriendState;
  isOwnPost: boolean;
  isSendingFriendRequest: boolean;
  onClose: () => void;
  onImageClick: (url: string) => void;
  onToggleFriend: () => void;
  onEdit: () => void;
  onViewProfile: () => void;
  onChat: () => void;
}) {
  const isFriend = friendState?.friendship_status === "accepted";
  const hasPendingRequest = friendRequested || friendState?.friendship_status === "pending";
  const canAddFriend = !isOwnPost && !isFriend && !friendState?.i_blocked_peer;

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={styles.modalCard} onClick={(event) => event.stopPropagation()}>
        <div style={styles.modalHero}>
          <div style={styles.modalHeroTop}>
            <span style={styles.modalCategory}>{COMPANION_LABELS[post.companion_type]}</span>
            <button type="button" style={styles.modalCloseButton} onClick={onClose}>
              x
            </button>
          </div>
          <div>
            <h2 style={styles.modalTitle}>{post.title}</h2>
            <p style={styles.modalDistance}>
              {post.region} / {post.travel_start_date} - {post.travel_end_date}
            </p>
          </div>
        </div>

        <div style={styles.modalBody}>
          <div style={styles.authorBlock}>
            <AuthorAvatar post={post} size="large" />
            <div>
              <p style={styles.authorName}>{post.author.user_name}</p>
              <p style={styles.authorMeta}>
                {[post.author.nationality, post.author.age, GENDER_LABELS[post.author.gender]]
                  .filter(Boolean)
                  .join(" / ")}
              </p>
            </div>
          </div>

          <p style={styles.modalDescription}>{post.content}</p>

          <div style={styles.metaGrid}>
            <span style={styles.metaChip}>{COMPANION_LABELS[post.companion_type]}</span>
            <span style={styles.metaChip}>
              Ages {post.preferred_age_min}-{post.preferred_age_max}
            </span>
            <span style={styles.metaChip}>{GENDER_LABELS[post.preferred_gender]}</span>
          </div>

          {post.image_urls?.length ? (
            <div style={styles.modalImages}>
              {post.image_urls.map((url, index) => (
                <button
                  key={`${url}-${index}`}
                  type="button"
                  style={styles.modalImageButton}
                  onClick={() => onImageClick(url)}
                >
                  <img src={url} alt="" style={styles.modalImage} />
                </button>
              ))}
            </div>
          ) : null}

          <div style={styles.modalButtonGrid}>
            {isOwnPost ? (
              <button type="button" style={styles.primaryButton} onClick={onEdit}>
                Edit Post
              </button>
            ) : null}
            {canAddFriend ? (
              <button
                type="button"
                style={hasPendingRequest ? styles.secondaryButton : styles.primaryButton}
                onClick={onToggleFriend}
                disabled={hasPendingRequest || isSendingFriendRequest}
              >
                {isSendingFriendRequest
                  ? "Sending..."
                  : hasPendingRequest
                    ? "Request Sent"
                    : "Add Friend"}
              </button>
            ) : null}
            <button type="button" style={styles.secondaryButton} onClick={onViewProfile}>
              View Feed
            </button>
            {!isOwnPost ? (
              <button type="button" style={styles.secondaryButton} onClick={onChat}>
                Chat
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatProfileKey(key: string): string {
  return key
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatProfileValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function getMatePreferenceTags(profile: {
  travel_styles?: string[];
  food_preferences?: string[];
  density_preference?: string;
  budget_preference?: string;
  walking_preference?: string;
  transport_preferences?: string[];
  companion_preference?: string;
  time_preferences?: string[];
  communication_preference?: string;
  planning_preference?: string;
}): string[] {
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
        .map((value) => formatPreferenceLabel(value))
    )
  );
}

function formatPreferenceLabel(value: string): string {
  const key = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
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

  return labelMap[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ImageLightbox({ src, onClose }: { src: string; onClose: () => void }) {
  return (
    <div style={styles.lightboxOverlay} onClick={onClose}>
      <button type="button" style={styles.lightboxClose} onClick={onClose}>
        x
      </button>
      <img src={src} alt="" style={styles.lightboxImage} onClick={(event) => event.stopPropagation()} />
    </div>
  );
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M10.5 18a7.5 7.5 0 1 1 5.303-12.803A7.5 7.5 0 0 1 10.5 18Zm0-13a5.5 5.5 0 1 0 0 11a5.5 5.5 0 0 0 0-11Zm10 15l-4.35-4.35"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function toErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as {
    response?: {
      data?:
        | {
            detail?: unknown;
            message?: unknown;
          }
        | string;
    };
    message?: string;
  };

  if (typeof apiError.response?.data === "string") {
    return apiError.response.data;
  }

  const detail = apiError.response?.data?.detail;
  const message = apiError.response?.data?.message;

  return stringifyApiMessage(detail) || stringifyApiMessage(message) || apiError.message || fallback;
}

function stringifyApiMessage(value: unknown): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const errorItem = item as {
            loc?: unknown[];
            msg?: string;
            type?: string;
            ctx?: { min_length?: number };
          };
          const location = Array.isArray(errorItem.loc) ? errorItem.loc.join(".") : "";
          const friendlyMessage = toFriendlyValidationMessage(errorItem);
          if (friendlyMessage) return friendlyMessage;
          return [location, errorItem.msg || errorItem.type].filter(Boolean).join(": ");
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }

  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }

  return String(value);
}

function dedupeSearchHistory(items: string[]): string[] {
  const seen = new Set<string>();
  const nextItems: string[] = [];

  items.forEach((item) => {
    const value = item.trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return;

    seen.add(key);
    nextItems.push(value);
  });

  return nextItems.slice(0, 10);
}

function toFriendlyValidationMessage(errorItem: {
  loc?: unknown[];
  msg?: string;
  type?: string;
  ctx?: { min_length?: number };
}): string {
  const location = Array.isArray(errorItem.loc) ? errorItem.loc.join(".") : "";
  const minLength = errorItem.ctx?.min_length;
  const isMinLengthError =
    errorItem.type === "string_too_short" ||
    /at least\s+\d+\s+characters/i.test(errorItem.msg ?? "");

  if (isMinLengthError && minLength === 10) {
    if (location.includes("content")) {
      return "Please enter at least 10 characters in the intro.";
    }

    return "Please enter at least 10 characters.";
  }

  return "";
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100dvh",
    padding: "24px 16px 40px",
    background: "transparent",
    fontFamily: "'Nunito', 'Apple SD Gothic Neo', sans-serif",
  },
  shell: {
    width: "100%",
    maxWidth: 760,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 18,
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 16,
    paddingTop: 8,
  },
  eyebrow: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 800,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
  },
  headerTitle: {
    margin: "6px 0 8px",
    fontSize: "clamp(1.9rem, 5vw, 2.4rem)",
    lineHeight: 1.05,
    color: "var(--text-primary)",
  },
  headerCopy: {
    maxWidth: 460,
    margin: 0,
    color: "var(--neutral-700)",
    fontSize: "0.95rem",
    lineHeight: 1.5,
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexShrink: 0,
  },
  headerButton: {
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 999,
    padding: "12px 16px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(5,181,187,0.22)",
    flexShrink: 0,
  },
  tabPanel: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 10,
    padding: 8,
    borderRadius: 22,
    background: "rgba(255,255,255,0.84)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  tabButton: {
    minHeight: 46,
    border: "none",
    borderRadius: 16,
    background: "transparent",
    color: "var(--neutral-700)",
    fontWeight: 800,
    cursor: "pointer",
  },
  tabButtonActive: {
    background: "linear-gradient(135deg, rgba(5,181,187,0.16), rgba(228,247,247,0.96))",
    color: "var(--text-primary)",
  },
  searchPanel: {
    position: "relative",
    padding: 20,
    borderRadius: 28,
    background:
      "linear-gradient(180deg, rgba(5,181,187,0.1), rgba(255,255,255,0.96) 44%)",
    border: "1px solid rgba(5,181,187,0.14)",
    boxShadow: "var(--shadow-soft)",
  },
  searchRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },
  searchWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    gap: 10,
    minHeight: 56,
    padding: "0 14px",
    borderRadius: 20,
    border: "1.5px solid rgba(5,181,187,0.16)",
    background: "rgba(255,255,255,0.92)",
    color: "var(--neutral-700)",
  },
  searchInput: {
    width: "100%",
    border: "none",
    outline: "none",
    background: "transparent",
    color: "var(--text-primary)",
    fontSize: "1rem",
  },
  searchAction: {
    minHeight: 54,
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 18,
    padding: "0 16px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
  },
  historyPanel: {
    position: "absolute",
    left: 20,
    right: 20,
    top: "calc(100% - 8px)",
    zIndex: 8,
    padding: 12,
    borderRadius: 20,
    background: "#ffffff",
    border: "1px solid var(--border-soft)",
    boxShadow: "0 18px 36px rgba(33,33,33,0.14)",
  },
  historyHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    marginBottom: 10,
  },
  historyTitle: {
    color: "var(--text-secondary)",
    fontSize: "0.82rem",
    fontWeight: 800,
  },
  historyList: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  suggestionHint: {
    margin: "0 0 10px",
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
    fontWeight: 800,
  },
  suggestionUserItem: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px",
    border: "none",
    borderRadius: 14,
    background: "rgba(5,181,187,0.08)",
    color: "var(--text-primary)",
    cursor: "pointer",
    textAlign: "left",
  },
  suggestionAvatar: {
    width: 34,
    height: 34,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  suggestionUserText: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  suggestionName: {
    color: "var(--text-primary)",
    fontSize: "0.9rem",
  },
  suggestionMeta: {
    color: "var(--neutral-700)",
    fontSize: "0.72rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  historyItem: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    padding: "10px 12px",
    borderRadius: 14,
    background: "var(--surface-muted)",
  },
  historyTerm: {
    border: "none",
    background: "transparent",
    color: "var(--text-primary)",
    fontWeight: 700,
    cursor: "pointer",
    padding: 0,
    textAlign: "left",
  },
  iconButton: {
    width: 28,
    height: 28,
    border: "none",
    borderRadius: "50%",
    background: "rgba(248,180,0,0.16)",
    color: "var(--text-secondary)",
    cursor: "pointer",
    fontWeight: 800,
  },
  linkButton: {
    border: "none",
    background: "transparent",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
    cursor: "pointer",
    padding: 0,
  },
  userSearchPanel: {
    padding: "14px 16px",
    borderRadius: 22,
    background: "rgba(255,255,255,0.82)",
    border: "1px solid rgba(248,180,0,0.16)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  userSearchHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 14,
  },
  userSearchStatus: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  userSearchError: {
    margin: 0,
    color: "#b91c1c",
    fontSize: "0.86rem",
    fontWeight: 800,
  },
  userResultList: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  userResultCard: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: 12,
    borderRadius: 18,
    background: "rgba(255,255,255,0.9)",
    border: "1px solid var(--border-soft)",
  },
  userResultSummary: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
    flex: 1,
  },
  userResultActions: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "flex-end",
    gap: 8,
  },
  userResultAvatar: {
    width: 48,
    height: 48,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  },
  userResultText: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 3,
  },
  userResultName: {
    color: "var(--text-primary)",
    fontSize: "0.95rem",
  },
  userResultMeta: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  userResultStyles: {
    color: "var(--neutral-700)",
    fontSize: "0.76rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  userResultId: {
    color: "var(--neutral-500)",
    fontSize: "0.7rem",
    overflowWrap: "anywhere",
  },
  filtersSection: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  filterGroup: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: 10,
  },
  filterChip: {
    border: "1px solid rgba(248,180,0,0.18)",
    borderRadius: 999,
    padding: "12px 18px",
    background: "rgba(255,255,255,0.86)",
    color: "var(--neutral-700)",
    fontWeight: 800,
    cursor: "pointer",
  },
  filterChipActive: {
    background: "linear-gradient(135deg, rgba(248,180,0,0.2), rgba(255,233,179,0.92))",
    color: "var(--text-primary)",
    boxShadow: "0 12px 24px rgba(248,180,0,0.14)",
  },
  recommendationPanel: {
    padding: "14px 16px",
    borderRadius: 22,
    background: "rgba(255,255,255,0.72)",
    border: "1px solid rgba(5,181,187,0.12)",
  },
  recommendationHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 14,
    marginBottom: 12,
  },
  recommendationEyebrow: {
    margin: 0,
    color: "var(--brand-primary-deep)",
    fontSize: "0.74rem",
    fontWeight: 800,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
  },
  recommendationTitle: {
    margin: "4px 0 0",
    color: "var(--text-primary)",
    fontSize: "1.1rem",
    lineHeight: 1.2,
  },
  recommendationSource: {
    maxWidth: 170,
    padding: "7px 10px",
    borderRadius: 999,
    background: "rgba(5,181,187,0.1)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.76rem",
    fontWeight: 800,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  recommendationLabel: {
    color: "var(--neutral-700)",
    fontSize: "0.76rem",
    fontWeight: 800,
  },
  recommendationSelect: {
    minHeight: 38,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 14,
    padding: "0 10px",
    background: "#ffffff",
    color: "var(--text-primary)",
    fontWeight: 800,
  },
  recommendationList: {
    display: "flex",
    gap: 10,
    overflowX: "auto",
    paddingBottom: 2,
  },
  recommendationItem: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 8,
    minWidth: 82,
    padding: "8px 6px",
    border: "none",
    background: "transparent",
    cursor: "pointer",
  },
  recommendationPhoto: {
    width: 62,
    height: 62,
    borderRadius: "50%",
    objectFit: "cover",
    border: "3px solid rgba(255,255,255,0.95)",
    boxShadow: "0 10px 22px rgba(5,181,187,0.16)",
  },
  recommendationPhotoFallback: {
    width: 62,
    height: 62,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    border: "3px solid rgba(255,255,255,0.95)",
    boxShadow: "0 10px 22px rgba(5,181,187,0.16)",
    fontWeight: 900,
  },
  recommendationText: {
    width: "100%",
    textAlign: "center",
  },
  recommendationName: {
    display: "block",
    color: "var(--text-primary)",
    fontSize: "0.84rem",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  recommendationScore: {
    margin: "2px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.7rem",
    fontWeight: 700,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  recommendationEmpty: {
    margin: 0,
    color: "var(--neutral-700)",
    fontSize: "0.86rem",
    fontWeight: 700,
  },
  listSection: {
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  card: {
    position: "relative",
    padding: 18,
    borderRadius: 28,
    background: "rgba(255,255,255,0.92)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
    cursor: "pointer",
  },
  cardHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  authorBlock: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    flexShrink: 0,
    background: "linear-gradient(135deg, var(--brand-primary), var(--brand-primary-deep))",
    color: "#ffffff",
    fontWeight: 800,
    overflow: "hidden",
  },
  avatarImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  largeAvatar: {
    width: 60,
    height: 60,
    fontSize: "1.25rem",
  },
  authorName: {
    margin: 0,
    color: "var(--text-primary)",
    fontWeight: 800,
  },
  authorMeta: {
    margin: "4px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
  },
  cardActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  typeBadge: {
    padding: "7px 10px",
    borderRadius: 999,
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    fontSize: "0.78rem",
    fontWeight: 800,
  },
  moreButton: {
    width: 34,
    height: 34,
    border: "1px solid rgba(5,181,187,0.14)",
    borderRadius: "50%",
    background: "rgba(255,255,255,0.9)",
    color: "var(--text-secondary)",
    fontWeight: 800,
    cursor: "pointer",
  },
  postMenu: {
    position: "absolute",
    right: 18,
    top: 58,
    zIndex: 12,
    display: "flex",
    flexDirection: "column",
    minWidth: 132,
    overflow: "hidden",
    borderRadius: 16,
    background: "#ffffff",
    border: "1px solid var(--border-soft)",
    boxShadow: "0 16px 34px rgba(33,33,33,0.16)",
  },
  menuButton: {
    border: "none",
    background: "transparent",
    padding: "12px 14px",
    color: "var(--text-secondary)",
    textAlign: "left",
    fontWeight: 700,
    cursor: "pointer",
  },
  dangerText: {
    color: "#dc2626",
  },
  cardBody: {
    marginTop: 16,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  cardTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.2rem",
    lineHeight: 1.2,
  },
  cardDescription: {
    margin: 0,
    color: "var(--neutral-700)",
    lineHeight: 1.55,
    fontSize: "0.94rem",
  },
  imageStrip: {
    display: "flex",
    gap: 8,
    marginTop: 14,
  },
  postImageWrap: {
    position: "relative",
    width: 72,
    height: 72,
    padding: 0,
    border: "none",
    borderRadius: 16,
    overflow: "hidden",
    background: "var(--surface-muted)",
    cursor: "zoom-in",
  },
  postImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  imageCount: {
    position: "absolute",
    inset: 0,
    display: "grid",
    placeItems: "center",
    background: "rgba(24,26,32,0.58)",
    color: "#ffffff",
    fontWeight: 800,
  },
  metaGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 14,
  },
  metaChip: {
    padding: "7px 10px",
    borderRadius: 999,
    background: "rgba(248,180,0,0.13)",
    color: "var(--text-secondary)",
    fontSize: "0.78rem",
    fontWeight: 700,
  },
  cardFooter: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    marginTop: 16,
  },
  likeButton: {
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 999,
    padding: "9px 13px",
    background: "rgba(255,255,255,0.9)",
    color: "var(--neutral-700)",
    fontWeight: 800,
    cursor: "pointer",
  },
  likeButtonActive: {
    borderColor: "rgba(248,180,0,0.26)",
    background: "var(--brand-secondary-soft)",
    color: "var(--text-primary)",
  },
  createdText: {
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
  },
  emptyState: {
    padding: "48px 20px",
    textAlign: "center",
    borderRadius: 28,
    background: "rgba(255,255,255,0.88)",
    color: "var(--neutral-700)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  loadingState: {
    minHeight: 180,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    borderRadius: 28,
    background: "rgba(255,255,255,0.88)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  emptyTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.05rem",
    fontWeight: 800,
  },
  emptyCopy: {
    margin: "8px 0 0",
    color: "var(--neutral-700)",
    lineHeight: 1.5,
  },
  spinner: {
    display: "block",
    width: 40,
    height: 40,
    borderRadius: "50%",
    border: "4px solid rgba(5,181,187,0.16)",
    borderTop: "4px solid var(--brand-primary)",
    animation: "spin 0.8s linear infinite",
  },
  smallSpinner: {
    display: "block",
    width: 22,
    height: 22,
    borderRadius: "50%",
    border: "3px solid rgba(255,255,255,0.5)",
    borderTop: "3px solid #ffffff",
    animation: "spin 0.8s linear infinite",
  },
  loadMoreButton: {
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 18,
    padding: "14px 16px",
    background: "rgba(255,255,255,0.88)",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "var(--shadow-soft)",
  },
  formPanel: {
    padding: 20,
    borderRadius: 28,
    background: "rgba(255,255,255,0.92)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-soft)",
  },
  editBanner: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    marginBottom: 14,
    borderRadius: 16,
    background: "var(--brand-secondary-soft)",
    color: "var(--text-secondary)",
    fontWeight: 800,
  },
  saveHint: {
    margin: "0 0 12px",
    color: "var(--neutral-700)",
    fontSize: "0.82rem",
    textAlign: "right",
  },
  formGrid: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  fieldLabel: {
    color: "var(--text-secondary)",
    fontSize: "0.9rem",
    fontWeight: 800,
  },
  required: {
    color: "#dc2626",
  },
  input: {
    width: "100%",
    minHeight: 48,
    border: "1px solid rgba(5,181,187,0.16)",
    borderRadius: 16,
    padding: "0 14px",
    background: "var(--surface-panel)",
    color: "var(--text-primary)",
    outline: "none",
  },
  textarea: {
    minHeight: 132,
    padding: 14,
    resize: "vertical",
    lineHeight: 1.55,
  },
  counterText: {
    margin: "-2px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.78rem",
    textAlign: "right",
  },
  twoColumn: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
  },
  optionGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
  },
  optionButton: {
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 999,
    padding: "10px 14px",
    background: "rgba(255,255,255,0.86)",
    color: "var(--neutral-700)",
    fontWeight: 700,
    cursor: "pointer",
  },
  optionButtonActive: {
    background: "linear-gradient(135deg, rgba(5,181,187,0.18), rgba(228,247,247,0.96))",
    color: "var(--text-primary)",
  },
  photoGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
  },
  photoPreview: {
    position: "relative",
    width: 86,
    height: 86,
    borderRadius: 18,
    overflow: "hidden",
    background: "var(--surface-muted)",
  },
  photoImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  uploadOverlay: {
    position: "absolute",
    inset: 0,
    display: "grid",
    placeItems: "center",
    background: "rgba(24,26,32,0.44)",
  },
  removePhotoButton: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 24,
    height: 24,
    border: "none",
    borderRadius: "50%",
    background: "rgba(24,26,32,0.66)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
  },
  addPhotoButton: {
    width: 86,
    height: 86,
    border: "2px dashed rgba(5,181,187,0.24)",
    borderRadius: 18,
    background: "rgba(228,247,247,0.36)",
    color: "var(--brand-primary-deep)",
    fontWeight: 800,
    cursor: "pointer",
  },
  hiddenInput: {
    display: "none",
  },
  formActions: {
    display: "flex",
    gap: 10,
    marginTop: 4,
  },
  primaryButton: {
    flex: 1,
    border: "1px solid rgba(5,181,187,0.2)",
    borderRadius: 18,
    padding: "14px 16px",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(5,181,187,0.22)",
  },
  secondaryButton: {
    flex: 1,
    border: "1px solid rgba(5,181,187,0.18)",
    borderRadius: 18,
    padding: "14px 16px",
    background: "rgba(255,255,255,0.88)",
    color: "var(--text-secondary)",
    fontWeight: 800,
    cursor: "pointer",
  },
  modalOverlay: {
    position: "fixed",
    inset: 0,
    zIndex: 30,
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "center",
    padding: "16px 16px 0",
    background: "rgba(24,26,32,0.42)",
    animation: "fadeInOverlay 220ms ease-out",
  },
  modalCard: {
    width: "100%",
    maxWidth: 760,
    maxHeight: "88dvh",
    overflowY: "auto",
    borderRadius: "32px 32px 0 0",
    background: "var(--surface-panel)",
    boxShadow: "0 28px 72px rgba(24,26,32,0.18)",
    animation: "slideUpModal 280ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  recommendedModalCard: {
    width: "100%",
    maxWidth: 760,
    maxHeight: "88dvh",
    overflowY: "auto",
    borderRadius: "30px 30px 0 0",
    background: "var(--surface-panel)",
    boxShadow: "0 28px 72px rgba(24,26,32,0.18)",
    padding: 20,
    display: "flex",
    flexDirection: "column",
    gap: 18,
    animation: "slideUpModal 280ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  recommendedModalHeader: {
    display: "flex",
    alignItems: "center",
    gap: 14,
  },
  recommendedModalPhoto: {
    width: 74,
    height: 74,
    borderRadius: "50%",
    objectFit: "cover",
    border: "3px solid rgba(255,255,255,0.95)",
    boxShadow: "0 14px 30px rgba(5,181,187,0.18)",
    flexShrink: 0,
  },
  recommendedModalPhotoFallback: {
    width: 74,
    height: 74,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    background: "linear-gradient(135deg, var(--brand-primary), #12c0c6)",
    color: "#ffffff",
    border: "3px solid rgba(255,255,255,0.95)",
    boxShadow: "0 14px 30px rgba(5,181,187,0.18)",
    fontWeight: 900,
    fontSize: "1.5rem",
    flexShrink: 0,
  },
  recommendedModalTitleBlock: {
    flex: 1,
    minWidth: 0,
  },
  recommendedModalTitle: {
    margin: "4px 0",
    color: "var(--text-primary)",
    fontSize: "1.45rem",
    lineHeight: 1.12,
  },
  recommendedModalScore: {
    margin: 0,
    color: "var(--neutral-700)",
    fontWeight: 800,
  },
  recommendedInfoGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 10,
  },
  recommendedInfoItem: {
    padding: 12,
    borderRadius: 16,
    background: "rgba(228,247,247,0.44)",
    border: "1px solid rgba(5,181,187,0.1)",
    minWidth: 0,
  },
  recommendedInfoLabel: {
    display: "block",
    marginBottom: 5,
    color: "var(--brand-primary-deep)",
    fontSize: "0.74rem",
    fontWeight: 900,
  },
  recommendedInfoValue: {
    display: "block",
    color: "var(--text-primary)",
    fontSize: "0.9rem",
    fontWeight: 700,
    overflowWrap: "anywhere",
    lineHeight: 1.35,
  },
  modalHero: {
    minHeight: 210,
    padding: 22,
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    borderRadius: "32px 32px 0 0",
    background: "linear-gradient(160deg, rgba(5,181,187,0.2), rgba(248,180,0,0.18))",
  },
  modalHeroTop: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  modalCategory: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.72)",
    color: "var(--text-secondary)",
    fontSize: "0.8rem",
    fontWeight: 800,
  },
  modalCloseButton: {
    width: 38,
    height: 38,
    border: "1px solid rgba(255,255,255,0.62)",
    borderRadius: "50%",
    background: "rgba(255,255,255,0.82)",
    color: "var(--text-secondary)",
    fontWeight: 800,
    cursor: "pointer",
  },
  modalTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "2rem",
    lineHeight: 1.05,
    fontWeight: 800,
  },
  modalDistance: {
    margin: "10px 0 0",
    color: "var(--text-secondary)",
    fontSize: "0.92rem",
  },
  modalBody: {
    padding: 22,
    display: "flex",
    flexDirection: "column",
    gap: 18,
  },
  modalDescription: {
    margin: 0,
    color: "var(--text-secondary)",
    lineHeight: 1.65,
  },
  modalImages: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(118px, 1fr))",
    gap: 10,
  },
  modalImage: {
    width: "100%",
    height: "100%",
    aspectRatio: "1 / 1",
    objectFit: "cover",
    background: "var(--surface-muted)",
  },
  modalImageButton: {
    width: "100%",
    aspectRatio: "1 / 1",
    padding: 0,
    border: "none",
    borderRadius: 18,
    overflow: "hidden",
    background: "var(--surface-muted)",
    cursor: "zoom-in",
  },
  modalButtonGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: 10,
  },
  lightboxOverlay: {
    position: "fixed",
    inset: 0,
    zIndex: 60,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 18,
    background: "rgba(8,12,16,0.82)",
    cursor: "zoom-out",
  },
  lightboxImage: {
    maxWidth: "min(100%, 980px)",
    maxHeight: "86dvh",
    objectFit: "contain",
    borderRadius: 20,
    boxShadow: "0 24px 80px rgba(0,0,0,0.36)",
  },
  lightboxClose: {
    position: "fixed",
    top: 18,
    right: 18,
    width: 42,
    height: 42,
    border: "1px solid rgba(255,255,255,0.32)",
    borderRadius: "50%",
    background: "rgba(255,255,255,0.92)",
    color: "var(--text-primary)",
    fontWeight: 800,
    cursor: "pointer",
  },
  chatSheet: {
    width: "100%",
    maxWidth: 760,
    borderRadius: "30px 30px 0 0",
    background: "var(--surface-panel)",
    boxShadow: "0 28px 72px rgba(24,26,32,0.18)",
    padding: "10px 18px 26px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    animation: "slideUpModal 280ms cubic-bezier(0.22, 1, 0.36, 1)",
  },
  sheetHandle: {
    width: 56,
    height: 6,
    borderRadius: 999,
    background: "rgba(5,181,187,0.24)",
    margin: "4px auto 6px",
  },
  sheetTitle: {
    margin: 0,
    color: "var(--text-primary)",
    fontSize: "1.1rem",
  },
  menuBackdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 10,
    background: "transparent",
  },
};
