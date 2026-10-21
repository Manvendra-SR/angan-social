from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from app.core.notifications import get_counts, push_counts, unread_messages_query
from app.core.realtime import push
from app.models.conversation_read import ConversationRead
from app.schemas.notification import Counts
from app.schemas.message import (
    ConversationCreate,
    ConversationOut,
    MarkRead,
    MessageCreate,
    MessageOut,
)
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.pagination import Page, get_page
from app.dependencies.privacy import is_blocked_between
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def get_participant_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Conversation:
    """Load a conversation the current user belongs to.

    Non-participants get 404 (not 403) so they can't even learn the
    conversation exists.
    """
    conversation = db.get(Conversation, conversation_id)
    if not conversation or not conversation.has_participant(current_user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def to_conversation_out(
    conversation: Conversation, current_user: User, last_message: Message | None, unread: int = 0
) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        other_user=conversation.other_user(current_user.id),
        last_message=last_message,
        unread_count=unread,
        updated_at=conversation.updated_at,
    )


def unread_by_conversation(db: Session, user_id: int, ids: list[int]) -> dict[int, int]:
    """Unread counts for a page of conversations, in one grouped query."""
    if not ids:
        return {}
    rows = db.execute(unread_messages_query(user_id).where(Message.conversation_id.in_(ids)))
    return {conversation_id: unread for conversation_id, unread in rows}


def latest_message(db: Session, conversation_id: int) -> Message | None:
    return db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(1)
    )


