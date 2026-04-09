import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Clock, CheckCircle, Circle, GitCommit, Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import { HelpTooltip } from '@/components/ui/HelpTooltip'
import { apiClient } from '@/lib/api'

interface RoadmapModule {
  name: string
  status: string
  created_at: string | null
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

const moduleStatusStyle = (s: string) => {
  if (s === 'completed') return 'bg-emerald-900/30 text-emerald-400'
  if (s === 'generating' || s === 'in_progress' || s === 'approved') return 'bg-violet-900/30 text-violet-400'
  if (s === 'failed') return 'bg-red-900/30 text-red-400'
  return 'bg-slate-800 text-slate-500'
}

const moduleStatusLabel = (s: string) => {
  const labels: Record<string, string> = {
    completed: 'Concluído',
    generating: 'Gerando',
    in_progress: 'Em progresso',
    approved: 'Aprovado',
    pending: 'Pendente',
    failed: 'Falhou',
    candidate: 'Candidato',
  }
  return labels[s] || s
}

export function RoadmapPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<RoadmapData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
                    {phase.modules.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {phase.modules.map((mod, mi) => (
                          <span key={mi} className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded ${moduleStatusStyle(mod.status)}`}>
                            <GitCommit className="w-3 h-3" />
                            {mod.name}
                            <span className="opacity-60">({moduleStatusLabel(mod.status)})</span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-600 text-xs italic">Nenhum módulo nesta fase</p>
                    )}
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
    </div>
  )
}

export default RoadmapPage
