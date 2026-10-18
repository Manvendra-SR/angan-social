from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, users, posts, comments, follows, likes, conversations

app = FastAPI(title="Social Media API")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(follows.router)
app.include_router(likes.router)
app.include_router(conversations.router)


# The JWT is sent in the Authorization header (no cookies), so credentials
# are not needed; only the configured frontend origins are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
