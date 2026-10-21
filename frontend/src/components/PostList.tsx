import type { Post } from "../types";
import PostCard from "./PostCard";
import { EmptyState } from "./States";

interface Props {
  posts: Post[];
  setPosts: (update: (prev: Post[]) => Post[]) => void;
  emptyTitle: string;
  emptyText?: string;
}

export default function PostList({ posts, setPosts, emptyTitle, emptyText }: Props) {
  if (posts.length === 0) return <EmptyState title={emptyTitle}>{emptyText}</EmptyState>;

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
