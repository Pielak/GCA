import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * Guarda de rota que bloqueia acesso a páginas admin para não-admins.
 * Redireciona para /projects se o usuário não é admin.
 */
export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore()

  if (!user?.is_admin) {
    return <Navigate to="/projects" replace />
  }

  return <>{children}</>
}
