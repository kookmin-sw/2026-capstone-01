import client from "./client";
import type { AxiosProgressEvent } from "axios";

const FEED_UPLOAD_TIMEOUT_MS = 60000;
const FEED_DELETE_TIMEOUT_MS = 30000;

export type FeedVisibility = "private" | "friends" | "public";

export interface FeedPost {
  post_id: string;
  user_id: string;
  visibility: FeedVisibility;
  caption: string | null;
  original_url: string;
  thumbnail_small_url: string;
  thumbnail_medium_url: string;
  like_count: number;
  comment_count: number;
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}

export interface FeedPostListResponse {
  posts: FeedPost[];
  next_cursor: string | null;
}

export interface FeedLikeUser {
  user_id: string;
  user_name: string;
  profile_image_url: string | null;
}

export interface FeedLikeUsersResponse {
  post_id: string;
  users: FeedLikeUser[];
}

export interface FeedComment {
  comment_id: string;
  post_id: string;
  user_id: string;
  user_name: string;
  profile_image_url: string | null;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface FeedCommentListResponse {
  comments: FeedComment[];
  next_cursor: string | null;
}

export interface FeedPopupResponse {
  user_id: string;
  user_name: string;
  nationality: string;
  travel_styles: string[];
  profile_image_url: string | null;
  status_message?: string | null;
  message?: string | null;
  feed: {
    items: FeedPost[];
  };
}

function cursorParams(cursor?: string): { cursor?: string } {
  return cursor ? { cursor } : {};
}

export async function createFeedPost({
  file,
  visibility = "public",
  caption,
  onUploadProgress,
}: {
  file: File;
  visibility?: FeedVisibility;
  caption?: string;
  onUploadProgress?: (progress: number) => void;
}): Promise<FeedPost> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("visibility", visibility);
  if (caption !== undefined) {
    formData.append("caption", caption);
  }

  const { data } = await client.post<FeedPost>("/api/feed/posts", formData, {
    timeout: FEED_UPLOAD_TIMEOUT_MS,
    onUploadProgress: (progressEvent: AxiosProgressEvent) => {
      const total = progressEvent.total ?? file.size;
      if (!total) return;

      const progress = Math.min(
        100,
        Math.max(0, Math.round((progressEvent.loaded / total) * 100))
      );
      onUploadProgress?.(progress);
    },
  });
  return normalizeFeedPost(data);
}

export async function getMyFeedPosts(cursor?: string): Promise<FeedPostListResponse> {
  const { data } = await client.get<FeedPostListResponse>("/api/feed/me", {
    params: cursorParams(cursor),
  });
  return {
    posts: Array.isArray(data.posts) ? data.posts.map(normalizeFeedPost) : [],
    next_cursor: data.next_cursor ?? null,
  };
}

export async function getUserFeedPosts(
  userId: string,
  cursor?: string
): Promise<FeedPostListResponse> {
  const { data } = await client.get<FeedPostListResponse>(
    `/api/feed/users/${encodeURIComponent(userId)}`,
    { params: cursorParams(cursor) }
  );
  return {
    posts: Array.isArray(data.posts) ? data.posts.map(normalizeFeedPost) : [],
    next_cursor: data.next_cursor ?? null,
  };
}

export async function getFeedPost(postId: string): Promise<FeedPost> {
  const { data } = await client.get<FeedPost>(
    `/api/feed/posts/${encodeURIComponent(postId)}`
  );
  return normalizeFeedPost(data);
}

export async function updateFeedPostVisibility(
  postId: string,
  visibility: FeedVisibility
): Promise<FeedPost> {
  const path = `/api/feed/posts/${encodeURIComponent(postId)}/visibility`;

  try {
    const { data } = await client.patch<FeedPost>(path, { visibility });
    return normalizeFeedPost(data);
  } catch (error) {
    const status = getApiStatus(error);
    if (status && ![400, 422, 500].includes(status)) {
      throw error;
    }

    const { data } = await client.patch<FeedPost>(path, null, {
      params: { visibility },
    });
    return normalizeFeedPost(data);
  }
}

export async function updateFeedPostCaption(
  postId: string,
  caption: string | null
): Promise<FeedPost> {
  const { data } = await client.patch<FeedPost>(
    `/api/feed/posts/${encodeURIComponent(postId)}/caption`,
    { caption }
  );
  return normalizeFeedPost(data);
}

export async function deleteFeedPost(postId: string): Promise<void> {
  await client.delete(`/api/feed/posts/${encodeURIComponent(postId)}`, {
    timeout: FEED_DELETE_TIMEOUT_MS,
  });
}

export async function likeFeedPost(
  postId: string
): Promise<{ post_id: string; like_count: number }> {
  const { data } = await client.post<{ post_id: string; like_count: number }>(
    `/api/feed/posts/${encodeURIComponent(postId)}/like`
  );
  return data;
}

export async function unlikeFeedPost(
  postId: string
): Promise<{ post_id: string; like_count: number }> {
  const { data } = await client.delete<{ post_id: string; like_count: number }>(
    `/api/feed/posts/${encodeURIComponent(postId)}/like`
  );
  return data;
}

export async function getFeedPostLikes(postId: string): Promise<FeedLikeUsersResponse> {
  const { data } = await client.get<FeedLikeUsersResponse>(
    `/api/feed/posts/${encodeURIComponent(postId)}/likes`
  );
  return {
    post_id: data.post_id,
    users: Array.isArray(data.users) ? data.users : [],
  };
}

export async function createFeedComment(
  postId: string,
  content: string
): Promise<FeedComment> {
  const { data } = await client.post<FeedComment>(
    `/api/feed/posts/${encodeURIComponent(postId)}/comments`,
    { content }
  );
  return data;
}

export async function getFeedComments(
  postId: string,
  cursor?: string
): Promise<FeedCommentListResponse> {
  const { data } = await client.get<FeedCommentListResponse>(
    `/api/feed/posts/${encodeURIComponent(postId)}/comments`,
    { params: cursorParams(cursor) }
  );
  return {
    comments: Array.isArray(data.comments) ? data.comments : [],
    next_cursor: data.next_cursor ?? null,
  };
}

export async function getFeedPopup(userId: string): Promise<FeedPopupResponse> {
  const { data } = await client.get<FeedPopupResponse>(
    `/api/feed/popup/${encodeURIComponent(userId)}`
  );
  return {
    ...data,
    travel_styles: Array.isArray(data.travel_styles) ? data.travel_styles : [],
    feed: {
      items: Array.isArray(data.feed?.items)
        ? data.feed.items.map(normalizeFeedPost)
        : [],
    },
  };
}

function normalizeFeedPost(post: FeedPost): FeedPost {
  return {
    ...post,
    is_liked: Boolean(post.is_liked),
  };
}

export async function deleteFeedComment(
  postId: string,
  commentId: string
): Promise<void> {
  await client.delete(
    `/api/feed/posts/${encodeURIComponent(postId)}/comments/${encodeURIComponent(commentId)}`
  );
}

function getApiStatus(error: unknown): number | undefined {
  const apiError = error as { status?: number; response?: { status?: number } };
  return apiError.status || apiError.response?.status;
}

export function isPossiblyCommittedFeedMutationError(error: unknown): boolean {
  const apiError = error as {
    code?: string;
    message?: string;
    response?: { status?: number };
  };
  const message = String(apiError.message || "").toLowerCase();

  return (
    apiError.code === "ECONNABORTED" ||
    message.includes("timeout") ||
    message.includes("network error") ||
    (!apiError.response && message.includes("network"))
  );
}
