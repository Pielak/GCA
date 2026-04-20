import { useState, useEffect, useCallback } from 'react'
import { Search, Loader2, Zap, Trash2, Shield, FolderOpen, UserPlus, ShieldOff, X } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { getErrorMessage } from '@/lib/errors'

interface ProjectRole {
  project_id: string
  project_name: string
  project_slug: string
  role: string
}

interface UserItem {
  id: string
  email: string
  full_name?: string
  is_admin?: boolean
  is_active?: boolean
  role?: string
  project_roles?: ProjectRole[]
  created_at?: string
  last_login_at?: string
}

// Papéis canônicos (GCA_CANONICAL_CONTRACT.md §4): GP, Dev, Tester, QA.
// Admin é camada administrativa (is_admin=true) — renderizado à parte, não aparece como "project role".
const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  gp:     { label: 'GP',     color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
  dev:    { label: 'Dev',    color: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
  tester: { label: 'Tester', color: 'bg-orange-500/20 text-orange-300 border-orange-500/30' },
  qa:     { label: 'QA',     color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
}

export function AdminUsersPage() {
  const { user: currentUser } = useAuthStore()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [users, setUsers] = useState<UserItem[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const toggleStatus = async (userId: string) => {
    setActionLoading(userId)
    try {
      const user = users.find(u => u.id === userId)
      const action = user?.is_active !== false ? 'block' : 'unblock'
      await apiClient.post(`/admin/users/${userId}/${action}`)
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_active: !(u.is_active !== false) } : u))
      showToast(`Usuário ${user?.is_active !== false ? 'desativado' : 'reativado'}`, 'success')
    } catch (err: unknown) {
      showToast(getErrorMessage(err), 'error')
    } finally {
      setActionLoading(null)
    }
  }

  const toggleAdmin = async (userId: string, currentIsAdmin: boolean, userName: string) => {
    const next = !currentIsAdmin
    const action = next ? 'promover' : 'rebaixar'
    if (!confirm(`Confirma ${action} "${userName}" ${next ? 'a Administrador' : 'de Administrador'}?`)) return
    setActionLoading(userId)
    try {
      await apiClient.patch(`/admin/users/${userId}/admin-flag`, { is_admin: next })
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_admin: next } : u))
      showToast(`"${userName}" ${next ? 'promovido a Admin' : 'rebaixado'}`, 'success')
    } catch (err: unknown) {
      showToast(getErrorMessage(err), 'error')
    } finally {
      setActionLoading(null)
    }
  }

  const deleteUser = async (userId: string, userName: string) => {
    if (!confirm(`Tem certeza que deseja excluir "${userName}"? Esta ação não pode ser desfeita.`)) return
    setActionLoading(userId)
    try {
      await apiClient.delete(`/admin/users/${userId}`)
      setUsers(prev => prev.filter(u => u.id !== userId))
      showToast(`Usuário "${userName}" excluído`, 'success')
    } catch (err: unknown) {
      showToast(getErrorMessage(err), 'error')
    } finally {
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

  const isSelf = (userId: string) => currentUser?.id === userId

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Gestão de Usuários</h1>
          <p className="text-slate-500 text-sm mt-0.5">Controle de acesso, perfis e camada administrativa.</p>
        </div>
        <button
          onClick={() => setInviteOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs rounded-lg flex-shrink-0"
        >
          <UserPlus className="w-3.5 h-3.5" />
          Convidar Administrador
        </button>
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
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium" title="Admin = camada administrativa (não atua em projetos). Demais = papel(is) por projeto.">PERFIL</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">PROJETOS / PAPEL</th>
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
              const projectRoles = u.project_roles || []
              return (
                <tr key={u.id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${i === filtered.length - 1 ? 'border-b-0' : ''}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-semibold flex-shrink-0 ${u.is_admin ? 'bg-purple-700/70' : 'bg-violet-700/60'}`}>
                        {displayName.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-slate-200 text-sm font-medium">{displayName}</p>
                        <p className="text-slate-500 text-xs">{u.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    {u.is_admin ? (
                      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border bg-purple-500/20 text-purple-200 border-purple-500/30" title="Administrador do sistema — não atua em projetos">
                        <Shield className="w-3 h-3" />
                        Admin (sistema)
                      </span>
                    ) : projectRoles.length === 0 ? (
                      <span className="text-xs text-slate-600 italic">— sem projeto —</span>
                    ) : (
                      <span className="text-xs text-slate-400">
                        {Array.from(new Set(projectRoles.map(pr => ROLE_LABELS[pr.role]?.label || pr.role))).join(' · ')}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    {u.is_admin ? (
                      <span className="text-xs text-slate-600">— camada administrativa —</span>
                    ) : projectRoles.length === 0 ? (
                      <span className="text-xs text-slate-600">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5 max-w-md">
                        {projectRoles.map((pr, idx) => {
                          const r = ROLE_LABELS[pr.role] || { label: pr.role, color: 'bg-slate-500/20 text-slate-300 border-slate-500/30' }
                          return (
                            <span
                              key={`${pr.project_id}-${idx}`}
                              className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border ${r.color}`}
                              title={`${r.label} em ${pr.project_name}`}
                            >
                              <FolderOpen className="w-3 h-3 opacity-70" />
                              <span className="font-medium">{r.label}</span>
                              <span className="opacity-70">·</span>
                              <span className="truncate max-w-[140px]">{pr.project_name}</span>
                            </span>
                          )
                        })}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                      isActive
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                        : 'bg-slate-700/50 text-slate-400 border-slate-600'
                    }`}>
                      <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                      {isActive ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className="text-slate-400 text-xs">{formatDate(u.last_login_at)}</span>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className="text-slate-400 text-xs">{formatDate(u.created_at)}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {/* Promover / Rebaixar Admin */}
                      <button
                        onClick={() => toggleAdmin(u.id, !!u.is_admin, u.full_name || u.email)}
                        disabled={actionLoading === u.id || !isActive}
                        className={`p-1.5 rounded transition-colors ${
                          u.is_admin
                            ? 'text-purple-400 hover:text-amber-400 hover:bg-amber-500/10'
                            : 'text-slate-500 hover:text-purple-400 hover:bg-purple-500/10'
                        } disabled:opacity-20 disabled:cursor-not-allowed`}
                        title={
                          !isActive
                            ? 'Ative o usuário antes de mudar o papel Admin'
                            : u.is_admin
                              ? (isSelf(u.id) ? 'Rebaixar-se (apenas se não for o último admin)' : 'Rebaixar de Administrador')
                              : 'Promover a Administrador'
                        }
                      >
                        {u.is_admin
                          ? <ShieldOff className="w-4 h-4" />
                          : <Shield className="w-4 h-4" />
                        }
                      </button>
                      {/* Excluir — não pode excluir a si mesmo */}
                      <button
                        onClick={() => deleteUser(u.id, u.full_name || u.email)}
                        disabled={actionLoading === u.id || isSelf(u.id)}
                        className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
                        title={isSelf(u.id) ? 'Você não pode excluir sua própria conta' : 'Excluir usuário'}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      {/* Ativar/Desativar */}
                      <button
                        onClick={() => toggleStatus(u.id)}
                        disabled={actionLoading === u.id || isSelf(u.id)}
                        className={`p-1.5 rounded transition-colors ${
                          isSelf(u.id) ? 'opacity-20 cursor-not-allowed text-slate-500' :
                          isActive
                            ? 'text-emerald-400 hover:text-red-400 hover:bg-red-500/10'
                            : 'text-red-400 hover:text-emerald-400 hover:bg-emerald-500/10'
                        }`}
                        title={isSelf(u.id) ? 'Você não pode alterar sua própria conta' : isActive ? 'Desativar usuário' : 'Reativar usuário'}
                      >
                        {actionLoading === u.id
                          ? <Loader2 className="w-4 h-4 animate-spin" />
                          : <Zap className="w-4 h-4" />
                        }
                      </button>
                    </div>
                  </td>
                </tr>
              )
            }) : (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500 text-sm">Nenhum usuário encontrado</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {inviteOpen && (
        <InviteAdminModal
          onClose={() => setInviteOpen(false)}
          onDone={(msg, type) => { setInviteOpen(false); showToast(msg, type); loadUsers() }}
        />
      )}
    </div>
  )
}


function InviteAdminModal({
  onClose, onDone,
}: { onClose: () => void; onDone: (msg: string, type: 'success' | 'error') => void }) {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ temp_password: string | null; email_sent: boolean } | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !fullName.trim()) {
      setError('Email e nome são obrigatórios.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const res = await apiClient.post('/admin/invitations/admin', {
        email: email.trim(),
        full_name: fullName.trim(),
      })
      if (res.data.temp_password) {
        // Mostra senha inline pro admin copiar (quando email falhou)
        setResult({ temp_password: res.data.temp_password, email_sent: false })
      } else {
        onDone(
          res.data.created
            ? `Admin "${email}" convidado. Email enviado.`
            : `"${email}" promovido a Admin (já era usuário).`,
          'success',
        )
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err) || 'Falha ao convidar administrador.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <form
        onSubmit={submit}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-400" />
            <h2 className="text-slate-100 text-sm font-semibold">Convidar Administrador</h2>
          </div>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-slate-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        {result ? (
          <div className="p-5 space-y-3">
            <div className="p-3 bg-amber-950/30 border border-amber-900/40 rounded-lg text-amber-200 text-xs">
              Usuário criado com sucesso, mas o envio de email falhou. Comunique a senha abaixo manualmente ao novo administrador. <strong>Ela não voltará a ser exibida.</strong>
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Senha temporária</label>
              <code className="block bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-emerald-300 font-mono break-all">
                {result.temp_password}
              </code>
            </div>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => onDone(`Admin criado. Senha exibida uma única vez — comunique ao usuário.`, 'success')}
                className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs rounded-lg"
              >
                Concluído
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="p-5 space-y-3">
              {error && (
                <div className="p-2.5 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-xs">
                  {error}
                </div>
              )}

              <div>
                <label className="text-slate-400 text-xs block mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="nome@empresa.com"
                  required
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50"
                />
              </div>
              <div>
                <label className="text-slate-400 text-xs block mb-1">Nome completo</label>
                <input
                  type="text"
                  value={fullName}
                  onChange={e => setFullName(e.target.value)}
                  placeholder="Nome do administrador"
                  required
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50"
                />
              </div>

              <p className="text-[11px] text-slate-500">
                Se o email já existir na instância, o usuário será promovido a Administrador sem mudar a senha.
                Se não existir, será criado com senha temporária enviada por email. Quando o envio falha, a senha é exibida aqui na hora.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-slate-800">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-slate-400 hover:text-slate-200 text-xs"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs rounded-lg"
              >
                {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Convidar
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  )
}
