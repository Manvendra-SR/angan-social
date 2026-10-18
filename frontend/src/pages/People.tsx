import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import type { UserSummary } from "../types";
import { errorText } from "../utils";

export default function People() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSummary[]>([]);
  const [error, setError] = useState("");

  // small debounce so we don't send a request on every keystroke
  useEffect(() => {
    const q = query.trim();
    if (!q) return setResults([]);
    const timer = setTimeout(() => {
      api.searchUsers(q).then(setResults).catch((err) => setError(errorText(err)));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div className="narrow">
      <div className="card stack">
        <h1>Find people</h1>
        <input placeholder="Search by username" value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
        {error && <p className="error">{error}</p>}
        {results.map((u) => (
          <Link key={u.id} to={`/users/${u.id}`} className="person">@{u.username}</Link>
        ))}
        {query.trim() && results.length === 0 && <p className="muted">No users found.</p>}
      </div>
    </div>
  );
}
