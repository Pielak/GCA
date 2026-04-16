import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  ClipboardList, ChevronLeft, ChevronRight, Send, Loader2, CheckCircle2,
  Info, HelpCircle, X, Download, AlertTriangle, AlertCircle, RefreshCw,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import {
  BLOCKS, NA_VALUE, VALIDATION_RULES, ANALYSIS_RESULT_FIELDS,
  type QuestionDef, type ValidationRule, type ValidationSeverity,
} from '@/data/questionnaireBlocks'
import { AnalysisOverlay } from '@/components/questionnaire/AnalysisOverlay'

// ============================================================================
// Types
// ============================================================================

type AnalysisStatus = 'pronto_para_ingestão' | 'pendente_ajustes' | 'recusado'

interface AnalysisResult {
  status: AnalysisStatus
  percentage: number
  blockers: string[]
  gaps: string[]
  caveats: string[]
  failedRules: { rule: ValidationRule; message: string }[]
}

// ============================================================================
// Tooltip
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
// Main Component
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
  const [loadingExisting, setLoadingExisting] = useState(true)

  // Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [showResult, setShowResult] = useState(false)

  // Carregar questionário existente (se já foi preenchido via externo)
  useEffect(() => {
    const loadExisting = async () => {
      if (!projectId) { setLoadingExisting(false); return }
      try {
        const res = await apiClient.get(`/projects/${projectId}/questionnaire`)
        if (res.data.questionnaire) {
          const q = res.data.questionnaire
          setResponses(q.responses || {})
          if (q.approved || q.status === 'ok') {
            setSubmitted(true)
            setResult({
              adherenceScore: q.adherence_score,
              status: q.status,
              validations: q.validations,
              observations: q.observations,
            })
          }
        }
      } catch { /* sem questionário existente */ }
      setLoadingExisting(false)
    }
    loadExisting()
  }, [projectId])

  const block = BLOCKS[currentBlock]

  // ─── Visibility helpers ────────────────────────────────────────────

  const isQuestionDisabled = (q: QuestionDef): boolean => {
    if (q.conditionalOn) return responses[q.conditionalOn.question] !== q.conditionalOn.value
    return false
  }

  const isQuestionLinked = (q: QuestionDef): boolean => {
    if (!q.linkedTo) return false
    return responses[q.linkedTo.question] === q.linkedTo.value
  }

  // ─── All visible questions across blocks (for percentage) ──────────

  const allApplicableQuestions = useMemo(() => {
    return BLOCKS.flatMap(b =>
      b.questions.filter(q => {
        if (q.type === 'computed' || q.id === '52' || q.id === '53') return false
        // Perguntas condicionais desabilitadas não contam para o percentual
        if (q.conditionalOn && responses[q.conditionalOn.question] !== q.conditionalOn.value) return false
        return true
      })
    )
  }, [responses])

  const answeredCount = useMemo(() => {
    return allApplicableQuestions.filter(q => {
      if (q.linkedTo && responses[q.linkedTo.question] === q.linkedTo.value) return false
      const val = responses[q.id]
      if (!val) return false
      if (typeof val === 'string') return val.trim().length > 0
      if (Array.isArray(val)) return val.length > 0
      return false
    }).length
  }, [allApplicableQuestions, responses])

  const percentage = useMemo(() => {
    if (allApplicableQuestions.length === 0) return 0
    return Math.round((answeredCount / allApplicableQuestions.length) * 100)
  }, [answeredCount, allApplicableQuestions])

  // ─── Handlers ──────────────────────────────────────────────────────

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

  // ─── Analysis (validation) ─────────────────────────────────────────

  const runAnalysis = useCallback((): AnalysisResult => {
    const failedRules: AnalysisResult['failedRules'] = []
    const blockers: string[] = []
    const gaps: string[] = []
    const caveats: string[] = []

    for (const rule of VALIDATION_RULES) {
      const failed = rule.check(responses, percentage)
      if (failed) {
        failedRules.push({ rule, message: rule.message })
        if (rule.severity === 'blocker') blockers.push(rule.id)
        else if (rule.severity === 'gap') gaps.push(rule.id)
        else caveats.push(rule.id)
      }
    }

    let status: AnalysisStatus
    if (blockers.length > 0 || percentage < 80) {
      status = 'recusado'
    } else if (gaps.length > 0) {
      status = 'pendente_ajustes'
    } else {
      status = 'pronto_para_ingestão'
    }

    // Auto-gravar motivo de recusa em Q51
    if (status === 'recusado') {
      const motivo = percentage < 80
        ? `[Auto] Recusado: percentual respondido ${percentage}% (mínimo 80%).`
        : `[Auto] Recusado: ${blockers.length} bloqueante(s) ativo(s).`
      setResponses(prev => ({
        ...prev,
        '51': prev['51'] ? `${prev['51']}\n${motivo}` : motivo,
      }))
    }

    return { status, percentage, blockers, gaps, caveats, failedRules }
  }, [responses, percentage])

  const handleAnalyze = () => {
    setIsAnalyzing(true)
    setShowResult(false)
    setAnalysisResult(null)
  }

  const handleAnalysisComplete = useCallback(() => {
    const result = runAnalysis()
    setAnalysisResult(result)
    setIsAnalyzing(false)
    setShowResult(true)
  }, [runAnalysis])

  // ─── JSON Export ───────────────────────────────────────────────────

  const handleExportJSON = useCallback(() => {
    const payload = {
      questionário_versao: '1.0',
      project_name: responses['1'] || '',
      project_slug: responses['2'] || '',
      data_preenchimento: new Date().toISOString(),
      percentual_respondido: percentage,
      status: analysisResult?.status || 'pendente_ajustes',
      gaps: analysisResult?.gaps || [],
      ressalvas: analysisResult?.caveats || [],
      areas_validadoras: responses['54'] || [],
      restricoes: responses['50'] || '',
      observacoes: responses['51'] || '',
      respostas: responses,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `questionário-gca-${responses['2'] || 'projeto'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [responses, percentage, analysisResult])

  // ─── Submit ────────────────────────────────────────────────────────

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
      const msg = typeof err === 'string' ? err
        : typeof err?.message === 'string' ? err.message
        : typeof err?.detail === 'string' ? err.detail
        : JSON.stringify(err) || 'Erro ao submeter questionário'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  // ─── Navigation to problem question ────────────────────────────────

  const navigateToQuestion = (qIds: number[]) => {
    const targetId = String(qIds[0])
    for (let i = 0; i < BLOCKS.length; i++) {
      if (BLOCKS[i].questions.some(q => q.id === targetId)) {
        setCurrentBlock(i)
        setShowResult(false)
        break
      }
    }
  }

  // ─── Submitted screen ─────────────────────────────────────────────

  // Questionário enviado: NÃO bloqueia a tela — mostra banner + perguntas read-only
  const isReadOnly = submitted && !!result

  // ─── Main render ───────────────────────────────────────────────────

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <AnalysisOverlay isVisible={isAnalyzing} onComplete={handleAnalysisComplete} />

      {/* Banner de status enviado */}
      {isReadOnly && (
        <div className="bg-emerald-950/30 border border-emerald-700/30 rounded-xl p-4 flex items-center gap-3">
          <CheckCircle2 className="w-6 h-6 text-emerald-400 flex-shrink-0" />
          <div>
            <p className="text-emerald-300 font-semibold text-sm">Questionario Enviado</p>
            <p className="text-slate-400 text-xs">Submetido para analise. As respostas abaixo sao exibidas como referencia para a equipe do projeto.</p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList className="w-6 h-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">Questionário Técnico</h1>
            <p className="text-slate-400 text-sm">49 perguntas em 8 blocos</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm text-slate-400">{answeredCount} respondidas — <span className={percentage >= 80 ? 'text-emerald-400' : 'text-amber-400'}>{percentage}%</span></p>
          <div className="w-32 h-1.5 bg-slate-700 rounded-full mt-1">
            <div
              className={`h-full rounded-full transition-all ${percentage >= 80 ? 'bg-emerald-500' : percentage >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
              style={{ width: `${Math.min(100, percentage)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {BLOCKS.map((b, i) => (
          <button key={b.id} onClick={() => { setCurrentBlock(i); setShowResult(false) }}
            className={`flex-shrink-0 px-3 py-1.5 text-xs rounded-lg transition-colors ${i === currentBlock && !showResult ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300'}`}
            title={b.title}
          >{b.id}</button>
        ))}
        {analysisResult && (
          <button
            onClick={() => setShowResult(true)}
            className={`flex-shrink-0 px-3 py-1.5 text-xs rounded-lg transition-colors ${showResult ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
          >Resultado</button>
        )}
      </div>

      {/* ─── Result Zone ──────────────────────────────────────────── */}
      {showResult && analysisResult && (
        <div className="space-y-4">
          {/* Status card */}
          <div className={`border rounded-xl p-6 ${
            analysisResult.status === 'pronto_para_ingestão'
              ? 'bg-emerald-950/20 border-emerald-800/30'
              : analysisResult.status === 'pendente_ajustes'
                ? 'bg-amber-950/20 border-amber-800/30'
                : 'bg-red-950/20 border-red-800/30'
          }`}>
            <div className="flex items-center gap-3 mb-3">
              {analysisResult.status === 'pronto_para_ingestão' ? (
                <CheckCircle2 className="w-6 h-6 text-emerald-400" />
              ) : analysisResult.status === 'pendente_ajustes' ? (
                <AlertTriangle className="w-6 h-6 text-amber-400" />
              ) : (
                <AlertCircle className="w-6 h-6 text-red-400" />
              )}
              <h3 className={`text-lg font-semibold ${
                analysisResult.status === 'pronto_para_ingestão' ? 'text-emerald-300'
                : analysisResult.status === 'pendente_ajustes' ? 'text-amber-300'
                : 'text-red-300'
              }`}>
                {analysisResult.status === 'pronto_para_ingestão' && 'Pronto para Ingestão'}
                {analysisResult.status === 'pendente_ajustes' && 'Pendente de Ajustes'}
                {analysisResult.status === 'recusado' && 'Recusado'}
              </h3>
            </div>

            {analysisResult.status === 'pronto_para_ingestão' && (
              <p className="text-slate-300 text-sm">
                Seu questionário está completo e consistente. Em até 48 horas você receberá as informações referentes ao seu projeto.
              </p>
            )}

            {analysisResult.status === 'pendente_ajustes' && (
              <p className="text-slate-300 text-sm">
                O questionário contem gaps ou ressalvas que devem ser revisados antes do envio.
              </p>
            )}

            {analysisResult.status === 'recusado' && (
              <p className="text-slate-300 text-sm">
                {percentage < 80
                  ? `Percentual respondido inferior a 80% (atual: ${percentage}%). Complete o questionário antes de solicitar a ingestão.`
                  : 'Existem bloqueantes que impedem a ingestão. Corrija os itens abaixo.'}
              </p>
            )}
          </div>

          {/* Failed rules detail */}
          {analysisResult.failedRules.length > 0 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
              <h4 className="text-slate-200 text-sm font-semibold">Resultados da Validacao</h4>

              {/* Blockers */}
              {analysisResult.failedRules.filter(r => r.rule.severity === 'blocker').length > 0 && (
                <div>
                  <p className="text-red-400 text-xs font-semibold mb-1.5">Bloqueantes</p>
                  {analysisResult.failedRules.filter(r => r.rule.severity === 'blocker').map(({ rule }) => (
                    <button key={rule.id} onClick={() => navigateToQuestion(rule.affectedQuestions)}
                      className="w-full text-left flex items-start gap-2 py-1.5 px-2 rounded hover:bg-slate-800/50 transition-colors">
                      <AlertCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0 mt-0.5" />
                      <span className="text-xs text-slate-300">{rule.id}: {rule.message}</span>
                    </button>
                  ))}
                </div>
              )}

              {/* Gaps */}
              {analysisResult.failedRules.filter(r => r.rule.severity === 'gap').length > 0 && (
                <div>
                  <p className="text-amber-400 text-xs font-semibold mb-1.5">Gaps (pendencias obrigatórias)</p>
                  {analysisResult.failedRules.filter(r => r.rule.severity === 'gap').map(({ rule }) => (
                    <button key={rule.id} onClick={() => navigateToQuestion(rule.affectedQuestions)}
                      className="w-full text-left flex items-start gap-2 py-1.5 px-2 rounded hover:bg-slate-800/50 transition-colors">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
                      <span className="text-xs text-slate-300">{rule.id}: {rule.message}</span>
                    </button>
                  ))}
                </div>
              )}

              {/* Caveats */}
              {analysisResult.failedRules.filter(r => r.rule.severity === 'caveat').length > 0 && (
                <div>
                  <p className="text-blue-400 text-xs font-semibold mb-1.5">Ressalvas (recomendacoes)</p>
                  {analysisResult.failedRules.filter(r => r.rule.severity === 'caveat').map(({ rule }) => (
                    <button key={rule.id} onClick={() => navigateToQuestion(rule.affectedQuestions)}
                      className="w-full text-left flex items-start gap-2 py-1.5 px-2 rounded hover:bg-slate-800/50 transition-colors">
                      <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                      <span className="text-xs text-slate-300">{rule.id}: {rule.message}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Campos A.12 — Resultado da Análise */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <h4 className="text-slate-200 text-sm font-semibold">Dados da Analise (A.12)</h4>

            <div>
              <p className="text-slate-400 text-xs font-medium mb-1">{ANALYSIS_RESULT_FIELDS.percentage.label}</p>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2.5 bg-slate-800 rounded-full">
                  <div className={`h-full rounded-full transition-all ${percentage >= 80 ? 'bg-emerald-500' : percentage >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                    style={{ width: `${percentage}%` }} />
                </div>
                <span className={`text-sm font-bold ${percentage >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>{percentage}%</span>
              </div>
            </div>

            <div>
              <p className="text-slate-400 text-xs font-medium mb-1">{ANALYSIS_RESULT_FIELDS.restrictions.label}</p>
              <p className="text-slate-300 text-sm bg-slate-800/50 rounded-lg px-3 py-2 min-h-[2rem]">
                {analysisResult.failedRules.length > 0
                  ? analysisResult.failedRules.map(r => r.message).join('. ')
                  : 'Nenhuma restrição identificada.'}
              </p>
            </div>

            <div>
              <p className="text-slate-400 text-xs font-medium mb-1">{ANALYSIS_RESULT_FIELDS.observations.label}</p>
              <p className="text-slate-300 text-sm bg-slate-800/50 rounded-lg px-3 py-2 min-h-[2rem]">
                {analysisResult.status === 'pronto_para_ingestão'
                  ? 'Questionário completo e consistente. Pronto para ingestão no pipeline OCG.'
                  : analysisResult.status === 'recusado'
                    ? `Questionário recusado. ${percentage < 80 ? `Percentual respondido (${percentage}%) abaixo do mínimo (80%).` : `${analysisResult.blockers.length} bloqueante(s) ativo(s).`}`
                    : `${analysisResult.gaps.length} gap(s) e ${analysisResult.caveats.length} ressalva(s) identificados. Revisão necessária antes do envio.`}
              </p>
            </div>

            <div>
              <p className="text-slate-400 text-xs font-medium mb-1">{ANALYSIS_RESULT_FIELDS.validators.label}</p>
              <p className="text-slate-500 text-xs italic">Sera preenchido após validação pelos responsáveis do projeto.</p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <button onClick={handleExportJSON}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-slate-800 border border-slate-700 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors">
              <Download className="w-4 h-4" /> Exportar JSON
            </button>
            <button onClick={() => { setShowResult(false); setCurrentBlock(0) }}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-slate-800 border border-slate-700 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors">
              <RefreshCw className="w-4 h-4" /> Corrigir pendencias
            </button>
            {analysisResult.status === 'pronto_para_ingestão' && (
              <button onClick={handleSubmit} disabled={submitting}
                className="flex items-center gap-2 px-5 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white rounded-lg transition-colors ml-auto">
                {submitting ? <><Loader2 className="w-4 h-4 animate-spin" />Enviando...</> : <><Send className="w-4 h-4" />Enviar para análise do GCA</>}
              </button>
            )}
          </div>
        </div>
      )}

      {/* ─── Question Block ───────────────────────────────────────── */}
      {!showResult && (
        <>
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-white mb-1">{block.title}</h2>
            <p className="text-slate-400 text-sm mb-6">{block.description}</p>

            {error && (
              <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            )}

            <div className="space-y-7">
              {block.questions.map(q => {
                const disabled = isQuestionDisabled(q)
                const linked = isQuestionLinked(q)
                const inactive = disabled || linked
                const fieldDisabled = inactive || isReadOnly

                return (
                  <div key={q.id} className={`transition-opacity ${inactive ? 'opacity-40' : ''}`}>
                    <label className="block text-sm text-slate-200 font-medium mb-2">
                      <span className="text-violet-400 mr-1 font-bold">Q{q.id}.</span>
                      {q.label}
                      <HelpTooltip text={q.help} />
                    </label>

                    {disabled && (
                      <div className="flex items-center gap-1.5 mb-2 px-3 py-1.5 bg-slate-800/40 border border-slate-700/30 rounded-lg">
                        <Info className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
                        <p className="text-xs text-slate-600 italic">Não se aplica — {q.conditionalOn ? `requer Q${q.conditionalOn.question} = "${q.conditionalOn.value}"` : ''}</p>
                      </div>
                    )}

                    {linked && !disabled && (
                      <div className="flex items-center gap-1.5 mb-2 px-3 py-1.5 bg-slate-800/40 border border-slate-700/30 rounded-lg">
                        <Info className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
                        <p className="text-xs text-slate-600 italic">{q.linkedTo?.message || 'Respostajá providenciada em perguntas anteriores.'}</p>
                      </div>
                    )}

                    {q.type === 'text' && !inactive && (
                      <input type="text" value={(responses[q.id] as string) || ''} onChange={e => !isReadOnly && handleTextChange(q.id, e.target.value)}
                        readOnly={isReadOnly}
                        className={`w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors ${isReadOnly ? 'cursor-default opacity-80' : ''}`}
                        placeholder={q.placeholder || ''} />
                    )}

                    {q.type === 'textarea' && !inactive && (
                      <textarea value={(responses[q.id] as string) || ''} onChange={e => !isReadOnly && handleTextChange(q.id, e.target.value)}
                        readOnly={isReadOnly}
                        rows={4}
                        className={`w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors resize-none ${isReadOnly ? 'cursor-default opacity-80' : ''}`}
                        placeholder={q.placeholder || ''} />
                    )}

                    {q.type === 'single' && !inactive && q.options && (
                      <div className="flex flex-wrap gap-2">
                        {q.options.map(opt => {
                          const isNA = opt === NA_VALUE
                          return (
                            <button key={opt} type="button" onClick={() => !isReadOnly && handleSingleSelect(q.id, opt)}
                              disabled={isReadOnly}
                              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${responses[q.id] === opt ? (isNA ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-violet-600/30 border-violet-500 text-violet-300') : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'} ${isNA ? 'italic' : ''} ${isReadOnly ? 'cursor-default' : ''}`}
                            >{opt}</button>
                          )
                        })}
                      </div>
                    )}

                    {q.type === 'multi' && !inactive && q.options && (
                      <div className="flex flex-wrap gap-2">
                        {q.options.map(opt => {
                          const currentVals = (responses[q.id] as string[]) || []
                          const selected = currentVals.includes(opt)
                          const isNA = opt === NA_VALUE
                          return (
                            <button key={opt} type="button" onClick={() => !isReadOnly && handleMultiSelect(q.id, opt)}
                              disabled={isReadOnly}
                              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${selected ? (isNA ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-violet-600/30 border-violet-500 text-violet-300') : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'} ${isNA ? 'italic' : ''} ${isReadOnly ? 'cursor-default' : ''}`}
                            >{selected && !isNA && <CheckCircle2 className="w-3 h-3 inline mr-1" />}{opt}</button>
                          )
                        })}
                        {q.allowNA && !q.options.includes(NA_VALUE) && (
                          <button type="button" onClick={() => !isReadOnly && handleMultiSelect(q.id, NA_VALUE)}
                            disabled={isReadOnly}
                            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors italic ${((responses[q.id] as string[]) || []).includes(NA_VALUE) ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'} ${isReadOnly ? 'cursor-default' : ''}`}
                          >Não se aplica</button>
                        )}
                      </div>
                    )}

                    {/* Perguntas desabilitadas mostram botão NA pré-marcado */}
                    {inactive && (q.type === 'single' || q.type === 'multi') && (
                      <div className="flex flex-wrap gap-2">
                        <span className="px-3 py-1.5 text-sm rounded-lg border bg-slate-600/20 border-slate-600/30 text-slate-500 italic">
                          Não se aplica
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between">
            <button onClick={() => setCurrentBlock(i => Math.max(0, i - 1))} disabled={currentBlock === 0}
              className="flex items-center gap-1 px-4 py-2 text-sm text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
              <ChevronLeft className="w-4 h-4" /> Anterior
            </button>
            <span className="text-sm text-slate-500">Bloco {currentBlock + 1} de {BLOCKS.length}</span>
            {currentBlock < BLOCKS.length - 1 ? (
              <button onClick={() => setCurrentBlock(i => Math.min(BLOCKS.length - 1, i + 1))}
                className="flex items-center gap-1 px-4 py-2 text-sm bg-violet-600 hover:bg-violet-500 text-white rounded-lg transition-colors">
                Proximo <ChevronRight className="w-4 h-4" />
              </button>
            ) : !isReadOnly ? (
              <button onClick={handleAnalyze}
                className="flex items-center gap-2 px-5 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 text-white rounded-lg transition-colors">
                <ClipboardList className="w-4 h-4" /> Analisar Consistencia
              </button>
            ) : (
              <span className="text-xs text-slate-500">Fim do questionario</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default QuestionnairePage
