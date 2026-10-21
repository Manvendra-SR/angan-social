# Improvement Plan: Social_Media_Platform

This is the single source of truth for planned work. It explains **how** each change will work, not just
**what** it adds.

**Labels:**

- **Existing** means current behaviour, verified in the code.
- **Bug** means a confirmed defect, verified by reading the code or running a script.
- **Proposed** means planned work that is **not implemented yet**.
- **Implemented** means built **and** verified by the tests listed in §1.

The code was inspected at commit `60ec72c` plus one uncommitted text change in
`frontend/src/pages/Register.tsx`.

**Stack (unchanged):** FastAPI with SQLAlchemy 2.0 (sync) on Neon PostgreSQL, Cloudinary for images, and
React + TypeScript + React Router with plain CSS. The backend runs as **one** uvicorn process.

---

## 1. Status at a glance

All eight phases are **implemented**. "Verified" means the tests named here were run and passed (results in §16).

| Item | Status | Verified by |
|---|---|---|
| JWT secret replaced | **Done** (by the owner). `SECRET_KEY` is set, 64 characters, not the placeholder (compared, never printed) | manual check |
| Startup validation of `SECRET_KEY` (§4.1) | **Implemented** | `tests/test_identity.py` |
| Case-insensitive username/email uniqueness in the DB (§4.2) | **Implemented**; main DB migrated with `python -m app.migrate` | `test_identity.py` (incl. concurrent sign-ups), `test_migrate.py` |
| Correct follower/following counts (§4.3) | **Implemented** | `test_follows_privacy.py` |
| Feed discovery rules + `before_id` cursor (§5.1) | **Implemented** | `tests/test_feed.py`, smoke script |
| Other backend fixes (§5.2) | **Implemented** (upload pre-check is a middleware; see §16) | `test_images.py`, `test_notifications.py`, `test_follows_privacy.py` |
| Notifications + unread-message tracking (§6) | **Implemented** | `tests/test_notifications.py`, `tests/test_messages.py` |
| Idempotent message sends (decision 6) | **Implemented** | `tests/test_messages.py` (incl. concurrent retries), smoke script |
| WebSocket backend (§7) | **Implemented** | `tests/test_realtime.py` |
| Real-time frontend (§8) | **Implemented** | Vitest (`realtimeLogic.test.ts`), smoke script (live delivery, drop + recovery) |
| Frontend foundation + page redesign (§9–§10) | **Implemented** | `npm run build`, Vitest, smoke script (states, responsive widths, console) |
| Testing, deployment checklist, docs (§11) | **Implemented**; deployment itself is out of scope | README "Deployment checklist" |

---

## 2. Phase order and dependencies

```
Phase 1 Security & identity ─┐
Phase 2 Backend fixes ───────┼─► Phase 3 Notifications + unread ─► Phase 4 WebSocket backend ─┐
                             │                                                                  ├─► Phase 6 Real-time UI ─► Phase 7 UI pages ─► Phase 8 Verify & docs
Phase 5 Frontend foundation ─┴──────────────────────────────────────────────────────────────────┘
```

