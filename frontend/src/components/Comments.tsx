import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Comment } from "../types";
import { errorText, timeAgo, uniqueById } from "../utils";

const PAGE = 20;

interface Props {
  postId: number;
  onCountChange: (delta: number) => void;
}

export default function Comments({ postId, onCountChange }: Props) {
  const { user } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  async function load(offset: number) {
    try {
      const batch = await api.comments(postId, offset, PAGE);
      // oldest first; on the first load `prev` can only hold comments added meanwhile
      setComments((prev) => uniqueById(offset === 0 ? [...batch, ...prev] : [...prev, ...batch]));
      setHasMore(batch.length === PAGE);
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load(0);
  }, [postId]);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      const comment = await api.addComment(postId, text.trim());
      setComments((prev) => uniqueById([...prev, comment]));
      setText("");
      onCountChange(1);
    } catch (err) {
      setError(errorText(err));
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
    <div className="comments">
      {comments.map((c) => (
        <div key={c.id} className="comment">
          <Link to={`/users/${c.author.id}`} className="author">@{c.author.username}</Link>{" "}
          <span>{c.content}</span>
          <span className="muted small"> · {timeAgo(c.created_at)}</span>
          {c.user_id === user?.id && (
            <button className="link danger small" onClick={() => remove(c.id)}>Delete</button>
          )}
        </div>
      ))}
      {hasMore && (
        <button className="link small" onClick={() => load(comments.length)}>Load more comments</button>
      )}
      {error && <p className="error">{error}</p>}
      <form className="row" onSubmit={add}>
        <input
          placeholder="Write a comment…"
          value={text}
          maxLength={1000}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="small" disabled={!text.trim()}>Send</button>
      </form>
    </div>
  );
}
