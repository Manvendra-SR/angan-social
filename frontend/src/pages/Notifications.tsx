/**
 * Notification history. Opening this page does NOT mark anything as read:
 * a notification is read when it's clicked, or via "Mark all as read".
 */
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import Avatar from "../components/Avatar";
import LoadMore from "../components/LoadMore";
import { EmptyState, InlineError, Spinner } from "../components/States";
import { useCursorList } from "../hooks/useCursorList";
import { useRealtime, useRealtimeEvents } from "../realtime";
import type { AppNotification } from "../types";
import { errorText, fullDate, notificationLink, notificationText, timeAgo, uniqueById } from "../utils";
import { useState } from "react";

const PAGE = 20;

export default function Notifications() {
  const { user } = useAuth();
  const { counts, setCounts } = useRealtime();
  const navigate = useNavigate();
  const [actionError, setActionError] = useState("");
  const list = useCursorList((beforeId, limit) => api.notifications(beforeId, limit), PAGE, []);

  useRealtimeEvents((event) => {
    if (event.type === "notification.created") {
      list.setItems((prev) => uniqueById([event.notification, ...prev]));
    } else if (event.type === "resync") {
      // pick up anything that arrived while offline; fresh copies win (read state)
      api.notifications(undefined, PAGE)
        .then((fresh) => list.setItems((prev) => uniqueById([...fresh, ...prev])))
        .catch(() => {});
    }
  });

  function setRead(id: number) {
    list.setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
  }

  function open(n: AppNotification) {
    if (!n.is_read) {
      setRead(n.id); // instant feedback; the server's counts follow
      api.markNotificationRead(n.id).then(setCounts).catch(() => {
        list.setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: false } : x)));
      });
    }
    navigate(notificationLink(n, user!.id));
  }

  async function markAll() {
    setActionError("");
    try {
      setCounts(await api.markAllNotificationsRead());
      list.setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  async function respond(n: AppNotification, accept: boolean) {
    setActionError("");
    try {
      await (accept ? api.acceptFollow(n.actor.id) : api.rejectFollow(n.actor.id));
      // the server removes the handled request notification
      list.setItems((prev) => prev.filter((x) => x.id !== n.id));
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  const unread = list.items.filter((n) => !n.is_read);
  const earlier = list.items.filter((n) => n.is_read);

  const renderRow = (n: AppNotification) => (
    <li key={n.id} className={`notification ${n.is_read ? "" : "unread"}`}>
      {/* avatar -> the person's profile; the rest of the row -> what happened */}
      <Link
        to={`/users/${n.actor.id}`}
        className="notification-avatar"
        title="View profile"
        aria-label={`View ${n.actor.username}'s profile`}
      >
        <Avatar user={n.actor} size={40} />
      </Link>
      <button type="button" className="notification-main" onClick={() => open(n)}>
        <span className="notification-text">
          <b>{n.actor.username}</b> {notificationText(n)}
          <time className="muted small" dateTime={n.created_at} title={fullDate(n.created_at)}>
            {" · "}{timeAgo(n.created_at)}
          </time>
        </span>
        {!n.is_read && <span className="unread-dot" aria-label="Unread" />}
      </button>
      {n.type === "follow_request" && (
        <div className="row notification-actions">
          <button className="btn btn-primary btn-sm" onClick={() => respond(n, true)}>Accept</button>
          <button className="btn btn-secondary btn-sm" onClick={() => respond(n, false)}>Reject</button>
        </div>
      )}
    </li>
  );

  return (
    <div className="column">
      <div className="page-header">
        <h1 className="page-title">Notifications</h1>
        <button className="btn btn-ghost btn-sm" onClick={markAll} disabled={counts.unread_notifications === 0}>
          Mark all as read
        </button>
      </div>
      {actionError && <InlineError message={actionError} />}

      {list.status === "loading" && <Spinner />}
      {list.status === "error" && <InlineError message={list.error} onRetry={list.reload} />}
      {list.status === "ready" && list.items.length === 0 && (
        <EmptyState title="No notifications yet">Likes, comments and follows will show up here.</EmptyState>
      )}
      {list.status === "ready" && list.items.length > 0 && (
        <>
          {unread.length > 0 && (
            <section className="card">
              <h2 className="section-title">New</h2>
              <ul className="notification-list">{unread.map(renderRow)}</ul>
            </section>
          )}
          {earlier.length > 0 && (
            <section className="card">
              <h2 className="section-title">Earlier</h2>
              <ul className="notification-list">{earlier.map(renderRow)}</ul>
            </section>
          )}
          <LoadMore
            hasMore={list.hasMore}
            loading={list.loadingMore}
            error={list.moreError}
            onLoadMore={list.loadMore}
            endText="That's everything"
          />
        </>
      )}
    </div>
  );
}
