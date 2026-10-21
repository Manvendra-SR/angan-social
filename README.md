# Social Media Platform

A small social media app: a **FastAPI + PostgreSQL** REST API with a **React + TypeScript** frontend.
Users can post text and images, comment, like, follow (including private accounts), block, get
notifications, and chat one-to-one in real time.

| Layer | Tech |
|---|---|
| API | FastAPI, Pydantic, SQLAlchemy 2.0 (sync), psycopg2, WebSockets (Starlette) |
| Database | PostgreSQL (Neon) |
| Auth | JWT (python-jose), Argon2 password hashing (passlib) |
| Images | Cloudinary |
| Frontend | React 19, React Router, Vite, TypeScript, plain CSS |
| Tests | pytest against a separate Neon branch; Vitest; a dependency-free browser smoke script |

## Features

- Register / log in (JWT), profile editing (username, bio, private flag), user search
- Posts with text and/or an image; edit, delete; post detail page
- Chronological feed: your posts, every public account's posts, and private accounts that accepted you
- Comments and likes (one like per user per post)
- Follows with private accounts (requests → accept/reject), blocking and unblocking
- Notifications for follow requests, new followers, accepted requests, likes and comments
- One-to-one messages with unread counts, real-time delivery and safe retries

## Project structure

```
backend/
  app/
    main.py              FastAPI app, CORS, upload-size guard, routers
    init_db.py           create tables on a new database
    migrate.py           bring an existing database up to date (idempotent, additive)
    core/                config, database, security (JWT), media (Cloudinary), notifications,
                         realtime (WebSocket connection manager), db_errors
    dependencies/        get_db, get_current_user, pagination (offset + cursor), privacy checks
    models/              one file per table
    schemas/             request/response models
    routers/             auth, users, posts, comments, likes, follows, conversations, notifications, ws
  tests/                 pytest suite
frontend/
  src/
    api.ts               typed fetch wrapper for every endpoint
    auth.tsx             auth context (token in localStorage)
    realtime.tsx         the shared WebSocket (RealtimeProvider); realtimeLogic.ts = pure helpers
    hooks/useCursorList  newest-first lists with before_id ("load more" / infinite scroll)
    pages/               Feed, PostDetail, Profile, Search, Notifications, Chat, Login, Register
    components/          Layout (app shell), PostCard, PostComposer, Comments, Avatar, Icon, Menu,
                         ConfirmDialog, LoadMore, Badge, States, PasswordInput
    styles/              tokens.css (design tokens), base.css, app.css
  scripts/smoke.mjs      end-to-end browser check
```

Request lifecycle: route → `get_current_user` (decodes JWT, loads user) → access check
(e.g. `get_accessible_post`) → Pydantic-validated body → SQLAlchemy query/commit → response,
then (for chat and notifications) a WebSocket push after the commit.

## Database schema

| Table | Key columns and constraints |
|---|---|
| `users` | `username`, `email`, `password_hash`, `is_private`, `bio`; UNIQUE `lower(username)` and `lower(email)` |
| `posts` | `user_id` FK → users (CASCADE), `content`, `image_url`, `image_public_id` |
| `comments` | `post_id` FK → posts, `user_id` FK → users (both CASCADE) |
| `likes` | composite PRIMARY KEY (`post_id`, `user_id`), which prevents duplicate likes |
| `follows` | UNIQUE (`follower_id`, `following_id`), CHECK follower ≠ following, `status` pending/accepted/blocked |
| `conversations` | `user_a_id < user_b_id` (CHECK) + UNIQUE pair: one conversation per two users |
| `messages` | `conversation_id` FK, `sender_id` FK, `body` (CHECK non-empty), `idempotency_key`; UNIQUE (`sender_id`, `idempotency_key`) |
| `notifications` | `recipient_id`, `actor_id`, `type`, `post_id`, `comment_id`, `is_read`; CHECKs per type; partial UNIQUE indexes for dedupe |
| `conversation_reads` | PK (`conversation_id`, `user_id`), `last_read_message_id` |

