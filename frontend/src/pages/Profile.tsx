import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import PostList from "../components/PostList";
import type { FollowRequest, Post, Profile as ProfileT } from "../types";
import { errorText, uniqueById } from "../utils";

const PAGE = 10;

export default function Profile() {
  const userId = Number(useParams().id);
  const { user: me } = useAuth();
  const isMe = me?.id === userId;
  const navigate = useNavigate();

  const [profile, setProfile] = useState<ProfileT | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");

  async function loadProfile() {
    try {
      const p = await api.user(userId);
      setProfile(p);
      if (p.can_view_posts) loadPosts(0);
      else setPosts([]);
    } catch (err) {
      setProfile(null);
      setError(errorText(err));
    }
  }

  async function loadPosts(offset: number) {
    const batch = await api.userPosts(userId, offset, PAGE);
    setPosts((prev) => (offset === 0 ? batch : uniqueById([...prev, ...batch])));
    setHasMore(batch.length === PAGE);
  }

  useEffect(() => {
    setError("");
    setEditing(false);
    loadProfile();
  }, [userId]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await loadProfile();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function message() {
    try {
      const conversation = await api.startConversation(userId);
      navigate(`/messages/${conversation.id}`);
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (!profile) return <p className="center error">{error || "Loading…"}</p>;

  return (
    <div className="narrow">
      <section className="card profile">
        <div className="row space-between">
          <div>
            <h1>@{profile.username}</h1>
            {profile.is_private && <span className="badge">Private</span>}
          </div>
          {!isMe && (
            <div className="row">
              <FollowButton profile={profile} run={run} />
              <button className="secondary" onClick={message}>Message</button>
            </div>
          )}
          {isMe && !editing && (
            <button className="secondary" onClick={() => setEditing(true)}>Edit profile</button>
          )}
        </div>
        {profile.bio && <p>{profile.bio}</p>}
        <div className="row stats">
          <span><b>{profile.posts_count}</b> posts</span>
          <span><b>{profile.followers_count}</b> followers</span>
          <span><b>{profile.following_count}</b> following</span>
        </div>
        {error && <p className="error">{error}</p>}
        {isMe && editing && (
          <EditProfile onDone={() => { setEditing(false); loadProfile(); }} />
        )}
      </section>

      {isMe && <FollowRequests onChange={loadProfile} />}

      {profile.can_view_posts ? (
        <>
          <PostList posts={posts} setPosts={setPosts} empty="No posts yet." />
          {hasMore && (
            <button className="secondary full" onClick={() => loadPosts(posts.length)}>Load more</button>
          )}
        </>
      ) : (
        <p className="card center muted">This account is private. Follow to see their posts.</p>
      )}
    </div>
  );
}

function FollowButton({ profile, run }: { profile: ProfileT; run: (a: () => Promise<unknown>) => void }) {
  if (profile.follow_status === "accepted") {
    return <button className="secondary" onClick={() => run(() => api.unfollow(profile.id))}>Unfollow</button>;
  }
  if (profile.follow_status === "pending") {
    return <button className="secondary" onClick={() => run(() => api.cancelFollow(profile.id))}>Requested</button>;
  }
  return <button onClick={() => run(() => api.follow(profile.id))}>Follow</button>;
}

function EditProfile({ onDone }: { onDone: () => void }) {
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({
    username: user!.username,
    bio: user!.bio ?? "",
    is_private: user!.is_private,
  });
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      setUser(await api.updateMe(form));
      onDone();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form className="stack edit-profile" onSubmit={submit}>
      <label>
        Username
        <input
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
          pattern="[A-Za-z0-9_]{3,30}"
          required
        />
      </label>
      <label>
        Bio
        <textarea value={form.bio} maxLength={300} onChange={(e) => setForm({ ...form, bio: e.target.value })} />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.is_private}
          onChange={(e) => setForm({ ...form, is_private: e.target.checked })}
        />
        Private account
      </label>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button>Save</button>
        <button type="button" className="secondary" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}

function FollowRequests({ onChange }: { onChange: () => void }) {
  const [requests, setRequests] = useState<FollowRequest[]>([]);

  async function load() {
    setRequests(await api.followRequests());
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  async function respond(followerId: number, accept: boolean) {
    await (accept ? api.acceptFollow(followerId) : api.rejectFollow(followerId));
    await load();
    onChange();
  }

  if (requests.length === 0) return null;

  return (
    <section className="card">
      <h2>Follow requests</h2>
      {requests.map((r) => (
        <div key={r.follower_id} className="row space-between request">
          <span>@{r.follower_username}</span>
          <div className="row">
            <button className="small" onClick={() => respond(r.follower_id, true)}>Accept</button>
            <button className="secondary small" onClick={() => respond(r.follower_id, false)}>Reject</button>
          </div>
        </div>
      ))}
    </section>
  );
}
