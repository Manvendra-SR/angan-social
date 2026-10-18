import { NavLink, Outlet } from "react-router";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">Social</NavLink>
          <nav>
            <NavLink to="/" end>Feed</NavLink>
            <NavLink to="/people">People</NavLink>
            <NavLink to="/messages">Messages</NavLink>
            <NavLink to={`/users/${user!.id}`}>Profile</NavLink>
            <button className="link" onClick={logout}>Log out</button>
          </nav>
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}
