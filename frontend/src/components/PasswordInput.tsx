import { useState, type InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

/** Password field with a show/hide toggle.
 *
 * We draw our own toggle instead of relying on Edge's built-in reveal button,
 * which the browser hides after the field loses focus (see index.css).
 */
export default function PasswordInput(props: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="password-field">
      <input {...props} type={visible ? "text" : "password"} />
      <button
        type="button" // never submits the form
        className="password-toggle"
        onClick={() => setVisible((v) => !v)}
        onMouseDown={(e) => e.preventDefault()} // keep focus and caret in the input
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        title={visible ? "Hide password" : "Show password"}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
          <circle cx="12" cy="12" r="3" />
          {visible && <line x1="3" y1="3" x2="21" y2="21" />}
        </svg>
      </button>
    </div>
  );
}
