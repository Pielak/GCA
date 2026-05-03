import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { ClipboardList, RefreshCw, Loader2, Filter, AlertTriangle, CheckCircle, Clock, Zap, Code2, Shield, X, TestTube2, GitBranch, GripVertical } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { DragDropContext, Droppable, Draggable, DropResult } from '@hello-pangea/dnd'
import { apiClient } from '@/lib/api'
import { RoleAssumptionPrompt } from '@/components/projects/RoleAssumptionPrompt'
import { BacklogIssuePanel } from '@/components/projects/BacklogIssuePanel'
import { OCGChangesTimelineCard } from '@/components/project/OCGChangesTimelineCard'
import { getErrorMessage, type ApiError } from '@/lib/errors'

interface BacklogItem {
  id: string
  category: string
  module_type: string | null
  title: string
  description: string
  priority: string
  status: string
  source: string
  source_version: number | null
  required_artifacts: string[]
  present_artifacts: string[]
  compliance_iso27001: string[]
  warnings: string[]
  generated_code_path: string | null
  commit_sha: string | null
  issues_total: number
  issues_resolved: number
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
  ready: { label: 'Pronto', bg: 'bg-emerald-900/40', text: 'text-emerald-400' },
  generating: { label: 'Gerando', bg: 'bg-violet-900/40', text: 'text-violet-400' },
  tests_running: { label: 'Testes', bg: 'bg-blue-900/40', text: 'text-blue-400' },
  security_review: { label: 'Segurança', bg: 'bg-orange-900/40', text: 'text-orange-400' },
  compliance_review: { label: 'Compliance', bg: 'bg-amber-900/40', text: 'text-amber-400' },
  awaiting_qa: { label: 'Aguardando QA', bg: 'bg-cyan-900/40', text: 'text-cyan-400' },
  ready_to_merge: { label: 'Pronto p/ Merge', bg: 'bg-emerald-900/40', text: 'text-emerald-300' },
  committed: { label: 'Consolidado', bg: 'bg-emerald-800/40', text: 'text-emerald-300' },
  published: { label: 'Publicado', bg: 'bg-emerald-700/40', text: 'text-emerald-200' },
  blocked: { label: 'Bloqueado', bg: 'bg-red-900/40', text: 'text-red-400' },
  in_progress: { label: 'Em andamento', bg: 'bg-blue-900/40', text: 'text-blue-400' },
  done: { label: 'Concluído', bg: 'bg-emerald-900/40', text: 'text-emerald-400' },
}

