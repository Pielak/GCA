import { useEffect, useState } from 'react'
import { Loader2, X, Download, ListOrdered, AlertTriangle, GitCommit } from 'lucide-react'
import api, { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

/**
 * MVP 9 Fase 9.4 — Modal "Plano de Deploy".
 *
 * Mostra os módulos do Roadmap ordenados por camada canônica + sort
 * topológico de dependências dentro de cada camada. Resumo: total /
 * prontos pra CodeGen / bloqueados. Botão exportar Markdown.
 */

type ReadinessStatus = 'ready_for_codegen' | 'partial' | 'needs_input' | 'unknown'

interface PlanItem {
  id: string
  name: string
  module_type: string
  priority: 'high' | 'medium' | 'low' | string
  status: string
  readiness_status: ReadinessStatus | null
  description: string
  depends_on: { id: string; name: string }[]
  cycle: boolean
}

interface PlanLayer {
  layer: string
  label: string
  items: PlanItem[]
}

interface DeployPlan {
  project_id: string
  generated_at: string
  total_modules: number
  ready_count: number
  blocked_count: number
  layers: PlanLayer[]
}

const READINESS_DOT: Record<string, string> = {
  ready_for_codegen: 'bg-emerald-400',
  partial: 'bg-amber-400',
  needs_input: 'bg-red-400',
  unknown: 'bg-slate-500',
}

const READINESS_LABEL: Record<string, string> = {
  ready_for_codegen: 'Pronto pra CodeGen',
  partial: 'Parcial',
  needs_input: 'Precisa input',
  unknown: 'Não avaliado',
}

const PRIORITY_LABEL: Record<string, string> = {
  high: 'Alta', medium: 'Média', low: 'Baixa',
}

interface Props {
  projectId: string
  onClose: () => void
}

export function DeployPlanModal({ projectId, onClose }: Props) {
  const [plan, setPlan] = useState<DeployPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const r = await apiClient.get<DeployPlan>(`/projects/${projectId}/roadmap/deploy-plan`)
        if (!cancelled) setPlan(r.data)
      } catch (e: unknown) {
        if (!cancelled) setErr(getErrorMessage(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [projectId])

  const exportMd = async () => {
    setExporting(true)
    try {
      const res = await api.get(
        `/projects/${projectId}/roadmap/deploy-plan.md`,
        { responseType: 'blob' },
      )
      const blob = new Blob([res.data], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `gca-deploy-plan-${projectId.slice(0, 8)}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      setErr(getErrorMessage(e))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-slate-950 border border-slate-700 rounded-xl max-w-4xl w-full max-h-[92vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              MVP 9 Fase 9.4 — Plano de Deploy
            </div>
            <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
              <ListOrdered className="w-4 h-4 text-violet-400" />
              Sequência sugerida de construção
            </h3>
            {plan && (
              <p className="text-[11px] text-slate-500 mt-1">
                {plan.total_modules} módulos &bull;{' '}
                <span className="text-emerald-300">{plan.ready_count} prontos</span> &bull;{' '}
                <span className="text-red-300">{plan.blocked_count} bloqueados</span>
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 ml-3">
            <button
              type="button"
              onClick={exportMd}
              disabled={exporting || loading || !!err}
              className="flex items-center gap-2 text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              {exporting ? 'Exportando…' : 'Baixar Markdown'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading && (
            <div className="flex items-center justify-center py-12 text-slate-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Montando plano…
            </div>
          )}

          {err && (
            <div className="flex items-start gap-3 bg-red-500/10 border border-red-500/30 rounded-lg p-4">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-300">{err}</p>
            </div>
          )}

          {plan && !loading && !err && plan.layers.length === 0 && (
            <p className="text-sm text-slate-500 text-center py-8">
              Nenhum módulo no Roadmap ainda.
            </p>
          )}

          {plan && !loading && !err && plan.layers.map((layer, li) => (
            <section key={layer.layer} className="border border-slate-800 rounded-lg overflow-hidden">
              <header className="px-4 py-2.5 bg-slate-900/60 border-b border-slate-800 flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 font-medium">
                  Camada {li + 1}
                </span>
                <h4 className="text-sm font-semibold text-slate-200">{layer.label}</h4>
                <span className="text-[10px] text-slate-500 ml-auto">
                  {layer.items.length} {layer.items.length === 1 ? 'item' : 'itens'}
                </span>
              </header>
              <ol className="divide-y divide-slate-800">
                {layer.items.map((item, ii) => {
                  const readinessKey = item.readiness_status || 'unknown'
                  return (
                    <li key={item.id} className="px-4 py-3 hover:bg-slate-900/40 transition-colors">
                      <div className="flex items-start gap-3 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-600 w-6 text-right pt-0.5">
                          {String(ii + 1).padStart(2, '0')}
                        </span>
                        <div className="flex-1 min-w-[280px]">
                          <div className="flex items-center gap-2 flex-wrap">
                            <GitCommit className="w-3 h-3 text-slate-500" />
                            <span className="text-sm font-medium text-slate-200">{item.name}</span>
                            {item.cycle && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                                ⚠ ciclo de dependência
                              </span>
                            )}
                          </div>
                          {item.description && (
                            <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                              {item.description}
                            </p>
                          )}
                          {item.depends_on.length > 0 && (
                            <div className="mt-1.5 text-[10px] text-slate-500">
                              <span className="opacity-60">depende de: </span>
                              {item.depends_on.map((d, di) => (
                                <span key={di} className="ml-1 px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 inline-block">
                                  {d.name}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500">
                          <span className={`w-1.5 h-1.5 rounded-full ${READINESS_DOT[readinessKey]}`} />
                          <span>{READINESS_LABEL[readinessKey]}</span>
                          <span className="opacity-60">·</span>
                          <span>{PRIORITY_LABEL[item.priority] || item.priority}</span>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/40">
          <p className="text-[10px] text-slate-500 leading-relaxed">
            <strong className="text-slate-400">Como ler:</strong> camadas vão de infra → observabilidade → middleware → backend → funcionalidade → deploy.
            Dentro de cada camada, ordem leva em conta dependências (Fase 9.3) + prioridade + readiness.
            Items em ⚠ ciclo de dependência precisam revisão manual.
          </p>
        </div>
      </div>
    </div>
  )
}
