import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  is_active: boolean
  first_access_completed: boolean
}

export interface AuthStore {
  token: string | null
  user: User | null
  isLoggedIn: boolean
  setToken: (token: string) => void
  setUser: (user: User) => void
  logout: () => void
  hydrate: () => void
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isLoggedIn: false,

      setToken: (token: string) => {
        set({ token, isLoggedIn: !!token })
        if (token) {
          localStorage.setItem('token', token)
        } else {
          localStorage.removeItem('token')
        }
      },

      setUser: (user: User) => {
        set({ user })
      },

      logout: () => {
        set({ token: null, user: null, isLoggedIn: false })
        localStorage.removeItem('token')
        localStorage.removeItem('auth-storage')
      },

      hydrate: () => {
        const token = localStorage.getItem('token')
        if (token) {
          set({ token, isLoggedIn: true })
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
      }),
    }
  )
)

// Hydrate on app load
useAuthStore.getState().hydrate()
