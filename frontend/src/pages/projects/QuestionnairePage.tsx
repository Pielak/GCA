import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { ClipboardList, ChevronLeft, ChevronRight, Send, Loader2, CheckCircle2, Info, HelpCircle, X } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { BLOCKS, NA_VALUE, type QuestionDef } from '@/data/questionnaireBlocks'

// ============================================================================
// Componente Tooltip "?"
// ============================================================================

function HelpTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-block ml-1.5 align-middle">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        className="w-5 h-5 rounded-full bg-slate-700 hover:bg-violet-600/40 text-slate-400 hover:text-violet-300 inline-flex items-center justify-center transition-colors focus:outline-none focus:ring-1 focus:ring-violet-500"
        aria-label="Ajuda"
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="absolute z-50 left-1/2 -translate-x-1/2 bottom-full mb-2 w-72 bg-slate-800 border border-slate-600 rounded-lg p-3 shadow-xl">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs text-slate-300 leading-relaxed">{text}</p>
            <button onClick={() => setOpen(false)} className="flex-shrink-0 text-slate-500 hover:text-slate-300">
              <X className="w-3 h-3" />
            </button>
          </div>
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[6px] border-t-slate-600" />
        </div>
      )}
    </span>
  )
}

// ============================================================================
// Componente Principal
// ============================================================================

