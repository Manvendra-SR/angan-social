/**
 * Permanent account deletion. Opening the dialog does nothing by itself: the
 * user has to type their username and press the delete button.
 */
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import { errorText } from "../utils";
import { APP_NAME } from "./Brand";
import { Modal } from "./ConfirmDialog";

export default function DeleteAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const confirmed = typed.trim() === user?.username;

  function close() {
    if (busy) return; // don't hide the dialog while the request is running
    setTyped("");
    setError("");
    onClose();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!confirmed || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteMe();
      // go to the login page, then drop the session: every signed-in page (feed,
      // profile, notifications, chat) unmounts with its cached data, and the
      // realtime socket is closed
      navigate("/", { replace: true, state: { accountDeleted: true } });
      logout();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title="Delete your account?" onClose={close}>
      <form className="stack" onSubmit={submit}>
        <p>This is permanent and can't be undone. Deleting your {APP_NAME} account removes:</p>
        <ul className="bullet-list">
          <li>your profile, posts and their photos</li>
          <li>your comments and likes on other people's posts</li>
          <li>your followers, follows, requests and blocks</li>
          <li>your notifications</li>
          <li>your conversations, including the messages the other person sent in them</li>
        </ul>
        <label className="field">
          <span>Type <b>{user?.username}</b> to confirm</span>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            aria-describedby="delete-help"
          />
          <span className="hint" id="delete-help">You can sign up again later with the same email, as a new account.</span>
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row end">
          <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>Cancel</button>
          <button className="btn btn-danger" disabled={!confirmed || busy}>
            {busy ? "Deleting…" : "Delete my account"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
