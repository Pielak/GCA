import { useState, useEffect, useCallback } from 'react'
import { Search, Loader2, Zap } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface UserItem {
  id: string
  email: string
  full_name?: string
  is_admin?: boolean
  is_active?: boolean
  role?: string
  created_at?: string
  last_login_at?: string
}

export function AdminUsersPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [users, setUsers] = useState<UserItem[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const toggleStatus = async (userId: string) => {
    setActionLoading(userId)
    try {
      const user = users.find(u => u.id === userId)
      const action = user?.is_active !== false ? 'block' : 'unblock'
      await apiClient.post(`/admin/users/${userId}/${action}`)
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_active: !(u.is_active !== false) } : u))
    } catch { /* empty */ } finally {
      setActionLoading(null)
    }
  }

  const loadUsers = useCallback(async () => {
    try {
      const res = await apiClient.get('/admin/users')
      setUsers(res.data.users || res.data || [])
    } catch { /* empty */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadUsers() }, [loadUsers])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  const filtered = users.filter(u => {
    const name = (u.full_name || u.email || '').toLowerCase()
    const email = (u.email || '').toLowerCase()
    const matchSearch = name.includes(search.toLowerCase()) || email.includes(search.toLowerCase())
    const isActive = u.is_active !== false
    const matchStatus = statusFilter === 'all' || (statusFilter === 'active' ? isActive : !isActive)
    return matchSearch && matchStatus
  })

  const formatDate = (d?: string) => {
    if (!d) return '—'
    try { return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(d)) }
    catch { return '—' }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Gestão de Usuários</h1>
        <p className="text-slate-500 text-sm mt-0.5">Controle de acesso e perfis do sistema</p>
      </div>

      {/* Filtros */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nome ou e-mail..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
          />
        </div>
        <select
          value={statusFilter} onChange={e => setStatusFilter(e.target.value as typeof statusFilter)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-violet-600"
        >
          <option value="all">Todos</option>
          <option value="active">Ativos</option>
          <option value="inactive">Inativos</option>
        </select>
      </div>

      {/* Tabela */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-800/50">
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">USUÁRIO</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">PERFIL</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">STATUS</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">ÚLTIMO ACESSO</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">CADASTRADO EM</th>
              <th className="text-right px-4 py-3 text-xs text-slate-500 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length > 0 ? filtered.map((u, i) => {
              const isActive = u.is_active !== false
              const displayName = u.full_name || u.email
              return (
                <tr key={u.id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${i === filtered.length - 1 ? 'border-b-0' : ''}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-violet-700/60 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
                        {displayName.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-slate-200 text-sm font-medium">{displayName}</p>
                        <p className="text-slate-500 text-xs">{u.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      u.is_admin ? 'bg-violet-600/20 text-violet-300' : 'bg-emerald-500/20 text-emerald-300'
                    }`}>
                      {u.is_admin ? 'Admin' : u.role || 'Usuário'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                      isActive
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                        : 'bg-slate-700/50 text-slate-400 border-slate-600'
                    }`}>
                      <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                      {isActive ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-slate-400 text-xs">{formatDate(u.last_login_at)}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-slate-400 text-xs">{formatDate(u.created_at)}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => toggleStatus(u.id)}
                      disabled={actionLoading === u.id}
                      className={`p-1.5 rounded transition-colors ${
                        isActive
                          ? 'text-emerald-400 hover:text-red-400 hover:bg-red-500/10'
                          : 'text-red-400 hover:text-emerald-400 hover:bg-emerald-500/10'
                      }`}
                      title={isActive ? 'Desativar usuário' : 'Reativar usuário'}
                    >
                      {actionLoading === u.id
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Zap className="w-4 h-4" />
                      }
                    </button>
                  </td>
                </tr>
              )
            }) : (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500 text-sm">Nenhum usuário encontrado</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
