import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import AuthLayout from "../components/AuthLayout";
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
    <AuthLayout>
      <form className="stack" onSubmit={submit}>
        <div>
          <h1>Create your account</h1>
          <p className="muted">Join Angan in less than a minute.</p>
        </div>
        <label className="field">
          <span>Username</span>
          <input
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            pattern="[A-Za-z0-9_]{3,30}"
            title="3–30 letters, numbers or underscores"
            required
            autoFocus
            autoComplete="username"
          />
          <span className="hint">3–30 letters, numbers or underscores</span>
        </label>
        <label className="field">
          <span>Email</span>
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required autoComplete="email" />
        </label>
        <label className="field">
          <span>Password</span>
          <PasswordInput
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            minLength={8}
            required
            autoComplete="new-password"
          />
          <span className="hint">At least 8 characters</span>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.is_private}
            onChange={(e) => setForm({ ...form, is_private: e.target.checked })}
          />
          Private account (only your followers can see your posts)
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Creating…" : "Sign up"}</button>
        <p className="muted small center">
          Already have an account? <Link to="/">Log in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
