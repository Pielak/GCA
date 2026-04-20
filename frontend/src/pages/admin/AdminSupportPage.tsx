import { useState, useEffect, useCallback } from 'react'
import {
  LifeBuoy, Shield, RefreshCw, Loader2, AlertCircle, UserPlus,
  Search, CheckCircle2,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface SupportUser {
  id: string
  email: string
  full_name: string | null
  is_admin: boolean
  is_support: boolean
}

interface SimpleUser {
  id: string
  email: string
  full_name: string | null
  is_admin: boolean
  is_support?: boolean
  is_active?: boolean
}

export function AdminSupportPage() {
  const [team, setTeam] = useState<SupportUser[]>([])
  const [allUsers, setAllUsers] = useState<SimpleUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [teamRes, usersRes] = await Promise.all([
        apiClient.get('/admin/support'),
        apiClient.get('/admin/users'),
      ])
      setTeam(teamRes.data.items || [])
      // /admin/users retorna {"users": [...]} (não "items") — conferir
      // backend/app/routers/admin.py:list_users
      const userList = usersRes.data.users || usersRes.data.items || []
      setAllUsers(Array.isArray(userList) ? userList : [])
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar Equipe Sustentação.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggleSupport = async (targetId: string, next: boolean) => {
    setTogglingId(targetId)
    try {
      await apiClient.patch(`/admin/support/${targetId}`, { is_support: next })
      await load()
    } catch (e: unknown) {
      alert(getErrorMessage(e) || 'Falha ao atualizar.')
    } finally {
      setTogglingId(null)
    }
  }

  // Candidatos = usuários ativos não-admin e ainda sem is_support
  const teamIds = new Set(team.map(u => u.id))
  const candidates = allUsers
    .filter(u => u.is_active !== false && !u.is_admin && !teamIds.has(u.id))
    .filter(u => {
      if (!search.trim()) return true
      const s = search.toLowerCase()
      return (u.email.toLowerCase().includes(s)
        || (u.full_name || '').toLowerCase().includes(s))
    })

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <LifeBuoy className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Equipe Sustentação</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Usuários que recebem tickets escalados junto com Admins. Admin herda
            Sustentação automaticamente. Promover Support a Admin é feito pela gestão
            canônica de usuários — não por esta tela.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Atualizar
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 p-6 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
        </div>
      ) : (
        <>
          {/* Equipe atual */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-xl">
            <div className="px-4 py-2.5 border-b border-slate-800">
              <h2 className="text-slate-200 text-sm font-medium">
                Membros da equipe ({team.length})
              </h2>
            </div>
            {team.length === 0 ? (
              <p className="text-slate-500 text-sm p-4">
                Ainda não há ninguém com is_support ativo. Admins continuam recebendo tickets (herança).
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="text-left py-2 px-4">Usuário</th>
                    <th className="text-left py-2 px-4">Papéis</th>
                    <th className="text-right py-2 px-4">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {team.map(u => (
                    <tr key={u.id} className="border-b border-slate-800/50 last:border-b-0">
                      <td className="py-2 px-4">
                        <div className="text-slate-200">{u.full_name || u.email}</div>
                        <div className="text-slate-500 text-xs">{u.email}</div>
                      </td>
                      <td className="py-2 px-4">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {u.is_admin && (
                            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-violet-500/10 text-violet-300 border border-violet-500/30">
                              <Shield className="w-3 h-3" /> Admin
                            </span>
                          )}
                          {u.is_support && (
                            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                              <LifeBuoy className="w-3 h-3" /> Sustentação
                            </span>
                          )}
                          {u.is_admin && !u.is_support && (
                            <span className="text-[10px] text-slate-500 italic">(Admin herda Sustentação)</span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 px-4 text-right">
                        {u.is_admin && !u.is_support && (
                          <button
                            onClick={() => toggleSupport(u.id, true)}
                            disabled={togglingId === u.id}
                            className="text-[11px] text-violet-400 hover:text-violet-300 disabled:opacity-40"
                          >
                            Marcar Sustentação explícita
                          </button>
                        )}
                        {u.is_support && (
                          <button
                            onClick={() => toggleSupport(u.id, false)}
                            disabled={togglingId === u.id}
                            className="text-[11px] text-red-400 hover:text-red-300 disabled:opacity-40"
                          >
                            {togglingId === u.id ? 'Aguarde…' : 'Rebaixar'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Promover novos */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-xl">
            <div className="px-4 py-2.5 border-b border-slate-800 flex items-center gap-2">
              <UserPlus className="w-4 h-4 text-slate-400" />
              <h2 className="text-slate-200 text-sm font-medium">Promover usuário a Sustentação</h2>
            </div>
            <div className="p-4 space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                <input
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar usuário por nome ou email"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50"
                />
              </div>
              {candidates.length === 0 ? (
                <p className="text-slate-500 text-xs italic">
                  Nenhum candidato encontrado {search ? 'para essa busca' : ''}.
                </p>
              ) : (
                <ul className="space-y-1 max-h-72 overflow-y-auto">
                  {candidates.slice(0, 30).map(u => (
                    <li key={u.id} className="flex items-center justify-between bg-slate-800/40 hover:bg-slate-800/70 rounded px-3 py-2">
                      <div>
                        <div className="text-slate-200 text-sm">{u.full_name || u.email}</div>
                        <div className="text-slate-500 text-xs">{u.email}</div>
                      </div>
                      <button
                        onClick={() => toggleSupport(u.id, true)}
                        disabled={togglingId === u.id}
                        className="flex items-center gap-1 px-2.5 py-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-[11px] rounded"
                      >
                        {togglingId === u.id
                          ? <Loader2 className="w-3 h-3 animate-spin" />
                          : <CheckCircle2 className="w-3 h-3" />
                        }
                        Adicionar
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {candidates.length > 30 && (
                <p className="text-slate-500 text-xs">
                  Mostrando 30 de {candidates.length} — refine a busca.
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
