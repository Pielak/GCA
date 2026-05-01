import { useState } from 'react'
import {
  HelpCircle, FileText, CheckCircle2,
  Loader2, Send, ChevronDown, ChevronRight,
} from 'lucide-react'
import { usePipelineQuestions, type PipelineQuestion } from '@/hooks/usePipelineQuestions'

interface Props {
  projectId: string
}

export function PipelineQuestionsSection({ projectId }: Props) {
  const {
    pendingQuestions,
    answeredQuestions,
    isLoading,
    submitAnswers,
    isSubmitting,
    refetch,
  } = usePipelineQuestions(projectId)

  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [collapsed, setCollapsed] = useState(false)
  const [showAnswered, setShowAnswered] = useState(false)

  const total = pendingQuestions.length + answeredQuestions.length
  if (total === 0 && !isLoading) return null

  const handleAnswer = (questionId: string, value: string) => {
    setAnswers(prev => ({ ...prev, [questionId]: value }))
  }

  const handleSubmit = async () => {
    if (Object.keys(answers).length === 0) return
    await submitAnswers(answers)
    setAnswers({})
    refetch()
  }

  // Agrupar perguntas pendentes por documento
  const pendingByDoc = groupByDoc(pendingQuestions)
  const answeredByDoc = groupByDoc(answeredQuestions)

  return (
    <div className="mt-8 pt-6 border-t border-slate-700 space-y-4">
      {/* Header colapsável */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors w-full text-left"
      >
        {collapsed
          ? <ChevronRight className="w-4 h-4 text-violet-400" />
          : <ChevronDown className="w-4 h-4 text-violet-400" />
        }
        <HelpCircle className="w-5 h-5 text-amber-400" />
        <span className="font-semibold text-base">
          Pendências do Pipeline
        </span>
        {pendingQuestions.length > 0 && (
          <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
            {pendingQuestions.length} pendente{pendingQuestions.length !== 1 ? 's' : ''}
          </span>
        )}
        {isLoading && <Loader2 className="w-4 h-4 animate-spin ml-auto" />}
      </button>

      {!collapsed && (
        <div className="space-y-4 pl-2">
          {/* Carregando */}
          {isLoading && (
            <div className="flex items-center gap-2 text-slate-400 text-sm py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              Carregando perguntas do pipeline...
            </div>
          )}

          {/* Sem perguntas pendentes */}
          {!isLoading && pendingQuestions.length === 0 && (
            <div className="flex items-center gap-2 text-slate-500 text-sm py-3">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Nenhuma pergunta pendente do pipeline.
            </div>
          )}

          {/* Grupo: Perguntas Pendentes por Documento */}
          {Object.entries(pendingByDoc).map(([docName, questions]) => (
            <div key={docName} className="space-y-3">
              <h4 className="flex items-center gap-1.5 text-sm font-medium text-slate-400">
                <FileText className="w-3.5 h-3.5" />
                {docName}
              </h4>
              {questions.map(q => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  answer={answers[q.id] ?? ''}
                  onAnswer={val => handleAnswer(q.id, val)}
                />
              ))}
            </div>
          ))}

          {/* Botão de envio */}
          {Object.keys(answers).length > 0 && (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
            >
              {isSubmitting
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Send className="w-4 h-4" />
              }
              Responder e Re-analisar ({Object.keys(answers).length} resposta{Object.keys(answers).length !== 1 ? 's' : ''})
            </button>
          )}

          {/* Perguntas já respondidas */}
          {answeredQuestions.length > 0 && (
            <div className="pt-2">
              <button
                onClick={() => setShowAnswered(!showAnswered)}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showAnswered ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                {answeredQuestions.length} pergunta{answeredQuestions.length !== 1 ? 's' : ''} respondida{answeredQuestions.length !== 1 ? 's' : ''}
              </button>
              {showAnswered && (
                <div className="mt-2 space-y-2">
                  {Object.entries(answeredByDoc).map(([docName, questions]) => (
                    <div key={docName}>
                      <h5 className="text-xs text-slate-500 mb-1">{docName}</h5>
                      {questions.map(q => (
                        <div key={q.id} className="flex items-start gap-2 text-xs text-slate-500 py-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-500 mt-0.5 flex-shrink-0" />
                          <span>{q.question_text}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Sub-componentes ───

function QuestionCard({
  question,
  answer,
  onAnswer,
}: {
  question: PipelineQuestion
  answer: string
  onAnswer: (val: string) => void
}) {
  const sourceLabel = SOURCE_LABELS[question.source] || question.source

  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 p-3 space-y-2">
      <div className="flex items-start gap-2">
        <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-300 uppercase">
          {sourceLabel}
        </span>
        <span className="text-xs text-slate-500">
          {SEVERITY_BADGE[question.severity ?? ''] || ''}
        </span>
      </div>

      <p className="text-sm text-slate-200 leading-relaxed">
        {question.question_text}
      </p>

      {question.rationale && (
        <p className="text-xs text-slate-400 italic">
          {question.rationale}
        </p>
      )}

      {question.status === 'pending' && (
        <div className="pt-1">
          {question.answer_type === 'boolean' ? (
            <div className="flex gap-2">
              <button
                onClick={() => onAnswer('Sim')}
                className={`px-3 py-1 text-xs rounded border transition-colors ${
                  answer === 'Sim'
                    ? 'bg-emerald-600/30 border-emerald-500/50 text-emerald-300'
                    : 'border-slate-600 text-slate-400 hover:border-slate-500'
                }`}
              >
                Sim
              </button>
              <button
                onClick={() => onAnswer('Não')}
                className={`px-3 py-1 text-xs rounded border transition-colors ${
                  answer === 'Não'
                    ? 'bg-red-600/30 border-red-500/50 text-red-300'
                    : 'border-slate-600 text-slate-400 hover:border-slate-500'
                }`}
              >
                Não
              </button>
            </div>
          ) : (
            <textarea
              value={answer}
              onChange={e => onAnswer(e.target.value)}
              placeholder="Digite sua resposta..."
              rows={2}
              className="w-full px-3 py-2 text-sm rounded-lg bg-slate-800 border border-slate-600 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-violet-500/50 resize-none"
            />
          )}
        </div>
      )}
    </div>
  )
}

// ─── Helpers ───

function groupByDoc(questions: PipelineQuestion[]): Record<string, PipelineQuestion[]> {
  const grouped: Record<string, PipelineQuestion[]> = {}
  for (const q of questions) {
    const key = q.document_name || q.document_id
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(q)
  }
  return grouped
}

const SOURCE_LABELS: Record<string, string> = {
  auditor: 'Auditor',
  gp: 'GP',
  arq: 'ARQ',
  dba: 'DBA',
  dev: 'DEV',
  qa: 'QA',
  ux: 'UX',
  ui: 'UI',
}

const SEVERITY_BADGE: Record<string, string> = {
  blocker: '🔴 Bloqueador',
  critical: '🟠 Crítico',
  important: '🟡 Importante',
  warning: '🟢 Atenção',
}
