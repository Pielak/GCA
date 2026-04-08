import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string;
  must_change_password: boolean;
}

interface AuthState {
  user: AuthUser | null;
  access_token: string | null;
  refresh_token: string | null;
  isAuthenticated: boolean;
  setAuth: (user: AuthUser, access_token: string, refresh_token: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      access_token: null,
      refresh_token: null,
      isAuthenticated: false,
      setAuth: (user, access_token, refresh_token) =>
        set({ user, access_token, refresh_token, isAuthenticated: true }),
      clearAuth: () =>
        set({ user: null, access_token: null, refresh_token: null, isAuthenticated: false }),
    }),
    { name: "gpd-auth" }
  )
);
