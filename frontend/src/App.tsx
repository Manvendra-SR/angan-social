import { Navigate, Route, Routes } from "react-router";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Spinner } from "./components/States";
import { RealtimeProvider } from "./realtime";
import Chat from "./pages/Chat";
import Feed from "./pages/Feed";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";
import PostDetail from "./pages/PostDetail";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import Search from "./pages/Search";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) return <Spinner />;

  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    // one realtime connection per logged-in session (key: a new user gets a new socket)
    <RealtimeProvider key={user.id}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Feed />} />
          <Route path="posts/:id" element={<PostDetail />} />
          <Route path="users/:id" element={<Profile />} />
          <Route path="search" element={<Search />} />
          <Route path="people" element={<Navigate to="/search" replace />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="messages" element={<Chat />} />
          <Route path="messages/:id" element={<Chat />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </RealtimeProvider>
  );
}
