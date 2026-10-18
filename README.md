# Social Media Platform

A small social media app: a **FastAPI + PostgreSQL** REST API with a **React + TypeScript** frontend.
Users can post text and images, comment, like, follow (including private accounts), block, and chat one-to-one.

| Layer | Tech |
|---|---|
| API | FastAPI, Pydantic, SQLAlchemy 2.0 (sync), psycopg2 |
| Database | PostgreSQL (Neon) |
| Auth | JWT (python-jose), Argon2 password hashing (passlib) |
| Images | Cloudinary |
| Frontend | React 19, React Router, Vite, TypeScript, plain CSS |
| Tests | pytest + FastAPI TestClient against a separate Neon branch |

## Features

- Register / log in (JWT), view and edit profile (username, bio, private flag), user search
- Posts: create (text and/or image), edit, delete, paginated feed and per-user listing
- Comments (add, edit, delete, paginated) and likes (one per user per post)
- Follows with private accounts (follow requests → accept/reject) and blocking
- One-to-one direct messages with cursor pagination; the frontend polls every 3 s

## Project structure

```
backend/
  app/
    main.py              FastAPI app, CORS, routers
    init_db.py           creates tables (Base.metadata.create_all)
    core/                config (env vars), database engine, JWT/password security, Cloudinary media
    dependencies/        get_db, get_current_user, pagination, privacy/access checks
    models/              SQLAlchemy models (one file per table)
    schemas/             Pydantic request/response models
    routers/             auth, users, posts, comments, likes, follows, conversations
  tests/                 pytest suite
frontend/
  src/
    api.ts               typed fetch wrapper for every endpoint
    auth.tsx             auth context (token in localStorage)
    pages/               Login, Register, Feed, Profile, People, Chat
    components/          Layout, PostComposer, PostCard, PostList, Comments
```

Request lifecycle: route → `get_current_user` (decodes JWT, loads user) → access check
(e.g. `get_accessible_post`) → Pydantic-validated body → SQLAlchemy query/commit → response model.

## Database schema

| Table | Key columns and constraints |
|---|---|
| `users` | `username` UNIQUE, `email` UNIQUE, `password_hash`, `is_private`, `bio` |
| `posts` | `user_id` FK → users (CASCADE), `content`, `image_url`, `image_public_id` |
| `comments` | `post_id` FK → posts, `user_id` FK → users (both CASCADE) |
| `likes` | composite PRIMARY KEY (`post_id`, `user_id`) – prevents duplicate likes |
| `follows` | UNIQUE (`follower_id`, `following_id`), CHECK follower ≠ following, `status` ENUM pending/accepted/blocked |
| `conversations` | `user_a_id`, `user_b_id` FKs, CHECK `user_a_id < user_b_id`, UNIQUE (`user_a_id`, `user_b_id`) |
| `messages` | `conversation_id` FK (CASCADE), `sender_id` FK, `body` (CHECK non-empty), INDEX (`conversation_id`, `id`) |

Like/comment counts are computed with correlated subqueries (`column_property`), not stored.

## Design decisions

- **Authentication vs authorization.** The JWT proves *who* you are (`sub` = user id). Authorization is
  checked per request: ownership for edit/delete (403), privacy/blocks for reading posts
  (`dependencies/privacy.py`), participation for conversations.
- **Duplicate likes** are prevented by the database (composite primary key); the API turns the
  `IntegrityError` into `409`. This is race-safe, unlike a check-then-insert.
- **One conversation per pair.** The pair is stored sorted (`user_a_id < user_b_id`) so the UNIQUE
  constraint holds regardless of who starts the chat. Concurrent creation is handled by catching the
  `IntegrityError` and re-reading.
- **Message privacy.** Non-participants get `404`, not `403`, so conversation ids don't leak.
  The sender is always taken from the token; the request body has no `sender_id`.
- **Pagination.** Feed/comments/lists use `limit`/`offset`. Messages use id cursors
  (`before_id` for history, `after_id` for polling), which don't skip or repeat rows when new messages arrive.
- **Polling instead of WebSockets.** Simpler (plain REST, stateless, works behind any host) at the cost of
  up to ~3 s delivery delay and some extra requests.
- **Image uploads.** The server reads at most 5 MB + 1 byte (413 if larger), detects the type from the
  file's magic bytes (JPEG/PNG/WebP, otherwise 415) and ignores the client's filename and MIME type.
  Cloudinary stores the file under a generated name; Postgres stores only the URL and `public_id`.
  If the DB commit fails after upload, the image is deleted; deleting a post or replacing its image also
  deletes the old file. Cloudinary errors return 502 instead of crashing.
  *Trade-off:* Cloudinary URLs are public to anyone who has the link, so images of private accounts are
  hidden only by not exposing their URLs.
- **Token storage.** The JWT is kept in `localStorage` and sent as a Bearer header (no cookies, so no CSRF).
  The trade-off is exposure to XSS; httpOnly cookies would avoid that but need CSRF handling.
- **Schema creation.** `python -m app.init_db` calls `Base.metadata.create_all()`. It only creates
  missing tables; it **never alters existing tables**. After changing a model, either reset a dev
  database (`--reset`, deletes data) or apply an `ALTER TABLE` by hand. A migration tool (Alembic)
  would be the next step for a long-lived database.
- **Neon connections.** The API uses the pooled URL (PgBouncer) with `pool_pre_ping` because Neon
  suspends idle compute; table creation uses the direct URL.

## Local setup

Prerequisites: Python 3.12+, Node 20+, a Neon project (main branch + a `test` branch), a Cloudinary account.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the values
python -m app.init_db           # create tables (once)
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

`VITE_API_URL` defaults to `http://127.0.0.1:8080` and is read when Vite starts, so restart
`npm run dev` after changing it. Vite is pinned to port 5173 (`strictPort`): if the port is busy it
exits instead of moving to 5174, which would not be an allowed CORS origin. If you run the frontend
elsewhere, add that origin to the backend's `CORS_ORIGINS`.

### Tests

```bash
cd backend
pytest                          # backend suite (uses TEST_DATABASE_URL only)
cd ../frontend
npm run build                   # type-check + production build
```

The test suite drops and recreates all tables in `TEST_DATABASE_URL`. It refuses to start if that
variable is missing or equals the main database URL. Cloudinary is replaced with a fake in tests.

## Environment variables

Backend (`backend/.env`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Neon direct connection (used for `init_db`) |
| `DATABASE_URL_POOLED` | Neon pooled connection (used by the API; optional) |
| `TEST_DATABASE_URL` | Neon test branch, used only by pytest |
| `SECRET_KEY` | JWT signing key (long random string) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | default 60 |
| `CORS_ORIGINS` | comma-separated frontend origins (default localhost:5173) |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Cloudinary credentials |
| `MAX_IMAGE_SIZE_MB` | default 5 |

Frontend (`frontend/.env`): `VITE_API_URL` (backend URL, default `http://127.0.0.1:8080`).

## Not included (by design)

Group chats, real-time delivery, read receipts, notifications, video, migrations, Docker/deployment.
