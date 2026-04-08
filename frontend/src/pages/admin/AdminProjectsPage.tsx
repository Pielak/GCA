import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, CheckCircle, XCircle, AlertCircle, Clock, ChevronRight, Loader2 } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface PendingRequest {
  id: string
  name: string
  description: string
  requestedBy: string
  outputProfile: string
  requestedAt: string
}

interface Project {
  id: string
  name: string
  slug: string
  status: string
  outputProfile: string
  phase: number
  gpName: string
  gatekeeperScore: number
  pendingIssues: number
}

const OUTPUT_LABELS: Record<string, string> = {
  web_app: 'Web App', api: 'API', desktop: 'Desktop', mobile: 'Mobile', improvement: 'Melhoria', new_feature: 'Nova Feature',
}

export function AdminProjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [pending, setPending] = useState<PendingRequest[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [pendingRes, projectsRes] = await Promise.allSettled([
        apiClient.get('/admin/projects/pending'),
        apiClient.get('/projects'),
      ])
      if (pendingRes.status === 'fulfilled') setPending(pendingRes.value.data.requests || pendingRes.value.data || [])
      if (projectsRes.status === 'fulfilled') setProjects(projectsRes.value.data.projects || projectsRes.value.data || [])
    } catch { /* empty */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleApprove = async (id: string) => {
    setActionLoading(id)
    try {
      await apiClient.post(`/admin/projects/${id}/approve`)
      setPending(prev => prev.filter(r => r.id !== id))
      await loadData()
    } catch { /* toast error */ } finally {
      setActionLoading(null)
    }
  }

  const handleReject = async (id: string) => {
    if (!confirm('Tem certeza que deseja rejeitar este projeto?')) return
    setActionLoading(id)
    try {
      await apiClient.post(`/admin/projects/${id}/reject`)
      setPending(prev => prev.filter(r => r.id !== id))
    } catch { /* toast error */ } finally {
      setActionLoading(null)
    }
  }

  const filtered = projects.filter(p => {
    const matchSearch = p.name.toLowerCase().includes(search.toLowerCase()) || p.slug.toLowerCase().includes(search.toLowerCase())
    const matchStatus = statusFilter === 'all' || p.status === statusFilter
    return matchSearch && matchStatus
  })

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Gestao de Projetos</h1>
        <p className="text-slate-500 text-sm mt-0.5">Consolide solicitacoes, avalie pre-requisitos e libere tenants.</p>
      </div>

      {/* Pending Requests */}
      {pending.length > 0 && (
        <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle className="w-4 h-4 text-amber-400" />
            <h3 className="text-amber-300 text-sm font-semibold">Solicitacoes Pendentes ({pending.length})</h3>
          </div>
          <div className="space-y-3">
            {pending.map(req => (
              <div key={req.id} className="flex items-center justify-between p-4 bg-slate-900/60 rounded-lg border border-slate-800">
                <div className="flex items-start gap-4">
                  <div className="w-9 h-9 rounded-lg bg-amber-900/30 border border-amber-700/30 flex items-center justify-center flex-shrink-0">
                    <Clock className="w-4 h-4 text-amber-400" />
                  </div>
                  <div>
                    <p className="text-slate-200 text-sm font-medium">{req.name}</p>
                    <p className="text-slate-400 text-xs mt-0.5">{req.description}</p>
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className="text-slate-500 text-xs">Solicitado por: <span className="text-slate-400">{req.requestedBy}</span></span>
                      <span className="text-slate-600">-</span>
                      <span className="text-slate-500 text-xs">{OUTPUT_LABELS[req.outputProfile] || req.outputProfile}</span>
                      <span className="text-slate-600">-</span>
                      <span className="text-slate-500 text-xs">{new Date(req.requestedAt).toLocaleDateString('pt-BR')}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => handleReject(req.id)}
                    disabled={actionLoading === req.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-900/30 border border-red-800/40 text-red-400 hover:bg-red-900/50 disabled:opacity-50 transition-colors text-xs"
                  >
                    <XCircle className="w-3.5 h-3.5" /> Rejeitar
                  </button>
                  <button
                    onClick={() => handleApprove(req.id)}
                    disabled={actionLoading === req.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-900/30 border border-emerald-800/40 text-emerald-400 hover:bg-emerald-900/50 disabled:opacity-50 transition-colors text-xs"
                  >
                    {actionLoading === req.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                    Aprovar e Liberar
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar projeto..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-violet-600"
        >
          <option value="all">Todos os status</option>
          <option value="active">Ativo</option>
          <option value="degraded">Degradado</option>
          <option value="provisioning">Provisionando</option>
          <option value="draft">Rascunho</option>
          <option value="suspended">Suspenso</option>
          <option value="archived">Arquivado</option>
        </select>
      </div>

      {/* Projects Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800">
                {['PROJETO', 'STATUS', 'OUTPUT', 'FASE', 'GP', 'GATEKEEPER', 'PENDENCIAS', ''].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs text-slate-500 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? filtered.map((proj, i) => (
                <tr
                  key={proj.id}
                  className={`border-b border-slate-800/50 hover:bg-slate-800/40 transition-colors cursor-pointer ${i === filtered.length - 1 ? 'border-b-0' : ''}`}
                  onClick={() => navigate(`/projects/${proj.id}`)}
                >
                  <td className="px-4 py-3">
                    <p className="text-slate-200 text-sm font-medium">{proj.name}</p>
                    <p className="text-slate-500 text-xs">{proj.slug}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      proj.status === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                      proj.status === 'degraded' ? 'bg-amber-500/20 text-amber-300' :
                      proj.status === 'provisioning' ? 'bg-blue-500/20 text-blue-300' :
                      'bg-slate-700 text-slate-400'
                    }`}>{proj.status}</span>
                  </td>
                  <td className="px-4 py-3"><span className="text-slate-400 text-xs">{OUTPUT_LABELS[proj.outputProfile] || proj.outputProfile}</span></td>
                  <td className="px-4 py-3"><span className="text-slate-300 text-sm">{proj.phase}</span></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <div className="w-5 h-5 rounded-full bg-violet-700/60 flex items-center justify-center text-white text-xs">{(proj.gpName || '?').charAt(0)}</div>
                      <span className="text-slate-400 text-xs">{(proj.gpName || '').split(' ')[0]}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 bg-slate-700 rounded-full h-1.5">
                        <div className="h-1.5 rounded-full transition-all" style={{
                          width: `${proj.gatekeeperScore || 0}%`,
                          backgroundColor: (proj.gatekeeperScore || 0) >= 90 ? '#34d399' : (proj.gatekeeperScore || 0) >= 70 ? '#fbbf24' : '#f87171'
                        }} />
                      </div>
                      <span className="text-xs text-slate-400">{proj.gatekeeperScore || 0}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {(proj.pendingIssues || 0) > 0 ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-red-900/50 text-red-400 text-xs">{proj.pendingIssues}</span>
                    ) : (
                      <span className="text-slate-600 text-xs">--</span>
                    )}
                  </td>
                  <td className="px-4 py-3"><ChevronRight className="w-4 h-4 text-slate-600" /></td>
                </tr>
              )) : (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500 text-sm">Nenhum projeto encontrado</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
