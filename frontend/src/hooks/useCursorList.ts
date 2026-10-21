/**
 * Newest-first list loaded with a `before_id` cursor (feed, profile posts,
 * notifications).
 *
 *   reload()   -> first page, replaces the list (used on mount and on refresh)
 *   loadMore() -> next page: before_id = id of the last item shown; appended
 *                 with a de-duplicating merge. A page shorter than `limit`
 *                 means we reached the end.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { errorText, uniqueById } from "../utils";

export type ListStatus = "loading" | "ready" | "error";

export function useCursorList<T extends { id: number }>(
  fetchPage: (beforeId: number | undefined, limit: number) => Promise<T[]>,
  limit: number,
  deps: unknown[],
) {
  const [items, setItems] = useState<T[]>([]);
  const [status, setStatus] = useState<ListStatus>("loading");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState("");
  const inFlight = useRef(false);
  const generation = useRef(0); // ignore responses from a superseded reload

  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;

  const reload = useCallback(async () => {
    const gen = ++generation.current;
    setStatus("loading");
    setError("");
    setMoreError("");
    try {
      const batch = await fetchRef.current(undefined, limit);
      if (gen !== generation.current) return;
      setItems(batch);
      setHasMore(batch.length === limit);
      setStatus("ready");
    } catch (err) {
      if (gen !== generation.current) return;
      setError(errorText(err));
      setStatus("error");
    }
  }, [limit]);

  const loadMore = useCallback(async (cursorId: number | undefined) => {
    if (inFlight.current || cursorId === undefined) return; // no double requests
    inFlight.current = true;
    const gen = generation.current;
    setLoadingMore(true);
    setMoreError("");
    try {
      const batch = await fetchRef.current(cursorId, limit);
      if (gen !== generation.current) return;
      setItems((prev) => uniqueById([...prev, ...batch]));
      setHasMore(batch.length === limit);
    } catch (err) {
      if (gen === generation.current) setMoreError(errorText(err)); // keep what's loaded
    } finally {
      inFlight.current = false;
      setLoadingMore(false);
    }
  }, [limit]);

  useEffect(() => {
    reload();
  }, deps); // the caller decides what triggers a fresh first page

  return {
    items,
    setItems,
    status,
    error,
    hasMore,
    loadingMore,
    moreError,
    reload,
    loadMore: () => loadMore(items[items.length - 1]?.id),
  };
}
