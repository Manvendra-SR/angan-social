"""Creating notifications and computing the two badge counts."""
from fastapi import BackgroundTasks
from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.realtime import push
from app.models.conversation import Conversation
from app.models.conversation_read import ConversationRead
from app.models.message import Message
from app.models.notification import Notification
from app.schemas.notification import Counts, NotificationOut


def notify(
    db: Session,
    *,
    recipient_id: int,
    actor_id: int,
    type: str,
    post_id: int | None = None,
    comment_id: int | None = None,
) -> Notification | None:
    """Add a notification to the current transaction.

    Call it after the action row is flushed and before commit, so the action
    and its notification are saved together or not at all. Returns None for
    self-actions and for duplicates absorbed by the unique indexes (e.g. a
    second like from the same user), in which case nothing should be pushed.
    """
    if recipient_id == actor_id:
        return None
    stmt = (
        pg_insert(Notification)
        .values(
            recipient_id=recipient_id, actor_id=actor_id, type=type,
            post_id=post_id, comment_id=comment_id,
        )
        .on_conflict_do_nothing()
        .returning(Notification.id)
    )
    new_id = db.execute(stmt).scalar()
    return db.get(Notification, new_id) if new_id else None


def delete_follow_request_notification(db: Session, owner_id: int, requester_id: int) -> None:
    """A handled or cancelled request is no longer actionable."""
    db.execute(
        delete(Notification).where(
            Notification.recipient_id == owner_id,
            Notification.actor_id == requester_id,
            Notification.type == "follow_request",
        )
    )


def unread_messages_query(user_id: int):
    """Messages from the other person newer than my read position, in all my conversations."""
    return (
        select(Message.conversation_id, func.count(Message.id).label("unread"))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .outerjoin(
            ConversationRead,
            and_(
                ConversationRead.conversation_id == Conversation.id,
                ConversationRead.user_id == user_id,
            ),
        )
        .where(
            or_(Conversation.user_a_id == user_id, Conversation.user_b_id == user_id),
            Message.sender_id != user_id,
            Message.id > func.coalesce(ConversationRead.last_read_message_id, 0),
        )
        .group_by(Message.conversation_id)
    )


def get_counts(db: Session, user_id: int) -> Counts:
    unread_notifications = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == user_id, Notification.is_read == False  # noqa: E712
        )
    )
    per_conversation = unread_messages_query(user_id).subquery()
    unread_messages = db.scalar(select(func.coalesce(func.sum(per_conversation.c.unread), 0)))
    return Counts(unread_notifications=unread_notifications, unread_messages=int(unread_messages))


def push_counts(background_tasks: BackgroundTasks, db: Session, user_id: int) -> None:
    """Send the user's current badge values (call after commit)."""
    push(background_tasks, user_id, "counts.updated", get_counts(db, user_id).model_dump())


def push_notification(background_tasks: BackgroundTasks, db: Session, notification: Notification | None) -> None:
    """Send a newly committed notification plus the recipient's new counts."""
    if notification is None:
        return
    db.refresh(notification)
    payload = NotificationOut.model_validate(notification).model_dump(mode="json")
    push(background_tasks, notification.recipient_id, "notification.created", {"notification": payload})
    push_counts(background_tasks, db, notification.recipient_id)