| Phase | Can start when | Effort |
|---|---|---|
| 1 Security & identity | now | small |
| 2 Backend correctness fixes | now (independent of 1) | small |
| 3 Notifications & unread tracking | Phase 1 done (`migrate.py` creates the new tables) | medium |
| 4 WebSocket backend | Phase 3 done (it pushes Phase 3's rows and counts) | medium |
| 5 Frontend foundation | now (no backend dependency) | medium |
| 6 Real-time integration | Phases 4 and 5 done | medium |
| 7 Feed/profile/search/chat/notification UI | Phases 2 (cursor API), 5 and 6 done | large |
| 8 Testing, deployment checks, docs | all phases done | small |

Every phase must end with pytest green on the test branch, `npm run build` green, and the app still runnable.

---

## 3. Current system (existing, brief)

- **Auth:**
  - `POST /auth/login` returns a JWT whose `sub` is the user id
  - `get_current_user` (`dependencies/auth.py`) decodes it on every request
  - the frontend stores the token in `localStorage` and logs out on any 401
- **Access control:** `dependencies/privacy.py`.
  - `is_blocked_between(a, b)` checks both directions.
  - `can_view_profile` is true for public accounts, yourself, or an accepted follower.
  - `get_accessible_post` combines them (404/403) and is reused by the post, comment and like endpoints.
- **Blocks:** a block of B by A is stored as the `follows` row `(follower_id=B, following_id=A, status='blocked')`.
- **Chat:**
  - one `conversations` row per pair (`user_a_id < user_b_id`, unique) and `messages` with id cursors
  - the frontend polls the open thread every 3 s and the conversation list every 9 s
    (`frontend/src/pages/Chat.tsx:8,19,105`)
  - nothing tracks read/unread
- **Schema creation:** `python -m app.init_db` runs `Base.metadata.create_all()`. That creates **missing tables
  only** and never alters existing ones. There is no migration framework.

---

## 4. Phase 1: Security and identity integrity

### 4.1 Validate configuration at startup (Implemented)

**What happens:** the backend refuses to start if `SECRET_KEY` is missing, shorter than 32 characters, or
equal to the known placeholder. The error names the problem but **never prints the value**.

**How it works:**

1. In `Settings` (`core/config.py`), add a `field_validator("SECRET_KEY")` that raises
   `ValueError("SECRET_KEY must be at least 32 characters and must not be the example value")`.
2. Set `hide_input_in_errors=True` in `SettingsConfigDict`. Pydantic validation errors otherwise include
   `input_value=...`, which would print the bad secret into the startup traceback.
3. Store `SECRET_KEY` and `CLOUDINARY_API_SECRET` as `SecretStr`, so an accidental `print(settings)` or log
   line shows `**********`. Read them with `.get_secret_value()` in the two places they're used:
   `core/security.py` and `core/media.py`.
4. Database URLs stay plain strings. They're already never logged: `init_db.py` prints only `engine.url.host`.

**Edge cases:**

- A missing variable fails with pydantic's normal "field required" error, which contains no value.
- The existing `DB_*` lines in `.env` are ignored (`extra="ignore"`).

**Verification:**

- Construct `Settings` with a short key and with the placeholder; each raises an error, and the error text
  doesn't contain the key.
- A valid key loads.

### 4.2 Case-insensitive unique usernames and emails (Bug → Implemented)

**Bug:**

- Uniqueness is checked with `lower()` in Python (`routers/auth.py:24`, `routers/users.py:39-44`).
- The database only has case-sensitive `UNIQUE(username)` and `UNIQUE(email)` (`models/user.py:13-17`).
- On the test branch (rolled back), the database accepted both `Manav` and `manav`.
- So two concurrent requests can both pass the Python check and both insert.

**Policy:**

- **Usernames:** stored exactly as typed (display casing is kept) and unique ignoring case. The ASCII-only
  pattern `^[A-Za-z0-9_]{3,30}$` (`schemas/user.py`) means Python's `lower()` and PostgreSQL's `lower()` always
  agree.
- **Emails:** always stored lowercase and unique ignoring case. Login already lowercases the submitted email
  (`auth.py:50`).

**How it works:**

1. Add two functional unique indexes, declared in the model so fresh databases and the test branch get them
   from `create_all()`:
   `Index("uq_users_username_lower", func.lower(User.username), unique=True)` and the same for `email`.
2. Add `backend/app/migrate.py`, an idempotent script for the existing main database:
   - run `SELECT lower(username), count(*) FROM users GROUP BY 1 HAVING count(*) > 1`, and the same for email
   - if any rows come back, print them and stop, so a human renames one account first
   - otherwise create each index with `Index.create(bind, checkfirst=True)`
   - run `create_all()` for the new tables added in Phase 3

   Running it twice does nothing the second time.

   A read-only check today found 12 users and **no collisions**, so the migration should run cleanly.
3. Move email lowercasing into the Pydantic schema (a `field_validator` on `UserCreate.email`) so no endpoint
   can forget it.
4. Keep the existing pre-checks, which give a friendly early 409, but **treat the database as the final
   word**. Wrap the commit:
   ```
   try: db.commit()
   except IntegrityError as e:
       db.rollback()
       name = e.orig.diag.constraint_name      # psycopg2 gives the violated constraint
       if name in {"uq_users_username_lower", "users_username_key"}: 409 "Username already taken"
       elif name in {"uq_users_email_lower", "users_email_key"}:     409 "Email already registered"
       else: re-raise (becomes a 500, logged; DB text never sent to the client)
   ```
   The same mapping applies to `PATCH /users/me`.

**Edge cases:**

- **Two users register `Manav` / `manav` at the same instant:** both pass the pre-check. The index lets
  exactly one commit, and the other gets `IntegrityError` → 409 "Username already taken".
- **A user renames themselves `bob` → `Bob`:** allowed. The pre-check skips names equal to your current name
  ignoring case, and the index sees the same `lower()` value on the same row.

**Verification:**

- `Manav` after `manav` → 409 username; `USER@x.com` after `user@x.com` → 409 email.
- Renaming to another user's name in different case → 409.
- **Race simulation:** insert a case-variant row directly, then call register with the pre-check bypassed;
  the result is 409, not 500.
- Running `migrate.py` twice is safe.

### 4.3 Correct follower and following counts (Bug → Implemented)

**Bug:**

- `followers_count` / `following_count` (`models/user.py:53-65`) count every `follows` row, including
  `pending` and `blocked`.
- Reproduced on the test branch (rolled back): 0 accepted followers showed as `followers_count = 2`.
- **Blocking someone increases your own follower count**, which also reveals that a block happened.

**How it works:** add `Follow.status == "accepted"` to both `column_property` subqueries.

**Verification:** after a pending request and a block, both counts stay 0; after an accept, the follower
count is 1.

---

## 5. Phase 2: Smaller backend correctness fixes

### 5.1 Feed and profile posts: discovery rules and cursor pagination

**Existing behaviour (verified in `routers/posts.py` `get_feed`):**

- One query returns posts whose author is:
  - **you**, or
  - **any public account** (discovery), or
  - **an account you follow with an accepted request**,

  excluding authors you blocked or who blocked you.
- Results are ordered `created_at DESC, id DESC` with `LIMIT/OFFSET`.

**What happens (after the change):** the feed stays chronological, newest first, with no ranking or
recommendations. "Load more" never shows a post twice and never skips one, even while others are posting.

**How the feed is combined:**

```
SELECT posts.* FROM posts JOIN users author ON author.id = posts.user_id
WHERE (
        posts.user_id = :me                                    -- my own posts
     OR author.is_private = false                              -- discovery: any public account
     OR posts.user_id IN (SELECT following_id FROM follows     -- private accounts I'm approved for
                          WHERE follower_id = :me AND status = 'accepted')
      )
  AND posts.user_id NOT IN (users I blocked)                   -- follows row: follower=them, following=me, blocked
  AND posts.user_id NOT IN (users who blocked me)              -- follows row: follower=me, following=them, blocked
  AND (:before_id IS NULL OR posts.id < :before_id)            -- cursor
ORDER BY posts.id DESC                                         -- id instead of created_at
LIMIT :limit
```

How this satisfies the rules:

- **No duplicates by construction.** The three conditions are combined with `OR` inside one `WHERE` over the
  posts table, which is joined 1:1 to its author. It isn't a `UNION` of separate queries, so a post that
  qualifies as both "followed" and "public" is still a single row.
- **Privacy:**
  - A private account's post can only match through the third condition, which requires an `accepted`
    follow. A `pending` request doesn't count.
  - Your own posts always match, even if your account is private.
- **Blocks:** both directions are excluded, regardless of which condition matched. This mirrors
  `is_blocked_between`.

**Cursor pagination (Implemented):**

- **Why `id` rather than `created_at`:** `posts.id` comes from a sequence, so it's unique and increases
  with every insert. `created_at` can tie between rows, so it can't serve as an exact cursor on its own.
  Ordering by `id DESC` is effectively newest first.
- **How the cursor works:**
  - The first page has no cursor.
  - The next request sends `before_id = <id of the last post shown>`.
  - New posts inserted after page 1 get *higher* ids, so they can't appear in `id < before_id`. Nothing
    shifts, nothing repeats, nothing is skipped.
  - A deleted post simply isn't returned. That's unlike offset pagination, where a deletion would make the
    next page skip an item.
- `/users/{id}/posts` uses the same cursor. Its existing private-account 403 and block 403 checks stay.
- `before_id` replaces `offset` on these two endpoints, and the frontend switches in the same phase.
  **Comments keep `offset`**: they're listed oldest-first and new comments are appended at the end, so
  offsets stay stable.

**Frontend "Load more":**

- state: `posts[]`, `status` (`idle | loading | error | end`)
- the cursor is the last post's id
- the button is disabled while loading, so a double click can't send two requests
- the response is appended through the existing `uniqueById` (`utils.ts`)
- `batch.length < limit` → `end`, showing "You're all caught up"
- on error, the loaded posts stay on screen with an inline message and a Retry button that repeats the same
  cursor
- an empty first page shows the empty state
- a newly created post is prepended locally
- clicking Home again reloads page 1 and replaces the list

**Edge cases:**

- **An author goes private, unfollows or blocks between page loads:** later pages apply the new rule
  immediately. Posts already on screen stay until the next refresh, which is acceptable.
- **A pending request isn't access:** posts from that private account only appear after acceptance.

**Verification:**

- **Discovery:** a non-followed public account's posts appear; a non-followed private account's don't; an
  accepted follow makes them appear; a pending one doesn't.
- **Blocks:** both directions are excluded.
- **One row per post:** a followed public account's posts appear exactly once.
- **Cursor:** insert a post between page 1 and page 2; page 2 has no repeats and no gaps.
- **Deletion:** delete a post from page 2's range before requesting it; nothing is skipped.
- **`end` reached:** a page shorter than `limit` ends the list.

### 5.2 Other fixes in this phase (Implemented)

| Fix | How it works | Verification |
|---|---|---|
| **Reject oversized uploads early.** Inferred: the full multipart body is received before `read_image()` (`core/media.py:48`) enforces 5 MB. | An HTTP middleware in `main.py` returns 413 when `Content-Length` > limit + 64 KB of form overhead, before the body is read. (A route dependency would be too late: FastAPI parses form bodies before it resolves dependencies.) The existing byte-level check stays as the real guard (chunked requests have no `Content-Length`). | oversized header → 413 and no Cloudinary call |
| **Accept pending requests when an account goes public.** Today they stay pending forever. | In `PATCH /users/me`, when `is_private` flips true→false, update that user's `pending` incoming rows to `accepted` in the same commit (and create `follow_accepted` notifications once Phase 3 exists). | the requester can see posts right after the switch |
| **Search hides users who blocked you.** Today they lead to a 403 profile. | Add `NOT IN (users who blocked me)` to `/users/search`. | a blocked searcher doesn't find the blocker |
| **App logging.** There's no logging configuration. | `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")` in `main.py`. Never log tokens, passwords or URLs with credentials. | — |

---

## 6. Phase 3: Notifications and unread-message tracking (Implemented)

These are **two separate features with separate counts**:

| | Notifications | Unread messages |
|---|---|---|
| Triggered by | follow request, new follower, accepted request, like, comment | a new direct message |
| Stored as | one row per event in `notifications` | no extra row per message; a read position per user per conversation in `conversation_reads` |
| Badge | Notifications nav item = number of unread notification rows | Messages nav item = total unread **messages** across conversations |
| Marked read by | clicking a notification, or "Mark all as read" | opening the conversation |

**Direct messages never create notification rows.** That's intentional: one row per message would flood the
notification list and duplicate the chat UI. Messages get their own badge.

### 6.1 Notifications

**Table `notifications` (new):**

| Column | Notes |
|---|---|
| `id` | PK, also the list cursor |
| `recipient_id`, `actor_id` | FK `users`, `ON DELETE CASCADE`; `CHECK (actor_id <> recipient_id)` |
| `type` | varchar with `CHECK (type IN ('follow_request','follow','follow_accepted','like','comment'))` (a CHECK is easier to extend than a PG enum) |
| `post_id` | FK `posts`, CASCADE; required for `like` / `comment` |
| `comment_id` | FK `comments`, CASCADE; required for `comment` |
| `is_read` | bool, default false |
| `created_at` | timestamptz, default now() |

**Indexes:**

- `(recipient_id, id DESC)` for the list
- partial `(recipient_id) WHERE NOT is_read` for the badge count
- **dedupe:**
  - partial `UNIQUE (recipient_id, actor_id, post_id) WHERE type = 'like'`
  - partial `UNIQUE (recipient_id, actor_id, type) WHERE type IN ('follow_request','follow','follow_accepted')`
  - comments are unique by `comment_id`

**When each notification is created and removed:**

| Action (existing endpoint) | Recipient | Type | Removed when |
|---|---|---|---|
| Follow a **private** account → `pending` (`POST /follows/{id}`) | the account owner | `follow_request` | the request is accepted, rejected or cancelled (same transaction) |
| Follow a **public** account → `accepted` | the account owner | `follow` | kept after an unfollow; the unique index stops a re-follow from duplicating it |
| Accept a request (`POST /follows/{id}/accept`) | the requester | `follow_accepted` | — (the owner's `follow_request` row is deleted in the same transaction) |
| Like (`POST /likes/{post_id}`) | the post owner | `like` | kept after an unlike; the unique index makes like/unlike/like produce at most one row |
| Comment (`POST /comments/posts/{id}`) | the post owner | `comment` | the comment or post is deleted (FK cascade) |
| Block (`POST /follows/{id}/block`) | — | — | **all notifications between the two users, both directions**, deleted in the block's transaction |

No notification is created for actions on your own post or account.

**Transaction flow** (the same for every action):

```
request
  → get_current_user + existing access checks (get_accessible_post / follow rules)  ── fail → 403/404, nothing written
  → add the action row (Like / Comment / Follow) and db.flush()                      ── duplicate → IntegrityError → rollback → 409
  → notify(db, recipient, actor, type, ...)   INSERT ... ON CONFLICT DO NOTHING RETURNING *
  → db.commit()                                ── action + notification are saved together or not at all
  → counts = get_counts(db, recipient)          (one query, §6.3)
  → response returned
  → background task: push notification.created + counts.updated to the recipient (§7)
```

Notes on the flow:

- **`flush()` before `notify()`.** The `Like` is added through the session (written at flush time), while
  the notification is a direct `INSERT … ON CONFLICT`. Flushing first makes a duplicate like fail
  **before** any notification SQL runs, so a 409 can never leave a notification behind. The rollback would
  undo it anyway; flushing first just makes the order obvious.
- **`notify()` returns `None`** when it skips a self-action or the unique index absorbs a duplicate, and
  then nothing is pushed.
- **Privacy is inherited:** a notification can only exist if the action passed the existing access checks.
  For example, you can't like a private post you can't see, so no notification can leak it.

**REST endpoints:**

| Endpoint | Behaviour |
|---|---|
| `GET /notifications?limit=20&before_id=` | newest first; each item has `actor {id, username}`, `type`, `post_id`, `comment_id`, `is_read`, `created_at` (actor loaded with `selectinload`, no N+1) |
| `POST /notifications/{id}/read` | sets `is_read`; **404 if you're not the recipient** (doesn't reveal that the row exists); returns new counts |
| `POST /notifications/read-all` | `UPDATE … SET is_read = true WHERE recipient_id = :me AND NOT is_read`; returns new counts |
| `GET /users/me/counts` | `{unread_notifications, unread_messages}`, one request for both badges |

**Frontend behaviour:**

- The **Notifications badge** shows `unread_notifications` (shown as "9+" above 9).
- The **Notifications page** lists "New" (unread) above "Earlier" and loads more with `before_id`.
  "Mark all as read" sends the request and then sets every visible row as read.
- **Clicking a row** marks it read (a fire-and-forget request; the UI updates immediately), then navigates:

  | Type | Goes to |
  |---|---|
  | `like` / `comment` | `/posts/:post_id` (the new post-detail page, comments open) |
  | `follow` / `follow_accepted` | `/users/:actor_id` |
  | `follow_request` | your own profile's "Follow requests" section; the row also has inline Accept / Reject buttons that call the existing endpoints |

**Edge cases:**

- **The post was deleted after the list loaded:** the post page shows "This post is no longer available".
  The cascade has already removed the notification, so it disappears on the next load.
- **Mark-read fails:** the row is shown as unread again and the next `counts.updated` corrects the badge.

**Verification:**

- each action creates exactly one notification for the right recipient
- no notification for self-actions
- like → unlike → like leaves one row
- a duplicate like (409) leaves no notification
- accept/reject/cancel removes the `follow_request` row
- deleting a post or comment cascades
- a block removes notifications both ways
- the list paginates
- marking someone else's notification → 404
- counts are correct after read and read-all

### 6.2 Conversations and unread messages

**Table `conversation_reads` (new):**

- `(conversation_id FK CASCADE, user_id FK CASCADE)` as the primary key
- `last_read_message_id INT NOT NULL DEFAULT 0`, where 0 means "nothing read yet"
- It's a new table rather than two columns on `conversations`, because `create_all()` can't add columns.

**How unread is calculated:**

```
unread in conversation C for me = count(messages WHERE conversation_id = C
                                         AND id > coalesce(my last_read_message_id in C, 0)
                                         AND sender_id <> me)
unread_messages (badge)        = the same count over every conversation I'm part of (one grouped query)
```

The existing index `ix_messages_conversation_id_id` serves the `conversation_id = C AND id > X` part.

**Sending a message** (existing endpoint `POST /conversations/{id}/messages`; the idempotency key, push and count are new):

```
A sends
  → participant check (404 for outsiders) + block check (403)           [existing]
  → Idempotency-Key header seen before for A? → same conversation + body: return that message (200)
                                                 different payload: 409, nothing created
  → INSERT ... ON CONFLICT (sender_id, idempotency_key) DO NOTHING  (a concurrent retry that
    inserted first makes this a no-op; we then return its message)
  → bump conversations.updated_at, COMMIT
  → counts = get_counts(db, B)
  → response (the saved message) to A
  → background: push message.created to A and B, counts.updated to B
```

**Marking as read:**

- The client sends `POST /conversations/{id}/read {"last_read_message_id": <id of the newest message it has
  displayed>}`. It does this when the thread is open, the tab is visible, and a newer message has rendered.
- The server:
  1. checks that you're a participant (404 otherwise)
  2. checks that the message belongs to this conversation (404 otherwise)
  3. runs `INSERT … ON CONFLICT (conversation_id, user_id) DO UPDATE SET last_read_message_id =
     GREATEST(conversation_reads.last_read_message_id, EXCLUDED.last_read_message_id)`
  4. commits, returns the new counts, and pushes `counts.updated` to all your tabs
- **Why the client sends the id it has displayed**, rather than the server using "latest": a message that
  arrives a moment before the request isn't marked read unless it was actually rendered.
- **`GREATEST` is atomic in a single statement**, so two tabs marking at once, or a stale tab, can't move
  the read position backwards.

**Conversation list:** `GET /conversations` gains `unread_count` per conversation, computed with one
grouped query for the page, like the existing last-message query.

**Edge cases:**

- **Offline recipient:** messages are rows in PostgreSQL, so the counts are computed from data. When the
  user returns, `GET /users/me/counts` and `GET /conversations` show the right badges, and opening the
  thread loads history through the existing REST endpoint.
- **A conversation with no messages:** unread count 0, nothing to mark.
- **Blocked pair:** sending is already forbidden; existing messages and counts stay readable.
- **A fabricated `last_read_message_id`** (another conversation's message, or a nonexistent id) → 404.

**Verification:**

- B's count goes up when A sends, and A's doesn't
- the per-conversation `unread_count` and the badge total agree
- mark-read resets the count
- a lower id doesn't move the position back
- an outsider gets 404 on mark-read

### 6.3 `get_counts(db, user_id)`

This one helper returns `{unread_notifications, unread_messages}` from two `COUNT` queries. It's used by
`GET /users/me/counts`, the mark-read endpoints, and every push.

Events carry **absolute counts, not "+1" increments**. A duplicated or missed event therefore can't make a
badge drift: the next event or fetch simply overwrites it with the true value.

---

## 7. Phase 4: WebSocket backend (Implemented)

**Purpose:** push updates only. REST stays responsible for sending messages, history, notification lists,
marking read and recovery.

**Scope:** the WebSocket carries chat and notification events only. Feed, likes, comments and profiles do
**not** get their own WebSocket events. A like or comment reaches the owner indirectly, as a
`notification.created` event.

### 7.1 Connecting and authenticating

**One endpoint, `GET /ws`, with one connection per browser tab.** It's shared by notifications and chat.

```
browser                                   server (routers/ws.py)
  │  open ws://host/ws ───────────────────► check Origin header ∈ CORS_ORIGINS   ── no → close 4403
  │                                          accept()
  │  {"type":"auth","token":"<jwt>"} ─────► wait ≤ 10 s                          ── timeout → close 4408
  │                                          decode with the existing JWT settings ── invalid/expired → close 4401
  │                                          load the user with a short SessionLocal(), close the session immediately
  │                                          manager.connect(user_id, ws)
  │  ◄──────────────────────── {"type":"ready"}
  │                                          loop: receive with timeout = seconds until the token's exp
  │                                            client message after auth → ignored
  │                                            token expires → close 4401
  │  (tab closed / network drop) ─────────► finally: manager.disconnect(user_id, ws)
```

**Design choices:**

- **Token in the first message, not `?token=` in the URL.** Browsers can't set headers on a WebSocket, and
  a URL token would be written to uvicorn's access log.
- **Origin check.** It stops another website from opening a socket from a victim's browser. The token
  check is the main guard; this is defence in depth.
- **No DB session held open** for the life of the connection. The session is used for the user lookup and
  closed straight away, which matters with Neon's connection pooler.
- **Dead connections:** uvicorn's built-in WebSocket ping (every 20 s by default) detects them and ends the
  receive loop, which triggers the `finally` cleanup.

### 7.2 Connection manager and routing

`core/realtime.py` (about 40 lines):

```python
class ConnectionManager:
    def __init__(self): self.connections: dict[int, set[WebSocket]] = {}
    def connect(self, user_id, ws): self.connections.setdefault(user_id, set()).add(ws)
    def disconnect(self, user_id, ws): ...remove; drop the key when the set is empty
    async def send_to_user(self, user_id, event):
        for ws in list(self.connections.get(user_id, ())):
            try: await ws.send_json(event)
            except Exception: self.disconnect(user_id, ws)   # dead socket
manager = ConnectionManager()
```

- **Routing is by user id only.** A client can't subscribe to anything. Recipients are computed on the
  server from data the endpoint has already authorized: the conversation's two participants, or the
  notification's recipient.
- **Several tabs per user** each have their own socket in the set, and all of them receive the event.
- **Offline user:** `send_to_user` finds no sockets and does nothing. The data is already in PostgreSQL
  (§7.4).

### 7.3 Pushing from the existing endpoints

**Why after the commit:** an event must never announce something the database could still roll back. If
the commit fails, nothing is pushed. If the push fails, the data is still saved and REST recovery finds it.

**How the sync endpoints push:**

- The route handlers are synchronous `def` functions running in a worker thread, so they mustn't call
  WebSocket methods directly.
- Each changed endpoint takes `background_tasks: BackgroundTasks` and, after `db.commit()`, calls
  `background_tasks.add_task(manager.send_to_user, user_id, event)`.
- FastAPI runs async background tasks on the event loop **after** the response is sent, so the manager is
  only ever used from the event loop and needs no locks.

**Events (server → client):**

| Event | Payload | Sent to | Frontend reaction (§8) |
|---|---|---|---|
| `ready` | `{}` | the connecting socket | run REST recovery |
| `message.created` | `{conversation_id, message}` (same shape as `MessageOut`) | both participants | append to the open thread / update the conversation list |
| `notification.created` | `{notification}` (same shape as the REST list item) | the recipient | prepend to the notifications list if it's loaded |
| `counts.updated` | `{unread_notifications, unread_messages}` | the affected user | replace both badge values |

### 7.4 Offline recipients and reconnecting

**The WebSocket isn't storage.** Every message and notification is committed to PostgreSQL before any push.
A user who is offline misses only the *push*, not the data. On the next connection, the client recovers
everything over REST (§8.2).

### 7.5 Why one worker and no Redis

- The manager lives in the memory of one Python process.
- With several uvicorn workers, a user connected to worker 1 wouldn't receive events produced on worker 2.
  Fixing that needs a shared pub/sub (for example Redis), which this project doesn't need at its size.
- **So the backend runs with one worker** (uvicorn's default), and that's documented.
- Kafka or a message broker would solve a problem this app doesn't have: many servers, durable event
  streams.

### 7.6 Verification

These use `TestClient.websocket_connect`:

- a wrong Origin → 4403; no auth message → 4408; a bad or expired token → 4401
- a valid connection receives `ready`
- A sends a message → B's socket gets `message.created`, C's (non-participant) gets nothing
- a like → the owner gets `notification.created` and `counts.updated` with correct absolute values
- two sockets for one user both receive the event
- a closed socket is removed from the manager
- a failed action (409) pushes nothing

---

## 8. Phase 6: Real-time integration in the frontend (Implemented)

(Phase 5's foundation is described in §9; this phase only needs its badge and app shell.)

### 8.1 `RealtimeProvider` (`src/realtime.tsx`)

- One provider at the app root, mounted only while a user is logged in. It opens one socket per tab.
- It exposes `status` (`connecting | open | reconnecting`), `counts`, and `subscribe(handler)` for pages.
- **Logout or unmount** closes the socket. The effect cleanup also handles React StrictMode's double mount
  in development, so the app never keeps two sockets open.

**Reconnecting:**

- If the socket closes for any reason other than 4401 or 4403, retry after 1, 2, 4, 8, 16, then every 30 s.
- Each delay gets ±20 % random jitter, so a server restart doesn't trigger every client at the same moment.
- Retry immediately on the browser's `online` event or when the tab becomes visible.
- **On 4401**, dispatch the existing `auth:logout` event (`api.ts`), which shows the login page.

### 8.2 Recovery after every `ready`

The socket subscribes first and then fetches, so nothing is lost in between:

1. `GET /users/me/counts` → set both badges.
2. If the conversation list is mounted → `GET /conversations` (this refreshes the unread counts).
3. If a thread is open → `GET /conversations/{id}/messages?after_id=<last shown id>`, repeated while a full
   page (50) comes back. This catches up even after a long disconnect.
4. If the notifications page is mounted → refetch its first page and merge by id.

### 8.3 Handling events without duplicates

- **`message.created`:**
  - **Open thread:** append through the existing merge-by-id. If the tab is visible, send mark-read.
  - **Conversation list:** update that row's last message, move it to the top, and add 1 to its unread
    count (unless the message is mine or the thread is open). The next list fetch corrects any drift.
- **Your own sent message:**
  - It appears as a "sending…" bubble with a temporary key.
  - When the REST response arrives, the temporary bubble is replaced by the saved message.
  - If the WebSocket copy (same id) arrived first, the temporary bubble is dropped.
  - On failure, the bubble shows "Failed, tap to retry".
- **`notification.created`:** prepend if the id isn't already in the list.
- **`counts.updated`:** overwrite the badges (absolute values, §6.3).

### 8.4 Fallback when the socket is unavailable

- If the status isn't `open` for more than 5 s:
  - the chat shows a small "Reconnecting…" banner
  - the open thread polls `after_id` every **15 s**, reusing today's poll code
  - badges keep their last values
- Polling stops on `ready`.
- **While the socket is open, no `setInterval` polling runs.** That removes today's 3 s and 9 s timers in
  `Chat.tsx`.

### 8.5 Verification

- **Vitest:** the event reducer (dedupe by id, absolute counts overwrite) and the backoff schedule.
- **Two-browser check:** a message appears in under 1 s, the badge increments, and opening the thread
  clears it.
- **Restart test:** stop the backend, send a message from another account after the restart, and confirm
  the first client reconnects and shows it exactly once.
- **Blocked socket:** "Reconnecting…" appears and the 15 s polling still delivers messages.

---

## 9. Phase 5: Frontend foundation (Implemented)

The goal is a consistent base, so new screens aren't built twice. React, TypeScript, React Router and plain
CSS stay; no UI framework, icon library or animation library is added.

**Design tokens (`src/styles/tokens.css`):** CSS variables for:

- colours: background, surface, border, text, muted text, one accent, danger, success, like
- a type scale: 12/14/15/17/20/24 px
- a 4 px spacing scale, radii of 8, 12 and 999 px, one shadow (menus and dialogs only)
- a focus ring

Components use only the variables, so a theme change touches one file. Muted text (`#65676b` on white) is
about 5.7:1 contrast, which passes WCAG AA.

**Shared components and how they work:**

| Component | Logic |
|---|---|
| `Icon` | about 12 inline SVG paths in one file, `aria-hidden` by default |
| `Avatar` | the username's initials on a background colour chosen as `palette[user.id % palette.length]`, so it's stable per user; sizes 24/32/40/80. Avatar upload is out of scope: it would need a schema change. |
| `Button` | variants primary / secondary / ghost / danger; a `loading` prop disables the button and shows a spinner, so double-submits can't happen; always `type="button"` unless it's a form's submit |
| `ConfirmDialog` | native `<dialog>` + `showModal()`, which gives focus trapping and Esc for free; returns a promise resolving to true/false; replaces `window.confirm` (`PostCard.tsx:45`) |
| `Badge` | hidden at 0, "9+" above 9, `aria-label="3 unread"` |
| `EmptyState` / `Spinner` / `InlineError` | every data view renders exactly one of: loading → error (with Retry) → empty → content |

**App shell (`Layout.tsx`):**

- One navigation list (Home, Search, Notifications, Messages, Profile, Log out), laid out purely with CSS
  media queries:

  | Width | Layout |
  |---|---|
  | ≥ 1024 px | left sidebar with labels |
  | 640–1023 px | icon-only sidebar |
  | < 640 px | bottom tab bar plus a slim top bar |

- `NavLink` sets `aria-current="page"`.
- Badges come from `RealtimeProvider.counts`.

**New routes:**

- `/posts/:id` (`PostDetail`): one `PostCard` with comments open; 403/404 show an explanation. Notifications
  link here.
- `/notifications`
- `/people` is renamed `/search`, with a redirect from the old path.

**Accessibility baseline:**

- A global `:focus-visible` ring on every interactive element. Today only inputs and the password toggle
  have one, and the composer removes its outline (`index.css:33,123,127`).
- Icon-only buttons get an `aria-label`.
- The like button gets `aria-pressed`.

**Verification:**

- **Vitest** (one dev dependency, pure functions only): `uniqueById`, `timeAgo`, avatar colour.
- Build passes.
- Keyboard-only walk through the navigation.
- No horizontal scroll at 375, 768 and 1280 px.

---

## 10. Phase 7: Page improvements (Implemented)

Phase 7 changes visuals and layout only, reusing the existing components (`PostCard`, `PostComposer`,
`Comments`, `PostList`, `PasswordInput`). It adds no product features beyond the ones listed.

| Page | What changes and how |
|---|---|
| **Feed** | composer with avatar and auto-growing textarea; skeleton rows on first load; Load more with the states from §5.1 |
| **Post card** | avatar + username + relative time (full date in `title`); Edit/Delete in a "more" menu (owner only) using `ConfirmDialog`; images use `object-fit: contain` on a neutral backdrop with `max-height: 600px` instead of the current cropping `cover` (`index.css:134`); optional Cloudinary delivery transform (`f_auto,q_auto,w_1080` inserted into the URL) for smaller files |
| **Comments** | avatar + compact layout, "View more comments" (offset), delete in a small menu |
| **Profile** | 80 px avatar, bio, stats (correct counts from §4.3); one action button driven by `follow_status`: none → Follow, `pending` → Requested (click → cancel), `accepted` → Following (click → confirm unfollow); Message; **"more" menu with Block / Unblock**. The API already supports blocking (`routers/follows.py`), but there's no UI today. Private-account placeholder; edit profile in a dialog; follow requests on your own profile only. |
| **Search** | debounced (existing 250 ms) with avatar rows and an empty/no-results state |
| **Notifications** | §6.1 behaviour, with avatars and grouped New/Earlier |
| **Chat** | list rows with avatar, preview, time and unread count; the thread header shows the other user, using a new `GET /conversations/{id}` (reuses `get_participant_conversation`). That fixes today's empty title when the conversation isn't in the list (`Chat.tsx:23,50`). Bubbles grouped by sender, day separators, sending/failed states (§8.3), the Reconnecting banner; the existing mobile single-pane behaviour stays. `aria-live="polite"` announces incoming messages. |
| **Login / Register** | the same layout with the new tokens and `Button`; field-level validation messages; `PasswordInput` unchanged |

**Verification:**

- **Visual checklist at 375 / 768 / 1280 px:**
  - no horizontal scroll
  - navigation reachable
  - images uncropped
  - dialogs usable with the keyboard and Esc
  - every data view shows correct loading, empty and error states
- No console errors.

---

## 11. Phase 8: Testing, deployment checks, documentation

**Full test run:**

- **pytest on the Neon test branch** (the existing `conftest.py` guard refuses the main DB). New tests:
  - `tests/test_identity.py` (§4)
  - `tests/test_feed.py` (§5.1)
  - `tests/test_notifications.py` (§6)
  - `tests/test_realtime.py` (§7)
  - additions to `tests/test_follows_privacy.py` (§4.3)
- `npm run build`, then Vitest.
- **Browser smoke script** (`frontend/scripts/smoke.mjs`, dependency-free, headless Edge/Chrome over the
  DevTools protocol; the same approach used during earlier verification):
  - register, log in
  - image post, like, comment
  - a second user receives the notification and the message without polling
  - badges update and clear
  - password toggle works
  - no console errors, and no requests to unexpected hosts

**Deployment checks** (a checklist only; deploying is not part of this plan):

- The backend host supports WebSockets, the deployed frontend uses `wss://`, and HTTPS sits in front.
- `CORS_ORIGINS` includes the deployed frontend origin. The WebSocket Origin check uses the same list.
- uvicorn runs **one worker**.
- `python -m app.migrate` has been run against the target database.

**Documentation:** the README gains the WebSocket design, the single-worker rule, `migrate.py`, the
notification types, and the two unread counts.

**Definition of done:**

- every phase's verification passes
- no polling while the socket is open
- the README matches the code

---

## 12. Security and privacy checklist

| Risk | Mitigation | Where |
|---|---|---|
| Weak or placeholder JWT secret | rotated (done); startup validation that never echoes values (proposed) | §4.1 |
| Duplicate identities by case or race | `UNIQUE(lower(...))` indexes and constraint-name → 409 mapping; DB error text never returned | §4.2 |
| Follower counts leaking blocks | count accepted rows only | §4.3 |
| Private or blocked content in the feed | single `WHERE` with an accepted-follow requirement and two-way block exclusion | §5.1 |
| Notifications exposing private activity | created only after the existing access checks pass; deleted on block; none for self-actions | §6.1 |
| Reading or marking others' notifications or read positions | every query filters by the current user; 404 otherwise | §6 |
| WebSocket hijack, events to the wrong user | Origin check, first-message token, server-computed recipients, close at token expiry | §7 |
| Token in logs | not in the WebSocket URL; never logged | §5.2, §7.1 |
| Large-upload abuse | `Content-Length` pre-check plus the existing byte cap | §5.2 |
| Orphaned Cloudinary images | existing delete-on-commit-failure stays; an orphan remains possible only if the process dies between upload and commit | existing |
| XSS stealing the token from `localStorage` | React escaping; never use `dangerouslySetInnerHTML`; documented trade-off | — |

---

## 13. Risks and trade-offs

| Trade-off | Why it's accepted / how it's handled |
|---|---|
| A like or follow notification remains after an unlike or unfollow | keeps dedupe simple and prevents spam from like/unlike loops |
| One uvicorn worker | needed for the in-memory manager; ample for this app; REST keeps working if the socket fails |
| A push is lost if the process dies right after a commit | REST recovery on reconnect covers it |
| A retried message send could duplicate if the first request succeeded but its response was lost | solved by idempotency keys (decision 6): one key per logical send, reused on retry, unique per sender in the DB |
| `--reload` drops sockets during development | the client reconnects automatically |
| Posts already on screen don't disappear immediately after a block or privacy change | they're gone on the next refresh; new pages already apply the rule |
| Tests are slow (about 3.5 min, network round trips to Neon) | acceptable; optional later switch to per-test transaction rollback |

---

## 14. Out of scope

- Redis, Kafka, message brokers, Celery, microservices, Kubernetes, event sourcing, multi-worker WebSocket
  fan-out
- WebSocket events for the feed, likes, comments or profiles (beyond the resulting notification)
- Ranking, recommendations, "explore" algorithms, trending
- Group chat, typing indicators, presence, read receipts shown to the sender, reactions, message
  editing/deletion, attachments, end-to-end encryption
- Push or email notifications, notification settings
- Avatar upload, stories, video, hashtags, mentions, reposts, bookmarks
- Dark theme (the tokens allow it later), UI frameworks, animation libraries
- OAuth, password reset by email, 2FA, refresh tokens, account deletion, rate limiting
- Alembic (`create_all()` plus the idempotent `migrate.py` is enough)

---

## 15. Finalized decisions

These were open in earlier drafts; they are now decided **and implemented**.

1. **Notification read status.** A notification becomes read when it's clicked, or with "Mark all as read".
   Opening `/notifications` alone marks nothing (`GET /notifications` never writes; tested).
2. **Unlike / unfollow keep their notification.** History isn't deleted when an action is reversed, and
   the partial unique indexes stop re-likes or re-follows from duplicating it.
   One deliberate exception stays as planned in §6.1: a **follow request's** notification is removed once
   the request is accepted, rejected or cancelled, because it's an actionable item (its Accept/Reject
   buttons would otherwise act on nothing). Blocking also removes notifications between the two users.
3. **Notification UI.** A dedicated `/notifications` page with "New"/"Earlier" sections, unread dots,
   inline Accept/Reject for follow requests, and "Mark all as read". No dropdown.
4. **Feed and profile posts.** `before_id` cursor pagination with `ORDER BY id DESC`. Scrolling loads older
   posts (infinite scroll with a "Load more" fallback), and clicking Home again reloads the newest. There
   are no new-post banners and no real-time feed updates.
5. **Comments** keep offset pagination (unchanged).
6. **Chat idempotency.**
   - Each logical send gets a random `Idempotency-Key` (`crypto.randomUUID()`), and "Retry" reuses it.
   - The server enforces `UNIQUE (sender_id, idempotency_key)` with `INSERT … ON CONFLICT DO NOTHING`, so
     concurrent retries create one message.
   - A replay returns the original message with **200** (a new send returns 201).
   - Reusing a key with a different body or conversation returns **409** and never returns an unrelated
     message.
   - Requests without a key behave as before.

---

## 16. Implementation notes and verification

**Differences from the plan text, and why:**

- **Upload size pre-check** is an HTTP middleware rather than a route dependency, because FastAPI parses
  form bodies before it resolves dependencies.
- **Profile of someone you blocked.** `GET /users/{id}` now returns a minimal profile with
  `blocked_by_me: true`, instead of a 403. Otherwise the Unblock button (§10) would be unreachable. The
  blocked user still gets a 403 and doesn't find the blocker in search.
- **Resync after every `ready`,** including the first connection, not only reconnects (§8.2). The
  browser smoke test showed that a message sent while a page was loading and its socket was still
  authenticating could otherwise be missed until the next event.
- **Composer race (found by the smoke test).** If an image was picked while the previous post was still
  uploading, the success handler cleared the new image. The composer now clears only what it actually
  sent.
- **`migrate.py`** also works on an empty database. It creates the tables first, then the indexes and
  column, so new setups can use it instead of `init_db`.

**Database migration applied:** `python -m app.migrate` ran on the main Neon database. It added the two
`lower(...)` unique indexes, `messages.idempotency_key` with its unique index, and the `notifications` and
`conversation_reads` tables. A second run was a no-op. No data was changed or removed.

**Test results (all actually run):**

| Check | Result |
|---|---|
| `pytest` (Neon test branch only) | **89 passed** (9 min 17 s) |
| `npm test` (Vitest) | **24 passed** |
| `npm run build` (`tsc` type-check + Vite build) | **passed** |
| `npm run smoke` (headless Edge, two users, against the running local stack) | **41/41 passed** on 3 consecutive runs |

The smoke runs left throwaway `smoke_*` / `uitest_*` accounts in the main database (there's no
account-deletion endpoint). Their posts and images were deleted.
