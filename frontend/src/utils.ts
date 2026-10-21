import type { AppNotification } from "./types";

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.floor((now - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString();
}

/** Full date + time, used as a tooltip next to relative times. */
export function fullDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

/** Keep the first occurrence of each id.
 *
 * Lists can receive the same item twice: a post created while the first page
 * is loading may come back in that page too, and a pushed message may also
 * arrive in a REST response.
 */
export function uniqueById<T extends { id: number }>(items: T[]): T[] {
  const seen = new Set<number>();
  return items.filter((item) => !seen.has(item.id) && seen.add(item.id));
}

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong";
}

// mirrors the backend limits so users get instant feedback
export const MAX_IMAGE_MB = 5;
export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

// warm, earthy tones; each keeps white initials readable (contrast >= 4.5:1)
const AVATAR_COLORS = ["#b5451b", "#a3600a", "#2f7563", "#4f56b3", "#93395f", "#3f6f35", "#8a4b2a", "#2a6592"];

/** Stable per user: the same id always gets the same colour. */
export function avatarColor(userId: number): string {
  return AVATAR_COLORS[Math.abs(userId) % AVATAR_COLORS.length];
}

export function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

/** Ask Cloudinary for a resized, auto-format copy instead of the original upload. */
export function optimizedImageUrl(url: string, width = 1080): string {
  const marker = "/image/upload/";
  if (!url.includes("res.cloudinary.com") || !url.includes(marker)) return url;
  return url.replace(marker, `${marker}f_auto,q_auto,w_${width}/`);
}

export function badgeLabel(count: number): string {
  return count > 9 ? "9+" : String(count);
}

const NOTIFICATION_TEXT: Record<AppNotification["type"], string> = {
  follow_request: "requested to follow you",
  follow: "started following you",
  follow_accepted: "accepted your follow request",
  like: "liked your post",
  comment: "commented on your post",
};

export function notificationText(n: AppNotification): string {
  return NOTIFICATION_TEXT[n.type];
}

/** Where clicking a notification goes. */
export function notificationLink(n: AppNotification, myId: number): string {
  switch (n.type) {
    case "like":
    case "comment":
      return `/posts/${n.post_id}`;
    case "follow_request":
      return `/users/${myId}#requests`;
    default:
      return `/users/${n.actor.id}`;
  }
}

/** Random key for one logical message send (reused for its retries). */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
