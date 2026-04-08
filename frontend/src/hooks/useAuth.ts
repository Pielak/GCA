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

  const handleLogout = useCallback(() => {
    logout()
    addToast('Logout realizado', 'info')
  }, [logout, addToast])

  return {
    token,
    user,
    isLoggedIn,
    login,
    logout: handleLogout,
  }
}
