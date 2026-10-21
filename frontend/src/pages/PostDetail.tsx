import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, ApiError } from "../api";
import PostCard from "../components/PostCard";
import { EmptyState, InlineError, SkeletonPosts } from "../components/States";
import type { Post } from "../types";
import { errorText } from "../utils";

/** A single post with its comments open (target of like/comment notifications). */
export default function PostDetail() {
  const postId = Number(useParams().id);
  const navigate = useNavigate();
  const [post, setPost] = useState<Post | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);

  function load() {
    setError(null);
    setPost(null);
    api.post(postId)
      .then(setPost)
      .catch((err) => setError({ status: err instanceof ApiError ? err.status : 0, message: errorText(err) }));
  }

  useEffect(load, [postId]);

  return (
    <div className="column">
      <h1 className="page-title">Post</h1>
      {error?.status === 404 && (
        <EmptyState title="This post is no longer available">
          It may have been deleted. <Link to="/">Back to Home</Link>
        </EmptyState>
      )}
      {error?.status === 403 && (
        <EmptyState title="You can't view this post">
          The account is private, or you don't have access.
        </EmptyState>
      )}
      {error && error.status !== 404 && error.status !== 403 && <InlineError message={error.message} onRetry={load} />}
      {!post && !error && <SkeletonPosts count={1} />}
      {post && (
        <PostCard post={post} onChange={setPost} onDelete={() => navigate("/")} commentsOpen />
      )}
    </div>
  );
}
