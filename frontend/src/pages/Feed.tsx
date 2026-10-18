import { useEffect, useState } from "react";
import { api } from "../api";
import PostComposer from "../components/PostComposer";
import PostList from "../components/PostList";
import type { Post } from "../types";
import { errorText, uniqueById } from "../utils";

const PAGE = 10;

export default function Feed() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(offset: number) {
    setLoading(true);
    try {
      const batch = await api.feed(offset, PAGE);
      // offset 0 only runs on mount, so `prev` can only hold posts created meanwhile
      setPosts((prev) => uniqueById([...prev, ...batch]));
      setHasMore(batch.length === PAGE);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(0);
  }, []);

  return (
    <div className="narrow">
      <PostComposer onCreated={(post) => setPosts((prev) => uniqueById([post, ...prev]))} />
      {error && <p className="error">{error}</p>}
      {!loading || posts.length > 0 ? (
        <PostList posts={posts} setPosts={setPosts} empty="No posts yet. Write the first one!" />
      ) : null}
      {loading && <p className="muted center">Loading…</p>}
      {hasMore && !loading && (
        <button className="secondary full" onClick={() => load(posts.length)}>Load more</button>
      )}
    </div>
  );
}
