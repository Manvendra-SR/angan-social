from dataclasses import dataclass
from fastapi import Query


@dataclass
class Page:
    limit: int
    offset: int


def get_page(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page:
    return Page(limit=limit, offset=offset)
