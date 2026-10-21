import { useLocation } from "react-router";
import { api } from "../api";
import LoadMore from "../components/LoadMore";
import PostComposer from "../components/PostComposer";
import PostList from "../components/PostList";
import { InlineError, SkeletonPosts } from "../components/States";
import { useCursorList } from "../hooks/useCursorList";
import { uniqueById } from "../utils";

const PAGE = 10;

/**
 * Chronological feed (my posts, public accounts, accepted follows).
 * Scrolling loads older posts with before_id; clicking Home again (a new
 * location key) reloads the newest posts.
 */
export default function Feed() {
  const location = useLocation();
  const feed = useCursorList((beforeId, limit) => api.feed(beforeId, limit), PAGE, [location.key]);

  return (
    <div className="column">
      <h1 className="page-title">Home</h1>
      <PostComposer onCreated={(post) => feed.setItems((prev) => uniqueById([post, ...prev]))} />

      {feed.status === "loading" && <SkeletonPosts />}
      {feed.status === "error" && <InlineError message={feed.error} onRetry={feed.reload} />}
      {feed.status === "ready" && (
        <>
          <PostList
            posts={feed.items}
            setPosts={feed.setItems}
            emptyTitle="Your feed is empty"
            emptyText="Write the first post, or find people to follow in Search."
          />
          {feed.items.length > 0 && (
            <LoadMore
              hasMore={feed.hasMore}
              loading={feed.loadingMore}
              error={feed.moreError}
              onLoadMore={feed.loadMore}
            />
          )}
        </>
      )}
    </div>
  );
}
