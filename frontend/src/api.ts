import type {
  Comment,
  Conversation,
  FollowRequest,
  Me,
  Message,
  Post,
  Profile,
  UserSummary,
} from "./types";

// set in frontend/.env; Vite reads it at startup, so restart `npm run dev` after changing it
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8080";
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

type Body = { json?: unknown; form?: FormData | URLSearchParams };

async function request<T>(method: string, path: string, body: Body = {}): Promise<T> {
  const headers: Record<string, string> = {};
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
const page = (limit: number, offset: number) => `limit=${limit}&offset=${offset}`;

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
  updateMe: (data: { username?: string; bio?: string; is_private?: boolean }) =>
    request<Me>("PATCH", "/users/me", { json: data }),
  user: (id: number) => get<Profile>(`/users/${id}`),
  userPosts: (id: number, offset = 0, limit = 10) =>
    get<Post[]>(`/users/${id}/posts?${page(limit, offset)}`),
  searchUsers: (q: string) => get<UserSummary[]>(`/users/search?q=${encodeURIComponent(q)}`),

  // posts
  feed: (offset = 0, limit = 10) => get<Post[]>(`/posts/feed?${page(limit, offset)}`),
  createPost: (form: FormData) => request<Post>("POST", "/posts", { form }),
  updatePost: (id: number, content: string) =>
    request<Post>("PATCH", `/posts/${id}`, { json: { content } }),
  deletePost: (id: number) => request<void>("DELETE", `/posts/${id}`),
  like: (id: number) => request<void>("POST", `/likes/${id}`),
  unlike: (id: number) => request<void>("DELETE", `/likes/${id}`),

  // comments
  comments: (postId: number, offset = 0, limit = 20) =>
    get<Comment[]>(`/comments/posts/${postId}?${page(limit, offset)}`),
  addComment: (postId: number, content: string) =>
    request<Comment>("POST", `/comments/posts/${postId}`, { json: { content } }),
  deleteComment: (id: number) => request<void>("DELETE", `/comments/${id}`),

  // follows
  follow: (id: number) => request<{ status: string }>("POST", `/follows/${id}`),
  unfollow: (id: number) => request<void>("DELETE", `/follows/${id}`),
  cancelFollow: (id: number) => request<void>("DELETE", `/follows/${id}/cancel`),
  followRequests: () => get<FollowRequest[]>("/follows/requests"),
  acceptFollow: (id: number) => request<void>("POST", `/follows/${id}/accept`),
  rejectFollow: (id: number) => request<void>("DELETE", `/follows/${id}/reject`),

  // messages
  conversations: () => get<Conversation[]>("/conversations?limit=50"),
  startConversation: (userId: number) =>
    request<Conversation>("POST", "/conversations", { json: { user_id: userId } }),
  messages: (conversationId: number, cursor: { before?: number; after?: number } = {}) => {
    const q = new URLSearchParams({ limit: "50" });
    if (cursor.before) q.set("before_id", String(cursor.before));
    if (cursor.after !== undefined) q.set("after_id", String(cursor.after));
    return get<Message[]>(`/conversations/${conversationId}/messages?${q}`);
  },
  sendMessage: (conversationId: number, body: string) =>
    request<Message>("POST", `/conversations/${conversationId}/messages`, { json: { body } }),
};
