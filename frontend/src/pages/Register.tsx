import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import PasswordInput from "../components/PasswordInput";
import { errorText } from "../utils";

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "", is_private: false });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.register(form);
      navigate("/", { state: { registered: true } });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card stack" onSubmit={submit}>
        <h1>Create account</h1>
        <label>
          Username
          <input
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            pattern="[A-Za-z0-9_]{3,30}"
            title="3–30 letters, numbers or underscores"
            required
            autoFocus
          />
        </label>
        <label>
          Email
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </label>
        <label>
          Password
          <PasswordInput
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            minLength={8}
            required
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.is_private}
            onChange={(e) => setForm({ ...form, is_private: e.target.checked })}
          />
          Private account (only approved followers see your posts)
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>{busy ? "Creating…" : "Sign up"}</button>
        <p className="muted small">
          Already have an account? <Link to="/">Log in</Link>
        </p>
      </form>
    </div>
  );
}
