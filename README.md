# Angan

Angan (आँगन, "courtyard") is a social media app for sharing posts and photos, following people, and
chatting one-to-one in real time.

## Features

### Accounts and profiles
- **Sign up and log in:** sign up with a username, email and password (at least 8 characters).
  Usernames keep the capitalisation you choose, but `Manav` and `manav` count as the same name, so two
  people can't register look-alikes. The same goes for email addresses.
- **Profile:** shows your posts, follower and following counts, and a short bio. You can change your
  username, bio and privacy setting at any time.
- **Private accounts:** only approved followers can see your posts. Anyone can still see your basic
  profile and send a follow request. If you switch from private to public, waiting requests are accepted
  automatically.
- **Account deletion:** Profile → ⋯ → Delete account. You confirm by typing your username. See
  [Account deletion](#account-deletion) for what is removed.

### Posts, likes and comments
- **Posts:** write a text post, add a photo (JPEG, PNG or WebP, up to 5 MB), or both. Photos are stored on
  Cloudinary and shown uncropped.
- **Editing:** you can edit or delete your own posts. Deleting a post also deletes its photo.
- **Likes:** like and unlike any post you can see. Each person can like a post only once.
- **Comments:** comment on posts and delete your own comments. Comments load oldest first.
- **Post pages:** every post has its own page, which notifications link to.

### Feed
- **What it shows:** a chronological feed (newest first, no ranking) with your own posts, posts from all
  public accounts (so you can discover people), and posts from private accounts that accepted your follow
  request.
- **Loading more:** older posts load as you scroll. Clicking **Home** again shows the newest posts.
- **Blocked accounts:** their posts never appear, in either direction.

### Following and blocking
- **Following:** follow public accounts instantly; for private accounts, the request waits until it's
  accepted. Pending requests appear on your profile with Accept and Reject buttons, and you can cancel a
  request you sent.
- **Blocking:** from someone's profile (⋯ → Block). Blocking hides both people's posts and profiles from
  each other, removes follows between you, and stops messages in both directions. You can unblock from the
  same menu.

### Search
- **Finding people:** search by username as you type. Accounts that blocked you don't appear in your
  results.

### Notifications
- **What notifies you:** a follow request, a new follower, an accepted request, a like on your post, or a
  comment on your post.
- **Live updates:** new notifications appear immediately, and the bell icon shows how many are unread.
- **Read status:** a notification is marked read when you click it, which takes you to the related post
  or profile. **Mark all as read** clears them all. Just opening the page doesn't mark anything read.
- **Follow requests:** can be accepted or rejected directly from the notification.
- **No duplicates:** liking, unliking and liking again doesn't send repeat notifications.

### Messages
- **Conversations:** start a private chat from anyone's profile with the **Message** button. Each pair of
  people has a single conversation.
- **Live delivery:** messages arrive instantly. The Messages icon shows your total unread messages, and
  each conversation shows its own unread count.
- **Read status:** opening a conversation marks its messages as read.
- **History:** older messages load on request.
- **Failed sends:** a message that fails to send shows **Retry**, and retrying never creates a duplicate.
- **Offline catch-up:** if your connection drops, Angan shows "Reconnecting…", keeps checking for new
  messages, and catches up on everything you missed once you're back online.

## Tech stack

| Part | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, WebSockets |
| Database | PostgreSQL (Neon) |
| Authentication | JWT, Argon2 password hashing |
| Image storage | Cloudinary |
| Frontend | React, TypeScript, React Router, Vite, plain CSS |

## Running locally

You need Python 3.12+, Node.js 22+, a PostgreSQL database (for example a free
[Neon](https://neon.tech) project) and a [Cloudinary](https://cloudinary.com) account.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then fill in the values below
python -m app.migrate             # creates or updates the database tables
uvicorn app.main:app --port 8080
```

The API runs at http://127.0.0.1:8080 (interactive docs at `/docs`).

`backend/.env`:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL |
| `DATABASE_URL_POOLED` | optional: pooled connection URL used by the running app (Neon) |
| `SECRET_KEY` | random string of at least 32 characters, used to sign login tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | login session length (default `60`) |
| `CORS_ORIGINS` | frontend address(es), comma-separated (default `http://localhost:5173,http://127.0.0.1:5173`) |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Cloudinary credentials |
| `MAX_IMAGE_SIZE_MB` | largest photo upload (default `5`) |

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Run the backend as a single process (the default). Live chat and notifications rely on it.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env              # VITE_API_URL=http://127.0.0.1:8080
npm run dev
```

Open http://localhost:5173 and create an account.

`frontend/.env`:

| Variable | Description |
|---|---|
| `VITE_API_URL` | backend address (default `http://127.0.0.1:8080`) |

## Account deletion

Deleting your account (Profile → ⋯ → Delete account) permanently removes your profile, posts and their
photos, your comments and likes, follows, notifications, and your one-to-one conversations, including the
other person's messages in them. Other users' accounts and posts are not affected.
