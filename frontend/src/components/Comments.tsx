import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Comment } from "../types";
import { errorText, fullDate, timeAgo, uniqueById } from "../utils";
import Avatar from "./Avatar";
import { InlineError } from "./States";

// comments keep offset pagination (oldest first, new ones are appended)
const PAGE = 20;

interface Props {
  postId: number;
  onCountChange: (delta: number) => void;
}

export default function Comments({ postId, onCountChange }: Props) {
  const { user } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function load(offset: number) {
    setLoading(true);
    setError("");
    try {
      const batch = await api.comments(postId, offset, PAGE);
      // on the first load `prev` can only hold comments added meanwhile
      setComments((prev) => uniqueById(offset === 0 ? [...batch, ...prev] : [...prev, ...batch]));
      setHasMore(batch.length === PAGE);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(0);
  }, [postId]);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      const comment = await api.addComment(postId, text.trim());
      setComments((prev) => uniqueById([...prev, comment]));
      setText("");
      onCountChange(1);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSending(false);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteComment(id);
      setComments((prev) => prev.filter((c) => c.id !== id));
      onCountChange(-1);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="comments" aria-label="Comments">
      {!loading && comments.length === 0 && !error && <p className="muted small">No comments yet.</p>}
      {comments.map((c) => (
        <div key={c.id} className="comment">
          <Avatar user={c.author} size={32} />
          <div className="comment-bubble">
            <div className="comment-meta">
              <Link to={`/users/${c.author.id}`} className="author-name">{c.author.username}</Link>
              <time className="muted small" dateTime={c.created_at} title={fullDate(c.created_at)}>
                {timeAgo(c.created_at)}
              </time>
              {c.user_id === user?.id && (
                <button className="link-btn danger small" onClick={() => remove(c.id)}>Delete</button>
              )}
            </div>
            <p>{c.content}</p>
          </div>
        </div>
      ))}
      {hasMore && (
        <button className="link-btn small" onClick={() => load(comments.length)} disabled={loading}>
          {loading ? "Loading…" : "View more comments"}
        </button>
      )}
      {error && <InlineError message={error} onRetry={() => load(comments.length)} />}
      <form className="comment-form" onSubmit={add}>
        <input
          placeholder="Write a comment…"
          value={text}
          maxLength={1000}
          onChange={(e) => setText(e.target.value)}
          aria-label="Write a comment"
        />
        <button className="btn btn-primary btn-sm" disabled={!text.trim() || sending}>
          {sending ? "…" : "Post"}
        </button>
      </form>
    </section>
  );
}