Like, comment and follower counts are computed with correlated subqueries (`column_property`).
Follower counts only include `accepted` follows.

## Design decisions

- **Authentication vs authorization.** The JWT proves *who* you are (`sub` = user id). Authorization is
  checked per request: ownership for edit/delete (403), privacy/blocks for reading posts
  (`dependencies/privacy.py`), participation for conversations (404 for outsiders).
- **Case-insensitive identity.** Usernames keep their display casing (`Boba`) but are unique ignoring
  case. Emails are stored lowercase. The Python check gives a friendly early 409, while the unique
  `lower(...)` indexes are the real guard: two simultaneous sign-ups for `Manav`/`manav` can't both succeed.
  The violated constraint's name is mapped to "Username already taken" or "Email already registered";
  database error text is never returned.
- **Secrets.** The app refuses to start if `SECRET_KEY` is missing, shorter than 32 characters, or the
  example placeholder. Validation errors never echo the value, and secrets are `SecretStr`, so
  printing the settings shows `**********`.
- **Feed.** One query with OR-ed conditions (own posts, public accounts, accepted follows) minus blocks in
  both directions. It's a single `WHERE`, not a `UNION`, so a post is never returned twice. It's
  chronological, with no ranking.
- **Cursor pagination.** The feed, profile posts and notifications are ordered by `id DESC`, and the next
  page asks for `before_id = <last id shown>`. New rows get higher ids, so they can't shift later pages
  (no repeats, no skips). Scrolling loads older posts; clicking Home again reloads the newest.
  Comments keep `limit`/`offset` (oldest first, append-only).
- **Notifications** are written **in the same transaction** as the like, comment or follow that causes
  them, so a failed action never leaves one behind. Duplicates are absorbed by partial unique indexes
  (`ON CONFLICT DO NOTHING`), so like → unlike → like produces one notification. Unlike/unfollow keep
  the history. A follow request's notification is removed once it's accepted, rejected or cancelled,
  because it's no longer actionable. Blocking removes notifications between the two users. Opening
  `/notifications` doesn't mark anything read: clicking a row or "Mark all as read" does.
- **Direct messages don't create notifications.** One row per message would flood the list. Instead,
  `conversation_reads` stores each user's read position, and unread = messages from the other person
  above it. The client reports the newest message it actually displayed; the server stores
  `GREATEST(old, new)`, so a stale tab can't move it backwards.
- **Idempotent sends.** The frontend creates a random `Idempotency-Key` for each message and reuses it for
  retries. The `(sender_id, idempotency_key)` unique index plus `INSERT … ON CONFLICT DO NOTHING` means a
  retried or concurrent duplicate returns the original message (200) instead of creating another.
  Reusing a key for a different message is rejected with 409.