export function QuestionnairePage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { user } = useAuthStore()

  const [currentBlock, setCurrentBlock] = useState(0)
  const [responses, setResponses] = useState<Record<string, any>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)

  const block = BLOCKS[currentBlock]

  const isQuestionVisible = (q: QuestionDef): boolean => {
    if (!q.conditionalOn) return true
    return responses[q.conditionalOn.question] === q.conditionalOn.value
  }

  const isQuestionLinked = (q: QuestionDef): boolean => {
    if (!q.linkedTo) return false
    return responses[q.linkedTo.question] === q.linkedTo.value
  }

  const visibleQuestions = block.questions.filter(isQuestionVisible)

  const totalAnswered = Object.keys(responses).filter(k => {
    const val = responses[k]
    return val && (typeof val === 'string' ? val.length > 0 : Array.isArray(val) && val.length > 0)
  }).length

  const handleTextChange = (qId: string, value: string) => {
    setResponses(prev => ({ ...prev, [qId]: value }))
  }

  const handleSingleSelect = (qId: string, value: string) => {
    setResponses(prev => ({ ...prev, [qId]: value }))
  }

  const handleMultiSelect = (qId: string, value: string) => {
    setResponses(prev => {
      const current = (prev[qId] as string[]) || []
      if (value === NA_VALUE) {
        return { ...prev, [qId]: current.includes(NA_VALUE) ? [] : [NA_VALUE] }
      }
      const filtered = current.filter(v => v !== NA_VALUE)
      if (filtered.includes(value)) {
        return { ...prev, [qId]: filtered.filter(v => v !== value) }
      }
      return { ...prev, [qId]: [...filtered, value] }
    })
  }

  const handleSubmit = async () => {
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await apiClient.post('/questionnaires/', {
        project_id: projectId,
        gp_email: user?.email || '',
        responses,
      })
      setResult(res.data)
      setSubmitted(true)
    } catch (err: any) {
      setError(err?.message || 'Erro ao submeter questionário')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted && result) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="bg-dark-100 border border-slate-700 rounded-xl p-8 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-white mb-2">Questionário Enviado!</h2>
          <p className="text-slate-400">Seu questionário foi submetido para análise. Você receberá um e-mail com o resultado.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList className="w-6 h-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">Questionário Técnico</h1>
            <p className="text-slate-400 text-sm">49 perguntas em 8 blocos — responda com calma</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm text-slate-400">{totalAnswered} de 49 respondidas</p>
          <div className="w-32 h-1.5 bg-slate-700 rounded-full mt-1">
            <div className="h-full bg-violet-600 rounded-full transition-all" style={{ width: `${Math.min(100, (totalAnswered / 49) * 100)}%` }} />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {BLOCKS.map((b, i) => {
          const isA2Disabled = b.id === 'A.2' && responses['3'] !== 'Sim'
          return (
            <button key={b.id} onClick={() => !isA2Disabled && setCurrentBlock(i)} disabled={isA2Disabled}
              className={`flex-shrink-0 px-3 py-1.5 text-xs rounded-lg transition-colors ${isA2Disabled ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed' : i === currentBlock ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300'}`}
              title={isA2Disabled ? 'Habilitado quando Q3 = "Sim"' : b.title}
            >{b.id}</button>
          )
        })}
      </div>

      {/* Bloco atual */}
      <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-1">{block.title}</h2>
        <p className="text-slate-400 text-sm mb-6">{block.description}</p>

        {block.id === 'A.2' && responses['3'] !== 'Sim' && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-center gap-2 mb-6">
            <Info className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <p className="text-amber-300 text-sm">Este bloco só é habilitado quando Q3 = "Sim" (projeto existente).</p>
          </div>
        )}

        {error && (
          <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-7">
          {visibleQuestions.map(q => {
            const linked = isQuestionLinked(q)
            return (
              <div key={q.id} className={linked ? 'opacity-50' : ''}>
                <label className="block text-sm text-slate-200 font-medium mb-2">
                  <span className="text-violet-400 mr-1 font-bold">Q{q.id}.</span>
                  {q.label}
                  <HelpTooltip text={q.help} />
                </label>

                {linked && (
                  <div className="flex items-center gap-1.5 mb-2 px-3 py-1.5 bg-slate-800/60 border border-slate-700/50 rounded-lg">
                    <Info className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
                    <p className="text-xs text-slate-500 italic">{q.linkedTo?.message || 'Resposta já providenciada em perguntas anteriores.'}</p>
                  </div>
                )}

                {q.type === 'text' && !linked && (
                  <input type="text" value={(responses[q.id] as string) || ''} onChange={e => handleTextChange(q.id, e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                    placeholder={q.placeholder || ''} />
                )}

                {q.type === 'single' && !linked && q.options && (
                  <div className="flex flex-wrap gap-2">
                    {q.options.map(opt => {
                      const isNA = opt === NA_VALUE
                      return (
                        <button key={opt} type="button" onClick={() => handleSingleSelect(q.id, opt)}
                          className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${responses[q.id] === opt ? (isNA ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-violet-600/30 border-violet-500 text-violet-300') : 'bg-dark-200 border-slate-700 text-slate-400 hover:border-slate-500'} ${isNA ? 'italic' : ''}`}
                        >{opt}</button>
                      )
                    })}
                  </div>
                )}

                {q.type === 'multi' && !linked && q.options && (
                  <div className="flex flex-wrap gap-2">
                    {q.options.map(opt => {
                      const currentVals = (responses[q.id] as string[]) || []
                      const selected = currentVals.includes(opt)
                      const isNA = opt === NA_VALUE
                      return (
                        <button key={opt} type="button" onClick={() => handleMultiSelect(q.id, opt)}
                          className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${selected ? (isNA ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-violet-600/30 border-violet-500 text-violet-300') : 'bg-dark-200 border-slate-700 text-slate-400 hover:border-slate-500'} ${isNA ? 'italic' : ''}`}
                        >{selected && !isNA && <CheckCircle2 className="w-3 h-3 inline mr-1" />}{opt}</button>
                      )
                    })}
                    {q.allowNA && !q.options.includes(NA_VALUE) && (
                      <button type="button" onClick={() => handleMultiSelect(q.id, NA_VALUE)}
                        className={`px-3 py-1.5 text-sm rounded-lg border transition-colors italic ${((responses[q.id] as string[]) || []).includes(NA_VALUE) ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-dark-200 border-slate-700 text-slate-400 hover:border-slate-500'}`}
                      >Não se aplica</button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Navegação */}
      <div className="flex items-center justify-between">
        <button onClick={() => setCurrentBlock(i => Math.max(0, i - 1))} disabled={currentBlock === 0}
          className="flex items-center gap-1 px-4 py-2 text-sm text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
          <ChevronLeft className="w-4 h-4" /> Anterior
        </button>
        <span className="text-sm text-slate-500">Bloco {currentBlock + 1} de {BLOCKS.length}</span>
        {currentBlock < BLOCKS.length - 1 ? (
          <button onClick={() => setCurrentBlock(i => Math.min(BLOCKS.length - 1, i + 1))}
            className="flex items-center gap-1 px-4 py-2 text-sm bg-violet-600 hover:bg-violet-500 text-white rounded-lg transition-colors">
            Próximo <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <button onClick={handleSubmit} disabled={submitting}
            className="flex items-center gap-2 px-5 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors">
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" />Enviando...</> : <><Send className="w-4 h-4" />Enviar para Análise</>}
          </button>
        )}
      </div>
    </div>
  )
}

export default QuestionnairePage
