import client from "./client";
import { API_BASE_URL } from "./auth/config";

export type ChatRoomType = "direct" | "group";
export type ChatMessageType = "text" | "image" | "file" | "system";

export type SystemContent =
  | { action: "created"; actor_id: string | null }
  | { action: "join"; actor_id: string | null; target_ids: string[] }
  | { action: "leave"; actor_id: string | null }
  | { action: "kick"; actor_id: string | null; target_ids: string[] };

export type LastMessageContent = string | SystemContent | null;

export interface ChatPeer {
  user_id: string | null;
  user_name: string | null;
  profile_image_url: string | null;
}

export interface ChatRoomMember extends ChatPeer {
  role?: string | null;
}

export interface ChatUserProfile {
  user_id: string;
  user_name: string;
  profile_image_url: string | null;
}

export interface LastMessagePreview {
  message_id: string;
  server_seq: number;
  sender_id: string | null;
  type: ChatMessageType;
  content: LastMessageContent;
  created_at: string;
}

export interface ChatRoom {
  chat_room_id: string;
  type: ChatRoomType;
  title: string | null;
  peer: ChatPeer | null;
  members?: ChatRoomMember[];
  last_message: LastMessagePreview | null;
  unread_count: number;
  notification_muted?: boolean;
  last_message_at: string | null;
  effective_last_at: string;
}

export interface ChatRoomListResponse {
  items: ChatRoom[];
  next_cursor: string | null;
}

export interface ChatMessage {
  message_id: string;
  chat_room_id: string;
  server_seq: number;
  sender_id: string | null;
  type: ChatMessageType;
  content: unknown;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  client_msg_id?: string;
  status?: "sending" | "sent" | "failed";
}

export interface ChatMessageListResponse {
  messages: ChatMessage[];
  has_more: boolean;
  next_cursor: number | null;
}

export interface ChatUserProfileListResponse {
  items: ChatUserProfile[];
}

export interface MessageEditResponse {
  message_id: string;
  content: unknown;
  edited_at: string;
}

export function getChatWebSocketUrl(): string {
  const url = new URL("/api/ws/chat", API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export async function createDirectChatRoom(peerUserId: string): Promise<ChatRoom> {
  const { data } = await client.post<ChatRoom>("/api/chat/rooms/direct", {
    peer_user_id: peerUserId,
  });
  return data;
}

export async function createGroupChatRoom(
  title: string,
  memberIds: string[]
): Promise<ChatRoom> {
  const { data } = await client.post<ChatRoom>("/api/chat/rooms/group", {
    title,
    member_ids: memberIds,
  });
  return data;
}

export async function getChatRooms(): Promise<ChatRoomListResponse> {
  const { data } = await client.get<ChatRoomListResponse>("/api/chat/rooms");
  return data;
}

export async function getChatRoom(chatRoomId: string): Promise<ChatRoom> {
  const { data } = await client.get<ChatRoom>(
    `/api/chat/rooms/${encodeURIComponent(chatRoomId)}`
  );
  return data;
}

export async function getChatMessages({
  chatRoomId,
  beforeServerSeq,
  afterServerSeq,
  limit = 50,
}: {
  chatRoomId: string;
  beforeServerSeq?: number;
  afterServerSeq?: number;
  limit?: number;
}): Promise<ChatMessageListResponse> {
  const { data } = await client.get<ChatMessageListResponse>(
    `/api/chat/rooms/${encodeURIComponent(chatRoomId)}/messages`,
    {
      params: {
        before_server_seq: beforeServerSeq,
        after_server_seq: afterServerSeq,
        limit,
      },
    }
  );
  return data;
}

export async function getChatRoomMembers(
  chatRoomId: string
): Promise<ChatUserProfileListResponse> {
  const { data } = await client.get<ChatUserProfileListResponse>(
    `/api/chat/rooms/${encodeURIComponent(chatRoomId)}/members`
  );
  return {
    items: Array.isArray(data.items) ? data.items : [],
  };
}

export async function getInvitableChatRoomFriends(
  chatRoomId: string
): Promise<ChatUserProfileListResponse> {
  const { data } = await client.get<ChatUserProfileListResponse>(
    `/api/chat/rooms/${encodeURIComponent(chatRoomId)}/invitable-friends`
  );
  return {
    items: Array.isArray(data.items) ? data.items : [],
  };
}

export async function inviteChatRoomMembers(
  chatRoomId: string,
  userIds: string[]
): Promise<{ invited_user_ids: string[]; skipped_already_member: string[] }> {
  const { data } = await client.post<{
    invited_user_ids: string[];
    skipped_already_member: string[];
  }>(`/api/chat/rooms/${encodeURIComponent(chatRoomId)}/invite`, {
    user_ids: userIds,
  });
  return data;
}

export async function leaveChatRoom(chatRoomId: string): Promise<void> {
  await client.post(`/api/chat/rooms/${encodeURIComponent(chatRoomId)}/leave`);
}

export async function kickChatRoomMember(
  chatRoomId: string,
  userId: string
): Promise<void> {
  await client.post(`/api/chat/rooms/${encodeURIComponent(chatRoomId)}/kick`, {
    user_id: userId,
  });
}

export async function editChatMessage(
  messageId: string,
  content: string
): Promise<MessageEditResponse> {
  const { data } = await client.patch<MessageEditResponse>(
    `/api/chat/messages/${encodeURIComponent(messageId)}`,
    { content }
  );
  return data;
}

export async function deleteChatMessage(messageId: string): Promise<void> {
  await client.delete(`/api/chat/messages/${encodeURIComponent(messageId)}`);
}
