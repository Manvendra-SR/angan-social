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
  updated_at: string;
}
