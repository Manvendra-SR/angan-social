import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import type { Post } from "../types";
import { errorText, IMAGE_TYPES, MAX_IMAGE_MB } from "../utils";

export default function PostComposer({ onCreated }: { onCreated: (post: Post) => void }) {
  const [content, setContent] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // object URLs must be released to avoid leaking memory
  useEffect(() => {
    if (!image) return setPreview(null);
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  function pickImage(file: File | undefined) {
    setError("");
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) return setError("Only JPEG, PNG or WebP images");
    if (file.size > MAX_IMAGE_MB * 1024 * 1024) return setError(`Image must be under ${MAX_IMAGE_MB} MB`);
    setImage(file);
  }

  function clearImage() {
    setImage(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!content.trim() && !image) return;
    const form = new FormData();
    if (content.trim()) form.append("content", content.trim());
    if (image) form.append("image", image);

    setBusy(true);
    setError("");
    try {
      onCreated(await api.createPost(form));
      setContent("");
      clearImage();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card composer" onSubmit={submit}>
      <textarea
        placeholder="What's happening?"
        value={content}
        maxLength={2000}
        onChange={(e) => setContent(e.target.value)}
      />
      {preview && (
        <div className="preview">
          <img src={preview} alt="Selected" />
          <button type="button" className="secondary small" onClick={clearImage}>Remove</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      <div className="row space-between">
        <label className="file-button">
          Add image
          <input
            ref={fileInput}
            type="file"
            accept={IMAGE_TYPES.join(",")}
            onChange={(e) => pickImage(e.target.files?.[0])}
            hidden
          />
        </label>
        <button disabled={busy || (!content.trim() && !image)}>
          {busy ? "Posting…" : "Post"}
        </button>
      </div>
    </form>
  );
}
