import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.media import MAX_IMAGE_BYTES
from app.routers import (
    auth, users, posts, comments, follows, likes, conversations, notifications, ws,
)

# never log tokens, passwords or database URLs
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Social Media API")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(follows.router)
app.include_router(likes.router)
app.include_router(conversations.router)
app.include_router(notifications.router)
app.include_router(ws.router)

# an image plus generous room for the other multipart fields
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 64 * 1024


@app.middleware("http")
async def reject_oversized_requests(request: Request, call_next):
    """Reject a too-large upload from its Content-Length header, before the
    body is received and parsed. media.read_image still enforces the exact
    limit (e.g. for chunked requests without a Content-Length)."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request is larger than {settings.MAX_IMAGE_SIZE_MB} MB"},
        )
    return await call_next(request)


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
