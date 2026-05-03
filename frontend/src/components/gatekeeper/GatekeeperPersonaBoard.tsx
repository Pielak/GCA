import React, { useEffect, useState } from 'react'
import { CheckCircle2, AlertCircle, Zap, TrendingUp } from 'lucide-react'
import { HelpTooltip } from '@/components/ui/HelpTooltip'
import { apiClient } from '@/lib/api'

interface PersonaScore {
  escopo: number
  stack: number
  dados: number
  implementacao: number
  testes: number
  ux: number
  ui: number
}

interface PersonaResponse {
  persona_tag: string
  passada: number
  scores: PersonaScore
  approved: boolean
  tentative: boolean
  issues: Array<{
    chunk_id: string
    category: string
    severity: string
    description: string
    suggested_action?: string
  }>
  questions: Array<{
    id: string
    question_text: string
    rationale: string
    answer_type: string
    severity: string
    chunk_refs: string[]
  }>
  justification?: string
  input_tokens: number
  output_tokens: number
  elapsed_ms: number
}

interface PersonasBoardResponse {
  route_map_id: string
  passada: number
  total_personas: number
  approved_count: number
  personas: Record<string, PersonaResponse>
}

const PERSONA_CONFIG: Record<string, { name: string; icon: string; color: string; bgColor: string }> = {
  gp: {
    name: 'Gerente de Projetos',
    icon: '📋',
    color: 'text-blue-500',
    bgColor: 'bg-blue-50 border-blue-200 dark:bg-blue-950 dark:border-blue-800',
  },
  arq: {
    name: 'Arquiteto',
    icon: '🏗️',
    color: 'text-purple-500',
    bgColor: 'bg-purple-50 border-purple-200 dark:bg-purple-950 dark:border-purple-800',
  },
  dba: {
    name: 'Data Engineer',
    icon: '🗄️',
    color: 'text-green-500',
    bgColor: 'bg-green-50 border-green-200 dark:bg-green-950 dark:border-green-800',
  },
  dev: {
    name: 'Developer Senior',
    icon: '💻',
    color: 'text-orange-500',
    bgColor: 'bg-orange-50 border-orange-200 dark:bg-orange-950 dark:border-orange-800',
  },
  qa: {
    name: 'QA/Testing',
    icon: '🧪',
    color: 'text-red-500',
    bgColor: 'bg-red-50 border-red-200 dark:bg-red-950 dark:border-red-800',
  },
  ux: {
    name: 'UX Designer',
    icon: '✨',
    color: 'text-pink-500',
    bgColor: 'bg-pink-50 border-pink-200 dark:bg-pink-950 dark:border-pink-800',
  },
  ui: {
    name: 'UI Designer',
    icon: '🎨',
    color: 'text-indigo-500',
    bgColor: 'bg-indigo-50 border-indigo-200 dark:bg-indigo-950 dark:border-indigo-800',
  },
}

interface GatekeeperPersonaBoardProps {
  routeMapId: string
  passada?: number
  onBoardUpdate?: (board: PersonasBoardResponse) => void
  pollInterval?: number
}

