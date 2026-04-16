import { useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useToastStore } from '@/stores/toastStore'
import api from '@/lib/api'

export const useAuth = () => {
  const { token, user, isLoggedIn, setToken, setUser, logout } = useAuthStore()
  const { addToast } = useToastStore()

  const login = useCallback(
    async (email: string, password: string) => {
      try {
        const response = await api.post('/auth/login', { email, password })
        const { access_token, user: userData } = response.data

        setToken(access_token)
        if (userData) {
          setUser(userData)
        }
        addToast('Login realizado com sucesso!', 'success')
        return true
      } catch (error: any) {
        const message = error.message || 'Erro ao fazer login'
        addToast(message, 'error')
        return false
      }
    },
    [setToken, setUser, addToast]
  )

  /**
   * Login via slug do projeto — chama POST /auth/project-login
   * Retorna { project_id, first_access_completed } em caso de sucesso.
   * Lança erro com status e message em caso de falha.
   */
  const projectLogin = useCallback(
    async (email: string, password: string, projectSlug: string) => {
      const response = await api.post('/auth/project-login', {
        email,
        password,
        project_slug: projectSlug,
      })
      const { access_token, user: userData, project_id } = response.data

      setToken(access_token)
      if (userData) {
        setUser(userData)
      }
      return { project_id, first_access_completed: userData?.first_access_completed ?? true }
    },
    [setToken, setUser]
  )

  const handleLogout = useCallback(() => {
    logout()
    addToast('Logout realizado', 'info')
  }, [logout, addToast])

  return {
    token,
    user,
    isLoggedIn,
    login,
    projectLogin,
    logout: handleLogout,
  }
}
