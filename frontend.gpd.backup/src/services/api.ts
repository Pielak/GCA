import axios from "axios";
import { useAuthStore } from "@/store/auth";

export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

// Injetar token em todas as requisições
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().access_token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh em 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const { refresh_token, setAuth, clearAuth, user } = useAuthStore.getState();
      if (refresh_token && user) {
        try {
          const { data } = await axios.post("/api/v1/auth/refresh", { refresh_token });
          setAuth(user, data.access_token, data.refresh_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          clearAuth();
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);
