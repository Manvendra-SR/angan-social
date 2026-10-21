import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Post } from "../types";
import { errorText, IMAGE_TYPES, MAX_IMAGE_MB } from "../utils";
import Avatar from "./Avatar";
import Icon from "./Icon";

const MAX_LENGTH = 2000;

export default function PostComposer({ onCreated }: { onCreated: (post: Post) => void }) {
  const { user } = useAuth();
  const [content, setContent] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const imageRef = useRef(image);
  imageRef.current = image;

  // object URLs must be released to avoid leaking memory
  useEffect(() => {
    if (!image) return setPreview(null);
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  // grow with the text instead of scrolling inside a tiny box
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [content]);

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
    if ((!content.trim() && !image) || busy) return;
    const form = new FormData();
    if (content.trim()) form.append("content", content.trim());
    if (image) form.append("image", image);

    const sentContent = content;
    const sentImage = image;
    setBusy(true);
    setError("");
    try {
      onCreated(await api.createPost(form));
      // clear only what was sent: text or an image picked while uploading stays
      setContent((current) => (current === sentContent ? "" : current));
      if (imageRef.current === sentImage) clearImage();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const remaining = MAX_LENGTH - content.length;

  return (
    <form className="card composer" onSubmit={submit}>
      <div className="composer-main">
        {user && <Avatar user={user} size={40} />}
        <textarea
          ref={textarea}
          placeholder="What's happening?"
          value={content}
          maxLength={MAX_LENGTH}
          rows={2}
          onChange={(e) => setContent(e.target.value)}
          aria-label="Post text"
        />
      </div>
      {preview && (
        <div className="preview">
          <img src={preview} alt="Selected image" />
          <button type="button" className="icon-btn preview-remove" onClick={clearImage} aria-label="Remove image">
            <Icon name="close" size={18} />
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      <div className="composer-footer">
        <label className="icon-btn file-button" title="Add image">
          <Icon name="image" />
          <span className="sr-only">Add image</span>
          <input
            ref={fileInput}
            type="file"
            accept={IMAGE_TYPES.join(",")}
            onChange={(e) => pickImage(e.target.files?.[0])}
            className="sr-only"
          />
        </label>
        {remaining <= 200 && <span className={`small ${remaining < 20 ? "danger" : "muted"}`}>{remaining}</span>}
        <span className="spacer" />
        <button className="btn btn-primary" disabled={busy || (!content.trim() && !image)}>
          {busy ? "Posting…" : "Post"}
        </button>
      </div>
    </form>
  );
}
