/**
 * FollowUpQuestionnaire — Interface para responder perguntas de clarificação
 *
 * Personas geram perguntas baseadas em análises iniciais.
 * User responde, personas refinam suas análises.
 */

import React, { useState, useEffect } from 'react'
import { Loader, Send, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useToast } from '@/hooks/useToast'

interface Question {
  id: string
  persona_name: string
  question_text: string
  context: string | null
  question_order: number
  answer_text: string | null
  status: 'pending' | 'answered' | 'refinement_complete'
  created_at: string | null
}

interface Props {
  projectId: string
  documentId: string
}

export function FollowUpQuestionnaire({ projectId, documentId }: Props) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [answers, setAnswers] = useState<{ [key: string]: string }>({})
  const toast = useToast()

  useEffect(() => {
    fetchQuestions()
  }, [projectId, documentId])

  const fetchQuestions = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/follow-up-questions`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setQuestions(data.questions || [])

        // Pre-populate answers
        const initialAnswers: { [key: string]: string } = {}
        data.questions?.forEach((q: Question) => {
          if (q.answer_text) {
            initialAnswers[q.id] = q.answer_text
          }
        })
        setAnswers(initialAnswers)
      } else {
        toast.error('Erro ao carregar perguntas')
      }
    } catch (error) {
      console.error('Erro ao buscar perguntas:', error)
      toast.error('Erro ao carregar perguntas')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async () => {
    // Validar que todas as perguntas foram respondidas
    const unanswered = questions.filter(
      (q) => q.status === 'pending' && !answers[q.id]
    )

    if (unanswered.length > 0) {
      toast.warning(
        `Responda todas as perguntas pendentes (${unanswered.length} faltando)`
      )
      return
    }

    try {
      setSubmitting(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/follow-up-answers`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
          body: JSON.stringify({ answers }),
        }
      )

      if (response.ok) {
        toast.success('Respostas submetidas! Personas estão refinando análises...')
        fetchQuestions()
      } else {
        toast.error('Erro ao submeter respostas')
      }
    } catch (error) {
      console.error('Erro ao submeter:', error)
      toast.error('Erro ao submeter respostas')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader className="h-6 w-6 animate-spin text-emerald-600" />
        <span className="ml-3 text-gray-700">Carregando perguntas...</span>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8">
        <CheckCircle2 className="h-12 w-12 text-emerald-600 mb-3" />
        <h3 className="text-lg font-semibold text-gray-900">Sem perguntas</h3>
        <p className="text-sm text-gray-600 mt-1">
          Personas ainda estão analisando o documento.
        </p>
      </div>
    )
  }

  const allAnswered = questions.every(
    (q) => q.status !== 'pending' || answers[q.id]
  )
  const answeredCount = questions.filter((q) => answers[q.id]).length

  return (
    <div className="space-y-4">
      {/* Header com progresso */}
      <div className="flex items-center justify-between p-4 bg-white rounded-lg border border-gray-200">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Perguntas de Clarificação
          </h2>
          <p className="text-sm text-gray-600 mt-1">
            {answeredCount} de {questions.length} respondidas
          </p>
        </div>
        <div className="w-48 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-600 transition-all duration-300"
            style={{ width: `${(answeredCount / questions.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Info box */}
      <div className="flex gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <AlertCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-700">
          <strong>Como funciona:</strong> Responda as perguntas dos personas com informações detalhadas.
          Suas respostas ajudam a refinar as análises e recomendações técnicas.
        </div>
      </div>

      {/* Questões */}
      <div className="space-y-4">
        {questions.map((question) => {
          const isAnswered = answers[question.id]
          const isPending = question.status === 'pending'

          return (
            <div
              key={question.id}
              className="p-4 bg-white border border-gray-200 rounded-lg hover:shadow-md transition-shadow"
            >
              {/* Header da pergunta */}
              <div className="flex items-start gap-3 mb-3">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900">
                    {question.question_text}
                  </h3>
                  <p className="text-xs text-gray-500 mt-1">
                    {question.persona_name}
                  </p>
                </div>
                {isAnswered && (
                  <CheckCircle2 className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-1" />
                )}
              </div>

              {/* Contexto */}
              {question.context && (
                <p className="text-sm text-gray-600 italic mb-3 p-2 bg-gray-50 rounded">
                  <strong>Por que essa pergunta?</strong> {question.context}
                </p>
              )}

              {/* Resposta */}
              {isPending ? (
                <textarea
                  value={answers[question.id] || ''}
                  onChange={(e) =>
                    setAnswers({
                      ...answers,
                      [question.id]: e.target.value,
                    })
                  }
                  placeholder="Sua resposta aqui..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm resize-none"
                  rows={3}
                />
              ) : (
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">
                    {answers[question.id]}
                  </p>
                </div>
              )}

              {/* Status */}
              {question.status === 'refinement_complete' && (
                <div className="mt-2 text-xs text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="h-4 w-4" />
                  Persona refinando análise com sua resposta
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Botão de submissão */}
      <div className="flex gap-3 pt-4">
        <button
          onClick={handleSubmit}
          disabled={!allAnswered || submitting}
          className="flex-1 px-4 py-3 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
        >
          {submitting ? (
            <>
              <Loader className="h-5 w-5 animate-spin" />
              Submetendo...
            </>
          ) : (
            <>
              <Send className="h-5 w-5" />
              Submeter Respostas
            </>
          )}
        </button>
      </div>

      {/* Info final */}
      <p className="text-xs text-gray-600 text-center">
        Suas respostas serão usadas para refinar as análises das personas
      </p>
    </div>
  )
}
