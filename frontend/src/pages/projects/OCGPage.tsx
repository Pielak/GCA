import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import {
  Settings, Brain, GitBranch, Plug, Layers, Shield, FileText, TestTube2,
  Users, Activity, History, Check, ChevronDown, ChevronRight, Edit2, Info,
  Loader2, AlertTriangle, RefreshCw
} from 'lucide-react'
import { apiClient } from '@/lib/api'

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
  { key: 'architecture', label: 'Arquitetura', icon: GitBranch, color: 'cyan' },
  { key: 'compliance', label: 'Compliance', icon: Shield, color: 'amber' },
  { key: 'testing', label: 'Estratégia de Testes', icon: TestTube2, color: 'emerald' },
  { key: 'deliverables', label: 'Entregas', icon: FileText, color: 'orange' },
  { key: 'risks', label: 'Riscos', icon: AlertTriangle, color: 'red' },
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
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
    } catch (err: any) {
      if (err?.status === 404 || err?.response?.status === 404) {
        setOcg(null) // OCG não gerado ainda
      } else {
        setError('Erro ao carregar OCG')
      }
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
        return ocg.PILLAR_SCORES ? (
          <div className="space-y-3">
            {Object.entries(ocg.PILLAR_SCORES).map(([pillar, data]: [string, any]) => (
              <div key={pillar} className="p-3 rounded-lg bg-slate-800/40">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-slate-200 text-sm font-medium">{pillar}</span>
                  <span className="text-xs text-slate-500">{typeof data === 'object' ? data.status || '' : ''}</span>
                </div>
                <ScoreBar score={typeof data === 'object' ? (data.score ?? 0) : (data ?? 0)} />
              </div>
            ))}
          </div>
        ) : <p className="text-slate-500 text-sm">Dados de pilares não disponíveis.</p>
      case 'stack':
        return (ocg.STACK_RECOMMENDATION || ocg.STACK_RECOMMENDATIONS) ? renderObject(ocg.STACK_RECOMMENDATION || ocg.STACK_RECOMMENDATIONS) : <p className="text-slate-500 text-sm">Stack não definida.</p>
      case 'architecture':
        return (ocg.ARCHITECTURE_OVERVIEW || ocg.ARCHITECTURE) ? renderObject(ocg.ARCHITECTURE_OVERVIEW || ocg.ARCHITECTURE) : <p className="text-slate-500 text-sm">Arquitetura não definida.</p>
      case 'compliance':
        return (ocg.COMPLIANCE_CHECKLIST || ocg.COMPLIANCE_PROFILE) ? renderObject(ocg.COMPLIANCE_CHECKLIST || ocg.COMPLIANCE_PROFILE) : <p className="text-slate-500 text-sm">Compliance não definido.</p>
      case 'testing':
        return (ocg.TESTING_REQUIREMENTS || ocg.TESTING_STRATEGY) ? renderObject(ocg.TESTING_REQUIREMENTS || ocg.TESTING_STRATEGY) : <p className="text-slate-500 text-sm">Estratégia de testes não definida.</p>
      case 'deliverables':
        return ocg.DELIVERABLES ? renderObject(ocg.DELIVERABLES) : <p className="text-slate-500 text-sm">Entregas não definidas.</p>
      case 'risks':
        return (ocg.RISK_ANALYSIS || ocg.RISKS) ? renderObject(ocg.RISK_ANALYSIS || ocg.RISKS) : <p className="text-slate-500 text-sm">Riscos não identificados.</p>
      default:
        return <p className="text-slate-500 text-sm">Seção não disponível.</p>
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">OCG — Objeto de Contexto Global</h2>
          <p className="text-slate-500 text-sm mt-0.5">Nenhum módulo opera sobre um projeto sem antes ler seu OCG.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-emerald-400 text-sm">
            <Check className="w-4 h-4" /> OCG Gerado
          </span>
          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 border border-indigo-600/30 text-indigo-400 text-sm hover:bg-indigo-600/30 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Atualizar
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
