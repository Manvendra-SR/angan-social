/**
 * Infinite scroll for cursor lists: loads the next page when this element
 * scrolls into view, with a button as a fallback (keyboard users, or if
 * IntersectionObserver isn't available). Shows Retry after an error and an
 * end-of-list message once everything is loaded.
 */
import { useEffect, useRef } from "react";

interface Props {
  hasMore: boolean;
  loading: boolean;
  error: string;
  onLoadMore: () => void;
  endText?: string;
}

export default function LoadMore({ hasMore, loading, error, onLoadMore, endText = "You're all caught up" }: Props) {
  const sentinel = useRef<HTMLDivElement>(null);
  const latest = useRef(onLoadMore);
  latest.current = onLoadMore;

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasMore || error || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) latest.current();
    }, { rootMargin: "300px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, error]);

  if (!hasMore) return <p className="list-end muted">{endText}</p>;

  return (
    <div ref={sentinel} className="load-more">
      {error ? (
        <div className="inline-error" role="alert">
          <span>{error}</span>
          <button className="btn btn-ghost btn-sm" onClick={onLoadMore}>Retry</button>
        </div>
      ) : (
        <button className="btn btn-secondary btn-block" onClick={onLoadMore} disabled={loading}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
