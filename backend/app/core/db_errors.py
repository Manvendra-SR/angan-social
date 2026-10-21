from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

# unique constraints on users -> safe, field-specific message
USER_CONFLICTS = {
    "uq_users_username_lower": "Username already taken",
    "users_username_key": "Username already taken",
    "uq_users_email_lower": "Email already registered",
    "users_email_key": "Email already registered",
}


def constraint_name(exc: IntegrityError) -> str | None:
    """Name of the violated constraint, as reported by PostgreSQL (psycopg2)."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def user_conflict(exc: IntegrityError) -> HTTPException:
    """409 for a known users-table conflict; unknown violations are re-raised
    by the caller so they surface as a logged 500, never as DB error text."""
    detail = USER_CONFLICTS.get(constraint_name(exc))
    if detail is None:
        raise exc
    return HTTPException(status_code=409, detail=detail)
