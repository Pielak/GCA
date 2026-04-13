import { useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Bell, Search, LogOut, Command } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'

export function AppLayout() {
  const { user, isLoggedIn } = useAuthStore()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [searchFocused, setSearchFocused] = useState(false)

  useEffect(() => {
    if (!isLoggedIn || !user) {
      navigate('/login')
    }
  }, [isLoggedIn, user, navigate])

  if (!user) return null

  const userName = user.full_name || user.email || 'Usuario'
  const initials = userName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className="flex h-screen bg-[#06060e] text-slate-100 overflow-hidden">
      {/* Noise overlay global */}
      <div className="fixed inset-0 pointer-events-none z-50 opacity-[0.015]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />

      <Sidebar />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* ── Top Bar ── */}
        <header className="flex items-center justify-between px-6 h-14 bg-[#0a0a16]/80 backdrop-blur-xl border-b border-white/[0.06] flex-shrink-0 relative z-20">
          {/* Left glow line */}
          <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-violet-500/20 to-transparent" />

          {/* Search */}
          <div className="flex items-center gap-3">
            <div className={`relative transition-all duration-300 ${searchFocused ? 'w-80' : 'w-64'}`}>
              <Search className={`w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 transition-colors duration-200 ${searchFocused ? 'text-violet-400' : 'text-slate-600'}`} />
              <input
                type="text"
                placeholder="Buscar projetos, artefatos..."
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setSearchFocused(false)}
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-12 py-2 text-sm text-slate-300 placeholder-slate-600 focus:outline-none focus:border-violet-500/40 focus:bg-white/[0.06] focus:shadow-[0_0_0_3px_rgba(112,56,224,0.08)] transition-all duration-300"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-slate-600">
                <kbd className="text-[10px] bg-white/[0.06] border border-white/[0.08] rounded px-1.5 py-0.5 font-mono">⌘K</kbd>
              </div>
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-2">
            {/* Notifications */}
            <button className="relative p-2 rounded-xl text-slate-500 hover:text-slate-200 hover:bg-white/[0.05] transition-all duration-200 group">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full ring-2 ring-[#0a0a16]" />
            </button>

            {/* Divider */}
            <div className="w-px h-6 bg-white/[0.06] mx-1" />

            {/* User */}
            <div className="flex items-center gap-2.5 pl-1">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-600 to-purple-700 flex items-center justify-center text-white text-xs font-bold shadow-[0_0_12px_rgba(112,56,224,0.25)]">
                {initials}
              </div>
              <div className="hidden sm:block">
                <p className="text-sm text-slate-200 font-medium leading-none">{userName}</p>
                <p className="text-[10px] text-slate-500 mt-0.5">{user.is_admin ? 'Administrador' : 'Membro'}</p>
              </div>
              <button
                onClick={() => { logout(); navigate('/login') }}
                className="p-2 rounded-xl text-slate-600 hover:text-red-400 hover:bg-red-500/[0.08] transition-all duration-200"
                title="Sair"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </header>

        {/* ── Content Area ── */}
        <main className="flex-1 overflow-y-auto bg-gradient-to-b from-[#0a0a16] to-[#06060e] relative">
          {/* Subtle ambient glow */}
          <div className="absolute top-0 left-1/4 w-[600px] h-[300px] bg-gradient-radial from-violet-500/[0.03] to-transparent rounded-full pointer-events-none" />
          <div className="relative z-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
