/** Pure helpers for the realtime connection (kept separate so they can be unit tested). */
import type { Counts, Message, RealtimeEvent } from "./types";
import { uniqueById } from "./utils";

/** Close codes sent by the backend (backend/app/routers/ws.py). */
export const CLOSE_UNAUTHORIZED = 4401;
export const CLOSE_FORBIDDEN_ORIGIN = 4403;

const BACKOFF_STEPS_SECONDS = [1, 2, 4, 8, 16, 30];

/** Delay before reconnect attempt `attempt` (0-based): 1, 2, 4, 8, 16, then 30 s, each ±20 %. */
export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const base = BACKOFF_STEPS_SECONDS[Math.min(attempt, BACKOFF_STEPS_SECONDS.length - 1)];
  const jitter = 1 + (random() * 0.4 - 0.2);
  return Math.round(base * 1000 * jitter);
}

/** Should we try again after the socket closed with this code? */
export function shouldReconnect(code: number): boolean {
  return code !== CLOSE_UNAUTHORIZED && code !== CLOSE_FORBIDDEN_ORIGIN;
}

/** Parse a socket message; unknown or malformed data is ignored. */
export function parseEvent(raw: string): RealtimeEvent | null {
  try {
    const data = JSON.parse(raw);
    switch (data?.type) {
      case "ready":
      case "message.created":
      case "notification.created":
      case "counts.updated":
        return data as RealtimeEvent;
      default:
        return null;
    }
  } catch {
    return null;
  }
}

/** counts.updated carries absolute values, so applying it twice is harmless. */
export function countsFromEvent(event: RealtimeEvent): Counts | null {
  if (event.type !== "counts.updated") return null;
  return { unread_notifications: event.unread_notifications, unread_messages: event.unread_messages };
}

/** Merge new messages into a thread: no duplicates, always in id order. */
export function mergeMessages(current: Message[], incoming: Message[]): Message[] {
  return uniqueById([...current, ...incoming]).sort((a, b) => a.id - b.id);
}
