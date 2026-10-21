import { describe, expect, it } from "vitest";
import type { AppNotification } from "./types";
import {
  avatarColor, badgeLabel, initials, notificationLink, notificationText, optimizedImageUrl, timeAgo, uniqueById,
} from "./utils";

describe("uniqueById", () => {
  it("keeps the first occurrence and the order", () => {
    const items = [{ id: 3, v: "new" }, { id: 1, v: "a" }, { id: 3, v: "old" }, { id: 2, v: "b" }];
    expect(uniqueById(items)).toEqual([{ id: 3, v: "new" }, { id: 1, v: "a" }, { id: 2, v: "b" }]);
  });
  it("handles an empty list", () => {
    expect(uniqueById([])).toEqual([]);
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-21T12:00:00Z").getTime();
  it.each([
    ["2026-10-21T11:59:30Z", "just now"],
    ["2026-10-21T11:55:00Z", "5m"],
    ["2026-10-21T09:00:00Z", "3h"],
    ["2026-10-19T12:00:00Z", "2d"],
  ])("%s -> %s", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });
});

describe("avatars", () => {
  it("gives a user the same colour every time", () => {
    expect(avatarColor(42)).toBe(avatarColor(42));
    expect(avatarColor(1)).not.toBe(avatarColor(2));
  });
  it("uses two uppercase initials", () => {
    expect(initials("boba")).toBe("BO");
  });
});

describe("badgeLabel", () => {
  it("caps at 9+", () => {
    expect(badgeLabel(3)).toBe("3");
    expect(badgeLabel(10)).toBe("9+");
  });
});

describe("optimizedImageUrl", () => {
  it("adds a Cloudinary delivery transform", () => {
    expect(optimizedImageUrl("https://res.cloudinary.com/demo/image/upload/v1/posts/1/a.jpg"))
      .toBe("https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,w_1080/v1/posts/1/a.jpg");
  });
  it("leaves other URLs alone", () => {
    expect(optimizedImageUrl("https://example.com/a.jpg")).toBe("https://example.com/a.jpg");
  });
});

describe("notifications", () => {
  const base: AppNotification = {
    id: 1, type: "like", actor: { id: 7, username: "kiwi" }, post_id: 12, comment_id: null,
    is_read: false, created_at: "2026-10-21T12:00:00Z",
  };
  it("links likes and comments to the post", () => {
    expect(notificationLink(base, 99)).toBe("/posts/12");
    expect(notificationLink({ ...base, type: "comment", comment_id: 5 }, 99)).toBe("/posts/12");
  });
  it("links follow requests to my requests list and follows to the actor", () => {
    expect(notificationLink({ ...base, type: "follow_request", post_id: null }, 99)).toBe("/users/99#requests");
    expect(notificationLink({ ...base, type: "follow", post_id: null }, 99)).toBe("/users/7");
    expect(notificationLink({ ...base, type: "follow_accepted", post_id: null }, 99)).toBe("/users/7");
  });
  it("describes each type", () => {
    expect(notificationText(base)).toBe("liked your post");
    expect(notificationText({ ...base, type: "follow_request" })).toBe("requested to follow you");
  });
});
