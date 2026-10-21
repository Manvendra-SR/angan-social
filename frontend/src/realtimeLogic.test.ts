import { describe, expect, it } from "vitest";
import {
  backoffDelay, CLOSE_FORBIDDEN_ORIGIN, CLOSE_UNAUTHORIZED, countsFromEvent, mergeMessages, parseEvent,
  shouldReconnect,
} from "./realtimeLogic";
import type { Message } from "./types";

describe("backoffDelay", () => {
  const noJitter = () => 0.5; // 0.5 -> jitter factor exactly 1
  it("follows 1, 2, 4, 8, 16, then 30 s", () => {
    expect([0, 1, 2, 3, 4, 5, 6, 20].map((a) => backoffDelay(a, noJitter)))
      .toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]);
  });
  it("adds at most ±20 % jitter", () => {
    expect(backoffDelay(0, () => 0)).toBe(800);
    expect(backoffDelay(0, () => 0.999999)).toBe(1200);
  });
});

describe("shouldReconnect", () => {
  it("retries after network drops and server restarts", () => {
    expect(shouldReconnect(1006)).toBe(true);
    expect(shouldReconnect(1001)).toBe(true);
  });
  it("does not retry a rejected token or origin", () => {
    expect(shouldReconnect(CLOSE_UNAUTHORIZED)).toBe(false);
    expect(shouldReconnect(CLOSE_FORBIDDEN_ORIGIN)).toBe(false);
  });
});

describe("parseEvent", () => {
  it("accepts known events", () => {
    expect(parseEvent('{"type":"ready"}')).toEqual({ type: "ready" });
    expect(parseEvent('{"type":"counts.updated","unread_notifications":2,"unread_messages":1}'))
      .toEqual({ type: "counts.updated", unread_notifications: 2, unread_messages: 1 });
  });
  it("ignores unknown or malformed data", () => {
    expect(parseEvent('{"type":"something.else"}')).toBeNull();
    expect(parseEvent("not json")).toBeNull();
    expect(parseEvent("null")).toBeNull();
  });
});

describe("countsFromEvent", () => {
  it("returns absolute values, so applying an event twice changes nothing", () => {
    const event = parseEvent('{"type":"counts.updated","unread_notifications":3,"unread_messages":0}')!;
    expect(countsFromEvent(event)).toEqual({ unread_notifications: 3, unread_messages: 0 });
    expect(countsFromEvent(event)).toEqual(countsFromEvent(event));
  });
  it("ignores other events", () => {
    expect(countsFromEvent({ type: "ready" })).toBeNull();
  });
});

describe("mergeMessages", () => {
  const msg = (id: number): Message => ({
    id, conversation_id: 1, sender_id: 1, body: `m${id}`, created_at: "2026-10-21T12:00:00Z",
  });
  it("drops duplicates (a pushed message that also came back over REST)", () => {
    expect(mergeMessages([msg(1), msg(2)], [msg(2), msg(3)]).map((m) => m.id)).toEqual([1, 2, 3]);
  });
  it("keeps id order when older history is prepended or events arrive out of order", () => {
    expect(mergeMessages([msg(5)], [msg(3), msg(4)]).map((m) => m.id)).toEqual([3, 4, 5]);
  });
});
