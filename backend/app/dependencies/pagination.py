from dataclasses import dataclass
from fastapi import Query


@dataclass
class Page:
    """Offset pagination (comments, follow requests, conversations)."""
    limit: int
    offset: int


def get_page(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page:
    return Page(limit=limit, offset=offset)


@dataclass
class CursorPage:
    """Cursor pagination for newest-first lists (feed, user posts, notifications).

    Results are ordered by id DESC and the next page asks for ids below the
    last one shown. Rows inserted meanwhile get higher ids, so they can't
    shift the window: no repeats, no skips.
    """
    limit: int
    before_id: int | None


def get_cursor_page(
    limit: int = Query(20, ge=1, le=100),
    before_id: int | None = Query(None, ge=1, description="return items with a smaller id"),
) -> CursorPage:
    return CursorPage(limit=limit, before_id=before_id)
