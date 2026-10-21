import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Post } from "../types";
import { errorText, fullDate, optimizedImageUrl, timeAgo } from "../utils";
import Avatar from "./Avatar";
import Comments from "./Comments";
import { useConfirm } from "./ConfirmDialog";
import Icon from "./Icon";
import Menu from "./Menu";

interface Props {
  post: Post;
  onChange: (post: Post) => void;
  onDelete: (id: number) => void;
  commentsOpen?: boolean;
}

export default function PostCard({ post, onChange, onDelete, commentsOpen = false }: Props) {
  const { user } = useAuth();
  const isMine = post.user_id === user?.id;
  const [showComments, setShowComments] = useState(commentsOpen);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.content ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [confirm, confirmDialog] = useConfirm();

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
    setSaving(true);
    try {
      onChange(await api.updatePost(post.id, draft.trim()));
      setEditing(false);
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    const ok = await confirm({
      title: "Delete post?", message: "This can't be undone.", confirmLabel: "Delete", danger: true,
    });
    if (!ok) return;
    try {
      await api.deletePost(post.id);
      onDelete(post.id);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <article className="card post">
      {confirmDialog}
      <header className="post-header">
        <Link to={`/users/${post.author.id}`} className="author">
          <Avatar user={post.author} size={40} />
          <span className="author-name">{post.author.username}</span>
        </Link>
        <time className="muted small" dateTime={post.created_at} title={fullDate(post.created_at)}>
          {timeAgo(post.created_at)}
        </time>
        {isMine && !editing && (
          <Menu
            label="Post options"
            items={[
              { label: "Edit", onSelect: () => { setDraft(post.content ?? ""); setEditing(true); } },
              { label: "Delete", onSelect: remove, danger: true },
            ]}
          />
        )}
      </header>

      {editing ? (
        <div className="stack">
          <textarea
            value={draft}
            maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
            aria-label="Edit post"
            autoFocus
          />
          <div className="row end">
            <button className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>Cancel</button>
            <button
              className="btn btn-primary btn-sm"
              onClick={saveEdit}
              disabled={saving || (!draft.trim() && !post.image_url)}
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      ) : (
        post.content && <p className="post-content">{post.content}</p>
      )}

      {post.image_url && (
        <div className="post-image-frame">
          <img className="post-image" src={optimizedImageUrl(post.image_url)} alt="" loading="lazy" />
        </div>
      )}

      {error && <p className="error">{error}</p>}

      <div className="post-actions">
        <button
          className={`action ${post.liked_by_me ? "liked" : ""}`}
          onClick={toggleLike}
          aria-pressed={post.liked_by_me}
          aria-label={post.liked_by_me ? "Unlike" : "Like"}
        >
          <Icon name="heart" filled={post.liked_by_me} />
          <span>{post.likes_count}</span>
        </button>
        <button
          className="action"
          onClick={() => setShowComments((s) => !s)}
          aria-expanded={showComments}
          aria-label="Comments"
        >
          <Icon name="comment" />
          <span>{post.comments_count}</span>
        </button>
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
