import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import Avatar from "../components/Avatar";
import { Modal, useConfirm } from "../components/ConfirmDialog";
import Icon from "../components/Icon";
import LoadMore from "../components/LoadMore";
import Menu from "../components/Menu";
import PostList from "../components/PostList";
import { EmptyState, InlineError, SkeletonPosts, Spinner } from "../components/States";
import { useCursorList } from "../hooks/useCursorList";
import type { FollowRequest, Profile as ProfileT } from "../types";
import { errorText } from "../utils";

const PAGE = 10;

export default function Profile() {
  const userId = Number(useParams().id);
  const { user: me } = useAuth();
  const isMe = me?.id === userId;
  const navigate = useNavigate();
  const location = useLocation();
  const [confirm, confirmDialog] = useConfirm();

  const [profile, setProfile] = useState<ProfileT | null>(null);
  const [loadError, setLoadError] = useState<{ status: number; message: string } | null>(null);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  const posts = useCursorList(
    (beforeId, limit) => (profile?.can_view_posts ? api.userPosts(userId, beforeId, limit) : Promise.resolve([])),
    PAGE,
    [userId, profile?.can_view_posts],
  );

  async function loadProfile() {
    try {
      setProfile(await api.user(userId));
      setLoadError(null);
    } catch (err) {
      setProfile(null);
      setLoadError({ status: err instanceof ApiError ? err.status : 0, message: errorText(err) });
    }
  }

  useEffect(() => {
    setProfile(null);
    setLoadError(null);
    setActionError("");
    setEditing(false);
    loadProfile();
  }, [userId]);

  // #requests (from a follow-request notification) scrolls to the requests list
  useEffect(() => {
    if (profile && location.hash === "#requests") {
      document.getElementById("requests")?.scrollIntoView({ block: "start" });
    }
  }, [profile, location.hash]);

  async function run(action: () => Promise<unknown>) {
    setActionError("");
    setBusy(true);
    try {
      await action();
      await loadProfile();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function message() {
    try {
      const conversation = await api.startConversation(userId);
      navigate(`/messages/${conversation.id}`);
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  async function unfollow() {
    if (await confirm({ title: `Unfollow ${profile!.username}?`, confirmLabel: "Unfollow" })) {
      run(() => api.unfollow(userId));
    }
  }

  async function block() {
    const ok = await confirm({
      title: `Block ${profile!.username}?`,
      message: "They won't be able to see your posts or message you, and you won't see theirs.",
      confirmLabel: "Block",
      danger: true,
    });
    if (ok) run(() => api.block(userId));
  }

  if (loadError) {
    return (
      <div className="column">
        {loadError.status === 404 && <EmptyState title="User not found" />}
        {loadError.status === 403 && <EmptyState title="This profile isn't available" />}
        {loadError.status !== 404 && loadError.status !== 403 && (
          <InlineError message={loadError.message} onRetry={loadProfile} />
        )}
      </div>
    );
  }
  if (!profile) return <div className="column"><Spinner /></div>;

  let followButton = null;
  if (!isMe && !profile.blocked_by_me) {
    if (profile.follow_status === "accepted") {
      followButton = <button className="btn btn-secondary" disabled={busy} onClick={unfollow}>Following</button>;
    } else if (profile.follow_status === "pending") {
      followButton = (
        <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => api.cancelFollow(userId))} title="Cancel request">
          Requested
        </button>
      );
    } else {
      followButton = (
        <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.follow(userId))}>
          {profile.is_private ? "Request to follow" : "Follow"}
        </button>
      );
    }
  }

  return (
    <div className="column">
      {confirmDialog}
      <section className="card profile-header">
        <Avatar user={profile} size={80} />
        <div className="profile-info">
          <div className="profile-name-row">
            <h1>{profile.username}</h1>
            {profile.is_private && (
              <span className="pill" title="Private account"><Icon name="lock" size={14} /> Private</span>
            )}
          </div>
          <div className="stats">
            <span><b>{profile.posts_count}</b> posts</span>
            <span><b>{profile.followers_count}</b> followers</span>
            <span><b>{profile.following_count}</b> following</span>
          </div>
          {profile.bio && <p className="bio">{profile.bio}</p>}
          <div className="row profile-actions">
            {isMe && <button className="btn btn-secondary" onClick={() => setEditing(true)}>Edit profile</button>}
            {followButton}
            {!isMe && !profile.blocked_by_me && (
              <button className="btn btn-secondary" onClick={message}>Message</button>
            )}
            {!isMe && (
              <Menu
                label="Profile options"
                items={[profile.blocked_by_me
                  ? { label: "Unblock", onSelect: () => run(() => api.unblock(userId)) }
                  : { label: "Block", onSelect: block, danger: true }]}
              />
            )}
          </div>
          {actionError && <p className="error">{actionError}</p>}
        </div>
      </section>

      {isMe && <EditProfileModal open={editing} onClose={() => setEditing(false)} onSaved={loadProfile} />}
      {isMe && <FollowRequests onChange={loadProfile} />}

      {profile.blocked_by_me ? (
        <EmptyState title="You blocked this account">
          <button className="btn btn-secondary" onClick={() => run(() => api.unblock(userId))}>Unblock</button>
        </EmptyState>
      ) : !profile.can_view_posts ? (
        <EmptyState title="This account is private">Follow to see their posts.</EmptyState>
      ) : (
        <>
          {posts.status === "loading" && <SkeletonPosts count={2} />}
          {posts.status === "error" && <InlineError message={posts.error} onRetry={posts.reload} />}
          {posts.status === "ready" && (
            <>
              <PostList posts={posts.items} setPosts={posts.setItems} emptyTitle="No posts yet" />
              {posts.items.length > 0 && (
                <LoadMore hasMore={posts.hasMore} loading={posts.loadingMore} error={posts.moreError} onLoadMore={posts.loadMore} />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function EditProfileModal({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({ username: "", bio: "", is_private: false });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && user) {
      setForm({ username: user.username, bio: user.bio ?? "", is_private: user.is_private });
      setError("");
    }
  }, [open, user]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      setUser(await api.updateMe(form));
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} title="Edit profile" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>Username</span>
          <input
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            pattern="[A-Za-z0-9_]{3,30}"
            title="3–30 letters, numbers or underscores"
            required
          />
        </label>
        <label className="field">
          <span>Bio</span>
          <textarea value={form.bio} maxLength={300} onChange={(e) => setForm({ ...form, bio: e.target.value })} />
          <span className="hint">{300 - form.bio.length} characters left</span>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.is_private}
            onChange={(e) => setForm({ ...form, is_private: e.target.checked })}
          />
          Private account (only your followers can see your posts)
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row end">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

function FollowRequests({ onChange }: { onChange: () => void }) {
  const [requests, setRequests] = useState<FollowRequest[]>([]);
  const [error, setError] = useState("");

  const load = () => api.followRequests().then(setRequests).catch((err) => setError(errorText(err)));

  useEffect(() => {
    load();
  }, []);

  async function respond(followerId: number, accept: boolean) {
    setError("");
    try {
      await (accept ? api.acceptFollow(followerId) : api.rejectFollow(followerId));
      await load();
      onChange();
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (requests.length === 0 && !error) return null;

  return (
    <section className="card" id="requests">
      <h2 className="section-title">Follow requests</h2>
      {error && <InlineError message={error} onRetry={load} />}
      <ul className="list">
        {requests.map((r) => (
          <li key={r.follower_id} className="list-row">
            <Avatar user={{ id: r.follower_id, username: r.follower_username }} size={40} />
            <span className="author-name">{r.follower_username}</span>
            <span className="spacer" />
            <button className="btn btn-primary btn-sm" onClick={() => respond(r.follower_id, true)}>Accept</button>
            <button className="btn btn-secondary btn-sm" onClick={() => respond(r.follower_id, false)}>Reject</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
