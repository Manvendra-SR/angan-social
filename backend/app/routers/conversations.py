from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from app.schemas.message import (
    ConversationCreate,
    ConversationOut,
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
    conversation: Conversation, current_user: User, last_message: Message | None
) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        other_user=conversation.other_user(current_user.id),
        last_message=last_message,
        updated_at=conversation.updated_at,
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

    last_message = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(1)
    )
    return to_conversation_out(conversation, current_user, last_message)


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

    return [
        to_conversation_out(c, current_user, last_messages.get(c.id))
        for c in conversations
    ]


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


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    data: MessageCreate,
    conversation: Conversation = Depends(get_participant_conversation),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    other = conversation.other_user(current_user.id)
    if is_blocked_between(db, current_user.id, other.id):
        raise HTTPException(status_code=403, detail="Access denied")

    message = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,  # always from the token, never the request
        body=data.body,
    )
    db.add(message)
    conversation.updated_at = func.now()
    db.commit()  # message insert and updated_at bump in one transaction
    db.refresh(message)
    return message
