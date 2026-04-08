import { useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Menu, Bell, Search, LogOut } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'

export function AppLayout() {
  const { user, isLoggedIn } = useAuthStore()
  const { logout } = useAuth()
  const navigate = useNavigate()

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isLoggedIn || !user) {
      navigate('/login')
    }
  }, [isLoggedIn, user, navigate])

  if (!user) return null

  const userName = user.full_name || user.email || 'Usuario'

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="flex items-center justify-between px-6 py-3 bg-slate-900/50 border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="Buscar projetos, artefatos..."
                className="bg-slate-800 border border-slate-700 rounded-md pl-8 pr-3 py-1.5 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 w-64"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button className="relative p-1.5 rounded-md text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors">
              <Bell className="w-4 h-4" />
              <span className="absolute top-0.5 right-0.5 w-2 h-2 bg-red-500 rounded-full" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-violet-700 flex items-center justify-center text-white text-xs font-semibold">
                {userName.charAt(0).toUpperCase()}
              </div>
              <div className="hidden sm:block">
                <p className="text-sm text-slate-200">{userName}</p>
              </div>
              <button
                onClick={() => { logout(); navigate('/login') }}
                className="p-1.5 rounded-md text-slate-500 hover:text-red-400 hover:bg-slate-800 transition-colors"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto bg-slate-950">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
