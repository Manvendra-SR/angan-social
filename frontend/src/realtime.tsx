/**
 * One WebSocket per tab, shared by chat and notifications. It only *receives*
 * pushes; everything is persisted server-side and recovered over REST.
 *
 *   connect -> send {type:"auth", token} -> "ready" -> refresh counts + pages over REST
 *   close   -> reconnect after 1, 2, 4, 8, 16, 30 s (±20 %), or at once when the
 *              browser comes back online / the tab becomes visible
 *   4401    -> token rejected or expired: log out
 */
import {
  createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode,
} from "react";
import { api, token, WS_URL } from "./api";
import {
  backoffDelay, CLOSE_UNAUTHORIZED, countsFromEvent, parseEvent, shouldReconnect,
} from "./realtimeLogic";
import type { Counts, RealtimeEvent } from "./types";

export type RealtimeStatus = "connecting" | "open" | "reconnecting" | "unavailable";

/**
 * Subscribers also get a synthetic "resync" after every "ready" (the first one
 * too): the socket is subscribed by then, so re-fetching closes the gap between a
 * page's initial REST load and the moment the socket started receiving events.
 */
export type RealtimeMessage = RealtimeEvent | { type: "resync" };
type Listener = (event: RealtimeMessage) => void;

interface RealtimeState {
  status: RealtimeStatus;
  counts: Counts;
  setCounts: (counts: Counts) => void;
  subscribe: (listener: Listener) => () => void;
}

const EMPTY: Counts = { unread_notifications: 0, unread_messages: 0 };
const RealtimeContext = createContext<RealtimeState | null>(null);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<RealtimeStatus>("connecting");
  const [counts, setCounts] = useState<Counts>(EMPTY);
  const listeners = useRef(new Set<Listener>());

  const emit = useCallback((event: RealtimeMessage) => {
    listeners.current.forEach((listener) => listener(event));
  }, []);

  const subscribe = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => { listeners.current.delete(listener); };
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let disposed = false; // set on logout/unmount (also covers StrictMode's double mount)

    const refreshCounts = () => api.counts().then(setCounts).catch(() => {});

    function connect() {
      clearTimeout(retryTimer);
      if (disposed || (socket && socket.readyState <= WebSocket.OPEN)) return;
      const t = token.get();
      if (!t) return;

      socket = new WebSocket(WS_URL);
      socket.onopen = () => socket?.send(JSON.stringify({ type: "auth", token: t }));
      socket.onmessage = (msg) => {
        const event = parseEvent(String(msg.data));
        if (!event) return;
        if (event.type === "ready") {
          attempt = 0;
          setStatus("open");
          refreshCounts(); // badges are always taken from the database
          emit({ type: "resync" }); // pages re-fetch what they show
          return;
        }
        const newCounts = countsFromEvent(event);
        if (newCounts) setCounts(newCounts);
        emit(event);
      };
      socket.onclose = (e) => {
        socket = null;
        if (disposed) return;
        if (e.code === CLOSE_UNAUTHORIZED) {
          window.dispatchEvent(new Event("auth:logout"));
          return;
        }
        if (!shouldReconnect(e.code)) {
          setStatus("unavailable");
          return;
        }
        setStatus("reconnecting");
        retryTimer = setTimeout(connect, backoffDelay(attempt++));
      };
    }

    // retry at once instead of waiting out the backoff
    const retryNow = () => { if (!disposed && !socket) connect(); };
    const onVisible = () => { if (document.visibilityState === "visible") retryNow(); };

    connect();
    window.addEventListener("online", retryNow);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      window.removeEventListener("online", retryNow);
      document.removeEventListener("visibilitychange", onVisible);
      socket?.close();
    };
  }, [emit]);

  return (
    <RealtimeContext.Provider value={{ status, counts, setCounts, subscribe }}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime() {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtime must be used inside RealtimeProvider");
  return ctx;
}

/** Subscribe to realtime events for the lifetime of a component. */
export function useRealtimeEvents(listener: Listener) {
  const { subscribe } = useRealtime();
  const latest = useRef(listener);
  latest.current = listener;
  useEffect(() => subscribe((event) => latest.current(event)), [subscribe]);
}

/** True once the socket has been down for longer than `ms` (drives fallbacks). */
export function useRealtimeDown(ms = 5000): boolean {
  const { status } = useRealtime();
  const [down, setDown] = useState(false);
  useEffect(() => {
    if (status === "open") { setDown(false); return; }
    const timer = setTimeout(() => setDown(true), ms);
    return () => clearTimeout(timer);
  }, [status, ms]);
  return down;
}
