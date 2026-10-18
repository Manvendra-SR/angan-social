import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../auth";
import PasswordInput from "../components/PasswordInput";
import { errorText } from "../utils";

export default function Login() {
  const { login } = useAuth();
  const registered = useLocation().state?.registered as boolean | undefined;
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
    <div className="auth-page">
      <form className="card stack" onSubmit={submit}>
        <h1>Log in</h1>
        {registered && <p className="success">Account created. Log in to continue.</p>}
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          Password
          <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
        <p className="muted small">
          No account? <Link to="/register">Sign up</Link>
        </p>
      </form>
    </div>
  );
}