export function GatekeeperPersonaBoard({
  routeMapId,
  passada = 1,
  onBoardUpdate,
  pollInterval = 2000,
}: GatekeeperPersonaBoardProps) {
  const [board, setBoard] = useState<PersonasBoardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedPersona, setExpandedPersona] = useState<string | null>(null)

  const fetchBoard = async () => {
    try {
      const response = await apiClient.get(`/gatekeeper/personas-board/${routeMapId}?passada=${passada}`)
      setBoard(response.data)
      onBoardUpdate?.(response.data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar board')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchBoard()
    const interval = setInterval(fetchBoard, pollInterval)
    return () => clearInterval(interval)
  }, [routeMapId, passada])

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin">⚙️</div>
        <span className="ml-2 text-gray-400">Carregando personas...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 border border-red-800/30 bg-red-950/10 rounded-lg">
        <div className="text-red-400">{error}</div>
      </div>
    )
  }

  if (!board) {
    return <div className="text-gray-400">Nenhuma persona encontrada</div>
  }

  return (
    <div className="space-y-4">
      {/* Header com resumo */}
      <div className="p-4 border border-emerald-800/30 bg-emerald-950/10 rounded-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <div>
              <h3 className="font-semibold text-emerald-300">Passada {board.passada}</h3>
              <p className="text-sm text-gray-400">
                {board.approved_count}/{board.total_personas} personas aprovadas
              </p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-emerald-300">
              {Math.round((board.approved_count / board.total_personas) * 100)}%
            </div>
            <p className="text-xs text-gray-400">Cobertura</p>
          </div>
        </div>
      </div>

      {/* Cards das personas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(board.personas).map(([tag, persona]) => {
          const config = PERSONA_CONFIG[tag]
          const isExpanded = expandedPersona === tag

          return (
            <div
              key={tag}
              className={`border rounded-lg p-4 cursor-pointer transition-all ${config.bgColor} ${
                isExpanded ? 'ring-2 ring-offset-1 ring-offset-slate-900 ring-emerald-500' : ''
              }`}
              onClick={() => setExpandedPersona(isExpanded ? null : tag)}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{config.icon}</span>
                  <div>
                    <h4 className="font-semibold text-slate-200">{config.name}</h4>
                    <p className="text-xs text-gray-400">{tag.toUpperCase()}</p>
                  </div>
                </div>
                <div>
                  {persona.approved ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-red-400" />
                  )}
                </div>
              </div>

              {/* Scores */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <ScoreBar label="Escopo" value={persona.scores.escopo} />
                <ScoreBar label="Stack" value={persona.scores.stack} />
                <ScoreBar label="Dados" value={persona.scores.dados} />
                <ScoreBar label="Impl" value={persona.scores.implementacao} />
                <ScoreBar label="Testes" value={persona.scores.testes} />
                {tag === 'ux' && <ScoreBar label="UX" value={persona.scores.ux} />}
                {tag === 'ui' && <ScoreBar label="UI" value={persona.scores.ui} />}
              </div>

              {/* Status badge */}
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-semibold text-slate-300">
                  {persona.tentative ? 'Tentativa' : 'Final'}
                </span>
                <span className="text-xs text-gray-400">
                  {persona.input_tokens} tokens in
                </span>
              </div>

              {/* Expandido */}
              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-slate-700 space-y-3">
                  {/* Issues */}
                  {persona.issues && persona.issues.length > 0 && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-300 mb-2">
                        Problemas ({persona.issues.length})
                      </h5>
                      <div className="space-y-1">
                        {persona.issues.map((issue, idx) => (
                          <div key={idx} className="text-xs text-gray-400">
                            <span className={`font-semibold ${severityColor(issue.severity)}`}>
                              {issue.severity.toUpperCase()}
                            </span>
                            : {issue.description}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Questions */}
                  {persona.questions && persona.questions.length > 0 && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-300 mb-2">
                        Perguntas ({persona.questions.length})
                      </h5>
                      <div className="space-y-2">
                        {persona.questions.map((q, idx) => (
                          <div key={idx} className="p-2 bg-slate-900 rounded border border-slate-700">
                            <p className="text-xs text-gray-300">{q.question_text}</p>
                            <p className="text-xs text-gray-500 mt-1">Razão: {q.rationale}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Justification */}
                  {persona.justification && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-300 mb-2">Justificativa</h5>
                      <p className="text-xs text-gray-400">{persona.justification}</p>
                    </div>
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

function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-400">{label}</span>
        <span className="text-xs font-semibold text-slate-200">{value}</span>
      </div>
      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${value}%` }}></div>
      </div>
    </div>
  )
}

function severityColor(severity: string) {
  switch (severity) {
    case 'blocker':
      return 'text-red-400'
    case 'critical':
      return 'text-orange-400'
    case 'warning':
      return 'text-amber-400'
    default:
      return 'text-gray-400'
  }
}
