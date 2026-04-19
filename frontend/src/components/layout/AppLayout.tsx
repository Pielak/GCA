import { useEffect, useState, useRef, useCallback } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Bell, Search, LogOut, Command, Check, CheckCheck, Sparkles } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { BackupActiveBanner } from '../BackupActiveBanner'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'
import { useNotificationsWS } from '@/hooks/useNotificationsWS'
import { apiClient } from '@/lib/api'

type Notification = {
  id: string
  event_type: string
  title: string
  message: string
  link: string | null
  severity: string
  read_at: string | null
  created_at: string | null
}

export function AppLayout() {
  const { user, isLoggedIn } = useAuthStore()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [searchFocused, setSearchFocused] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [notifLoading, setNotifLoading] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)

  const refreshCount = useCallback(async () => {
    if (!isLoggedIn) return
    try {
      const res = await apiClient.get('/notifications/count')
      setUnreadCount(res.data?.unread ?? 0)
    } catch { /* silencioso */ }
  }, [isLoggedIn])

  // WebSocket em tempo real: nova notif chega em ms, otimisticamente
  // bumpa o contador e prepende na lista local. O contador real é
  // re-sincronizado no próximo abrir do dropdown / fetch.
  const { connected: wsConnected } = useNotificationsWS({
    enabled: isLoggedIn,
    onNotification: (n) => {
      setUnreadCount(c => c + 1)
      setNotifications(prev => {
        // Evita duplicação se a mesma chegou duas vezes
        if (prev.some(p => p.id === n.id)) return prev
        return [{
          id: n.id,
          event_type: n.event_type,
          title: n.title,
          message: n.message,
          link: n.link,
          severity: n.severity,
          read_at: null,
          created_at: n.created_at,
        }, ...prev].slice(0, 50)
      })
    },
  })

  // Fetch inicial + fallback de poll (5min) só quando WS está OFFLINE.
  // Quando WS conecta, push real-time substitui o poll.
  useEffect(() => {
    refreshCount()
    if (wsConnected) return  // WS ativo: sem poll
    const interval = setInterval(refreshCount, 300_000)  // 5min fallback
    return () => clearInterval(interval)
  }, [refreshCount, wsConnected])

  const loadNotifications = async () => {
    setNotifLoading(true)
    try {
      const res = await apiClient.get('/notifications?limit=20')
      setNotifications(res.data?.notifications || [])
    } catch { setNotifications([]) }
    setNotifLoading(false)
  }

  const handleBellClick = () => {
    const next = !notifOpen
    setNotifOpen(next)
    if (next) loadNotifications()
  }

  // Close dropdown ao clicar fora
  useEffect(() => {
    if (!notifOpen) return
    const onClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [notifOpen])

  const markRead = async (id: string, link: string | null) => {
    try {
      await apiClient.post(`/notifications/${id}/read`)
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
      setUnreadCount(c => Math.max(0, c - 1))
    } catch { /* silencioso */ }
    if (link) {
      setNotifOpen(false)
      navigate(link)
    }
  }

  const markAllRead = async () => {
    try {
      await apiClient.post('/notifications/read-all')
      setNotifications(prev => prev.map(n => ({ ...n, read_at: n.read_at || new Date().toISOString() })))
      setUnreadCount(0)
    } catch { /* silencioso */ }
  }

  const formatTime = (iso: string | null) => {
    if (!iso) return ''
    const d = new Date(iso)
    const diffMin = (Date.now() - d.getTime()) / 60_000
    if (diffMin < 1) return 'agora'
    if (diffMin < 60) return `${Math.floor(diffMin)}min atrás`
    if (diffMin < 60 * 24) return `${Math.floor(diffMin / 60)}h atrás`
    return d.toLocaleDateString('pt-BR')
  }

  const sevDot = (s: string) => {
    if (s === 'error') return 'bg-red-500'
    if (s === 'warning') return 'bg-amber-500'
    if (s === 'success') return 'bg-emerald-500'
    return 'bg-violet-500'
  }

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
      {/* Backup-4: banner de backup ativo (cross-projeto) */}
      <BackupActiveBanner />
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
            <div ref={notifRef} className="relative">
              <button
                onClick={handleBellClick}
                className="relative p-2 rounded-xl text-slate-500 hover:text-slate-200 hover:bg-white/[0.05] transition-all duration-200 group"
                aria-label="Notificações"
              >
                <Bell className="w-4 h-4" />
                {unreadCount > 0 && (
                  <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-1 bg-red-500 rounded-full ring-2 ring-[#0a0a16] text-[10px] font-bold text-white flex items-center justify-center">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute right-0 top-full mt-2 w-96 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800">
                    <h3 className="text-slate-100 text-sm font-semibold">Notificações</h3>
                    {unreadCount > 0 && (
                      <button
                        onClick={markAllRead}
                        className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200"
                      >
                        <CheckCheck className="w-3 h-3" /> Marcar todas como lidas
                      </button>
                    )}
                  </div>
                  <div className="max-h-[28rem] overflow-y-auto">
                    {notifLoading ? (
                      <p className="text-slate-500 text-xs text-center py-6">Carregando…</p>
                    ) : notifications.length === 0 ? (
                      <p className="text-slate-500 text-xs text-center py-6">Sem notificações por enquanto.</p>
                    ) : (
                      notifications.map(n => (
                        <button
                          key={n.id}
                          onClick={() => markRead(n.id, n.link)}
                          className={`w-full text-left px-4 py-3 border-b border-slate-800/80 hover:bg-slate-800/40 transition-colors ${!n.read_at ? 'bg-violet-500/5' : ''}`}
                        >
                          <div className="flex items-start gap-2.5">
                            <span className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${sevDot(n.severity)} ${n.read_at ? 'opacity-30' : ''}`} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-2">
                                <p className={`text-sm font-medium truncate ${n.read_at ? 'text-slate-400' : 'text-slate-100'}`}>{n.title}</p>
                                <span className="text-[10px] text-slate-500 flex-shrink-0">{formatTime(n.created_at)}</span>
                              </div>
                              <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{n.message}</p>
                            </div>
                            {!n.read_at && <Check className="w-3 h-3 text-slate-600 flex-shrink-0 mt-1" />}
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Releases (changelog user-facing) */}
            <button
              onClick={() => navigate('/releases')}
              className="p-2 rounded-xl text-slate-500 hover:text-violet-300 hover:bg-white/[0.05] transition-all duration-200"
              title="Novidades e entregas"
              aria-label="Novidades"
            >
              <Sparkles className="w-4 h-4" />
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
