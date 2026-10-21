/**
 * State of one open chat thread, as a pure reducer so every ordering of
 * "REST response" vs "WebSocket push" can be unit tested.
 *
 * Messages reach a thread from five places: the first page, socket pushes,
 * catch-up after reconnect / fallback polling, older pages, and the response to
 * our own send. They can arrive in any order and overlap, so every source is
 * MERGED (never replaces): de-duplicated by message id and sorted by id, which
 * the server guarantees is chronological within a conversation.
 */
import type { Message } from "./types";
import { mergeMessages } from "./realtimeLogic";

export interface PendingMessage {
  key: string; // idempotency key: the same key is reused when retrying
  body: string;
  status: "sending" | "failed";
  error?: string;
}

export interface ThreadState {
  messages: Message[];
  pending: PendingMessage[];
}

export type ThreadAction =
  /** any batch from REST (first page, catch-up, older page) or a socket push */
  | { type: "merge"; messages: Message[] }
  /** our own message came back (REST response or socket echo carrying our key) */
  | { type: "confirmed"; key: string; message: Message }
  | { type: "sendStarted"; key: string; body: string }
  | { type: "sendFailed"; key: string; error: string }
  | { type: "retry"; key: string };

export const initialThread: ThreadState = { messages: [], pending: [] };

export function threadReducer(state: ThreadState, action: ThreadAction): ThreadState {
  switch (action.type) {
    case "merge":
      return { ...state, messages: mergeMessages(state.messages, action.messages) };
    case "confirmed":
      // matched by idempotency key, never by text: identical messages stay separate
      return {
        messages: mergeMessages(state.messages, [action.message]),
        pending: state.pending.filter((p) => p.key !== action.key),
      };
    case "sendStarted":
      return { ...state, pending: [...state.pending, { key: action.key, body: action.body, status: "sending" }] };
    case "sendFailed":
      return {
        ...state,
        pending: state.pending.map((p) => (p.key === action.key ? { ...p, status: "failed", error: action.error } : p)),
      };
    case "retry":
      return {
        ...state,
        pending: state.pending.map((p) => (p.key === action.key ? { ...p, status: "sending", error: undefined } : p)),
      };
  }
}

/** Cursor for catch-up: the newest message we hold (ids only grow). */
export function newestId(state: ThreadState): number {
  return state.messages[state.messages.length - 1]?.id ?? 0;
}
