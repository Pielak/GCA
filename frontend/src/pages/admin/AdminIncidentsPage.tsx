import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Bug, RefreshCw, Loader2, AlertCircle, Filter, ChevronRight,
  CheckCircle2, XCircle, PlayCircle,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface Ticket {
  id: string
  project_id: string
  project_name: string | null
  author_id: string
  author_name: string | null
  target_scope: 'gp' | 'admin'
  category: string
  priority: 'baixa' | 'media' | 'alta' | 'critica'
  status: 'open' | 'in_progress' | 'resolved' | 'closed'
  title: string
  description: string
  created_at: string
  resolved_at: string | null
}

const CATEGORY_LABELS: Record<string, string> = {
  bug: 'Bug',
  duvida: 'Dúvida',
  pedido_feature: 'Pedido de feature',
  incidente_pipeline: 'Incidente de pipeline',
}

const PRIORITY_CLASSES: Record<string, string> = {
  baixa: 'bg-slate-500/10 text-slate-300 border-slate-500/30',
  media: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
  alta: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  critica: 'bg-red-500/10 text-red-300 border-red-500/30',
}

const STATUS_META: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  open: { label: 'Aberto', icon: AlertCircle, color: 'text-amber-400' },
  in_progress: { label: 'Em andamento', icon: PlayCircle, color: 'text-cyan-400' },
  resolved: { label: 'Resolvido', icon: CheckCircle2, color: 'text-emerald-400' },
  closed: { label: 'Fechado', icon: XCircle, color: 'text-slate-500' },
}

export function AdminIncidentsPage() {
  const [items, setItems] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [projectFilter, setProjectFilter] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: string[] = []
      if (statusFilter !== 'all') params.push(`status=${statusFilter}`)
      if (projectFilter) params.push(`project_id=${projectFilter}`)
      const q = params.length ? `?${params.join('&')}` : ''
      const res = await apiClient.get(`/admin/incidents${q}`)
      setItems(res.data.items || [])
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar tickets.')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, projectFilter])

  useEffect(() => { load() }, [load])

  // Lista de projetos (derivada dos tickets — admin vê todos projetos que
  // tiveram pelo menos um ticket escalado)
  const projects = useMemo(() => {
    const map = new Map<string, string>()
    items.forEach(t => {
      if (t.project_id && !map.has(t.project_id)) {
        map.set(t.project_id, t.project_name || t.project_id.slice(0, 8))
      }
    })
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]))
  }, [items])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Bug className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Incidentes · visão admin</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Tickets escalados por GPs para administradores. Agregação cross-projeto.
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

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-end p-3 bg-slate-900/40 border border-slate-800 rounded-xl">
        <div>
          <label className="text-slate-500 text-xs block mb-1">
            <Filter className="inline w-3 h-3 mr-1" /> Status
          </label>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="all">Todos</option>
            <option value="open">Aberto</option>
            <option value="in_progress">Em andamento</option>
            <option value="resolved">Resolvido</option>
            <option value="closed">Fechado</option>
          </select>
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="text-slate-500 text-xs block mb-1">Projeto</label>
          <select
            value={projectFilter}
            onChange={e => setProjectFilter(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="">Todos os projetos</option>
            {projects.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        </div>
        <span className="text-slate-500 text-xs ml-auto self-end">
          {items.length} ticket(s)
        </span>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="flex items-center gap-2 p-6 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
        </div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-10 text-center text-slate-500 text-sm">
          Nenhum ticket escalado para administradores no momento.
        </div>
      ) : (
        <div className="overflow-x-auto bg-slate-900/40 border border-slate-800 rounded-xl">
          <table className="w-full text-sm">
            <thead className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th className="text-left py-2 px-3 w-10">Status</th>
                <th className="text-left py-2 px-3">Título</th>
                <th className="text-left py-2 px-3">Projeto</th>
                <th className="text-left py-2 px-3">Autor</th>
                <th className="text-left py-2 px-3">Categoria</th>
                <th className="text-left py-2 px-3">Prioridade</th>
                <th className="text-left py-2 px-3">Aberto em</th>
                <th className="py-2 px-3 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(t => {
                const sm = STATUS_META[t.status] ?? STATUS_META.open
                const SIcon = sm.icon
                return (
                  <tr key={t.id} className="border-b border-slate-800/50 hover:bg-slate-900/40">
                    <td className="py-2 px-3">
                      <SIcon className={`w-4 h-4 ${sm.color}`} />
                    </td>
                    <td className="py-2 px-3 text-slate-200">
                      <Link
                        to={`/projects/${t.project_id}/incidents/${t.id}`}
                        className="hover:text-violet-400"
                      >
                        {t.title}
                      </Link>
                    </td>
                    <td className="py-2 px-3 text-slate-400 text-xs">
                      {t.project_name || t.project_id.slice(0, 8)}
                    </td>
                    <td className="py-2 px-3 text-slate-400 text-xs">
                      {t.author_name || '—'}
                    </td>
                    <td className="py-2 px-3 text-slate-400 text-xs">
                      {CATEGORY_LABELS[t.category] || t.category}
                    </td>
                    <td className="py-2 px-3">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-md border ${PRIORITY_CLASSES[t.priority] || 'border-slate-500/30 text-slate-400'}`}>
                        {t.priority}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-500 text-xs">
                      {new Date(t.created_at).toLocaleString('pt-BR')}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <Link
                        to={`/projects/${t.project_id}/incidents/${t.id}`}
                        className="text-slate-500 hover:text-violet-400"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
