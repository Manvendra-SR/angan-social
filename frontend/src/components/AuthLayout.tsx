/**
 * Login / register frame: the courtyard photograph beside the form on wide
 * screens, as a short banner above it on phones. The photo is a bundled local
 * asset (see assets/CREDITS.md); a warm gradient shows if it ever fails to load.
 */
import type { ReactNode } from "react";
import courtyard from "../assets/angan-courtyard.jpg";
import Brand, { APP_NAME } from "./Brand";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-page">
      <aside className="auth-visual" style={{ backgroundImage: `url(${courtyard})` }}>
        <div className="auth-visual-text">
          <Brand size={40} />
          <p className="auth-tagline">A warm courtyard for the people who matter.</p>
          <p className="auth-subtag">Share moments, follow friends and talk, all in one calm place.</p>
        </div>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <div className="auth-card-brand"><Brand size={36} /></div>
          {children}
        </div>
        <p className="auth-footnote muted small">
          {APP_NAME} (आँगन) means “courtyard”.
        </p>
      </main>
    </div>
  );
}
