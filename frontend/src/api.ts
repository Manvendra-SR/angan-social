import type {
  AppNotification,
  Comment,
  Conversation,
  Counts,
  FollowRequest,
  Me,
  Message,
  Post,
  Profile,
  UserSummary,
} from "./types";

// set in frontend/.env; Vite reads it at startup, so restart `npm run dev` after changing it
export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8080";
/** ws://host/ws (or wss:// when the API is served over https) */
export const WS_URL = API_URL.replace(/^http/, "ws") + "/ws";
const TOKEN_KEY = "token";

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (value: string) => localStorage.setItem(TOKEN_KEY, value),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// FastAPI errors are {detail: "..."} or, for validation errors, {detail: [{msg}]}
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

type Body = { json?: unknown; form?: FormData | URLSearchParams; headers?: Record<string, string> };

async function request<T>(method: string, path: string, body: Body = {}): Promise<T> {
  const headers: Record<string, string> = { ...body.headers };
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;

  let payload: BodyInit | undefined;
  if (body.json !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body.json);
  } else if (body.form) {
    payload = body.form; // browser sets the multipart/form-urlencoded header
  }

  let res: Response;
  try {
    res = await fetch(API_URL + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the server");
  }

  if (res.status === 401 && t) {
    token.clear();
    window.dispatchEvent(new Event("auth:logout"));
  }
  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, res.statusText));
  return data as T;
}

const get = <T>(path: string) => request<T>("GET", path);

/** ?limit=..&before_id=.. for newest-first cursor lists */
function cursor(limit: number, beforeId?: number) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (beforeId) q.set("before_id", String(beforeId));
  return q.toString();
}

export const api = {
  // auth
  login: (email: string, password: string) =>
    request<{ access_token: string }>("POST", "/auth/login", {
      form: new URLSearchParams({ username: email, password }),
    }),
  register: (data: { username: string; email: string; password: string; is_private: boolean }) =>
    request<Me>("POST", "/auth/register", { json: data }),

  // users
  me: () => get<Me>("/users/me"),
  counts: () => get<Counts>("/users/me/counts"),
  updateMe: (data: { username?: string; bio?: string; is_private?: boolean }) =>
    request<Me>("PATCH", "/users/me", { json: data }),
  user: (id: number) => get<Profile>(`/users/${id}`),
  userPosts: (id: number, beforeId?: number, limit = 10) =>
    get<Post[]>(`/users/${id}/posts?${cursor(limit, beforeId)}`),
  searchUsers: (q: string) => get<UserSummary[]>(`/users/search?q=${encodeURIComponent(q)}`),

  // posts
  feed: (beforeId?: number, limit = 10) => get<Post[]>(`/posts/feed?${cursor(limit, beforeId)}`),
  post: (id: number) => get<Post>(`/posts/${id}`),
  createPost: (form: FormData) => request<Post>("POST", "/posts", { form }),
  updatePost: (id: number, content: string) =>
    request<Post>("PATCH", `/posts/${id}`, { json: { content } }),
  deletePost: (id: number) => request<void>("DELETE", `/posts/${id}`),
  like: (id: number) => request<void>("POST", `/likes/${id}`),
  unlike: (id: number) => request<void>("DELETE", `/likes/${id}`),

  // comments (offset pagination, oldest first)
  comments: (postId: number, offset = 0, limit = 20) =>
    get<Comment[]>(`/comments/posts/${postId}?limit=${limit}&offset=${offset}`),
  addComment: (postId: number, content: string) =>
    request<Comment>("POST", `/comments/posts/${postId}`, { json: { content } }),
  deleteComment: (id: number) => request<void>("DELETE", `/comments/${id}`),

  // follows
  follow: (id: number) => request<{ status: string }>("POST", `/follows/${id}`),
  unfollow: (id: number) => request<void>("DELETE", `/follows/${id}`),
  cancelFollow: (id: number) => request<void>("DELETE", `/follows/${id}/cancel`),
  followRequests: () => get<FollowRequest[]>("/follows/requests?limit=50"),
  acceptFollow: (id: number) => request<void>("POST", `/follows/${id}/accept`),
  rejectFollow: (id: number) => request<void>("DELETE", `/follows/${id}/reject`),
  block: (id: number) => request<void>("POST", `/follows/${id}/block`),
  unblock: (id: number) => request<void>("DELETE", `/follows/${id}/unblock`),

  // notifications
  notifications: (beforeId?: number, limit = 20) =>
    get<AppNotification[]>(`/notifications?${cursor(limit, beforeId)}`),
  markNotificationRead: (id: number) => request<Counts>("POST", `/notifications/${id}/read`),
  markAllNotificationsRead: () => request<Counts>("POST", "/notifications/read-all"),

  // messages
  conversations: () => get<Conversation[]>("/conversations?limit=50"),
  conversation: (id: number) => get<Conversation>(`/conversations/${id}`),
  startConversation: (userId: number) =>
    request<Conversation>("POST", "/conversations", { json: { user_id: userId } }),
  messages: (conversationId: number, cursor: { before?: number; after?: number } = {}) => {
    const q = new URLSearchParams({ limit: "50" });
    if (cursor.before) q.set("before_id", String(cursor.before));
    if (cursor.after !== undefined) q.set("after_id", String(cursor.after));
    return get<Message[]>(`/conversations/${conversationId}/messages?${q}`);
  },
  /** idempotencyKey: one per logical send, reused for retries -> never duplicated */
  sendMessage: (conversationId: number, body: string, idempotencyKey: string) =>
    request<Message>("POST", `/conversations/${conversationId}/messages`, {
      json: { body },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  markConversationRead: (conversationId: number, lastReadMessageId: number) =>
    request<Counts>("POST", `/conversations/${conversationId}/read`, {
      json: { last_read_message_id: lastReadMessageId },
    }),
};
