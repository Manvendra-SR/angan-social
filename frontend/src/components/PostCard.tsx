import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Post } from "../types";
import { errorText, timeAgo } from "../utils";
import Comments from "./Comments";

interface Props {
  post: Post;
  onChange: (post: Post) => void;
  onDelete: (id: number) => void;
}

export default function PostCard({ post, onChange, onDelete }: Props) {
  const { user } = useAuth();
  const isMine = post.user_id === user?.id;
  const [showComments, setShowComments] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.content ?? "");
  const [error, setError] = useState("");

  async function toggleLike() {
    const liked = !post.liked_by_me;
    // optimistic update, rolled back on failure
    onChange({ ...post, liked_by_me: liked, likes_count: post.likes_count + (liked ? 1 : -1) });
    try {
      await (liked ? api.like(post.id) : api.unlike(post.id));
    } catch (err) {
      onChange(post);
      setError(errorText(err));
    }
  }

  async function saveEdit() {
    try {
      onChange(await api.updatePost(post.id, draft.trim()));
      setEditing(false);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function remove() {
    if (!confirm("Delete this post?")) return;
    try {
      await api.deletePost(post.id);
      onDelete(post.id);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <article className="card post">
      <div className="row space-between">
        <Link to={`/users/${post.author.id}`} className="author">@{post.author.username}</Link>
        <span className="muted small">{timeAgo(post.created_at)}</span>
      </div>

      {editing ? (
        <div className="stack">
          <textarea value={draft} maxLength={2000} onChange={(e) => setDraft(e.target.value)} />
          <div className="row">
            <button className="small" onClick={saveEdit} disabled={!draft.trim()}>Save</button>
            <button className="secondary small" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        post.content && <p className="content">{post.content}</p>
      )}

      {post.image_url && <img className="post-image" src={post.image_url} alt="" loading="lazy" />}

      {error && <p className="error">{error}</p>}

      <div className="row actions">
        <button className={`link ${post.liked_by_me ? "liked" : ""}`} onClick={toggleLike}>
          {post.liked_by_me ? "♥" : "♡"} {post.likes_count}
        </button>
        <button className="link" onClick={() => setShowComments((s) => !s)}>
          💬 {post.comments_count}
        </button>
        {isMine && !editing && (
          <>
            <span className="spacer" />
            <button className="link muted" onClick={() => { setDraft(post.content ?? ""); setEditing(true); }}>Edit</button>
            <button className="link danger" onClick={remove}>Delete</button>
          </>
        )}
      </div>

      {showComments && (
        <Comments
          postId={post.id}
          onCountChange={(delta) => onChange({ ...post, comments_count: post.comments_count + delta })}
        />
      )}
    </article>
  );
}
