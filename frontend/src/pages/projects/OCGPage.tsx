import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import {
  Settings, Brain, GitBranch, Plug, Layers, Shield, FileText, TestTube2,
  Users, Activity, History, Check, ChevronDown, ChevronRight, Edit2, Info,
  Loader2, AlertTriangle, RefreshCw, ExternalLink
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { pillarMeta, pillarKey, PILLAR_ORDER } from '@/data/pillarMeta'
import { getErrorMessage, getErrorStatus, type ApiError } from '@/lib/errors'
import RnfContractsEditor from '@/components/projects/RnfContractsEditor'
import DesignTokensEditor from '@/components/projects/DesignTokensEditor'
import { FigmaImportPanel } from '@/components/projects/FigmaImportPanel'
import { PreviewSessionsPanel } from '@/components/projects/PreviewSessionsPanel'
import { formatDateTimeBR } from '@/lib/datetime'

/**
 * Formata erros de operações OCG-mutantes (regenerate/reconsolidate).
 * Trata especificamente HTTP 409 com detail estruturado do
 * `project_operation_lock` (backend DT-080 commit 7b45209), mostrando
 * mensagem amigável em vez de erro genérico.
 */
function formatOCGOperationError(err: unknown, action: string): string {
  const status = getErrorStatus(err)
  if (status === 409) {
    // Backend envia detail={error, blocked_by, started_at, elapsed_seconds, message}
    const e = err as { response?: { data?: { detail?: unknown } } }
    const detail = e?.response?.data?.detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String((detail as { message: string }).message)
    }
    return `Não é possível ${action} agora — outra operação OCG já está em andamento neste projeto. Aguarde terminar e tente de novo.`
  }
  return `Falha ao ${action.toLowerCase()}: ${getErrorMessage(err)}`
}

interface OCGData {
  ocg_id: string
  questionnaire_id: string
  project_id: string
  COMPOSITE_SCORE: Record<string, any>
  PILLAR_SCORES: Record<string, any>
  STACK_RECOMMENDATIONS: Record<string, any>
  COMPLIANCE_PROFILE: Record<string, any>
  TESTING_STRATEGY: Record<string, any>
  ARCHITECTURE: Record<string, any>
  DELIVERABLES: Record<string, any>
  RISKS: Record<string, any>
  [key: string]: any
}

interface ProjectData {
  id: string
  name: string
  slug: string
  description: string
  status: string
  gp_email: string
  gp_name: string
  created_at: string
}

const DIMENSIONS = [
  { key: 'composite', label: 'Score Composto', icon: Activity, color: 'indigo' },
  { key: 'pillars', label: 'Scores por Pilar', icon: Layers, color: 'violet' },
  { key: 'stack', label: 'Stack Recomendada', icon: Settings, color: 'blue' },
  { key: 'architecture', label: 'Visão Arquitetural', icon: GitBranch, color: 'cyan' },
  { key: 'compliance', label: 'Conformidade e Regulatório', icon: Shield, color: 'amber' },
  { key: 'rnf', label: 'Contratos RNF (editável)', icon: Edit2, color: 'violet' },
  { key: 'design_tokens', label: 'Design Tokens (editável)', icon: Edit2, color: 'violet' },
  { key: 'figma', label: 'Figma (import)', icon: ExternalLink, color: 'violet' },
  { key: 'preview', label: 'Preview Local (G4)', icon: Activity, color: 'emerald' },
  { key: 'testing', label: 'Estratégia de Testes', icon: TestTube2, color: 'emerald' },
  { key: 'deliverables', label: 'Entregáveis', icon: FileText, color: 'orange' },
  { key: 'risks', label: 'Análise de Riscos', icon: AlertTriangle, color: 'red' },
  { key: 'approval', label: 'Status de Aprovação', icon: Check, color: 'indigo' },
  { key: 'history', label: 'Histórico de Versões', icon: History, color: 'violet' },
]

const colorClass: Record<string, string> = {
  indigo: 'bg-indigo-900/20 border-indigo-800/30 text-indigo-400',
  violet: 'bg-violet-900/20 border-violet-800/30 text-violet-400',
  blue: 'bg-blue-900/20 border-blue-800/30 text-blue-400',
  cyan: 'bg-cyan-900/20 border-cyan-800/30 text-cyan-400',
  amber: 'bg-amber-900/20 border-amber-800/30 text-amber-400',
  emerald: 'bg-emerald-900/20 border-emerald-800/30 text-emerald-400',
  orange: 'bg-orange-900/20 border-orange-800/30 text-orange-400',
  red: 'bg-red-900/20 border-red-800/30 text-red-400',
}

