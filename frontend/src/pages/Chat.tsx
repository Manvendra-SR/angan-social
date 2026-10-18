import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Conversation, Message } from "../types";
import { errorText, timeAgo, uniqueById } from "../utils";

const POLL_MS = 3000;

export default function Chat() {
  const params = useParams();
  const activeId = params.id ? Number(params.id) : null;
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const loadConversations = () => api.conversations().then(setConversations).catch(() => {});

  useEffect(() => {
    loadConversations();
    const timer = setInterval(loadConversations, POLL_MS * 3);
    return () => clearInterval(timer);
  }, []);

  const active = conversations.find((c) => c.id === activeId);

  return (
    <div className={`chat ${activeId ? "has-active" : ""}`}>
      <aside className="card conversation-list">
        <h2>Messages</h2>
        {conversations.length === 0 && (
          <p className="muted small">
            No conversations yet. Open someone's profile from <Link to="/people">People</Link> and press Message.
          </p>
        )}
        {conversations.map((c) => (
          <Link
            key={c.id}
            to={`/messages/${c.id}`}
            className={`conversation ${c.id === activeId ? "active" : ""}`}
          >
            <b>@{c.other_user.username}</b>
            <span className="muted small ellipsis">{c.last_message?.body ?? "No messages yet"}</span>
          </Link>
        ))}
      </aside>

      {activeId ? (
        <Thread
          key={activeId}
          conversationId={activeId}
          title={active ? `@${active.other_user.username}` : ""}
          onSent={loadConversations}
        />
      ) : (
        <section className="card thread empty muted">Select a conversation</section>
      )}
    </div>
  );
}

interface ThreadProps {
  conversationId: number;
  title: string;
  onSent: () => void;
}

function Thread({ conversationId, title, onSent }: ThreadProps) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const lastId = useRef(0);

  function append(newer: Message[]) {
    if (newer.length === 0) return;
    setMessages((prev) => {
      // a sent message can also come back from the next poll: dedupe by id
      const seen = new Set(prev.map((m) => m.id));
      return [...prev, ...newer.filter((m) => !seen.has(m.id))].sort((a, b) => a.id - b.id);
    });
    lastId.current = Math.max(lastId.current, newer[newer.length - 1].id);
    setTimeout(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), 0);
  }

  // initial load, then poll for messages newer than the last one we have
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function poll() {
      try {
        const newer = await api.messages(conversationId, { after: lastId.current });
        if (!cancelled) append(newer);
      } catch {
        /* keep polling; a temporary network error shouldn't break the chat */
      }
    }

    api.messages(conversationId)
      .then((batch) => {
        if (cancelled) return;
        setHasOlder(batch.length === 50);
        append(batch);
        timer = setInterval(poll, POLL_MS);
      })
      .catch((err) => setError(errorText(err)));

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [conversationId]);

  async function loadOlder() {
    const older = await api.messages(conversationId, { before: messages[0]?.id });
    setHasOlder(older.length === 50);
    setMessages((prev) => uniqueById([...older, ...prev]));
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    setError("");
    try {
      append([await api.sendMessage(conversationId, body)]);
      setText("");
      onSent();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="card thread">
      <header className="row thread-header">
        <Link to="/messages" className="back">←</Link>
        <b>{title}</b>
      </header>
      <div className="messages">
        {hasOlder && (
          <button className="link small center-self" onClick={loadOlder}>Load older messages</button>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.sender_id === user?.id ? "mine" : ""}`}>
            <span>{m.body}</span>
            <span className="time">{timeAgo(m.created_at)}</span>
          </div>
        ))}
        <div ref={bottom} />
      </div>
      {error && <p className="error">{error}</p>}
      <form className="row composer-row" onSubmit={send}>
        <input
          placeholder="Write a message…"
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <button disabled={!text.trim()}>Send</button>
      </form>
    </section>
  );
}
