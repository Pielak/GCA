import React, { useState } from 'react'
import { Send, AlertCircle } from 'lucide-react'
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

interface HumanAnswerFormProps {
  routeMapId: string
  questions: PersonaQuestion[]
  onSubmit?: () => void
  onError?: (error: string) => void
}

interface FormAnswer {
  persona_tag: string
  question_id: string
  answer_text: string
}

const PERSONA_LABELS: Record<string, string> = {
  gp: '📋 Gerente de Projetos',
  arq: '🏗️ Arquiteto',
  dba: '🗄️ Data Engineer',
  dev: '💻 Developer Senior',
  qa: '🧪 QA/Testing',
  ux: '✨ UX Designer',
  ui: '🎨 UI Designer',
}

export function HumanAnswerForm({
  routeMapId,
  questions,
  onSubmit,
  onError,
}: HumanAnswerFormProps) {
  const [answers, setAnswers] = useState<Map<string, string>>(new Map())
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleAnswerChange = (questionId: string, value: string) => {
    const newAnswers = new Map(answers)
    newAnswers.set(questionId, value)
    setAnswers(newAnswers)
  }

  const allAnswered = questions.length > 0 && answers.size === questions.length

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!allAnswered) {
      onError?.('Todas as perguntas devem ser respondidas')
      return
    }

    setSubmitting(true)

    try {
      const humanAnswers = questions.map((q) => ({
        persona_tag: q.persona_tag,
        question_id: q.id,
        answer_text: answers.get(q.id) || '',
      }))

      await apiClient.post(`/gatekeeper/human-answers`, {
        route_map_id: routeMapId,
        answers: humanAnswers,
      })

      setSubmitted(true)
      onSubmit?.()
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Erro ao enviar respostas')
    } finally {
      setSubmitting(false)
    }
  }

  if (questions.length === 0) {
    return (
      <div className="p-4 border border-emerald-800/30 bg-emerald-950/10 rounded-lg">
        <div className="text-emerald-300">✓ Nenhuma pergunta para responder nesta etapa</div>
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="p-4 border border-emerald-800/30 bg-emerald-950/10 rounded-lg">
        <div className="text-emerald-300 font-semibold">✓ Respostas enviadas com sucesso!</div>
        <p className="text-sm text-gray-400 mt-2">
          Suas respostas foram registradas. A análise final (Passada 2) será executada em breve.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Agrupamento por persona */}
      {Array.from(new Set(questions.map((q) => q.persona_tag))).map((personaTag) => {
        const personaQuestions = questions.filter((q) => q.persona_tag === personaTag)

        return (
          <div key={personaTag} className="border border-slate-700 rounded-lg p-4 space-y-4">
            {/* Header da persona */}
            <div className="pb-4 border-b border-slate-700">
              <h3 className="text-lg font-semibold text-slate-200">
                {PERSONA_LABELS[personaTag] || personaTag}
              </h3>
              <p className="text-sm text-gray-400 mt-1">
                {personaQuestions.length} pergunta{personaQuestions.length !== 1 ? 's' : ''}
              </p>
            </div>

            {/* Perguntas */}
            <div className="space-y-5">
              {personaQuestions.map((question, idx) => (
                <div key={question.id} className="space-y-2">
                  {/* Número e severidade */}
                  <div className="flex items-start gap-2">
                    <span className="text-sm font-semibold text-slate-300 mt-0.5">
                      {idx + 1}.
                    </span>
                    <div className="flex-1">
                      <h4 className="text-sm text-slate-200 font-medium">
                        {question.question_text}
                      </h4>

                      {/* Severidade e tipo */}
                      <div className="flex gap-2 mt-2">
                        <span
                          className={`text-xs px-2 py-1 rounded ${severityBadge(
                            question.severity
                          )}`}
                        >
                          {question.severity.toUpperCase()}
                        </span>
                        <span className="text-xs px-2 py-1 rounded bg-slate-800 text-gray-400">
                          {answerTypeLabel(question.answer_type)}
                        </span>
                      </div>

                      {/* Rationale */}
                      {question.rationale && (
                        <p className="text-xs text-gray-500 mt-2 italic">
                          Razão: {question.rationale}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Input de resposta */}
                  {question.answer_type === 'free_text' ? (
                    <textarea
                      value={answers.get(question.id) || ''}
                      onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                      placeholder="Digite sua resposta aqui..."
                      rows={3}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded text-slate-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                      required
                    />
                  ) : (
                    <input
                      type={question.answer_type === 'numeric' ? 'number' : 'text'}
                      value={answers.get(question.id) || ''}
                      onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                      placeholder="Digite sua resposta..."
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded text-slate-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                      required
                    />
                  )}

                  {/* Status de resposta */}
                  {answers.has(question.id) && (
                    <div className="text-xs text-emerald-400">✓ Respondido</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {/* Summary de respostas */}
      <div className="p-4 border border-slate-700 rounded-lg bg-slate-950/50">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <p className="text-sm text-slate-300">
              <strong>{answers.size}</strong> de <strong>{questions.length}</strong> perguntas
              respondidas
            </p>
          </div>
          <div className="w-48 bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{ width: `${(answers.size / questions.length) * 100}%` }}
            ></div>
          </div>
        </div>
      </div>

      {/* Submit button */}
      <button
        type="submit"
        disabled={!allAnswered || submitting}
        className={`w-full py-3 rounded-lg font-semibold flex items-center justify-center gap-2 transition-all ${
          allAnswered && !submitting
            ? 'bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer'
            : 'bg-slate-800 text-gray-500 cursor-not-allowed'
        }`}
      >
        <Send className="w-4 h-4" />
        {submitting ? 'Enviando...' : 'Enviar Respostas'}
      </button>

      {/* Info message */}
      <div className="p-3 border border-blue-800/30 bg-blue-950/10 rounded-lg flex gap-3">
        <AlertCircle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-blue-300">
          Depois de enviar, as personas executarão a Passada 2 (análise final) com suas respostas incorporadas.
        </p>
      </div>
    </form>
  )
}

function severityBadge(severity: string): string {
  switch (severity) {
    case 'blocker':
      return 'bg-red-900/30 text-red-300'
    case 'critical':
      return 'bg-orange-900/30 text-orange-300'
    case 'important':
      return 'bg-amber-900/30 text-amber-300'
    case 'nice_to_have':
      return 'bg-gray-800 text-gray-300'
    default:
      return 'bg-gray-800 text-gray-300'
  }
}

function answerTypeLabel(type: string): string {
  switch (type) {
    case 'free_text':
      return 'Texto livre'
    case 'numeric':
      return 'Numérico'
    case 'single_choice':
      return 'Escolha única'
    default:
      return type
  }
}