function OCGField({ label, value, mono = false, full = false }: { label: string; value: React.ReactNode; mono?: boolean; full?: boolean }) {
  return (
    <div className={`${full ? 'col-span-2' : ''}`}>
      <p className="text-slate-500 text-xs mb-1">{label}</p>
      {typeof value === 'string' || typeof value === 'number' ? (
        <p className={`text-sm ${mono ? 'font-mono text-indigo-300' : 'text-slate-200'}`}>{String(value)}</p>
      ) : value}
    </div>
  )
}

function ScoreBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min(100, (score / max) * 100)
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-slate-700 rounded-full">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-mono text-slate-300 w-12 text-right">{score}/{max}</span>
    </div>
  )
}

function renderListItem(item: any): React.ReactNode {
  if (typeof item === 'string') return <span className="text-slate-300 text-sm">{item}</span>
  if (typeof item !== 'object' || !item) return <span className="text-slate-400 text-sm">{String(item)}</span>

  // Renderizar campos-chave de objetos estruturados (risk, finding, compliance, etc.)
  const mainField = item.risk || item.finding || item.item || item.title || item.name || item.description || item.text
  const details: string[] = []
  if (item.mitigation) details.push(`Mitigação: ${item.mitigation}`)
  if (item.owner) details.push(`Responsável: ${item.owner}`)
  if (item.severity) details.push(`Severidade: ${item.severity}`)
  if (item.status) details.push(`Status: ${item.status}`)
  if (item.priority) details.push(`Prioridade: ${item.priority}`)
  if (item.rationale) details.push(`Justificativa: ${item.rationale}`)
  if (item.pillar) details.push(`Pilar: ${item.pillar}`)

  if (mainField) {
    return (
      <div>
        <span className="text-slate-200 text-sm">{mainField}</span>
        {details.length > 0 && (
          <div className="mt-1 space-y-0.5">
            {details.map((d, i) => (
              <p key={i} className="text-slate-500 text-xs ml-2">{d}</p>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Fallback: renderizar todos os campos
  return (
    <div className="space-y-0.5">
      {Object.entries(item).map(([k, v]) => (
        <p key={k} className="text-sm">
          <span className="text-slate-500">{k.replace(/_/g, ' ')}: </span>
          <span className="text-slate-300">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
        </p>
      ))}
    </div>
  )
}

function renderObject(obj: Record<string, any>, depth = 0): React.ReactNode {
  if (!obj || typeof obj !== 'object') return <span className="text-slate-400 text-sm">{String(obj)}</span>

  if (Array.isArray(obj)) {
    if (obj.length === 0) return <p className="text-slate-500 text-sm italic">Aguardando Documentação</p>
    return (
      <ul className="space-y-2 ml-2">
        {obj.map((item, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-slate-600 mt-1">•</span>
            {renderListItem(item)}
          </li>
        ))}
      </ul>
    )
  }

  const entries = Object.entries(obj).filter(([, v]) => v !== null && v !== undefined && v !== '')
  if (entries.length === 0) return <p className="text-slate-500 text-sm italic">Aguardando Documentação</p>

  return (
    <div className={`grid grid-cols-2 gap-4 ${depth > 0 ? 'ml-2' : ''}`}>
      {entries.map(([key, val]) => (
        <OCGField
          key={key}
          label={key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
          value={typeof val === 'object' && val !== null ? (
            <div className="mt-1">{renderObject(val, depth + 1)}</div>
          ) : String(val ?? '—')}
          full={typeof val === 'object' && val !== null}
        />
      ))}
    </div>
  )
}

export function OCGPage() {
  const { id } = useParams<{ id: string }>()
  const [ocg, setOcg] = useState<OCGData | null>(null)
  const [project, setProject] = useState<ProjectData | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [currentVersion, setCurrentVersion] = useState<number>(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // DT-039: estados pras 2 ações manuais (reconsolidate + regenerate)
  const [reconsolidating, setReconsolidating] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [expanded, setExpanded] = useState<string | null>('composite')

  useEffect(() => {
    loadData()
  }, [id])

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      // Buscar dados do projeto
      const projRes = await apiClient.get(`/dashboard/project/${id}/metrics`)
      setProject(projRes.data)
    } catch {
      // Projeto pode não ter métricas ainda
    }

    try {
      // Buscar OCG do projeto
      const ocgRes = await apiClient.get(`/projects/${id}/ocg`)
      const raw = ocgRes.data.ocg || ocgRes.data
      if (raw && raw.ocg_data) {
        // Merge ocg_data fields into top level for frontend compatibility
        const merged = { ...raw, ...raw.ocg_data }
        setOcg(merged)
      } else {
        setOcg(raw)
      }
    } catch (err: unknown) {
      if ((err as ApiError)?.status === 404 || getErrorStatus(err) === 404) {
        setOcg(null) // OCG não gerado ainda
      } else {
        setError('Erro ao carregar OCG')
      }
    // Buscar histórico de versões
    try {
      const histRes = await apiClient.get(`/projects/${id}/ocg/history`)
      setHistory(histRes.data?.history || [])
      setCurrentVersion(histRes.data?.current_version || 0)
    } catch { setHistory([]) }

    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
      </div>
    )
  }

  // OCG ainda não foi gerado
  if (!ocg) {
    return (
      <div className="p-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">OCG — Objeto de Contexto Global</h2>
            <p className="text-slate-500 text-sm mt-0.5">Nenhum módulo opera sobre um projeto sem antes ler seu OCG.</p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <Brain className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-slate-300 mb-2">OCG ainda não gerado</h3>
          <p className="text-slate-500 text-sm mb-4 max-w-md mx-auto">
            O Objeto de Contexto Global será gerado automaticamente após a aprovação do questionário
            técnico e a análise pelos 8 agentes de IA (Analyzer + 7 Pillar Specialists + Consolidator).
          </p>
          {error && (
            <p className="text-red-400 text-sm mb-4">{error}</p>
          )}
          <button
            onClick={loadData}
            className="flex items-center gap-2 mx-auto px-4 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 rounded-lg text-sm hover:bg-violet-600/30 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Verificar novamente
          </button>
        </div>
      </div>
    )
  }

  const compositeScore = ocg.COMPOSITE_SCORE || {}
  const overallScore = ocg.overall_score ?? compositeScore.overall ?? compositeScore.value ?? compositeScore.score ?? 0
  const overallStatus = ocg.status ?? compositeScore.status ?? (ocg.APPROVAL_STATUS || {}).status ?? 'UNKNOWN'

  const renderDimensionContent = (key: string) => {
    switch (key) {
      case 'composite':
        return (
          <div className="space-y-4">
            <div className="flex items-center gap-4 mb-4">
              <div className={`text-3xl font-bold ${overallScore >= 80 ? 'text-emerald-400' : overallScore >= 60 ? 'text-amber-400' : 'text-red-400'}`}>
                {overallScore}
              </div>
              <div>
                <p className="text-slate-200 text-sm font-medium">Score Geral</p>
                <p className={`text-xs ${overallStatus === 'APPROVED' ? 'text-emerald-400' : 'text-amber-400'}`}>{overallStatus}</p>
              </div>
            </div>
            {renderObject(compositeScore)}
          </div>
        )
      case 'pillars':
        if (!ocg.PILLAR_SCORES) return <p className="text-slate-500 text-sm">Dados de pilares não disponíveis.</p>
        {
          // Reorganiza os pillars por P1..P7 independente da ordem que o
          // OCG entregue (agents podem embaralhar). Mantém pilares
          // desconhecidos ao final para não sumir com dados.
          const raw = Object.entries(ocg.PILLAR_SCORES) as [string, any][]
          const byKey = new Map<string, { raw_key: string, data: any }>()
          for (const [k, d] of raw) {
            const pk = pillarKey(k)
            if (pk && !byKey.has(pk)) byKey.set(pk, { raw_key: k, data: d })
          }
          const ordered = PILLAR_ORDER
            .filter(id => byKey.has(id))
            .map(id => ({ id, ...byKey.get(id)! }))
          const unknown = raw.filter(([k]) => !pillarKey(k))
          return (
            <div className="space-y-3">
              {ordered.map(({ id, data }) => {
                const meta = pillarMeta(id)!
                const score = typeof data === 'object' ? (data.score ?? 0) : (data ?? 0)
                const status = typeof data === 'object' ? data.status || '' : ''
                const belowBlocking = meta.blocking && score < 70
                return (
                  <div key={id} className="p-4 rounded-lg bg-slate-800/40 border border-slate-800">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-slate-200 text-sm font-semibold">
                            <span className="text-violet-400 font-bold mr-1">{id}</span>
                            {meta.name}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/60 text-slate-400 uppercase tracking-wide">
                            peso {meta.weight}%
                          </span>
                          {meta.blocking && (
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide ${
                                belowBlocking
                                  ? 'bg-red-500/20 text-red-300 border border-red-500/40'
                                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                              }`}
                              title="Este pilar bloqueia a aprovação do OCG se score < 70"
                            >
                              {belowBlocking ? 'BLOQUEANTE ' : ''}bloqueante{belowBlocking ? '!' : ' (<70)'}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 mt-1 leading-snug">{meta.description}</p>
                      </div>
                      {status && <span className="text-xs text-slate-500 flex-shrink-0">{status}</span>}
                    </div>
                    <ScoreBar score={score} />
                  </div>
                )
              })}
              {unknown.length > 0 && (
                <div className="mt-4 pt-3 border-t border-slate-800">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Outros pilares</p>
                  {unknown.map(([pillar, data]: [string, any]) => (
                    <div key={pillar} className="p-3 rounded-lg bg-slate-800/40 mb-2">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-slate-200 text-sm font-medium">{pillar}</span>
                        <span className="text-xs text-slate-500">{typeof data === 'object' ? data.status || '' : ''}</span>
                      </div>
                      <ScoreBar score={typeof data === 'object' ? (data.score ?? 0) : (data ?? 0)} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        }
      case 'stack':
        return (ocg.STACK_RECOMMENDATION || ocg.STACK_RECOMMENDATIONS) ? renderObject(ocg.STACK_RECOMMENDATION || ocg.STACK_RECOMMENDATIONS) : <p className="text-slate-500 text-sm">Aguardando Documentação</p>
      case 'architecture':
        return (ocg.ARCHITECTURE_OVERVIEW || ocg.ARCHITECTURE) ? renderObject(ocg.ARCHITECTURE_OVERVIEW || ocg.ARCHITECTURE) : <p className="text-slate-500 text-sm">Aguardando Documentação</p>
      case 'compliance':
        return (ocg.COMPLIANCE_CHECKLIST || ocg.COMPLIANCE_PROFILE) ? renderObject(ocg.COMPLIANCE_CHECKLIST || ocg.COMPLIANCE_PROFILE) : <p className="text-slate-500 text-sm">Aguardando Documentação</p>
      case 'rnf':
        return id ? <RnfContractsEditor projectId={id} /> : null
      case 'design_tokens':
        return id ? <DesignTokensEditor projectId={id} /> : null
      case 'figma':
        return id ? <FigmaImportPanel projectId={id} /> : null
      case 'preview':
        return id ? <PreviewSessionsPanel projectId={id} /> : null
      case 'testing':
        return (ocg.TESTING_REQUIREMENTS || ocg.TESTING_STRATEGY) ? renderObject(ocg.TESTING_REQUIREMENTS || ocg.TESTING_STRATEGY) : <p className="text-slate-500 text-sm">Aguardando Documentação</p>
      case 'deliverables':
        return ocg.DELIVERABLES ? renderObject(ocg.DELIVERABLES) : <p className="text-slate-500 text-sm">Aguardando Documentação</p>
      case 'risks':
        return (ocg.RISK_ANALYSIS || ocg.RISKS) ? renderObject(ocg.RISK_ANALYSIS || ocg.RISKS) : <p className="text-slate-500 text-sm italic">Aguardando Documentação</p>
      case 'approval':
        return (ocg.APPROVAL_STATUS) ? renderObject(ocg.APPROVAL_STATUS) : <p className="text-slate-500 text-sm italic">Aguardando Documentação</p>
      case 'history':
        return history.length > 0 ? (
          <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg overflow-hidden">
            <div className="grid grid-cols-[1fr_auto] gap-4 px-4 py-2 bg-slate-900/60 text-[10px] uppercase text-slate-500 font-medium tracking-wide">
              <span>Documento ingerido</span>
              <span className="text-right">Impacto no OCG</span>
            </div>
            {history.map((h: any) => {
              const delta: number | null = h.overall_delta
              const deltaColor = delta == null
                ? 'text-slate-500'
                : delta > 0
                  ? 'text-emerald-400'
                  : delta < 0
                    ? 'text-red-400'
                    : 'text-slate-400'
              const deltaSign = delta == null ? '' : delta > 0 ? '+' : ''
              return (
                <div
                  key={h.id}
                  className="grid grid-cols-[1fr_auto] gap-4 items-center px-4 py-3 hover:bg-slate-800/30 transition-colors"
                >
                  <div className="min-w-0">
                    {h.document_id ? (
                      <a
                        href={`/projects/${id}/ingestion?doc=${h.document_id}`}
                        className="text-sm text-slate-200 hover:text-violet-300 hover:underline break-all"
                      >
                        {h.document_filename}
                      </a>
                    ) : (
                      <span className="text-sm text-slate-500 italic">{h.document_filename}</span>
                    )}
                    <div className="text-[10px] text-slate-600 mt-0.5">
                      v{h.version_from} → v{h.version_to}
                      {h.created_at && <> · {formatDateTimeBR(h.created_at)}</>}
                    </div>
                  </div>
                  <div className={`text-sm font-semibold tabular-nums ${deltaColor}`}>
                    {delta == null ? (
                      <span className="text-slate-500">—</span>
                    ) : (
                      <>
                        {deltaSign}{delta.toFixed(2)}
                        <span className="text-[10px] text-slate-500 ml-1">
                          ({h.overall_before?.toFixed(1) ?? '?'} → {h.overall_after?.toFixed(1) ?? '?'})
                        </span>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-slate-500 text-sm italic">
            Nenhum documento ingerido alterou o OCG ainda. Faça upload de documentos pela aba <strong className="text-slate-300">Ingestão</strong>.
          </p>
        )
      default:
        return <p className="text-slate-500 text-sm italic">Aguardando Documentação</p>
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">OCG — Objeto de Contexto Global</h2>
          <p className="text-slate-500 text-sm mt-0.5">Nenhum módulo opera sobre um projeto sem antes ler seu OCG.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1.5 text-emerald-400 text-sm">
            <Check className="w-4 h-4" /> OCG Gerado
          </span>
          <button
            onClick={loadData}
            title="Busca a versão mais recente do OCG no servidor (não dispara regeneração)"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-sm hover:bg-slate-700 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Recarregar
          </button>
          <button
            onClick={async () => {
              if (!id || reconsolidating) return
              if (!confirm('Re-aplicar deltas de TODAS as análises Arguidor existentes? Não chama o Arguidor de novo (sem custo extra). Útil quando o prompt mudou ou o ocg_updater falhou.')) return
              setReconsolidating(true)
              try {
                // /reconsolidate chama LLM updater (DeepSeek) — pode levar 30-90s.
                // Override timeout default do apiClient (30s) para 3min.
                const res: any = await apiClient.post(
                  `/projects/${id}/ocg/reconsolidate`,
                  {},
                  { timeout: 180000 },
                )
                alert(res?.data?.message || 'Reconsolidação disparada')
                await loadData()
              } catch (err: unknown) {
                alert(formatOCGOperationError(err, 'Re-consolidar'))
              } finally {
                setReconsolidating(false)
              }
            }}
            disabled={reconsolidating || regenerating}
            title="Re-aplica deltas das análises Arguidor existentes (sem chamar Arguidor de novo). Aguarda terminar se já houver outra operação OCG rodando."
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 border border-indigo-600/30 text-indigo-300 text-sm hover:bg-indigo-600/30 disabled:opacity-40 transition-colors"
          >
            {reconsolidating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Re-consolidar OCG
          </button>
          <button
            onClick={async () => {
              if (!id || regenerating) return
              if (!confirm('REGENERAR o OCG do zero a partir do questionário aprovado? ATENÇÃO: chama os 8 agentes IA novamente (custo em tokens, leva 3-5min). O histórico de deltas é preservado. Continuar?')) return
              setRegenerating(true)
              try {
                // /regenerate chama 8 agentes IA (3-5min). Timeout 5min.
                const res: any = await apiClient.post(
                  `/projects/${id}/ocg/regenerate?confirm=true`,
                  {},
                  { timeout: 300000 },
                )
                alert(res?.data?.message || 'Regeneração disparada em background. Verifique em alguns minutos.')
                await loadData()
              } catch (err: unknown) {
                alert(formatOCGOperationError(err, 'Regenerar'))
              } finally {
                setRegenerating(false)
              }
            }}
            disabled={reconsolidating || regenerating}
            title="Regenera OCG do zero a partir do questionário aprovado (3-5min, custo em tokens). Bloqueia se outra operação OCG está rodando no mesmo projeto."
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600/10 border border-red-600/30 text-red-300 text-sm hover:bg-red-600/20 disabled:opacity-40 transition-colors"
          >
            {regenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <AlertTriangle className="w-3.5 h-3.5" />}
            Regenerar OCG
          </button>
        </div>
      </div>

      {DIMENSIONS.map(dim => {
        const Icon = dim.icon
        const isOpen = expanded === dim.key
        return (
          <div key={dim.key} className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setExpanded(isOpen ? null : dim.key)}
              className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-800/40 transition-colors"
            >
              <div className={`w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0 ${colorClass[dim.color]}`}>
                <Icon className="w-4 h-4" />
              </div>
              <span className="text-slate-200 text-sm font-medium flex-1 text-left">{dim.label}</span>
              {isOpen ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
            </button>
            {isOpen && (
              <div className="px-5 pb-5 border-t border-slate-800">
                <div className="pt-4">{renderDimensionContent(dim.key)}</div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default OCGPage
