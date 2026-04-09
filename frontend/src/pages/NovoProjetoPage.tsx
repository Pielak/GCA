import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Code2, Mail, User, ChevronLeft, ChevronRight, Send, Save, Loader2,
  CheckCircle2, ClipboardList, AlertTriangle, Clock, Timer, HelpCircle, X, Info
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { BLOCKS, NA_VALUE, type QuestionDef } from '@/data/questionnaireBlocks'

type Step = 'identify' | 'questionnaire' | 'submitted'

export function NovoProjetoPage() {
  const navigate = useNavigate()

  // Step 1: Identification
  const [step, setStep] = useState<Step>('identify')
  const [gpEmail, setGpEmail] = useState('')
  const [gpName, setGpName] = useState('')
  const gpRole = 'gp'
  const [identifyLoading, setIdentifyLoading] = useState(false)
  const [identifyError, setIdentifyError] = useState<string | null>(null)

  // Step 2: Questionnaire
  const [currentBlock, setCurrentBlock] = useState(0)
  const [responses, setResponses] = useState<Record<string, any>>({})
  const [submitting, setSubmitting] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [draftSaved, setDraftSaved] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [showExitWarning, setShowExitWarning] = useState(false)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)

  // Timer: usa expires_at do servidor (definido no request-access, nunca reinicia)
  const [expiresAt, setExpiresAt] = useState(() => {
    // Primeiro: verificar se veio na URL (link do email)
    const params = new URLSearchParams(window.location.search)
    const deadline = params.get('expires')
    if (deadline) return new Date(deadline)
    // Segundo: verificar localStorage (sessão anterior)
    const saved = localStorage.getItem('gca_questionnaire_expires')
    if (saved) return new Date(saved)
    // Fallback temporário — será sobrescrito pelo servidor
    const now = new Date()
    now.setDate(now.getDate() + 5)
    return now
  })
  const [timeLeft, setTimeLeft] = useState('')
  const [expired, setExpired] = useState(false)

  useEffect(() => {
    const tick = () => {
      const now = new Date().getTime()
      const end = expiresAt.getTime()
      const diff = end - now

      if (diff <= 0) {
        setExpired(true)
        setTimeLeft('00d 00h 00m 00s')
        return
      }

      const days = Math.floor(diff / (1000 * 60 * 60 * 24))
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
      const seconds = Math.floor((diff % (1000 * 60)) / 1000)
      setTimeLeft(`${String(days).padStart(2, '0')}d ${String(hours).padStart(2, '0')}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`)
    }

    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [expiresAt])

  // Handle identification
  const handleIdentify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (identifyLoading) return // Proteção contra double-click
    setIdentifyError(null)
    setIdentifyLoading(true)

    try {
      // Send email with unique questionnaire link
      const res = await apiClient.post('/questionnaires/request-access', {
        email: gpEmail,
        full_name: gpName,
        role: gpRole,
      })
      // Usar expires_at do servidor (nunca reinicia o timer)
      if (res.data?.expires_at) {
        const serverExpires = new Date(res.data.expires_at)
        setExpiresAt(serverExpires)
        localStorage.setItem('gca_questionnaire_expires', serverExpires.toISOString())
        localStorage.setItem('gca_questionnaire_email', gpEmail)
      }
      setStep('questionnaire')
    } catch (err: any) {
      // If 404, endpoint not available — proceed anyway
      if (err?.status === 404) {
        setStep('questionnaire')
      } else {
        setIdentifyError(err?.message || 'Erro ao validar e-mail. Tente novamente.')
      }
    } finally {
      setIdentifyLoading(false)
    }
  }

  // Questionnaire helpers
  const isQuestionVisible = (q: QuestionDef): boolean => {
    if (!q.conditionalOn) return true
    return responses[q.conditionalOn.question] === q.conditionalOn.value
  }

  const isQuestionLinked = (q: QuestionDef): boolean => {
    if (!q.linkedTo) return false
    return responses[q.linkedTo.question] === q.linkedTo.value
  }

  const handleTextChange = (qId: string, value: string) => {
    setResponses(prev => ({ ...prev, [qId]: value }))
    setHasUnsavedChanges(true)
    setDraftSaved(false)
  }

  const handleSingleSelect = (qId: string, value: string) => {
    setResponses(prev => ({ ...prev, [qId]: value }))
    setHasUnsavedChanges(true)
    setDraftSaved(false)
  }

  const handleMultiSelect = (qId: string, value: string) => {
    setResponses(prev => {
      const current = (prev[qId] as string[]) || []
      if (value === NA_VALUE) {
        setHasUnsavedChanges(true)
        setDraftSaved(false)
        return { ...prev, [qId]: current.includes(NA_VALUE) ? [] : [NA_VALUE] }
      }
      const filtered = current.filter(v => v !== NA_VALUE)
      if (filtered.includes(value)) {
        setHasUnsavedChanges(true)
        setDraftSaved(false)
        return { ...prev, [qId]: filtered.filter(v => v !== value) }
      }
      setHasUnsavedChanges(true)
      setDraftSaved(false)
      return { ...prev, [qId]: [...filtered, value] }
    })
  }

  const handleExit = () => {
    if (hasUnsavedChanges && !draftSaved) {
      setShowExitWarning(true)
    } else {
      navigate('/login')
    }
  }

  const handleSaveDraft = async () => {
    setSavingDraft(true)
    try {
      await apiClient.post('/questionnaires/draft', {
        gp_email: gpEmail,
        gp_name: gpName,
        responses,
        expires_at: expiresAt.toISOString(),
      })
      setDraftSaved(true)
      setHasUnsavedChanges(false)
      setTimeout(() => setDraftSaved(false), 3000)
    } catch {
      // Fallback: save to localStorage
      localStorage.setItem('gca_draft', JSON.stringify({ gpEmail, gpName, responses, expiresAt: expiresAt.toISOString() }))
      setDraftSaved(true)
      setHasUnsavedChanges(false)
      setTimeout(() => setDraftSaved(false), 3000)
    } finally {
      setSavingDraft(false)
    }
  }

  const handleSubmit = async () => {
    setSubmitError(null)
    setSubmitting(true)
    try {
      await apiClient.post('/questionnaires/', {
        project_id: null,
        gp_email: gpEmail,
        responses,
      })
      setStep('submitted')
    } catch (err: any) {
      setSubmitError(err?.message || 'Erro ao enviar questionário')
    } finally {
      setSubmitting(false)
    }
  }

  const block = BLOCKS[currentBlock]
  const totalAnswered = Object.keys(responses).filter(k => {
    const val = responses[k]
    return val && (typeof val === 'string' ? val.length > 0 : Array.isArray(val) && val.length > 0)
  }).length

  // === STEP: IDENTIFY ===
  if (step === 'identify') {
    return (
      <div className="min-h-screen bg-dark flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className="flex items-center justify-center gap-2 mb-6">
            <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
            <span className="text-white text-lg font-semibold">GCA</span>
          </div>

          <div className="bg-dark-100 border border-slate-700 rounded-2xl p-6 shadow-xl">
            <h1 className="text-xl font-bold text-white mb-1">Criar Novo Projeto</h1>
            <p className="text-slate-400 text-sm mb-6">
              Identifique-se para iniciar o processo de criação de projeto no GCA.
            </p>

            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-start gap-3 mb-6">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-amber-200/80 text-xs">
                Após o envio, você receberá uma confirmação por e-mail informando que seu projeto está em análise.
                O questionário pode ser salvo como rascunho por até 5 dias úteis.
              </p>
            </div>

            {identifyError && (
              <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
                <p className="text-red-300 text-sm">{identifyError}</p>
              </div>
            )}

            <form onSubmit={handleIdentify} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Seu nome completo</label>
                <div className="relative">
                  <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text" value={gpName} onChange={e => setGpName(e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                    placeholder="Nome Completo" required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Seu e-mail</label>
                <div className="relative">
                  <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type="email" value={gpEmail} onChange={e => setGpEmail(e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                    placeholder="seu@email.com" required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Seu papel</label>
                <div className="w-full bg-dark-200 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-400">
                  Gerente de Projeto (GP)
                </div>
              </div>

              <button
                type="submit" disabled={identifyLoading || !gpEmail || !gpName}
                className="w-full bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {identifyLoading ? <><Loader2 className="w-4 h-4 animate-spin" />Validando...</> : 'Continuar para o Questionário'}
              </button>
            </form>

            <div className="mt-4 text-center">
              <button onClick={() => navigate('/login')} className="text-sm text-slate-500 hover:text-slate-300 transition-colors">
                ← Voltar ao login
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // === STEP: SUBMITTED ===
  if (step === 'submitted') {
    return (
      <div className="min-h-screen bg-dark flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className="bg-dark-100 border border-emerald-700/30 rounded-2xl p-8 shadow-xl text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-white mb-2">Projeto Enviado!</h1>
            <p className="text-slate-400 mb-2">
              Seu questionário foi enviado para análise pelo Admin e pelo GP responsável.
            </p>
            <p className="text-slate-500 text-sm mb-6">
              Você receberá uma notificação por e-mail em <strong className="text-slate-300">{gpEmail}</strong> informando
              o status do seu projeto. Após o aceite, você poderá acompanhar na seção Projetos.
            </p>
            <button
              onClick={() => navigate('/login')}
              className="bg-violet-600 hover:bg-violet-500 text-white rounded-lg px-6 py-2.5 text-sm font-medium transition-colors"
            >
              Voltar ao Login
            </button>
          </div>
        </div>
      </div>
    )
  }

  // === STEP: QUESTIONNAIRE ===
  return (
    <div className="min-h-screen bg-dark p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Expirado */}
        {expired && (
          <div className="bg-red-900/40 border border-red-800/50 rounded-xl p-6 text-center">
            <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-3" />
            <h2 className="text-xl font-bold text-white mb-2">Formulário Expirado</h2>
            <p className="text-slate-400 text-sm mb-4">
              O prazo de 5 dias para preenchimento foi excedido. Este formulário foi excluído.
              Uma notificação foi enviada ao GP e ao Admin.
            </p>
            <button onClick={() => navigate('/login')} className="bg-violet-600 hover:bg-violet-500 text-white rounded-lg px-6 py-2 text-sm transition-colors">
              Voltar ao Login
            </button>
          </div>
        )}

        {!expired && <>
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ClipboardList className="w-6 h-6 text-violet-400" />
            <div>
              <h1 className="text-2xl font-bold text-white">Questionário Técnico</h1>
              <p className="text-slate-400 text-sm">{gpName} · {gpEmail}</p>
            </div>
          </div>

          {/* Right side: timer + draft */}
          <div className="flex flex-col items-end gap-2">
            {/* Countdown timer */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
              timeLeft.startsWith('00d') ? 'bg-red-900/30 border-red-800/40' : 'bg-slate-800 border-slate-700'
            }`}>
              <Timer className={`w-4 h-4 ${timeLeft.startsWith('00d') ? 'text-red-400' : 'text-amber-400'}`} />
              <span className={`font-mono text-sm font-medium ${timeLeft.startsWith('00d') ? 'text-red-300' : 'text-amber-300'}`}>
                {timeLeft}
              </span>
            </div>

            {/* Save draft button */}
            <button
              onClick={handleSaveDraft}
              disabled={savingDraft}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 text-slate-300 rounded-lg text-xs hover:bg-slate-700 transition-colors"
            >
              {savingDraft ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              {draftSaved ? 'Rascunho Salvo' : 'Salvar Rascunho'}
            </button>

            {/* Progress */}
            <div className="text-right">
              <p className="text-xs text-slate-500">{totalAnswered} respondidas</p>
              <div className="w-28 h-1 bg-slate-700 rounded-full mt-0.5">
                <div className="h-full bg-violet-600 rounded-full transition-all" style={{ width: `${Math.min(100, (totalAnswered / 49) * 100)}%` }} />
              </div>
            </div>
          </div>
        </div>

        {/* Block tabs */}
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {BLOCKS.map((b, i) => {
            const isA2Disabled = b.id === 'A.2' && responses['3'] !== 'Sim'
            return (
              <button key={b.id} onClick={() => !isA2Disabled && setCurrentBlock(i)} disabled={isA2Disabled}
                className={`flex-shrink-0 px-3 py-1.5 text-xs rounded-lg transition-colors ${isA2Disabled ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed' : i === currentBlock ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
                title={isA2Disabled ? 'Habilitado quando Q3 = "Sim"' : b.title}
              >{b.id}</button>
            )
          })}
        </div>

        {/* Current block */}
        <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-1">{block.title}</h2>
          <p className="text-slate-400 text-sm mb-6">{block.description}</p>

          {block.id === 'A.2' && responses['3'] !== 'Sim' && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-center gap-2 mb-6">
              <Info className="w-4 h-4 text-amber-400 flex-shrink-0" />
              <p className="text-amber-300 text-sm">Este bloco só é habilitado quando Q3 = "Sim" (projeto existente).</p>
            </div>
          )}

          {submitError && (
            <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
              <p className="text-red-300 text-sm">{submitError}</p>
            </div>
          )}

          <div className="space-y-7">
            {block.questions.filter(isQuestionVisible).map(q => {
              const linked = isQuestionLinked(q)
              return (
                <div key={q.id} className={linked ? 'opacity-50' : ''}>
                  <label className="block text-sm text-slate-200 font-medium mb-2">
                    <span className="text-violet-400 mr-1 font-bold">Q{q.id}.</span>{q.label}
                    {q.help && (
                      <span className="relative inline-block ml-1.5 align-middle group">
                        <span className="w-5 h-5 rounded-full bg-slate-700 text-slate-400 inline-flex items-center justify-center cursor-help" title={q.help}>
                          <HelpCircle className="w-3.5 h-3.5" />
                        </span>
                      </span>
                    )}
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

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button onClick={() => setCurrentBlock(i => Math.max(0, i - 1))} disabled={currentBlock === 0}
            className="flex items-center gap-1 px-4 py-2 text-sm text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" /> Anterior
          </button>

          <span className="text-sm text-slate-500">Bloco {currentBlock + 1} de {BLOCKS.length}</span>

          {currentBlock < BLOCKS.length - 1 ? (
            <button onClick={() => setCurrentBlock(i => Math.min(BLOCKS.length - 1, i + 1))}
              className="flex items-center gap-1 px-4 py-2 text-sm bg-violet-600 hover:bg-violet-500 text-white rounded-lg transition-colors"
            >
              Próximo <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={handleSubmit} disabled={submitting}
              className="flex items-center gap-2 px-5 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" />Enviando...</> : <><Send className="w-4 h-4" />Enviar para Análise</>}
            </button>
          )}
        </div>

        {/* Exit button */}
        <div className="flex items-center justify-between pt-4 border-t border-slate-800">
          <button
            onClick={handleExit}
            className="text-sm text-slate-500 hover:text-slate-300 transition-colors"
          >
            ← Sair do Questionário
          </button>
          {hasUnsavedChanges && !draftSaved && (
            <p className="text-xs text-amber-400">Esse rascunho não foi salvo ainda</p>
          )}
        </div>

        {/* Exit warning modal */}
        {showExitWarning && (
          <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
            <div className="bg-dark-100 border border-amber-700/30 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
              <div className="flex items-center gap-3 mb-4">
                <AlertTriangle className="w-6 h-6 text-amber-400" />
                <h3 className="text-white font-semibold">Rascunho não salvo</h3>
              </div>
              <p className="text-slate-300 text-sm mb-6">
                Se sair sem salvar, todas as informações preenchidas serão perdidas.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowExitWarning(false)}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg py-2 text-sm transition-colors"
                >
                  Voltar ao Questionário
                </button>
                <button
                  onClick={() => navigate('/login')}
                  className="flex-1 bg-red-600 hover:bg-red-500 text-white rounded-lg py-2 text-sm transition-colors"
                >
                  Sair assim mesmo
                </button>
              </div>
            </div>
          </div>
        )}
        </>}
      </div>
    </div>
  )
}

export default NovoProjetoPage
