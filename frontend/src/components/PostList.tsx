import type { Post } from "../types";
import PostCard from "./PostCard";

interface Props {
  posts: Post[];
  setPosts: (update: (prev: Post[]) => Post[]) => void;
  empty: string;
}

export default function PostList({ posts, setPosts, empty }: Props) {
  if (posts.length === 0) return <p className="muted center">{empty}</p>;

  return (
    <>
      {posts.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          onChange={(updated) => setPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))}
          onDelete={(id) => setPosts((prev) => prev.filter((p) => p.id !== id))}
        />
      ))}
    </>
  );
}
