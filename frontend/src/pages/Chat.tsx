/**
 * Direct messages. New messages arrive over the shared WebSocket; REST is used
 * for history, sending and recovery. While the socket is down for more than
 * 5 s, the open thread falls back to polling every 15 s.
 */
import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import Avatar from "../components/Avatar";
import Badge from "../components/Badge";
import Icon from "../components/Icon";
import { EmptyState, InlineError, Spinner } from "../components/States";
import { useRealtime, useRealtimeDown, useRealtimeEvents } from "../realtime";
import { initialThread, newestId, threadReducer, type PendingMessage } from "../chatThread";
import type { Conversation, Message } from "../types";
import { errorText, fullDate, newIdempotencyKey, timeAgo } from "../utils";

const FALLBACK_POLL_MS = 15000;
const HISTORY_PAGE = 50;

const byRecent = (a: Conversation, b: Conversation) =>
  new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime() || b.id - a.id;

export default function Chat() {
  const params = useParams();
  const activeId = params.id ? Number(params.id) : null;
  const { user } = useAuth();
  const down = useRealtimeDown();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listStatus, setListStatus] = useState<"loading" | "ready" | "error">("loading");
  const [listError, setListError] = useState("");

  // refs let the event handler see current values without re-subscribing
  const conversationsRef = useRef(conversations);
  conversationsRef.current = conversations;
  const activeRef = useRef(activeId);
  activeRef.current = activeId;

  const loadList = useCallback(async () => {
    try {
      setConversations(await api.conversations());
      setListStatus("ready");
    } catch (err) {
      setListError(errorText(err));
      setListStatus((s) => (s === "ready" ? "ready" : "error")); // keep a list we already have
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  // fallback: keep the list fresh while the socket is down
  useEffect(() => {
    if (!down) return;
    const timer = setInterval(loadList, FALLBACK_POLL_MS);
    return () => clearInterval(timer);
  }, [down, loadList]);

  const applyMessage = useCallback((message: Message) => {
    if (!conversationsRef.current.some((c) => c.id === message.conversation_id)) {
      loadList(); // a conversation we haven't seen yet
      return;
    }
    const mine = message.sender_id === user!.id;
    const open = message.conversation_id === activeRef.current;
    setConversations((prev) => prev
      .map((c) => (c.id !== message.conversation_id ? c : {
        ...c,
        last_message: c.last_message && c.last_message.id > message.id ? c.last_message : message,
        updated_at: message.created_at,
        unread_count: mine || open ? c.unread_count : c.unread_count + 1,
      }))
      .sort(byRecent));
  }, [loadList, user]);

  useRealtimeEvents((event) => {
    if (event.type === "message.created") applyMessage(event.message);
    else if (event.type === "resync") loadList();
  });

  const markedRead = useCallback((conversationId: number) => {
    setConversations((prev) => prev.map((c) => (c.id === conversationId ? { ...c, unread_count: 0 } : c)));
  }, []);

  return (
    <div className={`chat ${activeId ? "has-active" : ""}`}>
      <aside className="card conversation-list" aria-label="Conversations">
        <h1 className="page-title">Messages</h1>
        {listStatus === "loading" && <Spinner />}
        {listStatus === "error" && <InlineError message={listError} onRetry={loadList} />}
        {listStatus === "ready" && conversations.length === 0 && (
          <EmptyState title="No conversations yet">
            Open someone's profile from <Link to="/search">Search</Link> and press Message.
          </EmptyState>
        )}
        <ul>
          {conversations.map((c) => (
            <li key={c.id}>
              <Link
                to={`/messages/${c.id}`}
                className={`conversation ${c.id === activeId ? "active" : ""} ${c.unread_count ? "unread" : ""}`}
                aria-current={c.id === activeId ? "page" : undefined}
              >
                <Avatar user={c.other_user} size={40} />
                <span className="conversation-text">
                  <span className="conversation-top">
                    <b>{c.other_user.username}</b>
                    {c.last_message && (
                      <time className="muted small" dateTime={c.last_message.created_at}>
                        {timeAgo(c.last_message.created_at)}
                      </time>
                    )}
                  </span>
                  <span className="muted small ellipsis">
                    {c.last_message
                      ? `${c.last_message.sender_id === user!.id ? "You: " : ""}${c.last_message.body}`
                      : "No messages yet"}
                  </span>
                </span>
                <Badge count={c.unread_count} label="unread messages" />
              </Link>
            </li>
          ))}
        </ul>
      </aside>

      {activeId ? (
        <Thread key={activeId} conversationId={activeId} onRead={markedRead} onSent={applyMessage} />
      ) : (
        <section className="card thread thread-empty">
          <Icon name="message" size={40} />
          <p>Select a conversation</p>
        </section>
      )}
    </div>
  );
}

interface ThreadProps {
  conversationId: number;
  onRead: (conversationId: number) => void;
  onSent: (message: Message) => void;
}

function Thread({ conversationId, onRead, onSent }: ThreadProps) {
  const { user } = useAuth();
  const { setCounts } = useRealtime();
  const down = useRealtimeDown();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  // messages + pending sends; every source is merged by id (see chatThread.ts)
  const [thread, dispatch] = useReducer(threadReducer, initialThread);
  const { messages, pending } = thread;
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<{ status: number; message: string } | null>(null);
  const [hasOlder, setHasOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const lastRead = useRef(0);

  const statusRef = useRef(status);
  statusRef.current = status;
  const resyncPending = useRef(false);
  const lastIdRef = useRef(0);
  lastIdRef.current = newestId(thread);

  /** Fetch everything after the newest message we have (recovery and fallback polling). */
  const catchUp = useCallback(async () => {
    try {
      for (;;) {
        const newer = await api.messages(conversationId, { after: lastIdRef.current });
        if (newer.length === 0) break;
        dispatch({ type: "merge", messages: newer });
        lastIdRef.current = Math.max(lastIdRef.current, newer[newer.length - 1].id);
        if (newer.length < HISTORY_PAGE) break;
      }
    } catch {
      /* temporary network problem: the next attempt will catch up */
    }
  }, [conversationId]);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [conv, history] = await Promise.all([api.conversation(conversationId), api.messages(conversationId)]);
      setConversation(conv);
      // merge, don't replace: a message pushed while this request was in flight stays
      dispatch({ type: "merge", messages: history });
      setHasOlder(history.length === HISTORY_PAGE);
      setStatus("ready");
      lastIdRef.current = Math.max(lastIdRef.current, history[history.length - 1]?.id ?? 0);
      if (resyncPending.current) {
        resyncPending.current = false;
        catchUp();
      }
    } catch (err) {
      setLoadError({ status: err instanceof ApiError ? err.status : 0, message: errorText(err) });
      setStatus("error");
    }
  }, [conversationId, catchUp]);

  useEffect(() => { load(); }, [load]);

  useRealtimeEvents((event) => {
    if (event.type === "resync") {
      // before the first page has arrived, catch up right after it does: a message
      // committed between that page's query and the socket subscribing is in neither
      if (statusRef.current === "ready") catchUp();
      else resyncPending.current = true;
    } else if (event.type === "message.created" && event.conversation_id === conversationId) {
      // our own send echoed back (possibly before its REST response): the server
      // includes our idempotency key, so the matching "sending" bubble is replaced.
      // Without a key (other person, or our other tab) it's just merged by id.
      if (event.idempotency_key) dispatch({ type: "confirmed", key: event.idempotency_key, message: event.message });
      else dispatch({ type: "merge", messages: [event.message] });
    }
  });

  // fallback while the socket is unavailable
  useEffect(() => {
    if (!down || status !== "ready") return;
    catchUp();
    const timer = setInterval(catchUp, FALLBACK_POLL_MS);
    return () => clearInterval(timer);
  }, [down, status, catchUp]);

  // mark as read: only messages actually displayed, only while the tab is visible
  const markRead = useCallback(() => {
    if (document.visibilityState !== "visible") return;
    const newestFromOther = [...messages].reverse().find((m) => m.sender_id !== user!.id);
    if (!newestFromOther || newestFromOther.id <= lastRead.current) return;
    const upTo = lastIdRef.current;
    lastRead.current = upTo;
    api.markConversationRead(conversationId, upTo)
      .then((counts) => { setCounts(counts); onRead(conversationId); })
      .catch(() => { lastRead.current = 0; }); // try again on the next change
  }, [messages, conversationId, user, setCounts, onRead]);

  useEffect(() => { if (status === "ready") markRead(); }, [status, markRead]);
  useEffect(() => {
    const onVisible = () => markRead();
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [markRead]);

  // keep the view pinned to the newest message unless the user scrolled up
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  function onScroll() {
    const el = scroller.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  async function loadOlder() {
    if (loadingOlder || messages.length === 0) return;
    setLoadingOlder(true);
    const el = scroller.current;
    const fromBottom = el ? el.scrollHeight - el.scrollTop : 0;
    try {
      const older = await api.messages(conversationId, { before: messages[0].id });
      setHasOlder(older.length === HISTORY_PAGE);
      stickToBottom.current = false;
      dispatch({ type: "merge", messages: older });
      // keep the same message under the user's eyes after prepending
      requestAnimationFrame(() => { if (el) el.scrollTop = el.scrollHeight - fromBottom; });
    } catch {
      /* the button stays, so the user can try again */
    } finally {
      setLoadingOlder(false);
    }
  }

  async function deliver(key: string, body: string) {
    try {
      const saved = await api.sendMessage(conversationId, body, key);
      dispatch({ type: "confirmed", key, message: saved });
      onSent(saved);
    } catch (err) {
      dispatch({ type: "sendFailed", key, error: errorText(err) });
    }
  }

  function send(e: FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    const key = newIdempotencyKey(); // one key per logical send
    dispatch({ type: "sendStarted", key, body });
    setText("");
    stickToBottom.current = true;
    deliver(key, body);
  }

  function retry(entry: PendingMessage) {
    dispatch({ type: "retry", key: entry.key });
    deliver(entry.key, entry.body); // same key: if the first attempt did reach the server, no duplicate
  }

  if (status === "error") {
    return (
      <section className="card thread thread-empty">
        {loadError?.status === 404
          ? <EmptyState title="Conversation not found" />
          : <InlineError message={loadError?.message ?? "Could not load messages"} onRetry={load} />}
      </section>
    );
  }

  const other = conversation?.other_user;

  return (
    <section className="card thread" aria-label="Conversation">
      <header className="thread-header">
        <Link to="/messages" className="icon-btn back" aria-label="Back to conversations">
          <Icon name="back" />
        </Link>
        {other && (
          <Link to={`/users/${other.id}`} className="author">
            <Avatar user={other} size={32} />
            <span className="author-name">{other.username}</span>
          </Link>
        )}
      </header>

      {down && (
        <div className="banner" role="status">Reconnecting… new messages may be delayed.</div>
      )}

      <div className="messages" ref={scroller} onScroll={onScroll} aria-live="polite">
        {status === "loading" && <Spinner />}
        {hasOlder && (
          <button className="link-btn small center-self" onClick={loadOlder} disabled={loadingOlder}>
            {loadingOlder ? "Loading…" : "Load older messages"}
          </button>
        )}
        {status === "ready" && messages.length === 0 && pending.length === 0 && (
          <p className="muted center">Say hi 👋</p>
        )}
        {messages.map((m, i) => {
          const prev = messages[i - 1];
          const day = new Date(m.created_at).toDateString();
          const newDay = !prev || new Date(prev.created_at).toDateString() !== day;
          const grouped = !newDay && prev?.sender_id === m.sender_id
            && new Date(m.created_at).getTime() - new Date(prev.created_at).getTime() < 5 * 60 * 1000;
          return (
            <div key={m.id} className="message-wrap">
              {newDay && <div className="day-separator"><span>{new Date(m.created_at).toLocaleDateString()}</span></div>}
              <div className={`bubble ${m.sender_id === user!.id ? "mine" : ""} ${grouped ? "grouped" : ""}`}>
                <span>{m.body}</span>
                <time className="time" dateTime={m.created_at} title={fullDate(m.created_at)}>
                  {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </time>
              </div>
            </div>
          );
        })}
        {pending.map((p) => (
          <div key={p.key} className={`bubble mine pending ${p.status}`}>
            <span>{p.body}</span>
            {p.status === "sending" ? (
              <span className="time">Sending…</span>
            ) : (
              <button type="button" className="retry" onClick={() => retry(p)} title={p.error}>
                Not sent · Retry
              </button>
            )}
          </div>
        ))}
      </div>

      <form className="composer-row" onSubmit={send}>
        <input
          placeholder="Write a message…"
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
          aria-label="Write a message"
          autoFocus
        />
        <button className="btn btn-primary icon-only" disabled={!text.trim()} aria-label="Send">
          <Icon name="send" size={20} />
        </button>
      </form>
    </section>
  );
}
