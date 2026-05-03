import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Zap, ChevronRight, AlertTriangle, Loader2 } from 'lucide-react'
import { GatekeeperPersonaBoard, HumanAnswerForm } from '@/components/gatekeeper'
import { apiClient } from '@/lib/api'

interface PersonaQuestion {
  id: string
  persona_tag: string
  question_text: string
  rationale: string
  answer_type: string
  severity: string
  chunk_refs: string[]
}

interface PersonasBoardResponse {
  route_map_id: string
  passada: number
  total_personas: number
  approved_count: number
  personas: Record<string, any>
}

export function GatekeeperPassadaPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [passada, setPassada] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [board, setBoard] = useState<PersonasBoardResponse | null>(null)
  const [questions, setQuestions] = useState<PersonaQuestion[]>([])
  const [passada2InProgress, setPassada2InProgress] = useState(false)

  // Executa Passada 1
  const handleRunPassada1 = async () => {
    if (!id) return

    setLoading(true)
    setError(null)

    try {
      const response = await apiClient.post(`/gatekeeper/passada-1`, {
        route_map_id: id,
        execute_now: true,
      })

      setBoard(response.data.personas_board)
      setQuestions(response.data.questions_to_answer || [])
      setPassada(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao executar Passada 1')
    } finally {
      setLoading(false)
    }
  }

  // Executa Passada 2 após respostas humanas
  const handlePassada2Started = async () => {
    if (!id) return

    setPassada2InProgress(true)
    setError(null)

    try {
      // Aguarda um pouco e depois carrega o board de Passada 2
      await new Promise((resolve) => setTimeout(resolve, 2000))

      const response = await apiClient.get(`/gatekeeper/personas-board/${id}?passada=2`)
      setBoard(response.data)
      setPassada(2)
      setQuestions([]) // Limpa perguntas já que Passada 2 não gera novas questões
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar Passada 2')
    } finally {
      setPassada2InProgress(false)
    }
  }

  // Carrega estado inicial
  useEffect(() => {
    const loadInitialState = async () => {
      if (!id) return

      setLoading(true)
      try {
        // Tenta carregar board existente de Passada 1
        const response = await apiClient.get(`/gatekeeper/personas-board/${id}?passada=1`)
        setBoard(response.data)
        setPassada(1)
      } catch {
        // Se não encontrar, state fica em inicial (sem board carregado)
      } finally {
        setLoading(false)
      }
    }

    loadInitialState()
  }, [id])

  if (!id) {
    return <div className="text-red-400">Erro: ID da rota não encontrado</div>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Zap className="w-6 h-6 text-emerald-400" />
          <h1 className="text-3xl font-bold text-slate-100">Validação Gatekeeper</h1>
        </div>
        <p className="text-gray-400">
          Análise técnica em paralelo com 7 personas especializadas
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="p-4 border border-red-800/30 bg-red-950/10 rounded-lg flex gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-red-300">Erro</h4>
            <p className="text-sm text-red-300/80">{error}</p>
          </div>
        </div>
      )}

      {/* Status info */}
      {passada2InProgress && (
        <div className="p-4 border border-blue-800/30 bg-blue-950/10 rounded-lg flex gap-3">
          <Loader2 className="w-5 h-5 text-blue-400 animate-spin flex-shrink-0" />
          <div>
            <h4 className="font-semibold text-blue-300">Processando...</h4>
            <p className="text-sm text-blue-300/80">
              Executando Passada 2 com suas respostas incorporadas...
            </p>
          </div>
        </div>
      )}

      {/* Conteúdo principal */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Coluna principal - Board */}
        <div className="lg:col-span-2">
          {!board ? (
            <div className="space-y-4">
              <div className="p-6 border border-slate-700 rounded-lg bg-slate-950/50 text-center space-y-4">
                <div className="flex items-center justify-center">
                  <Zap className="w-12 h-12 text-emerald-400 opacity-50" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-slate-200 mb-2">
                    Pronto para iniciar validação
                  </h3>
                  <p className="text-gray-400 mb-4">
                    Clique no botão abaixo para executar a análise de Passada 1 com todas as 7
                    personas em paralelo.
                  </p>
                </div>
                <button
                  onClick={handleRunPassada1}
                  disabled={loading}
                  className={`px-6 py-3 rounded-lg font-semibold flex items-center justify-center gap-2 mx-auto transition-all ${
                    loading
                      ? 'bg-slate-800 text-gray-500 cursor-not-allowed'
                      : 'bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer'
                  }`}
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Executando...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      Iniciar Passada 1
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Board de Passada 1 */}
              <GatekeeperPersonaBoard
                routeMapId={id}
                passada={passada}
                onBoardUpdate={setBoard}
                pollInterval={3000}
              />

              {/* Passada 2 - Se houver perguntas respondidas e estamos em Passada 1 */}
              {passada === 1 && questions.length > 0 && (
                <div className="border border-slate-700 rounded-lg p-6 bg-slate-950/50 space-y-4">
                  <div className="flex items-center gap-2 text-amber-400">
                    <AlertTriangle className="w-5 h-5" />
                    <h3 className="font-semibold">Próximo passo: Responder Perguntas</h3>
                  </div>
                  <p className="text-gray-400">
                    As personas levantaram {questions.length} pergunta{questions.length !== 1 ? 's' : ''}{' '}
                    que precisam ser respondidas para prosseguir com a análise final.
                  </p>
                </div>
              )}

              {/* Passada 2 completa */}
              {passada === 2 && (
                <div className="p-4 border border-emerald-800/30 bg-emerald-950/10 rounded-lg">
                  <h3 className="font-semibold text-emerald-300 mb-2">✓ Passada 2 Completa</h3>
                  <p className="text-sm text-gray-400">
                    Análise final executada com suas respostas incorporadas.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Coluna lateral - Formulário de respostas */}
        <div className="space-y-4">
          {questions.length > 0 && (
            <div className="border border-slate-700 rounded-lg bg-slate-950/50 p-4 space-y-4 sticky top-4">
              <h3 className="font-semibold text-slate-200">Responder Perguntas</h3>
              <HumanAnswerForm
                routeMapId={id}
                questions={questions}
                onSubmit={handlePassada2Started}
                onError={setError}
              />
            </div>
          )}

          {/* Info panel */}
          <div className="border border-slate-700 rounded-lg bg-slate-950/50 p-4 space-y-3">
            <h4 className="font-semibold text-slate-200 text-sm">Informações</h4>
            <div className="space-y-2 text-xs">
              <div>
                <p className="text-gray-500">Passada atual</p>
                <p className="text-slate-300 font-semibold">Passada {passada}</p>
              </div>
              {board && (
                <div>
                  <p className="text-gray-500">Personas</p>
                  <p className="text-slate-300 font-semibold">
                    {board.approved_count}/{board.total_personas} aprovadas
                  </p>
                </div>
              )}
              {questions.length > 0 && (
                <div>
                  <p className="text-gray-500">Perguntas pendentes</p>
                  <p className="text-slate-300 font-semibold">{questions.length}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
