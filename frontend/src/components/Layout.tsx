/**
 * App shell: one navigation list, laid out by CSS only
 *   >= 1024px  sidebar with labels
 *   640-1023   icon-only sidebar
 *   < 640      slim top bar + bottom tab bar
 */
import { NavLink, Outlet } from "react-router";
import { useAuth } from "../auth";
import { useRealtime } from "../realtime";
import Badge from "./Badge";
import Brand from "./Brand";
import Icon, { type IconName } from "./Icon";

export default function Layout() {
  const { user, logout } = useAuth();
  const { counts } = useRealtime();

  const items: { to: string; label: string; icon: IconName; badge?: number; badgeLabel?: string; end?: boolean }[] = [
    { to: "/", label: "Home", icon: "home", end: true },
    { to: "/search", label: "Search", icon: "search" },
    { to: "/notifications", label: "Notifications", icon: "bell", badge: counts.unread_notifications, badgeLabel: "unread notifications" },
    { to: "/messages", label: "Messages", icon: "message", badge: counts.unread_messages, badgeLabel: "unread messages" },
    { to: `/users/${user!.id}`, label: "Profile", icon: "user" },
  ];

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand-link" aria-label="Angan home"><Brand size={28} /></NavLink>
      </header>

      <nav className="sidenav" aria-label="Main">
        <NavLink to="/" className="brand-link brand-side" aria-label="Angan home"><Brand size={34} /></NavLink>
        <ul>
          {items.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className="nav-item" title={item.label}>
                <span className="nav-icon">
                  <Icon name={item.icon} />
                  {item.badge !== undefined && <Badge count={item.badge} label={item.badgeLabel!} />}
                </span>
                <span className="nav-label">{item.label}</span>
              </NavLink>
            </li>
          ))}
          <li className="nav-logout">
            <button type="button" className="nav-item" onClick={logout} title="Log out">
              <span className="nav-icon"><Icon name="logout" /></span>
              <span className="nav-label">Log out</span>
            </button>
          </li>
        </ul>
      </nav>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
