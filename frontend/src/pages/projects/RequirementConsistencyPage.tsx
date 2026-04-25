import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { ScanSearch, CheckCircle2, Clock, AlertTriangle, Loader2, ChevronDown, ChevronRight, FileCheck } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { formatDateTimeBR } from '@/lib/datetime'

interface ConsistencyItem {
  document_id: string
  original_filename: string
  file_type: string
  is_canonical_decision: boolean
  category: string | null
  status: 'clean' | 'has_issues' | 'processing' | 'error' | 'pending'
  gaps_count: number
  show_stoppers_count: number
  poor_definitions_count: number
  modules_count: number
  total_issues: number
  uploaded_at: string | null
  checked_at: string | null
}

interface ConsistencyResponse {
  project_id: string
  total_documents: number
  counts: Record<string, number>
  all_clean: boolean
  items: ConsistencyItem[]
}

interface IssueDetail {
  document_id: string
  gaps: any[]
  show_stoppers: any[]
  poor_definitions: any[]
  checked_at: string | null
}

const STATUS_ICON: Record<string, { icon: typeof CheckCircle2; className: string; label: string }> = {
  clean: { icon: CheckCircle2, className: 'text-emerald-400', label: 'OK' },
  has_issues: { icon: Clock, className: 'text-amber-400', label: 'Pendente' },
  processing: { icon: Loader2, className: 'text-blue-400 animate-spin', label: 'Analisando' },
  error: { icon: AlertTriangle, className: 'text-red-400', label: 'Erro' },
  pending: { icon: Clock, className: 'text-slate-500', label: 'Aguardando' },
}

