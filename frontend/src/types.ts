export interface UserSummary {
  id: number;
  username: string;
}

export interface Me extends UserSummary {
  email: string;
  bio: string | null;
  is_private: boolean;
  created_at: string;
}

export interface Profile extends UserSummary {
  bio: string | null;
  is_private: boolean;
  created_at: string;
  followers_count: number;
  following_count: number;
  posts_count: number;
  follow_status: "pending" | "accepted" | null;
  blocked_by_me: boolean;
  can_view_posts: boolean;
}

export interface Post {
  id: number;
  user_id: number;
  author: UserSummary;
  content: string | null;
  image_url: string | null;
  created_at: string;
  likes_count: number;
  comments_count: number;
  liked_by_me: boolean;
}

export interface Comment {
  id: number;
  post_id: number;
  user_id: number;
  author: UserSummary;
  content: string;
  created_at: string;
}

export interface FollowRequest {
  follower_id: number;
  follower_username: string;
  created_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  sender_id: number;
  body: string;
  created_at: string;
}

export interface Conversation {
  id: number;
  other_user: UserSummary;
  last_message: Message | null;
  unread_count: number;
  updated_at: string;
}

export type NotificationType = "follow_request" | "follow" | "follow_accepted" | "like" | "comment";

export interface AppNotification {
  id: number;
  type: NotificationType;
  actor: UserSummary;
  post_id: number | null;
  comment_id: number | null;
  is_read: boolean;
  created_at: string;
}

/** Absolute badge values from the server. */
export interface Counts {
  unread_notifications: number;
  unread_messages: number;
}

/** Events pushed over the WebSocket. */
export type RealtimeEvent =
  | { type: "ready" }
  // idempotency_key is only included in the sender's own copy (to match its "sending" bubble)
  | { type: "message.created"; conversation_id: number; message: Message; idempotency_key?: string | null }
  | { type: "notification.created"; notification: AppNotification }
  | ({ type: "counts.updated" } & Counts);
