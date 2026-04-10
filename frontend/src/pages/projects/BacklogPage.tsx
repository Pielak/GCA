import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { ClipboardList, RefreshCw, Loader2, Filter, AlertTriangle, CheckCircle, Clock, Zap, Code2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '@/lib/api'

interface BacklogItem {
  id: string
  category: string
  title: string
  description: string
  priority: string
  status: string
  source: string
  source_version: number | null
  created_at: string | null
}

const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  modules: { label: 'Módulos', color: 'violet', icon: '📦' },
  tests: { label: 'Testes', color: 'emerald', icon: '🧪' },
  compliance: { label: 'Compliance', color: 'amber', icon: '🔒' },
  security: { label: 'Segurança', color: 'red', icon: '🛡️' },
  agile: { label: 'Ágil', color: 'blue', icon: '⚡' },
  other: { label: 'Outros', color: 'slate', icon: '📋' },
}

const PRIORITY_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  critical: { label: 'Crítica', bg: 'bg-red-900/40', text: 'text-red-400' },
  high: { label: 'Alta', bg: 'bg-orange-900/40', text: 'text-orange-400' },
  medium: { label: 'Média', bg: 'bg-amber-900/40', text: 'text-amber-400' },
  low: { label: 'Baixa', bg: 'bg-slate-800', text: 'text-slate-400' },
}

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  pending: { label: 'Pendente', bg: 'bg-slate-800', text: 'text-slate-400' },
  in_progress: { label: 'Em andamento', bg: 'bg-blue-900/40', text: 'text-blue-400' },
  done: { label: 'Concluído', bg: 'bg-emerald-900/40', text: 'text-emerald-400' },
  blocked: { label: 'Bloqueado', bg: 'bg-red-900/40', text: 'text-red-400' },
}

export function BacklogPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [items, setItems] = useState<BacklogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')

  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const loadData = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/backlog`)
      setItems(res.data?.items || [])
    } catch { setItems([]) }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadData() }, [loadData])

  const handleRegenerate = async () => {
    setRefreshing(true)
    try {
      const res = await apiClient.post(`/projects/${projectId}/backlog/regenerate`)
      showToast(`Backlog regenerado: ${res.data.regenerated} itens`, 'success')
      await loadData()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao regenerar', 'error')
    }
    setRefreshing(false)
  }

  const filtered = items.filter(i => {
    if (categoryFilter !== 'all' && i.category !== categoryFilter) return false
    if (priorityFilter !== 'all' && i.priority !== priorityFilter) return false
    return true
  })

  // Stats por categoria
  const catCounts: Record<string, number> = {}
  items.forEach(i => { catCounts[i.category] = (catCounts[i.category] || 0) + 1 })

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Backlog Vivo</h2>
          <p className="text-slate-500 text-sm mt-0.5">
            Derivado automaticamente do OCG. Regenera quando o OCG muda.
            {items.length > 0 && ` ${items.length} itens no total.`}
          </p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm rounded-lg hover:bg-violet-600/30 disabled:opacity-40 transition-colors"
        >
          {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Regenerar do OCG
        </button>
      </div>

      {/* Stats por categoria */}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => {
            const count = catCounts[key] || 0
            if (count === 0) return null
            return (
              <button
                key={key}
                onClick={() => setCategoryFilter(categoryFilter === key ? 'all' : key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors border ${
                  categoryFilter === key
                    ? `bg-${cfg.color}-900/40 border-${cfg.color}-700/50 text-${cfg.color}-300`
                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <span>{cfg.icon}</span>
                {cfg.label}
                <span className="font-bold">{count}</span>
              </button>
            )
          })}
          {categoryFilter !== 'all' && (
            <button onClick={() => setCategoryFilter('all')} className="text-xs text-slate-500 hover:text-slate-300 px-2">
              Limpar filtro
            </button>
          )}
        </div>
      )}

      {/* Filtro de prioridade */}
      {items.length > 0 && (
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-500" />
          <select
            value={priorityFilter}
            onChange={e => setPriorityFilter(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-violet-600"
          >
            <option value="all">Todas as prioridades</option>
            <option value="critical">Crítica</option>
            <option value="high">Alta</option>
            <option value="medium">Média</option>
            <option value="low">Baixa</option>
          </select>
          <span className="text-slate-600 text-xs">{filtered.length} de {items.length} itens</span>
        </div>
      )}

      {/* Lista de itens */}
      {filtered.length > 0 ? (
        <div className="space-y-2">
          {filtered.map(item => {
            const cat = CATEGORY_CONFIG[item.category] || CATEGORY_CONFIG.other
            const pri = PRIORITY_CONFIG[item.priority] || PRIORITY_CONFIG.medium
            const st = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending
            return (
              <div key={item.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <div className="flex items-start gap-3">
                  <span className="text-lg flex-shrink-0 mt-0.5">{cat.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-slate-200 text-sm font-medium">{item.title}</p>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${pri.bg} ${pri.text}`}>{pri.label}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${st.bg} ${st.text}`}>{st.label}</span>
                    </div>
                    {item.description && (
                      <p className="text-slate-500 text-xs mt-1">{item.description}</p>
                    )}
                    <div className="flex items-center justify-between mt-2">
                      <div className="flex items-center gap-3 text-slate-600 text-xs">
                        <span>{cat.label}</span>
                        {item.source_version && <span>OCG v{item.source_version}</span>}
                        <span>Fonte: {item.source}</span>
                      </div>
                      {item.category === 'modules' && item.status === 'pending' && (
                        <button
                          onClick={() => navigate(`/projects/${projectId}/codegen`)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-violet-600/20 border border-violet-600/30 text-violet-400 rounded-lg hover:bg-violet-600/30 transition-colors"
                        >
                          <Code2 className="w-3 h-3" />
                          Gerar Código
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <ClipboardList className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-slate-300 font-semibold mb-2">Backlog vazio</h3>
          <p className="text-slate-500 text-sm max-w-md mx-auto">
            Clique em "Regenerar do OCG" para criar itens de backlog a partir do contexto do projeto.
          </p>
        </div>
      ) : (
        <p className="text-slate-500 text-sm text-center py-8">Nenhum item corresponde aos filtros selecionados.</p>
      )}
    </div>
  )
}
