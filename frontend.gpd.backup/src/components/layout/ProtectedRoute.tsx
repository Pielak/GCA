import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

export function ProtectedRoute() {
  const { isAuthenticated, user } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  // Força re-autenticação: usuário deve passar pelo login antes da troca de senha
  if (user?.must_change_password) return <Navigate to="/login" replace />;
  return <Outlet />;
}