export function RequirementConsistencyPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [data, setData] = useState<ConsistencyResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [details, setDetails] = useState<Record<string, IssueDetail>>({})
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const res = await apiClient.get(`/projects/${projectId}/consistency`)
      setData(res.data)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const toggleExpand = async (docId: string) => {
    const next = new Set(expanded)
    if (next.has(docId)) {
      next.delete(docId)
      setExpanded(next)
      return
    }
    next.add(docId)
    setExpanded(next)
    if (!details[docId] && projectId) {
      setLoadingDetail(docId)
      try {
        const res = await apiClient.get(`/projects/${projectId}/consistency/${docId}/issues`)
        setDetails(prev => ({ ...prev, [docId]: res.data }))
      } finally {
        setLoadingDetail(null)
      }
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  if (!data || data.total_documents === 0) {
    return (
      <div className="p-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <FileCheck className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-300">Nenhum documento ingerido ainda.</p>
          <p className="text-slate-500 text-xs mt-1">A validação aparece automaticamente após o Arguidor analisar os requisitos.</p>
        </div>
      </div>
    )
  }

  const cleanCount = data.counts.clean || 0
  const issuesCount = data.counts.has_issues || 0
  const processingCount = (data.counts.processing || 0) + (data.counts.pending || 0)

  return (
    <div className="p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          <ScanSearch className="w-5 h-5 text-violet-400" />
          Validação de Requisitos
        </h2>
        <p className="text-slate-500 text-sm mt-0.5">
          Status agregado por documento. ✅ aderente, ⏳ tem requisito faltante ou contradição.
          Atualiza automaticamente após cada análise do Arguidor.
        </p>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="bg-emerald-900/20 border border-emerald-700/30 rounded-lg px-3 py-2 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span className="text-emerald-300 text-sm font-medium">{cleanCount}</span>
          <span className="text-slate-400 text-xs">aderentes</span>
        </div>
        <div className="bg-amber-900/20 border border-amber-700/30 rounded-lg px-3 py-2 flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-400" />
          <span className="text-amber-300 text-sm font-medium">{issuesCount}</span>
          <span className="text-slate-400 text-xs">pendentes</span>
        </div>
        {processingCount > 0 && (
          <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg px-3 py-2 flex items-center gap-2">
            <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            <span className="text-blue-300 text-sm font-medium">{processingCount}</span>
            <span className="text-slate-400 text-xs">processando</span>
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        {data.items.map(item => {
          const cfg = STATUS_ICON[item.status] || STATUS_ICON.pending
          const Icon = cfg.icon
          const isExpanded = expanded.has(item.document_id)
          const detail = details[item.document_id]
          const canExpand = item.status === 'has_issues'

          return (
            <div key={item.document_id} className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => canExpand && toggleExpand(item.document_id)}
                disabled={!canExpand}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left ${
                  canExpand ? 'hover:bg-slate-800/50 cursor-pointer' : 'cursor-default'
                }`}
                title={canExpand ? 'Clique pra ver detalhes' : ''}
              >
                <Icon className={`w-5 h-5 flex-shrink-0 ${cfg.className}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-200 text-sm font-medium truncate">
                      {item.original_filename}
                    </span>
                    {item.is_canonical_decision && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/30 text-violet-300 uppercase tracking-wide">
                        canônico
                      </span>
                    )}
                  </div>
                  {item.status === 'has_issues' && (
                    <div className="text-xs text-slate-500 mt-0.5 flex gap-3">
                      {item.gaps_count > 0 && <span>{item.gaps_count} faltante{item.gaps_count > 1 ? 's' : ''}</span>}
                      {item.show_stoppers_count > 0 && <span className="text-red-400">{item.show_stoppers_count} contradição{item.show_stoppers_count > 1 ? 'ões' : ''}</span>}
                      {item.poor_definitions_count > 0 && <span>{item.poor_definitions_count} ambiguidade{item.poor_definitions_count > 1 ? 's' : ''}</span>}
                    </div>
                  )}
                  {item.status === 'clean' && item.modules_count > 0 && (
                    <div className="text-xs text-emerald-500/80 mt-0.5">
                      {item.modules_count} módulo{item.modules_count > 1 ? 's' : ''} extraído{item.modules_count > 1 ? 's' : ''}
                    </div>
                  )}
                </div>
                <span className="text-xs text-slate-500 shrink-0">
                  {item.checked_at ? formatDateTimeBR(item.checked_at) : '-'}
                </span>
                {canExpand && (
                  isExpanded ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />
                )}
              </button>

              {isExpanded && (
                <div className="border-t border-slate-800 px-4 py-3 bg-slate-950/50 text-sm space-y-3">
                  {loadingDetail === item.document_id && !detail ? (
                    <div className="flex items-center gap-2 text-slate-400 text-xs">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> Carregando detalhes...
                    </div>
                  ) : detail ? (
                    <>
                      {detail.show_stoppers && detail.show_stoppers.length > 0 && (
                        <Section title="Contradições" color="text-red-400" items={detail.show_stoppers} />
                      )}
                      {detail.gaps && detail.gaps.length > 0 && (
                        <Section title="Requisitos faltantes" color="text-amber-400" items={detail.gaps} />
                      )}
                      {detail.poor_definitions && detail.poor_definitions.length > 0 && (
                        <Section title="Ambiguidades" color="text-slate-400" items={detail.poor_definitions} />
                      )}
                    </>
                  ) : (
                    <div className="text-slate-500 text-xs">Sem detalhes disponíveis.</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Section({ title, color, items }: { title: string; color: string; items: any[] }) {
  return (
    <div>
      <div className={`text-xs font-medium ${color} mb-1.5`}>{title} ({items.length})</div>
      <ul className="space-y-1 text-xs text-slate-300">
        {items.slice(0, 10).map((it, idx) => {
          const text = typeof it === 'string' ? it : (it.text || it.description || it.title || it.name || JSON.stringify(it))
          const id = typeof it === 'object' ? (it.id || it.gap_id) : null
          return (
            <li key={idx} className="flex gap-2 items-start">
              <span className="text-slate-600 text-[10px] mt-0.5 font-mono">{id || `#${idx + 1}`}</span>
              <span className="flex-1">{String(text).slice(0, 240)}</span>
            </li>
          )
        })}
        {items.length > 10 && (
          <li className="text-slate-500 italic">+{items.length - 10} item{items.length - 10 > 1 ? 's' : ''}...</li>
        )}
      </ul>
    </div>
  )
}
