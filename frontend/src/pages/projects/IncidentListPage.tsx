import { useState, useEffect, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bug, Plus, RefreshCw, Loader2, AlertCircle, Filter,
  ChevronRight, MessageSquare,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { NewIncidentModal } from '@/components/incidents/NewIncidentModal'
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
  updated_at: string
  resolved_at: string | null
}

const CATEGORY_LABELS: Record<string, string> = {
  bug: 'Bug',
  duvida: 'Dúvida',
  pedido_feature: 'Pedido de feature',
  incidente_pipeline: 'Incidente de pipeline',
}

const PRIORITY_DOT: Record<string, string> = {
  baixa: 'bg-slate-500',
  media: 'bg-cyan-400',
  alta: 'bg-amber-400',
  critica: 'bg-red-500',
}

const STATUS_LABELS: Record<string, { label: string; classes: string }> = {
  open: { label: 'Aberto', classes: 'bg-amber-500/10 text-amber-300 border-amber-500/30' },
  in_progress: { label: 'Em andamento', classes: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30' },
  resolved: { label: 'Resolvido', classes: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' },
  closed: { label: 'Fechado', classes: 'bg-slate-500/10 text-slate-400 border-slate-500/30' },
}

export function IncidentListPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [items, setItems] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [modalOpen, setModalOpen] = useState(false)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const q = statusFilter !== 'all' ? `?status=${statusFilter}` : ''
      const res = await apiClient.get(`/projects/${projectId}/incidents${q}`)
      setItems(res.data.items || [])
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar tickets.')
    } finally {
      setLoading(false)
    }
  }, [projectId, statusFilter])

  useEffect(() => { load() }, [load])

  const onCreated = () => {
    setModalOpen(false)
    load()
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Bug className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Incidentes</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Reporte bugs, dúvidas ou pedidos de funcionalidade. Dev/Tester/QA → vai para o GP do projeto.
            GP → vai para os administradores.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Atualizar
          </button>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs rounded-lg"
          >
            <Plus className="w-3.5 h-3.5" /> Abrir ticket
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Filtro status */}
      <div className="flex items-center gap-3 p-3 bg-slate-900/40 border border-slate-800 rounded-xl">
        <label className="text-slate-500 text-xs flex items-center gap-1">
          <Filter className="w-3 h-3" /> Status
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
        <span className="text-slate-500 text-xs ml-auto">{items.length} ticket(s)</span>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="flex items-center gap-2 p-6 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
        </div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-10 text-center text-slate-500 text-sm">
          Nenhum ticket encontrado.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map(t => {
            const sb = STATUS_LABELS[t.status] ?? STATUS_LABELS.open
            return (
              <Link
                key={t.id}
                to={`/projects/${projectId}/incidents/${t.id}`}
                className="block bg-slate-900/40 hover:bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-xl px-4 py-3 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${PRIORITY_DOT[t.priority] || 'bg-slate-500'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-slate-100 text-sm font-medium truncate">{t.title}</h3>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-md border ${sb.classes}`}>{sb.label}</span>
                      <span className="text-[10px] text-slate-500">
                        {CATEGORY_LABELS[t.category] || t.category} · prioridade {t.priority}
                      </span>
                    </div>
                    <p className="text-slate-400 text-xs mt-1 line-clamp-2">{t.description}</p>
                    <div className="flex items-center gap-3 mt-1.5 text-[11px] text-slate-500">
                      <span>Por {t.author_name || 'autor desconhecido'}</span>
                      <span>·</span>
                      <span>{new Date(t.created_at).toLocaleString('pt-BR')}</span>
                      <span>·</span>
                      <span className="uppercase tracking-wider">
                        {t.target_scope === 'admin' ? 'Escalado → Admin' : 'Para GP'}
                      </span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-600 mt-2" />
                </div>
              </Link>
            )
          })}
        </div>
      )}

      {modalOpen && projectId && (
        <NewIncidentModal
          projectId={projectId}
          onClose={() => setModalOpen(false)}
          onCreated={onCreated}
        />
      )}
    </div>
  )
}
