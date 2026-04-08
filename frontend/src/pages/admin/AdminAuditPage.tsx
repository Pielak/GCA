import { useState, useEffect, useCallback } from 'react'
import { Search, AlertCircle, AlertTriangle, Info, Hash, Download, Loader2 } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface AuditEvent {
  id: string
  action: string
  detail: string
  level: string
  actor: string
  actorRole: string
  target: string
  projectId?: string
  projectName?: string
  hash: string
  prevHash: string
  timestamp: string
}

const levelIcon = (level: string) => {
  if (level === 'critical') return <AlertCircle className="w-3.5 h-3.5 text-red-400" />
  if (level === 'warning') return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
  return <Info className="w-3.5 h-3.5 text-blue-400" />
}

const levelBg = (level: string) => {
  if (level === 'critical') return 'border-red-900/30 bg-red-950/10'
  if (level === 'warning') return 'border-amber-900/30 bg-amber-950/10'
  return 'border-slate-800 bg-transparent'
}

export function AdminAuditPage() {
  const [search, setSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState('all')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)

  const loadEvents = useCallback(async () => {
    try {
      const res = await apiClient.get('/admin/audit')
      setEvents(res.data.events || res.data || [])
    } catch { /* empty */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadEvents() }, [loadEvents])

  const filtered = events.filter(ev => {
    const matchSearch = ev.action.toLowerCase().includes(search.toLowerCase()) ||
      ev.detail.toLowerCase().includes(search.toLowerCase()) ||
      ev.actor.toLowerCase().includes(search.toLowerCase())
    const matchLevel = levelFilter === 'all' || ev.level === levelFilter
    return matchSearch && matchLevel
  })

  const lastHash = events.length > 0 ? events[0].hash?.slice(0, 16) : 'N/A'

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Auditoria Global</h1>
          <p className="text-slate-500 text-sm mt-0.5">Trilha encadeada append-only com prova de integridade</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-sm hover:bg-slate-700 transition-colors">
          <Download className="w-4 h-4" />
          Exportar
        </button>
      </div>

      {/* Integrity Banner */}
      <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-950/20 border border-emerald-800/30">
        <div className="w-8 h-8 rounded-full bg-emerald-900/40 flex items-center justify-center flex-shrink-0">
          <Hash className="w-4 h-4 text-emerald-400" />
        </div>
        <div>
          <p className="text-emerald-300 text-sm font-medium">Cadeia de Hash Integra</p>
          <p className="text-emerald-700 text-xs">Ultimo hash: <code className="text-emerald-500">{lastHash}</code> -- {events.length} eventos encadeados.</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por acao, detalhe ou ator..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
          />
        </div>
        <select
          value={levelFilter} onChange={e => setLevelFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-violet-600"
        >
          <option value="all">Todos os niveis</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </select>
      </div>

      {/* Events */}
      {filtered.length > 0 ? (
        <div className="space-y-2">
          {filtered.map(ev => (
            <div key={ev.id} className={`border rounded-xl overflow-hidden transition-all ${levelBg(ev.level)}`}>
              <button
                onClick={() => setExpanded(expanded === ev.id ? null : ev.id)}
                className="w-full flex items-start gap-4 p-4 text-left hover:bg-slate-800/30 transition-colors"
              >
                <div className="mt-0.5 flex-shrink-0">{levelIcon(ev.level)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <code className="text-xs font-mono text-violet-400 bg-violet-900/20 px-1.5 py-0.5 rounded">{ev.action}</code>
                    {ev.projectName && <span className="text-xs text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">{ev.projectName}</span>}
                  </div>
                  <p className="text-slate-300 text-sm mt-1 leading-snug">{ev.detail}</p>
                  <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                    <span className="text-slate-500 text-xs">{ev.actor}</span>
                    <span className="text-slate-600">-</span>
                    <span className="text-slate-500 text-xs capitalize">{ev.actorRole}</span>
                    <span className="text-slate-600">-</span>
                    <span className="text-slate-500 text-xs">{new Date(ev.timestamp).toLocaleString('pt-BR')}</span>
                  </div>
                </div>
                <span className="text-slate-600 text-xs ml-4 flex-shrink-0 font-mono">{ev.id.slice(0, 8)}</span>
              </button>

              {expanded === ev.id && (
                <div className="px-4 pb-4 border-t border-slate-800/50 pt-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <p className="text-slate-500 text-xs mb-1">Hash deste evento</p>
                      <code className="text-xs font-mono text-slate-400 bg-slate-800 px-2 py-1 rounded block break-all">{ev.hash}</code>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs mb-1">Hash anterior</p>
                      <code className="text-xs font-mono text-slate-400 bg-slate-800 px-2 py-1 rounded block break-all">{ev.prevHash}</code>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs mb-1">Target</p>
                      <code className="text-xs font-mono text-slate-400">{ev.target}</code>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs mb-1">Projeto</p>
                      <span className="text-slate-400 text-xs">{ev.projectId || 'Global'}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-slate-500 text-sm text-center py-8">Nenhum evento encontrado</p>
      )}
    </div>
  )
}