@router.post("", response_model=ConversationOut)
def start_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the conversation with another user, creating it if needed."""
    if data.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    if not db.get(User, data.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if is_blocked_between(db, current_user.id, data.user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # canonical order: smaller id is always user_a
    user_a_id, user_b_id = sorted((current_user.id, data.user_id))
    find = select(Conversation).where(
        Conversation.user_a_id == user_a_id,
        Conversation.user_b_id == user_b_id,
    )

    conversation = db.scalar(find)
    if not conversation:
        db.add(Conversation(user_a_id=user_a_id, user_b_id=user_b_id))
        try:
            db.commit()
        except IntegrityError:
            # the other user created it at the same moment
            db.rollback()
        conversation = db.scalar(find)

    unread = unread_by_conversation(db, current_user.id, [conversation.id]).get(conversation.id, 0)
    return to_conversation_out(conversation, current_user, latest_message(db, conversation.id), unread)


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    page: Page = Depends(get_page),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversations = db.scalars(
        select(Conversation)
        .options(selectinload(Conversation.user_a), selectinload(Conversation.user_b))
        .where(
            or_(
                Conversation.user_a_id == current_user.id,
                Conversation.user_b_id == current_user.id,
            )
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()

    # last message of each conversation on this page, in one query
    ids = [c.id for c in conversations]
    last_ids = (
        select(func.max(Message.id))
        .where(Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
    )
    last_messages = {
        m.conversation_id: m
        for m in db.scalars(select(Message).where(Message.id.in_(last_ids)))
    } if ids else {}

    unread = unread_by_conversation(db, current_user.id, ids)

    return [
        to_conversation_out(c, current_user, last_messages.get(c.id), unread.get(c.id, 0))
        for c in conversations
    ]


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation: Conversation = Depends(get_participant_conversation),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unread = unread_by_conversation(db, current_user.id, [conversation.id]).get(conversation.id, 0)
    return to_conversation_out(conversation, current_user, latest_message(db, conversation.id), unread)


@router.post("/{conversation_id}/read", response_model=Counts)
def mark_conversation_read(
    data: MarkRead,
    background_tasks: BackgroundTasks,
    conversation: Conversation = Depends(get_participant_conversation),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move my read position up to a message the client has displayed."""
    message = db.get(Message, data.last_read_message_id)
    if not message or message.conversation_id != conversation.id:
        raise HTTPException(status_code=404, detail="Message not found")

    # GREATEST in one statement: concurrent or stale tabs can't move it backwards
    stmt = pg_insert(ConversationRead).values(
        conversation_id=conversation.id,
        user_id=current_user.id,
        last_read_message_id=message.id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[ConversationRead.conversation_id, ConversationRead.user_id],
        set_={"last_read_message_id": func.greatest(
            ConversationRead.last_read_message_id, stmt.excluded.last_read_message_id
        )},
    )
    db.execute(stmt)
    db.commit()
    push_counts(background_tasks, db, current_user.id)  # other tabs update their badge
    return get_counts(db, current_user.id)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(
    conversation: Conversation = Depends(get_participant_conversation),
    before_id: int | None = Query(None, ge=1, description="older messages, for scrolling back"),
    after_id: int | None = Query(None, ge=0, description="newer messages, for polling"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Messages in chronological order (oldest first).

    No cursor: the latest `limit` messages.
    after_id: messages newer than that id (used for polling).
    before_id: the `limit` messages just before that id (load older history).
    Id-based cursors don't skip or repeat rows when new messages arrive,
    unlike offset pagination.
    """
    if before_id is not None and after_id is not None:
        raise HTTPException(status_code=400, detail="Use before_id or after_id, not both")

    stmt = select(Message).where(Message.conversation_id == conversation.id)

    if after_id is not None:
        stmt = stmt.where(Message.id > after_id).order_by(Message.id.asc()).limit(limit)
        return db.scalars(stmt).all()

    if before_id is not None:
        stmt = stmt.where(Message.id < before_id)
    newest_first = db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all()
    return list(reversed(newest_first))


IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    data: MessageCreate,
    response: Response,
    background_tasks: BackgroundTasks,
    conversation: Conversation = Depends(get_participant_conversation),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(
        None, alias="Idempotency-Key", pattern=IDEMPOTENCY_KEY_PATTERN,
        description="client-generated key for this send; retries reuse it",
    ),
):
    """Send a message. With an Idempotency-Key, a retry of the same send
    returns the original message (200) instead of creating a duplicate."""

    def replay_existing() -> Message | None:
        if idempotency_key is None:
            return None
        existing = db.scalar(
            select(Message).where(
                Message.sender_id == current_user.id,
                Message.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            return None
        # the same key for a different message is a client bug: never return an unrelated message
        if existing.conversation_id != conversation.id or existing.body != data.body:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key was already used for a different message"
            )
        response.status_code = status.HTTP_200_OK
        return existing

    existing = replay_existing()
    if existing is not None:
        return existing

    other = conversation.other_user(current_user.id)
    if is_blocked_between(db, current_user.id, other.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Lock the conversation row BEFORE inserting. Message ids come from a
    # sequence at INSERT time; without the lock two people sending at once could
    # commit out of id order (11 visible before 10), and a client catching up with
    # after_id=11 would never see 10. With it, a conversation's messages become
    # visible in id order, so "id > last seen" never skips anything.
    db.execute(
        select(Conversation.id).where(Conversation.id == conversation.id).with_for_update()
    )

    # ON CONFLICT DO NOTHING on (sender_id, idempotency_key): if a concurrent
    # retry inserted first, PostgreSQL waits for it and then skips our insert
    stmt = (
        pg_insert(Message)
        .values(
            conversation_id=conversation.id,
            sender_id=current_user.id,  # always from the token, never the request
            body=data.body,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=[Message.sender_id, Message.idempotency_key])
        .returning(Message.id)
    )
    new_id = db.execute(stmt).scalar()
    if new_id is None:
        db.rollback()
        return replay_existing()

    conversation.updated_at = func.now()
    db.commit()  # message insert and updated_at bump in one transaction
    message = db.get(Message, new_id)

    # push only after the commit; offline users catch up over REST
    event = {
        "conversation_id": conversation.id,
        "message": MessageOut.model_validate(message).model_dump(mode="json"),
    }
    # my tabs get my idempotency key back, so the sending tab can match its
    # "sending" bubble exactly; the other person never sees it
    push(background_tasks, current_user.id, "message.created", {**event, "idempotency_key": idempotency_key})
    push(background_tasks, other.id, "message.created", event)
    push_counts(background_tasks, db, other.id)
    return message
