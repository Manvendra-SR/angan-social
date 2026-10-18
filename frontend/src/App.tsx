import { Navigate, Route, Routes } from "react-router";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Feed from "./pages/Feed";
import Profile from "./pages/Profile";
import People from "./pages/People";
import Chat from "./pages/Chat";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) return <p className="center muted">Loading…</p>;

  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Feed />} />
        <Route path="users/:id" element={<Profile />} />
        <Route path="people" element={<People />} />
        <Route path="messages" element={<Chat />} />
        <Route path="messages/:id" element={<Chat />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
