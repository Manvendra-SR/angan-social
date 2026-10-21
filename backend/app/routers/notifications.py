from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload
from app.core.notifications import get_counts, push_counts
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.dependencies.pagination import CursorPage, get_cursor_page
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import Counts, NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    page: CursorPage = Depends(get_cursor_page),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """My notifications, newest first. Listing never marks anything as read."""
    stmt = (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.recipient_id == current_user.id)
    )
    if page.before_id is not None:
        stmt = stmt.where(Notification.id < page.before_id)
    return db.scalars(stmt.order_by(Notification.id.desc()).limit(page.limit)).all()


@router.post("/read-all", response_model=Counts)
def mark_all_read(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.execute(
        update(Notification)
        .where(Notification.recipient_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    db.commit()
    push_counts(background_tasks, db, current_user.id)  # keeps my other tabs in sync
    return get_counts(db, current_user.id)


@router.post("/{notification_id}/read", response_model=Counts)
def mark_read(
    notification_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = db.get(Notification, notification_id)
    # someone else's notification looks exactly like a missing one
    if not notification or notification.recipient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notification.is_read:
        notification.is_read = True
        db.commit()
        push_counts(background_tasks, db, current_user.id)
    return get_counts(db, current_user.id)
