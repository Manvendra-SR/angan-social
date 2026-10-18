import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, token } from "./api";
import type { Me } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setUser: (user: Me) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(Boolean(token.get()));

  useEffect(() => {
    if (token.get()) {
      api.me().then(setUser).catch(() => token.clear()).finally(() => setLoading(false));
    }
    // api.ts fires this when the server rejects the token (expired)
    const onLogout = () => setUser(null);
    window.addEventListener("auth:logout", onLogout);
    return () => window.removeEventListener("auth:logout", onLogout);
  }, []);

  async function login(email: string, password: string) {
    const { access_token } = await api.login(email, password);
    token.set(access_token);
    setUser(await api.me());
  }

  function logout() {
    token.clear();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
