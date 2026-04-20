import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Clock, CheckCircle, Circle, GitCommit, Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import { HelpTooltip } from '@/components/ui/HelpTooltip'
import { apiClient } from '@/lib/api'
import { ModuleDetailsModal } from '@/components/roadmap/ModuleDetailsModal'

// MVP 9 Fase 9.1 — categorias canônicas de módulos no Roadmap.
// Mantido em sync com `backend/app/constants/module_categories.py`.
type ModuleCategory =
  | 'infrastructure'
  | 'observability'
  | 'middleware'
  | 'backend_service'
  | 'feature'
  | 'deploy_pipeline'

const CATEGORY_LABEL: Record<ModuleCategory, string> = {
  infrastructure: 'Infraestrutura',
  observability: 'Observabilidade',
  middleware: 'Middleware',
  backend_service: 'Serviço de Backend',
  feature: 'Funcionalidade',
  deploy_pipeline: 'Pipeline de Deploy',
}

const CATEGORY_STYLE: Record<ModuleCategory, string> = {
  infrastructure: 'bg-slate-700/40 text-slate-200 border-slate-600',
  observability: 'bg-sky-900/30 text-sky-300 border-sky-700/50',
  middleware: 'bg-amber-900/20 text-amber-300 border-amber-700/40',
  backend_service: 'bg-violet-900/30 text-violet-300 border-violet-700/50',
  feature: 'bg-emerald-900/20 text-emerald-300 border-emerald-700/40',
  deploy_pipeline: 'bg-fuchsia-900/20 text-fuchsia-300 border-fuchsia-700/40',
}

const CATEGORY_ORDER: ModuleCategory[] = [
  'infrastructure', 'observability', 'middleware',
  'backend_service', 'feature', 'deploy_pipeline',
]

type ReadinessStatus = 'ready_for_codegen' | 'partial' | 'needs_input' | 'unknown'

interface RoadmapModule {
  id?: string
  name: string
  status: string
  module_type?: ModuleCategory | string
  description?: string
  priority?: string
  // MVP 9 Fase 9.3 — avaliação Premium do estado pra CodeGen
  readiness_status?: ReadinessStatus | string | null
  created_at: string | null
}

const READINESS_STYLE: Record<string, string> = {
  ready_for_codegen: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  partial: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  needs_input: 'bg-red-500/15 text-red-300 border-red-500/40',
  unknown: 'bg-slate-700/40 text-slate-400 border-slate-600',
}

const READINESS_LABEL: Record<string, string> = {
  ready_for_codegen: '✓ Pronto pra CodeGen',
  partial: '◐ Parcial',
  needs_input: '⚠ Precisa input',
  unknown: '? Não avaliado',
}

interface RoadmapPhase {
  name: string
  modules: RoadmapModule[]
  status: string
}

interface RoadmapData {
  phases: RoadmapPhase[]
  total_modules: number
  completed_modules: number
  progress_percent: number
  next_action: string
}

// MVP 9 Fase 9.1.2 — status canônicos pt-BR (backend já normaliza
// aliases antigos). CodeGen ainda emite generating/in_progress/failed
// que preservamos com label humano.
const moduleStatusStyle = (s: string) => {
  if (s === 'concluido' || s === 'completed') return 'bg-emerald-900/30 text-emerald-400'
  if (s === 'adicionado') return 'bg-emerald-900/20 text-emerald-300'
  if (s === 'aguardando_resposta') return 'bg-amber-900/30 text-amber-300'
  if (s === 'sugerido') return 'bg-slate-800 text-slate-400'
  if (s === 'generating' || s === 'in_progress') return 'bg-violet-900/30 text-violet-400'
  if (s === 'failed') return 'bg-red-900/30 text-red-400'
  return 'bg-slate-800 text-slate-500'
}

const moduleStatusLabel = (s: string) => {
  const labels: Record<string, string> = {
    sugerido: 'Sugerido',
    aguardando_resposta: 'Aguardando resposta',
    adicionado: 'Adicionado',
    concluido: 'Concluído',
    // CodeGen terminals
    completed: 'Concluído',
    generating: 'Gerando',
    in_progress: 'Em progresso',
    failed: 'Falhou',
  }
  return labels[s] || s
}