- **Real time.** One WebSocket per browser tab (`GET /ws`), used only for server → client pushes:
  `message.created`, `notification.created`, `counts.updated` (absolute badge values, so a duplicate or
  missed event can't make a badge drift).
  - **Authentication:** the token goes in the first message (`{"type":"auth","token":…}`), not the URL
    (URLs end up in access logs), and the `Origin` must be an allowed frontend origin.
  - **Close codes:** 4401 bad or expired token, 4403 origin, 4408 no auth within 10 s.
  - **Order of operations:** events are pushed after the commit (FastAPI background tasks), and
    everything is in PostgreSQL first. The socket is never the storage.
  - **Recovery:** after every connect or reconnect, the client re-fetches counts, the conversation list
    and missed messages over REST.
  - **Reconnecting:** reconnects back off 1 → 30 s with jitter. If the socket is down for more than 5 s,
    the chat shows "Reconnecting…" and polls every 15 s.
- **Single worker.** The WebSocket registry lives in the process's memory, so run **one** uvicorn worker
  (the default). Several workers would need a shared pub/sub such as Redis, which this app doesn't need.
- **Image uploads.**
  - **Size:** requests with a `Content-Length` over the limit are rejected before the body is read. The
    server then reads at most 5 MB + 1 byte (413 if larger).
  - **Type:** checked from the magic bytes (JPEG/PNG/WebP, otherwise 415). The client's filename and MIME
    type are ignored.
  - **Storage:** Cloudinary stores the file, while Postgres keeps only the URL and `public_id`.
  - **Cleanup:** a failed DB commit deletes the uploaded file, and so do deleting or replacing the post's
    image.
  - *Trade-off:* Cloudinary URLs are public to anyone who has the link.
- **Token storage.** The JWT is kept in `localStorage` and sent as a Bearer header (no cookies, so no CSRF).
  The trade-off is exposure to XSS; React escapes output and `dangerouslySetInnerHTML` isn't used.
- **Schema changes without a migration framework.** `init_db` (`create_all`) creates missing tables but
  never alters existing ones. `python -m app.migrate` applies additions to an existing database:
  - it **stops if existing users collide case-insensitively**, so a person can fix them first
  - then creates the `lower(...)` indexes, adds `messages.idempotency_key` and its index, and creates any
    new tables

  It's safe to run repeatedly and never drops anything.

## Local setup

Prerequisites: Python 3.12+, Node 22+, a Neon project (main branch + a `test` branch), a Cloudinary account.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the values
python -m app.migrate           # new or existing database: creates/updates the schema
uvicorn app.main:app --reload --port 8080
```

API docs: http://127.0.0.1:8080/docs

### Frontend

```bash
cd frontend
npm install
cp .env.example .env            # VITE_API_URL=http://127.0.0.1:8080
npm run dev                     # http://localhost:5173
```

`VITE_API_URL` is read when Vite starts (restart after changing it). The WebSocket URL is derived from
it (`http` → `ws`). Vite is pinned to port 5173 (`strictPort`), so it never drifts to a port that
`CORS_ORIGINS` doesn't allow.

### Tests

```bash
cd backend && pytest            # uses TEST_DATABASE_URL only (refuses to run against the main DB)
cd frontend && npm test         # Vitest: pure logic (utils, realtime helpers)
cd frontend && npm run build    # type-check + production build
cd frontend && npm run smoke    # end-to-end in headless Edge/Chrome (needs both servers running)
```

The smoke script registers two throwaway `smoke_*` users. It checks real-time notifications and
messages, read state, reconnect recovery, idempotent retries, responsive layouts, and the console and
network. Its posts are deleted at the end.

## Environment variables

Backend (`backend/.env`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Neon direct connection (used by `init_db` / `migrate`) |
| `DATABASE_URL_POOLED` | Neon pooled connection (used by the API; optional) |
| `TEST_DATABASE_URL` | Neon test branch, used only by pytest |
| `SECRET_KEY` | JWT signing key: at least 32 random characters (checked at startup) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | default 60 (a WebSocket is closed when its token expires) |
| `CORS_ORIGINS` | comma-separated frontend origins (also checked for WebSockets) |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Cloudinary credentials |
| `MAX_IMAGE_SIZE_MB` | default 5 |

Frontend (`frontend/.env`): `VITE_API_URL` (backend URL, default `http://127.0.0.1:8080`).

## Deployment checklist

This project is not deployed yet; these are the checks for when it is.

- The backend host supports WebSockets, and the deployed frontend uses `https://`/`wss://`
  (set `VITE_API_URL` to the `https://` API URL).
- `CORS_ORIGINS` contains the deployed frontend origin (the WebSocket Origin check uses the same list).
- uvicorn runs **one worker**.
- `python -m app.migrate` has been run against the target database.

## Not included (by design)

Group chats, typing indicators, presence, read receipts shown to the sender, push/email notifications,
ranking or recommendations, video, avatar uploads, Redis or message brokers, multi-worker fan-out.