export function BacklogPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [items, setItems] = useState<BacklogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [reordering, setReordering] = useState(false)

  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const handleDragEnd = async (result: DropResult) => {
    const { source, destination, draggableId } = result

    if (!destination) return
    if (source.index === destination.index) return

    setReordering(true)
    try {
      const newItems = Array.from(items)
      const [movedItem] = newItems.splice(source.index, 1)
      newItems.splice(destination.index, 0, movedItem)

      const reorderPayload = newItems.map((item, index) => ({
        id: item.id,
        display_order: index,
      }))

      await apiClient.patch(`/projects/${projectId}/backlog/reorder`, {
        reorder: reorderPayload,
      })

      setItems(newItems)
      showToast('Ordem atualizada com sucesso', 'success')
    } catch (err) {
      showToast(getErrorMessage(err) || 'Erro ao reordenar', 'error')
      await loadData()
    } finally {
      setReordering(false)
    }
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
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao regenerar', 'error')
    }
    setRefreshing(false)
  }

  const [generating, setGenerating] = useState(false)
  const [rolePrompt, setRolePrompt] = useState<{ action: string; retry: () => void } | null>(null)

  const withRoleCheck = (action: string, fn: () => Promise<void>) => {
    return async () => {
      try {
        await fn()
      } catch (err: unknown) {
        if ((err as ApiError)?.status === 403) {
          setRolePrompt({ action, retry: () => { setRolePrompt(null); fn().then(() => loadData()) } })
        } else {
          showToast(getErrorMessage(err), 'error')
        }
      }
    }
  }
  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const res = await apiClient.post(`/projects/${projectId}/backlog/generate`)
      showToast(`Backlog inteligente: ${res.data.ocg_items} OCG + ${res.data.arguider_items} Arguider. ${res.data.ready} prontos, ${res.data.blocked} bloqueados.`, 'success')
      await loadData()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao gerar', 'error')
    }
    setGenerating(false)
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
      {/* Role Assumption Prompt */}
      {rolePrompt && (
        <RoleAssumptionPrompt
          action={rolePrompt.action}
          onRoleAssumed={rolePrompt.retry}
          onCancel={() => setRolePrompt(null)}
        />
      )}

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
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 text-sm rounded-lg hover:bg-emerald-600/30 disabled:opacity-40 transition-colors"
          >
            {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Gerar Backlog Inteligente
          </button>
          <button
            onClick={handleRegenerate}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm rounded-lg hover:bg-violet-600/30 disabled:opacity-40 transition-colors"
          >
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Regenerar do OCG
          </button>
        </div>
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

      {/* Lista de itens com drag-and-drop */}
      {filtered.length > 0 ? (
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="backlog-items">
            {(provided, snapshot) => (
              <div
                {...provided.droppableProps}
                ref={provided.innerRef}
                className={`space-y-2 ${snapshot.isDraggingOver ? 'bg-slate-800/50 rounded-lg p-2' : ''}`}
              >
                {filtered.map((item, index) => {
                  const cat = CATEGORY_CONFIG[item.category] || CATEGORY_CONFIG.other
                  const pri = PRIORITY_CONFIG[item.priority] || PRIORITY_CONFIG.medium
                  const st = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending
                  return (
                    <Draggable key={item.id} draggableId={item.id} index={index}>
                      {(provided, snapshot) => (
                        <div
                          ref={provided.innerRef}
                          {...provided.draggableProps}
                          className={`bg-slate-900 border border-slate-800 rounded-xl p-4 transition-all ${
                            snapshot.isDragging ? 'bg-slate-800 border-violet-600 shadow-lg shadow-violet-600/20' : ''
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div {...provided.dragHandleProps} className="flex-shrink-0 mt-0.5 cursor-grab active:cursor-grabbing">
                              <GripVertical className="h-5 w-5 text-slate-600 hover:text-slate-400" />
                            </div>
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
                    {/* Warnings */}
                    {item.warnings && item.warnings.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {item.warnings.map((w, i) => (
                          <div key={i} className="flex items-center gap-1.5 text-xs text-amber-400">
                            <AlertTriangle className="w-3 h-3 shrink-0" />
                            <span>{w}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {/* ISO 27001 */}
                    {item.compliance_iso27001 && item.compliance_iso27001.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {item.compliance_iso27001.map((c, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-500 border border-amber-800/30">{c.split(' - ')[0]}</span>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center justify-between mt-2">
                      <div className="flex items-center gap-3 text-slate-600 text-xs">
                        <span>{cat.label}</span>
                        {item.module_type && <span className="text-violet-400">{item.module_type}</span>}
                        {item.source_version && <span>OCG v{item.source_version}</span>}
                        <span>Fonte: {item.source}</span>
                        {item.commit_sha && <span className="text-emerald-400">SHA: {item.commit_sha.slice(0, 7)}</span>}
                      </div>
                      {/* Acoes contextuais por status */}
                      {item.category === 'modules' && (item.status === 'pending' || item.status === 'ready') && (
                        <button
                          onClick={() => navigate(`/projects/${projectId}/codegen?backlog_item=${item.id}`)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-violet-600/20 border border-violet-600/30 text-violet-400 rounded-lg hover:bg-violet-600/30 transition-colors"
                        >
                          <Code2 className="w-3 h-3" />
                          Gerar Código
                        </button>
                      )}
                      {item.status === 'generating' && (
                        <button
                          onClick={withRoleCheck('code:write', async () => { await apiClient.post(`/projects/${projectId}/backlog/${item.id}/generate-tests`); await loadData() })}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-600/20 border border-blue-600/30 text-blue-400 rounded-lg hover:bg-blue-600/30 transition-colors"
                        >
                          <TestTube2 className="w-3 h-3" />
                          Gerar Testes
                        </button>
                      )}
                      {item.status === 'tests_running' && (
                        <span className="flex items-center gap-1 px-2 py-1 text-xs text-blue-400">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Testes executando...
                        </span>
                      )}
                      {item.status === 'security_review' && (
                        <button
                          onClick={withRoleCheck('security:review', async () => { await apiClient.post(`/projects/${projectId}/backlog/${item.id}/security-scan`); await loadData() })}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-orange-600/20 border border-orange-600/30 text-orange-400 rounded-lg hover:bg-orange-600/30 transition-colors"
                        >
                          <Shield className="w-3 h-3" />
                          Security Scan
                        </button>
                      )}
                      {item.status === 'compliance_review' && (
                        <button
                          onClick={withRoleCheck('compliance:validate', async () => { await apiClient.post(`/projects/${projectId}/backlog/${item.id}/compliance-check`); await loadData() })}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-amber-600/20 border border-amber-600/30 text-amber-400 rounded-lg hover:bg-amber-600/30 transition-colors"
                        >
                          <Shield className="w-3 h-3" />
                          Compliance Check
                        </button>
                      )}
                      {item.status === 'awaiting_qa' && (
                        <div className="flex gap-1">
                          <button
                            onClick={withRoleCheck('qa:approve', async () => { await apiClient.post(`/projects/${projectId}/backlog/${item.id}/qa-approve`, { approved: true, notes: 'Aprovado via backlog' }); await loadData() })}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 rounded-lg hover:bg-emerald-600/30 transition-colors"
                          >
                            <CheckCircle className="w-3 h-3" />
                            Aprovar
                          </button>
                          <button
                            onClick={withRoleCheck('qa:approve', async () => { await apiClient.post(`/projects/${projectId}/backlog/${item.id}/qa-approve`, { approved: false, rejection_reason: 'Rejeitado via backlog' }); await loadData() })}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/20 border border-red-600/30 text-red-400 rounded-lg hover:bg-red-600/30 transition-colors"
                          >
                            <X className="w-3 h-3" />
                            Rejeitar
                          </button>
                        </div>
                      )}
                      {item.status === 'ready_to_merge' && (
                        <button
                          onClick={() => navigate(`/projects/${projectId}/codegen?backlog_item=${item.id}`)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 rounded-lg hover:bg-emerald-600/30 transition-colors"
                        >
                          <GitBranch className="w-3 h-3" />
                          Commit Final
                        </button>
                      )}
                      {['committed', 'published', 'ready_to_merge', 'awaiting_qa'].includes(item.status) && (
                        <button
                          onClick={async () => {
                            const res = await apiClient.get(`/projects/${projectId}/audit/pipeline/${item.id}/export`)
                            const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = `audit-${item.title.replace(/\s+/g, '-')}.json`
                            a.click()
                          }}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-700/50 border border-slate-600/30 text-slate-400 rounded-lg hover:bg-slate-600/30 transition-colors"
                        >
                          Exportar Audit
                        </button>
                      )}
                    </div>

                    {/* Issue Panel — sub-items de security/compliance */}
                    {item.issues_total > 0 && projectId && (
                      <BacklogIssuePanel
                        projectId={projectId}
                        itemId={item.id}
                        issuesTotal={item.issues_total}
                        issuesResolved={item.issues_resolved}
                      />
                    )}
                        </div>
                        </div>
                        </div>
                      )}
                    </Draggable>
                  )
                })}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>
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

      {/* MVP 27 Fase 2 — Timeline de eventos do OCG que afetam o Backlog */}
      {projectId && <OCGChangesTimelineCard projectId={projectId} scope="backlog" />}
    </div>
  )
}
