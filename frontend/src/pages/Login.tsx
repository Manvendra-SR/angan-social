import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../auth";
import AuthLayout from "../components/AuthLayout";
import PasswordInput from "../components/PasswordInput";
import { errorText } from "../utils";

export default function Login() {
  const { login } = useAuth();
  const state = useLocation().state as { registered?: boolean; accountDeleted?: boolean } | null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
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
          <h1>Welcome back</h1>
          <p className="muted">Log in to your courtyard.</p>
        </div>
        {state?.registered && <p className="notice success" role="status">Account created. Log in to continue.</p>}
        {state?.accountDeleted && <p className="notice" role="status">Your account has been deleted.</p>}
        <label className="field">
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus autoComplete="email" />
        </label>
        <label className="field">
          <span>Password</span>
          <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
        <p className="muted small center">
          No account? <Link to="/register">Sign up</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
