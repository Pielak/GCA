import { useMemo, useState, useEffect } from 'react'
import { Loader2, CheckCircle2, Save, ShieldCheck, Send, FileText } from 'lucide-react'
import {
  usePipelineQuestions,
  usePersonaSubmit,
  type PipelineQuestion,
} from '@/hooks/usePipelineQuestions'

interface Props {
  projectId: string
}

const PERSONA_LABELS: Record<string, string> = {
  AUD: 'Auditor', GP: 'GP', ARQ: 'Arquitetura', DBA: 'Banco de Dados',
  DEV: 'Desenvolvimento', QA: 'QA', UX: 'UX', UI: 'UI',
  SEG: 'Segurança', CONF: 'Conformidade', LGPD: 'LGPD/Dados', NEG: 'Negócio',
}

function groupByPersona(questions: PipelineQuestion[]): Record<string, PipelineQuestion[]> {
  const out: Record<string, PipelineQuestion[]> = {}
  for (const q of questions) {
    const key = (q.source || '').toUpperCase()
    if (!out[key]) out[key] = []
    out[key].push(q)
  }
  return out
}

export function PersonaFollowUpTabs({ projectId }: Props) {
  const { pendingQuestions, isLoading, refetch } = usePipelineQuestions(projectId)
  const { runPersona, isPending } = usePersonaSubmit(projectId)

  const grouped = useMemo(() => groupByPersona(pendingQuestions), [pendingQuestions])
  const personas = useMemo(() => Object.keys(grouped).sort(), [grouped])

  const [activePersona, setActivePersona] = useState<string | null>(null)
  // Drafts isolados por pergunta (não-persistidos até clicar em Salvar)
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!activePersona && personas.length > 0) {
      setActivePersona(personas[0])
    } else if (activePersona && !personas.includes(activePersona) && personas.length > 0) {
      setActivePersona(personas[0])
    }
  }, [personas, activePersona])

  // Inicializa drafts com answer_text já salvos no backend
  useEffect(() => {
    setDrafts(prev => {
      const next = { ...prev }
      for (const q of pendingQuestions) {
        if (next[q.id] === undefined && q.answer_text) {
          next[q.id] = q.answer_text
        }
      }
      return next
    })
  }, [pendingQuestions])

  if (isLoading) {
    return (
      <div className="p-4 flex items-center gap-2 text-slate-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando perguntas...
      </div>
    )
  }

  if (personas.length === 0) {
    return (
      <div className="p-4 text-sm text-slate-500 flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
        Nenhuma pergunta pendente das personas no momento.
      </div>
    )
  }

  const currentQuestions = activePersona ? grouped[activePersona] || [] : []
  const collectAnswers = (): Record<string, string> => {
    const out: Record<string, string> = {}
    for (const q of currentQuestions) {
      const v = drafts[q.id]
      if (v !== undefined) out[q.id] = v
    }
    return out
  }

  const totalCurrent = currentQuestions.length
  const answeredCurrent = currentQuestions.filter(
    q => (drafts[q.id] ?? q.answer_text ?? '').trim().length > 0,
  ).length
  const missingCount = totalCurrent - answeredCurrent

  const handleAction = async (mode: 'save' | 'validate' | 'submit') => {
    if (!activePersona) return
    if (mode === 'submit' && answeredCurrent === 0) {
      // Nada a submeter — backend também bloqueia, mas evita request inútil.
      return
    }
    await runPersona({
      personaId: activePersona,
      mode,
      answers: collectAnswers(),
    })
    await refetch()
  }

  return (
    <div className="border border-slate-800 rounded-lg bg-slate-900/40">
      {/* Sub-abas (uma por persona com pendentes) */}
      <div className="flex flex-wrap gap-1 border-b border-slate-800 px-2 pt-2">
        {personas.map(p => {
          const count = grouped[p].length
          const isActive = p === activePersona
          return (
            <button
              key={p}
              onClick={() => setActivePersona(p)}
              className={`px-3 py-1.5 text-xs rounded-t-md flex items-center gap-1.5 transition-colors ${
                isActive
                  ? 'bg-slate-800 text-violet-300 border border-b-0 border-slate-700'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
              }`}
            >
              <span className="font-semibold">{PERSONA_LABELS[p] || p}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                isActive ? 'bg-violet-500/20 text-violet-200' : 'bg-slate-700/60 text-slate-300'
              }`}>{count}</span>
            </button>
          )
        })}
      </div>

      {/* Cabeçalho com contador */}
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <div className="text-sm text-slate-300">
          <span className="font-semibold text-slate-100">
            {PERSONA_LABELS[activePersona || ''] || activePersona}
          </span>
          <span className="text-slate-500 ml-2">
            {answeredCurrent}/{totalCurrent} respondida{totalCurrent !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleAction('save')}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-50"
          >
            {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Salvar
          </button>
          <button
            onClick={() => handleAction('validate')}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-amber-600/20 hover:bg-amber-600/30 text-amber-200 border border-amber-700/40 disabled:opacity-50"
          >
            {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
            Validar Escopo
          </button>
          <button
            onClick={() => handleAction('submit')}
            disabled={isPending || answeredCurrent === 0}
            title={
              answeredCurrent === 0
                ? 'Preencha ao menos 1 resposta'
                : missingCount > 0
                  ? `Submete ${answeredCurrent} respondida(s); ${missingCount} em branco continuam aqui`
                  : `Submete todas as ${answeredCurrent} respostas e fecha esta sub-aba`
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Submeter
          </button>
        </div>
      </div>

      {/* Lista de perguntas da persona ativa */}
      <div className="p-4 space-y-3 max-h-[60vh] overflow-y-auto">
        {currentQuestions.map((q, idx) => (
          <div key={q.id} className="rounded-md border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex items-start gap-2 mb-2">
              <span className="text-[10px] font-semibold text-slate-500 mt-0.5 w-6">#{idx + 1}</span>
              <div className="flex-1">
                <p className="text-sm text-slate-200 leading-relaxed">{q.question_text}</p>
                {q.rationale && (
                  <p className="text-[11px] text-slate-500 italic mt-1">{q.rationale}</p>
                )}
                {q.document_name && (
                  <div className="flex items-center gap-1 text-[10px] text-slate-600 mt-1">
                    <FileText className="w-3 h-3" />
                    Origem: {q.document_name}
                  </div>
                )}
              </div>
            </div>
            <textarea
              value={drafts[q.id] ?? q.answer_text ?? ''}
              onChange={e => setDrafts(prev => ({ ...prev, [q.id]: e.target.value }))}
              placeholder="Sua resposta..."
              rows={3}
              className="w-full px-3 py-2 text-sm rounded-md bg-slate-950 border border-slate-700 text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-violet-500/60 resize-y"
            />
          </div>
        ))}
      </div>
    </div>
  )
}