export function RoadmapPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<RoadmapData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // MVP 9 Fase 9.1 — filtro por categoria. null = todas.
  const [categoryFilter, setCategoryFilter] = useState<ModuleCategory | null>(null)
  // MVP 9 Fase 9.2 — modal de detalhamento on-demand. Guarda o módulo aberto.
  const [detailsModule, setDetailsModule] = useState<{ id: string; name: string } | null>(null)

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.get(`/projects/${id}/roadmap`)
      setData(res.data)
    } catch (err: any) {
      setError('Erro ao carregar roadmap')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [id])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800/30 rounded-xl p-6 text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-3" />
          <p className="text-red-300 text-sm mb-3">{error || 'Dados não disponíveis'}</p>
          <button onClick={loadData} className="flex items-center gap-2 mx-auto px-4 py-2 bg-slate-800 border border-slate-700 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors">
            <RefreshCw className="w-4 h-4" /> Tentar novamente
          </button>
        </div>
      </div>
    )
  }

  const { phases, total_modules, completed_modules, progress_percent, next_action } = data
  const hasModules = total_modules > 0

  // MVP 9 Fase 9.1 — contagem por categoria (todas as fases somadas) +
  // filtragem aplicada. Sem mexer nas fases em si: a fase só some da
  // tela se todos seus módulos forem filtrados.
  const categoryCounts: Record<ModuleCategory, number> = {
    infrastructure: 0, observability: 0, middleware: 0,
    backend_service: 0, feature: 0, deploy_pipeline: 0,
  }
  for (const phase of phases) {
    for (const m of phase.modules) {
      const mt = (m.module_type || 'feature') as ModuleCategory
      if (mt in categoryCounts) categoryCounts[mt] += 1
    }
  }

  const matchesFilter = (m: RoadmapModule) => {
    if (!categoryFilter) return true
    return (m.module_type || 'feature') === categoryFilter
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-1.5">
            Roadmap do Projeto
            <HelpTooltip text="O Roadmap é a visão macro do projeto organizada em fases de desenvolvimento. É gerado automaticamente pelo GCA a partir do OCG, que define quais módulos existem, suas dependências e complexidade estimada (alta/média/baixa = Fase 1/2/3). Atualiza-se em tempo real: módulo aprovado no Gatekeeper → fica verde; módulo bloqueado → fica vermelho." />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Evolução dos módulos por fase e prioridade</p>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={loadData} className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors" title="Atualizar">
            <RefreshCw className="w-4 h-4" />
          </button>
          {hasModules && (
            <div className="flex items-center gap-3 min-w-[200px]">
              <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-violet-600 rounded-full transition-all duration-500" style={{ width: `${progress_percent}%` }} />
              </div>
              <span className="text-xs text-slate-400 font-medium whitespace-nowrap">{completed_modules}/{total_modules} módulos ({progress_percent}%)</span>
            </div>
          )}
        </div>
      </div>

      {/* MVP 9 Fase 9.1 — barra de filtros por categoria */}
      {hasModules && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-slate-500 uppercase tracking-wide mr-1">
            Filtrar:
          </span>
          <button
            onClick={() => setCategoryFilter(null)}
            className={`text-xs px-2 py-1 rounded border transition-colors ${
              categoryFilter === null
                ? 'bg-violet-600/30 border-violet-500/60 text-violet-100'
                : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
            }`}
          >
            Todas ({total_modules})
          </button>
          {CATEGORY_ORDER.map(cat => {
            const count = categoryCounts[cat]
            if (count === 0) return null
            const active = categoryFilter === cat
            return (
              <button
                key={cat}
                onClick={() => setCategoryFilter(active ? null : cat)}
                className={`text-xs px-2 py-1 rounded border transition-colors ${
                  active
                    ? CATEGORY_STYLE[cat].replace('/20', '/40').replace('/30', '/50')
                    : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                {CATEGORY_LABEL[cat]} ({count})
              </button>
            )
          })}
        </div>
      )}

      {!hasModules ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <Clock className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <h3 className="text-slate-300 font-medium mb-2">Nenhum módulo no roadmap</h3>
          <p className="text-slate-500 text-sm max-w-md mx-auto">
            O roadmap será populado automaticamente quando o Code Generator criar módulos candidatos
            a partir do OCG do projeto.
          </p>
        </div>
      ) : (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[18px] top-4 bottom-4 w-0.5 bg-slate-800" />
          <div className="space-y-4">
            {phases.map((phase, pi) => {
              const isDone = phase.status === 'completed'
              const isActive = phase.status === 'in_progress'
              return (
                <div key={pi} className="flex gap-4">
                  {/* Node */}
                  <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center flex-shrink-0 z-10 ${isDone ? 'bg-emerald-900/40 border-emerald-600' : isActive ? 'bg-violet-900/40 border-violet-600 ring-4 ring-violet-600/10' : 'bg-slate-900 border-slate-700'}`}>
                    {isDone ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : isActive ? <span className="w-2.5 h-2.5 rounded-full bg-violet-400 animate-pulse" /> : <Circle className="w-4 h-4 text-slate-600" />}
                  </div>
                  {/* Content */}
                  <div className={`flex-1 p-4 rounded-xl border mb-1 ${isDone ? 'border-slate-800 opacity-75' : isActive ? 'border-violet-600/40 bg-violet-950/10' : 'border-slate-800'}`}>
                    <div className="flex items-start justify-between mb-2 flex-wrap gap-2">
                      <p className={`text-sm font-medium ${isDone ? 'text-slate-300' : isActive ? 'text-violet-300' : 'text-slate-500'}`}>{phase.name}</p>
                      <span className={`text-xs px-2 py-0.5 rounded ${isDone ? 'bg-emerald-900/30 text-emerald-400' : isActive ? 'bg-violet-900/30 text-violet-400' : 'bg-slate-800 text-slate-600'}`}>
                        {isDone ? 'Concluída' : isActive ? 'Em andamento' : 'Pendente'}
                      </span>
                    </div>
                    {(() => {
                      const visibleModules = phase.modules.filter(matchesFilter)
                      if (visibleModules.length === 0) {
                        return (
                          <p className="text-slate-600 text-xs italic">
                            {categoryFilter
                              ? `Nenhum módulo desta fase é "${CATEGORY_LABEL[categoryFilter]}"`
                              : 'Nenhum módulo nesta fase'}
                          </p>
                        )
                      }
                      return (
                        <div className="flex flex-wrap gap-1.5">
                          {visibleModules.map((mod, mi) => {
                            const cat = (mod.module_type || 'feature') as ModuleCategory
                            const knownCat = cat in CATEGORY_LABEL
                            // MVP 9 Fase 9.2 — chip clicável abre modal de
                            // detalhamento. Só ativo se temos id (rows
                            // antigas pré-MVP9 podem não ter retornado id).
                            const clickable = !!mod.id
                            return (
                              <button
                                key={mod.id || mi}
                                type="button"
                                disabled={!clickable}
                                onClick={() => clickable && setDetailsModule({ id: mod.id!, name: mod.name })}
                                title={clickable
                                  ? `${mod.description || mod.name} · clique para detalhar`
                                  : (mod.description || mod.name)
                                }
                                className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded ${moduleStatusStyle(mod.status)} ${clickable ? 'hover:ring-1 hover:ring-violet-500/50 cursor-pointer' : 'cursor-default opacity-80'}`}
                              >
                                <GitCommit className="w-3 h-3" />
                                {mod.name}
                                {knownCat && (
                                  <span className={`ml-1 px-1 rounded border text-[10px] ${CATEGORY_STYLE[cat]}`}>
                                    {CATEGORY_LABEL[cat]}
                                  </span>
                                )}
                                {mod.readiness_status && READINESS_LABEL[mod.readiness_status] && (
                                  <span className={`ml-1 px-1 rounded border text-[10px] ${READINESS_STYLE[mod.readiness_status] || READINESS_STYLE.unknown}`}>
                                    {READINESS_LABEL[mod.readiness_status]}
                                  </span>
                                )}
                                <span className="opacity-60">({moduleStatusLabel(mod.status)})</span>
                              </button>
                            )
                          })}
                        </div>
                      )
                    })()}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Próxima ação */}
      {hasModules && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-slate-500 text-xs mb-1">Próxima ação recomendada</p>
          <p className="text-slate-300 text-sm">{next_action}</p>
        </div>
      )}

      {/* MVP 9 Fase 9.2 — Modal de detalhamento on-demand */}
      {detailsModule && id && (
        <ModuleDetailsModal
          projectId={id}
          moduleId={detailsModule.id}
          moduleName={detailsModule.name}
          onClose={() => setDetailsModule(null)}
        />
      )}
    </div>
  )
}

export default RoadmapPage
