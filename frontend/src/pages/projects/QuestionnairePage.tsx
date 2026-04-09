import { useState, useMemo, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  ClipboardList, ChevronLeft, ChevronRight, Send, Loader2, CheckCircle2,
  Info, HelpCircle, X, Download, AlertTriangle, AlertCircle, RefreshCw,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import {
  BLOCKS, NA_VALUE, VALIDATION_RULES,
  type QuestionDef, type ValidationRule, type ValidationSeverity,
} from '@/data/questionnaireBlocks'
import { AnalysisOverlay } from '@/components/questionnaire/AnalysisOverlay'

// ============================================================================
// Types
// ============================================================================

type AnalysisStatus = 'pronto_para_ingestao' | 'pendente_ajustes' | 'recusado'

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

  // Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [showResult, setShowResult] = useState(false)

  const block = BLOCKS[currentBlock]
  const totalQuestions = 54 // Q1-Q49 + Q50-Q54 (excluindo Q52 e Q53)

  // ─── Visibility helpers ────────────────────────────────────────────

  const isQuestionVisible = (q: QuestionDef): boolean => {
    if (!q.conditionalOn) return true
    return responses[q.conditionalOn.question] === q.conditionalOn.value
  }

  const isQuestionLinked = (q: QuestionDef): boolean => {
    if (!q.linkedTo) return false
    return responses[q.linkedTo.question] === q.linkedTo.value
  }

  const visibleQuestions = block.questions.filter(isQuestionVisible)

  // ─── All visible questions across blocks (for percentage) ──────────

  const allVisibleQuestions = useMemo(() => {
    return BLOCKS.flatMap(b =>
      b.questions.filter(q => {
        if (q.type === 'computed' || q.id === '52' || q.id === '53') return false
        if (!q.conditionalOn) return true
        return responses[q.conditionalOn.question] === q.conditionalOn.value
      })
    )
  }, [responses])

  const answeredCount = useMemo(() => {
    return allVisibleQuestions.filter(q => {
      if (q.linkedTo && responses[q.linkedTo.question] === q.linkedTo.value) return false
      const val = responses[q.id]
      if (!val) return false
      if (typeof val === 'string') return val.trim().length > 0
      if (Array.isArray(val)) return val.length > 0
      return false
    }).length
  }, [allVisibleQuestions, responses])

  const percentage = useMemo(() => {
    if (allVisibleQuestions.length === 0) return 0
    return Math.round((answeredCount / allVisibleQuestions.length) * 100)
  }, [answeredCount, allVisibleQuestions])

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
      status = 'pronto_para_ingestao'
    }

    // Auto-gravar motivo de recusa em Q51
    if (status === 'recusado') {
      const motivo = percentage < 80
        ? `[Auto] Recusado: percentual respondido ${percentage}% (minimo 80%).`
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
      questionario_versao: '1.0',
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
    a.download = `questionario-gca-${responses['2'] || 'projeto'}.json`
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
      setError(err?.message || 'Erro ao submeter questionario')
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

  if (submitted && result) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-8 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-white mb-2">Questionario Enviado!</h2>
          <p className="text-slate-400 mb-4">Seu questionario foi submetido para analise.</p>
          <p className="text-slate-300 text-sm">
            Em ate 48 horas voce recebera as informacoes referentes ao seu projeto, incluindo convite de acesso ao GCA e lista de instrucoes para parametrizar seu projeto.
          </p>
        </div>
      </div>
    )
  }

  // ─── Main render ───────────────────────────────────────────────────

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <AnalysisOverlay isVisible={isAnalyzing} onComplete={handleAnalysisComplete} />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList className="w-6 h-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">Questionario Tecnico</h1>
            <p className="text-slate-400 text-sm">54 perguntas em 9 blocos</p>
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
        {BLOCKS.map((b, i) => {
          const isA2Disabled = b.id === 'A.2' && responses['3'] !== 'Sim'
          return (
            <button key={b.id} onClick={() => { !isA2Disabled && setCurrentBlock(i); setShowResult(false) }} disabled={isA2Disabled}
              className={`flex-shrink-0 px-3 py-1.5 text-xs rounded-lg transition-colors ${isA2Disabled ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed' : i === currentBlock && !showResult ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300'}`}
              title={isA2Disabled ? 'Habilitado quando Q3 = "Sim"' : b.title}
            >{b.id}</button>
          )
        })}
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
            analysisResult.status === 'pronto_para_ingestao'
              ? 'bg-emerald-950/20 border-emerald-800/30'
              : analysisResult.status === 'pendente_ajustes'
                ? 'bg-amber-950/20 border-amber-800/30'
                : 'bg-red-950/20 border-red-800/30'
          }`}>
            <div className="flex items-center gap-3 mb-3">
              {analysisResult.status === 'pronto_para_ingestao' ? (
                <CheckCircle2 className="w-6 h-6 text-emerald-400" />
              ) : analysisResult.status === 'pendente_ajustes' ? (
                <AlertTriangle className="w-6 h-6 text-amber-400" />
              ) : (
                <AlertCircle className="w-6 h-6 text-red-400" />
              )}
              <h3 className={`text-lg font-semibold ${
                analysisResult.status === 'pronto_para_ingestao' ? 'text-emerald-300'
                : analysisResult.status === 'pendente_ajustes' ? 'text-amber-300'
                : 'text-red-300'
              }`}>
                {analysisResult.status === 'pronto_para_ingestao' && 'Pronto para Ingestao'}
                {analysisResult.status === 'pendente_ajustes' && 'Pendente de Ajustes'}
                {analysisResult.status === 'recusado' && 'Recusado'}
              </h3>
            </div>

            {analysisResult.status === 'pronto_para_ingestao' && (
              <p className="text-slate-300 text-sm">
                Seu questionario esta completo e consistente. Em ate 48 horas voce recebera as informacoes referentes ao seu projeto.
              </p>
            )}

            {analysisResult.status === 'pendente_ajustes' && (
              <p className="text-slate-300 text-sm">
                O questionario contem gaps ou ressalvas que devem ser revisados antes do envio.
              </p>
            )}

            {analysisResult.status === 'recusado' && (
              <p className="text-slate-300 text-sm">
                {percentage < 80
                  ? `Percentual respondido inferior a 80% (atual: ${percentage}%). Complete o questionario antes de solicitar a ingestao.`
                  : 'Existem bloqueantes que impedem a ingestao. Corrija os itens abaixo.'}
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
                  <p className="text-amber-400 text-xs font-semibold mb-1.5">Gaps (pendencias obrigatorias)</p>
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
            {analysisResult.status === 'pronto_para_ingestao' && (
              <button onClick={handleSubmit} disabled={submitting}
                className="flex items-center gap-2 px-5 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white rounded-lg transition-colors ml-auto">
                {submitting ? <><Loader2 className="w-4 h-4 animate-spin" />Enviando...</> : <><Send className="w-4 h-4" />Enviar para analise do GCA</>}
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

            {block.id === 'A.2' && responses['3'] !== 'Sim' && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-center gap-2 mb-6">
                <Info className="w-4 h-4 text-amber-400 flex-shrink-0" />
                <p className="text-amber-300 text-sm">Este bloco so e habilitado quando Q3 = "Sim" (projeto existente).</p>
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
                const isComputed = q.type === 'computed'

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
                        <p className="text-xs text-slate-500 italic">{q.linkedTo?.message || 'Resposta ja providenciada em perguntas anteriores.'}</p>
                      </div>
                    )}

                    {isComputed && (
                      <div className="flex items-center gap-3 px-4 py-3 bg-slate-800/60 border border-slate-700/50 rounded-lg">
                        <div className="flex-1">
                          <div className="w-full h-2 bg-slate-700 rounded-full">
                            <div className={`h-full rounded-full transition-all ${percentage >= 80 ? 'bg-emerald-500' : percentage >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                              style={{ width: `${percentage}%` }} />
                          </div>
                        </div>
                        <span className={`text-sm font-semibold ${percentage >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>{percentage}%</span>
                      </div>
                    )}

                    {q.type === 'text' && !linked && (
                      <input type="text" value={(responses[q.id] as string) || ''} onChange={e => handleTextChange(q.id, e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                        placeholder={q.placeholder || ''} />
                    )}

                    {q.type === 'textarea' && !linked && (
                      <textarea value={(responses[q.id] as string) || ''} onChange={e => handleTextChange(q.id, e.target.value)}
                        rows={4}
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors resize-none"
                        placeholder={q.placeholder || ''} />
                    )}

                    {q.type === 'single' && !linked && q.options && (
                      <div className="flex flex-wrap gap-2">
                        {q.options.map(opt => {
                          const isNA = opt === NA_VALUE
                          return (
                            <button key={opt} type="button" onClick={() => handleSingleSelect(q.id, opt)}
                              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${responses[q.id] === opt ? (isNA ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-violet-600/30 border-violet-500 text-violet-300') : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'} ${isNA ? 'italic' : ''}`}
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
                              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${selected ? (isNA ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-violet-600/30 border-violet-500 text-violet-300') : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'} ${isNA ? 'italic' : ''}`}
                            >{selected && !isNA && <CheckCircle2 className="w-3 h-3 inline mr-1" />}{opt}</button>
                          )
                        })}
                        {q.allowNA && !q.options.includes(NA_VALUE) && (
                          <button type="button" onClick={() => handleMultiSelect(q.id, NA_VALUE)}
                            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors italic ${((responses[q.id] as string[]) || []).includes(NA_VALUE) ? 'bg-slate-600/40 border-slate-500 text-slate-300' : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'}`}
                          >Nao se aplica</button>
                        )}
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
            ) : (
              <button onClick={handleAnalyze}
                className="flex items-center gap-2 px-5 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 text-white rounded-lg transition-colors">
                <ClipboardList className="w-4 h-4" /> Analisar Consistencia
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default QuestionnairePage
