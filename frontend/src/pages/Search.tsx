import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import Avatar from "../components/Avatar";
import Icon from "../components/Icon";
import { EmptyState, InlineError, Spinner } from "../components/States";
import type { UserSummary } from "../types";
import { errorText } from "../utils";

export default function Search() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0); // bumping it re-runs the search (Retry)

  // small debounce so we don't send a request on every keystroke
  useEffect(() => {
    const q = query.trim();
    setError("");
    if (!q) { setResults(null); setLoading(false); return; }
    setLoading(true);
    let cancelled = false;
    const timer = setTimeout(() => {
      api.searchUsers(q)
        .then((users) => { if (!cancelled) setResults(users); })
        .catch((err) => { if (!cancelled) setError(errorText(err)); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, attempt]);

  return (
    <div className="column">
      <h1 className="page-title">Search</h1>
      <div className="search-box">
        <Icon name="search" size={20} />
        <input
          type="search"
          placeholder="Search by username"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search by username"
          autoFocus
        />
      </div>

      {error && <InlineError message={error} onRetry={() => setAttempt((a) => a + 1)} />}
      {loading && <Spinner />}
      {!loading && results === null && <EmptyState title="Find people">Search by username to see profiles.</EmptyState>}
      {!loading && results?.length === 0 && <EmptyState title="No users found">Try a different name.</EmptyState>}
      {!loading && results && results.length > 0 && (
        <ul className="card list">
          {results.map((u) => (
            <li key={u.id}>
              <Link to={`/users/${u.id}`} className="list-row">
                <Avatar user={u} size={40} />
                <span className="author-name">{u.username}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
