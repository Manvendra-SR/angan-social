import { describe, expect, it } from "vitest";
import { initialThread, newestId, threadReducer, type ThreadAction, type ThreadState } from "./chatThread";
import type { Message } from "./types";

const msg = (id: number, body = `m${id}`, sender = 2): Message => ({
  id, conversation_id: 1, sender_id: sender, body, created_at: new Date(1_700_000_000_000 + id * 1000).toISOString(),
});
const run = (actions: ThreadAction[], start: ThreadState = initialThread) => actions.reduce(threadReducer, start);
const ids = (s: ThreadState) => s.messages.map((m) => m.id);

describe("first page vs socket push", () => {
  it("keeps a message pushed while the first page was loading (page queried before it existed)", () => {
    const s = run([
      { type: "merge", messages: [msg(11)] },                    // socket push arrives first
      { type: "merge", messages: [msg(8), msg(9), msg(10)] },    // then the first page (without 11)
    ]);
    expect(ids(s)).toEqual([8, 9, 10, 11]);
  });

  it("shows a message once when it is in both the push and the first page", () => {
    const s = run([
      { type: "merge", messages: [msg(10)] },
      { type: "merge", messages: [msg(9), msg(10)] },
    ]);
    expect(ids(s)).toEqual([9, 10]);
  });
});

describe("catch-up after reconnect vs pushes", () => {
  it("merges overlapping catch-up batches and pushes without duplicates", () => {
    const s = run([
      { type: "merge", messages: [msg(1), msg(2)] },             // before the disconnect
      { type: "merge", messages: [msg(5)] },                     // push right after reconnect
      { type: "merge", messages: [msg(3), msg(4), msg(5)] },     // catch-up (after_id=2) also returns 5
      { type: "merge", messages: [msg(5), msg(6)] },             // fallback poll overlapping again
    ]);
    expect(ids(s)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(newestId(s)).toBe(6);
  });

  it("orders by id even when events arrive out of order", () => {
    const s = run([{ type: "merge", messages: [msg(12)] }, { type: "merge", messages: [msg(11)] }]);
    expect(ids(s)).toEqual([11, 12]);
  });
});

describe("older history vs pushes", () => {
  it("prepends an older page while new messages keep arriving", () => {
    const s = run([
      { type: "merge", messages: [msg(51), msg(52)] },           // current page
      { type: "merge", messages: [msg(53)] },                    // push during "load older"
      { type: "merge", messages: [msg(49), msg(50), msg(51)] },  // older page (before_id=51) overlaps by one
    ]);
    expect(ids(s)).toEqual([49, 50, 51, 52, 53]);
  });
});

describe("own sends", () => {
  it("socket echo first, then REST response: one message, pending cleared", () => {
    const sent = msg(20, "hi", 1);
    const s = run([
      { type: "sendStarted", key: "k1", body: "hi" },
      { type: "confirmed", key: "k1", message: sent },           // echo carrying our key
      { type: "confirmed", key: "k1", message: sent },           // REST response
    ]);
    expect(ids(s)).toEqual([20]);
    expect(s.pending).toEqual([]);
  });

  it("an echo from another tab with the same text doesn't touch this tab's pending send", () => {
    const s = run([
      { type: "sendStarted", key: "mine", body: "ok" },
      { type: "merge", messages: [msg(30, "ok", 1)] },           // other tab's message, no key for us
      { type: "sendFailed", key: "mine", error: "Cannot reach the server" },
    ]);
    expect(ids(s)).toEqual([30]);
    expect(s.pending).toEqual([{ key: "mine", body: "ok", status: "failed", error: "Cannot reach the server" }]);
  });

  it("two identical messages sent in a row stay two messages", () => {
    const s = run([
      { type: "sendStarted", key: "a", body: "ok" },
      { type: "sendStarted", key: "b", body: "ok" },
      { type: "confirmed", key: "b", message: msg(41, "ok", 1) },
      { type: "confirmed", key: "a", message: msg(40, "ok", 1) },
    ]);
    expect(ids(s)).toEqual([40, 41]);
    expect(s.pending).toEqual([]);
  });

  it("failed send, then retry with the same key: delivered once", () => {
    const s = run([
      { type: "sendStarted", key: "k", body: "retry me" },
      { type: "sendFailed", key: "k", error: "offline" },
      { type: "retry", key: "k" },
      { type: "confirmed", key: "k", message: msg(7, "retry me", 1) },
    ]);
    expect(ids(s)).toEqual([7]);
    expect(s.pending).toEqual([]);
  });
});
