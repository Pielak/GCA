/**
 * SolicitarProjetoPage — wizard 2 passos para solicitar novo projeto.
 *
 * Passo 1: básico (nome, email, projeto, tipo, descrição obrigatória).
 *          Tipo "Outro" abre input livre para o usuário escrever (ex:
 *          "Browser Extension", "Web Application").
 * Passo 2: perguntas obrigatórias do tipo escolhido — alimentam o seed
 *          inicial do OCG após o admin aprovar (Arguidor já tem contexto
 *          mínimo para gerar o primeiro CodeGen).
 *
 * Submete via POST /api/v1/public/project-requests (sem auth).
 */
import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Loader2, ArrowLeft, ArrowRight, CheckCircle2, FilePlus } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getQuestionsForType, type Question } from '@/data/projectRequestQuestions'

const DELIVERABLE_TYPES = [
  { value: 'new_system', label: 'Novo sistema' },
  { value: 'mobile_app', label: 'Aplicativo mobile' },
  { value: 'module', label: 'Módulo / extensão' },
  { value: 'enhancement', label: 'Melhoria em sistema existente' },
  { value: 'integration', label: 'Integração' },
  { value: 'modernization', label: 'Modernização / refatoração' },
  { value: 'etl', label: 'ETL / pipeline de dados' },
  { value: 'maintenance', label: 'Sustentação evolutiva' },
  { value: 'other', label: 'Outro (descrever)' },
]

const DESCRIPTION_MIN = 30

type Answers = Record<string, string>

export function SolicitarProjetoPage() {
  const navigate = useNavigate()

  // Step state
  const [step, setStep] = useState<1 | 2>(1)

  // Step 1 fields
  const [requesterName, setRequesterName] = useState('')
  const [requesterEmail, setRequesterEmail] = useState('')
  const [projectName, setProjectName] = useState('')
  const [description, setDescription] = useState('')
  const [deliverableType, setDeliverableType] = useState('new_system')
  const [customType, setCustomType] = useState('')

  // Step 2 fields
  const [answers, setAnswers] = useState<Answers>({})

  // Submission state
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<{ id: string; slug: string } | null>(null)

  const questions: Question[] = useMemo(
    () => getQuestionsForType(deliverableType),
    [deliverableType],
  )

  const step1Valid =
    requesterName.trim().length >= 2 &&
    requesterEmail.trim().length > 3 &&
    projectName.trim().length >= 3 &&
    description.trim().length >= DESCRIPTION_MIN &&
    (deliverableType !== 'other' || customType.trim().length >= 2)

  const step2Valid = questions.every(q => {
    if (!q.required) return true
    const v = (answers[q.id] || '').trim()
    if (!v) return false
    if (q.minLength && v.length < q.minLength) return false
    return true
  })

  const goNext = () => {
    setError(null)
    if (!step1Valid) {
      setError('Preencha todos os campos obrigatórios antes de continuar.')
      return
    }
    setStep(2)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const goBack = () => {
    setError(null)
    setStep(1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!step2Valid) {
      setError('Responda todas as perguntas obrigatórias.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const payload: Record<string, unknown> = {
        requester_name: requesterName.trim(),
        requester_email: requesterEmail.trim().toLowerCase(),
        project_name: projectName.trim(),
        description: description.trim(),
        deliverable_type: deliverableType,
        requirements: answers,
      }
      if (deliverableType === 'other') {
        payload.custom_deliverable_type = customType.trim()
      }
      const res = await apiClient.post('/public/project-requests', payload)
      setSuccess({ id: res.data.id, slug: res.data.slug })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : (err?.message || 'Falha ao enviar solicitação'))
    } finally {
      setSubmitting(false)
    }
  }

  // ─── Tela de sucesso ──────────────────────────────────────────────
  if (success) {
    return (
      <div className="min-h-screen bg-[#0a0a1f] flex items-center justify-center p-6">
        <div className="bg-[#1c1c34]/90 backdrop-blur-xl border border-emerald-500/20 rounded-2xl p-8 max-w-md w-full text-center">
          <CheckCircle2 className="w-16 h-16 text-emerald-400 mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-slate-100 mb-2">Solicitação enviada!</h1>
          <p className="text-slate-400 text-sm mb-1">
            Sua solicitação foi registrada e aguarda aprovação do administrador.
          </p>
          <p className="text-slate-500 text-xs mb-6">
            Você receberá um email assim que o admin aprovar (ou rejeitar) — verifique também o spam.
          </p>
          <div className="text-xs text-slate-600 mb-6 font-mono">
            Slug provisório: <span className="text-slate-400">{success.slug}</span>
          </div>
          <button
            onClick={() => navigate('/login')}
            className="w-full bg-violet-600 hover:bg-violet-500 text-white rounded-lg py-2.5 text-sm font-medium transition-colors"
          >
            Voltar para o login
          </button>
        </div>
      </div>
    )
  }

  // ─── Wizard ───────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a1f] flex items-center justify-center p-6">
      <div className="bg-[#1c1c34]/90 backdrop-blur-xl border border-violet-500/20 rounded-2xl p-8 max-w-2xl w-full">
        <Link to="/login" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-violet-400 mb-4">
          <ArrowLeft className="w-3 h-3" />
          Voltar ao login
        </Link>

        <div className="flex items-center gap-2 mb-1">
          <FilePlus className="w-5 h-5 text-violet-400" />
          <h1 className="text-xl font-semibold text-slate-100">Solicitar novo projeto</h1>
        </div>
        <p className="text-slate-500 text-xs mb-6">
          Preencha os campos abaixo. O administrador receberá sua solicitação e aprovará (ou rejeitará).
        </p>

        {/* ── Stepper ── */}
        <div className="flex items-center gap-3 mb-6">
          <StepDot n={1} label="Básico" active={step === 1} done={step > 1} />
          <div className={`h-px flex-1 ${step > 1 ? 'bg-violet-500/40' : 'bg-slate-700'}`} />
          <StepDot n={2} label="Requisitos" active={step === 2} done={false} />
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 bg-red-900/30 border border-red-700 rounded text-xs text-red-300">
            ⚠ {error}
          </div>
        )}

        {step === 1 ? (
          <Step1
            requesterName={requesterName}
            setRequesterName={setRequesterName}
            requesterEmail={requesterEmail}
            setRequesterEmail={setRequesterEmail}
            projectName={projectName}
            setProjectName={setProjectName}
            description={description}
            setDescription={setDescription}
            deliverableType={deliverableType}
            setDeliverableType={setDeliverableType}
            customType={customType}
            setCustomType={setCustomType}
            onNext={goNext}
            canProceed={step1Valid}
          />
        ) : (
          <Step2
            deliverableType={deliverableType}
            customType={customType}
            questions={questions}
            answers={answers}
            setAnswers={setAnswers}
            onBack={goBack}
            onSubmit={submit}
            submitting={submitting}
            canSubmit={step2Valid}
          />
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Step 1 — básico
// ═══════════════════════════════════════════════════════════════════════

interface Step1Props {
  requesterName: string
  setRequesterName: (v: string) => void
  requesterEmail: string
  setRequesterEmail: (v: string) => void
  projectName: string
  setProjectName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  deliverableType: string
  setDeliverableType: (v: string) => void
  customType: string
  setCustomType: (v: string) => void
  onNext: () => void
  canProceed: boolean
}

function Step1(p: Step1Props) {
  const descRemaining = Math.max(0, DESCRIPTION_MIN - p.description.trim().length)

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-slate-400 mb-1">Seu nome *</label>
        <input
          type="text"
          required
          minLength={2}
          maxLength={255}
          value={p.requesterName}
          onChange={e => p.setRequesterName(e.target.value)}
          placeholder="Ex: Maria Silva"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
        />
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">Seu email *</label>
        <input
          type="email"
          required
          value={p.requesterEmail}
          onChange={e => p.setRequesterEmail(e.target.value)}
          placeholder="voce@empresa.com"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
        />
        <p className="text-[10px] text-slate-600 mt-1">Usado para comunicação. Se não tem conta, será criada na aprovação.</p>
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">Nome do projeto *</label>
        <input
          type="text"
          required
          minLength={3}
          maxLength={255}
          value={p.projectName}
          onChange={e => p.setProjectName(e.target.value)}
          placeholder="Ex: Webapp de previsão do tempo"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
        />
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">Tipo de entregável *</label>
        <select
          value={p.deliverableType}
          onChange={e => p.setDeliverableType(e.target.value)}
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
        >
          {DELIVERABLE_TYPES.map(d => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
      </div>

      {p.deliverableType === 'other' && (
        <div>
          <label className="block text-xs text-slate-400 mb-1">Descreva o tipo *</label>
          <input
            type="text"
            required
            minLength={2}
            maxLength={100}
            value={p.customType}
            onChange={e => p.setCustomType(e.target.value)}
            placeholder="Ex: Browser Extension, Web Application, CLI Tool…"
            className="w-full bg-slate-800 border border-amber-700/40 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
          />
          <p className="text-[10px] text-amber-500/80 mt-1">
            O Arguidor usará esta descrição para escolher a stack — seja específico.
          </p>
        </div>
      )}

      <div>
        <label className="block text-xs text-slate-400 mb-1">
          Descrição breve <span className="text-red-400">*obrigatória</span>
        </label>
        <textarea
          required
          minLength={DESCRIPTION_MIN}
          maxLength={2000}
          rows={5}
          value={p.description}
          onChange={e => p.setDescription(e.target.value)}
          placeholder="Conte o objetivo, escopo principal, quem vai usar e o problema resolvido."
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600 resize-none"
        />
        <p className={`text-[10px] mt-1 ${descRemaining > 0 ? 'text-amber-500' : 'text-slate-600'}`}>
          {p.description.trim().length}/2000 — mínimo {DESCRIPTION_MIN} caracteres
          {descRemaining > 0 && ` (faltam ${descRemaining})`}
        </p>
      </div>

      <button
        type="button"
        onClick={p.onNext}
        disabled={!p.canProceed}
        className="w-full bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg py-3 text-sm font-semibold flex items-center justify-center gap-2 transition-colors"
      >
        Próximo: requisitos
        <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Step 2 — perguntas type-specific
// ═══════════════════════════════════════════════════════════════════════

interface Step2Props {
  deliverableType: string
  customType: string
  questions: Question[]
  answers: Answers
  setAnswers: (fn: (prev: Answers) => Answers) => void
  onBack: () => void
  onSubmit: (e: React.FormEvent) => void
  submitting: boolean
  canSubmit: boolean
}

function Step2(p: Step2Props) {
  const typeLabel =
    p.deliverableType === 'other'
      ? p.customType
      : (DELIVERABLE_TYPES.find(d => d.value === p.deliverableType)?.label || p.deliverableType)

  const setAnswer = (id: string, v: string) =>
    p.setAnswers(prev => ({ ...prev, [id]: v }))

  return (
    <form onSubmit={p.onSubmit} className="space-y-4">
      <div className="px-3 py-2 bg-violet-900/20 border border-violet-700/40 rounded text-xs text-violet-200">
        Tipo selecionado: <strong>{typeLabel}</strong>. Responda as perguntas abaixo para o Arguidor já ter contexto inicial.
      </div>

      {p.questions.length === 0 && (
        <div className="px-3 py-3 bg-slate-800/50 border border-slate-700 rounded text-xs text-slate-400">
          Sem perguntas específicas para este tipo. Continue para enviar.
        </div>
      )}

      {p.questions.map(q => (
        <QuestionField
          key={q.id}
          question={q}
          value={p.answers[q.id] || ''}
          onChange={v => setAnswer(q.id, v)}
        />
      ))}

      <div className="flex gap-3 pt-2">
        <button
          type="button"
          onClick={p.onBack}
          disabled={p.submitting}
          className="flex-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-40"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>
        <button
          type="submit"
          disabled={p.submitting || !p.canSubmit}
          className="flex-[2] bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg py-3 text-sm font-semibold flex items-center justify-center gap-2 transition-colors"
        >
          {p.submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {p.submitting ? 'Enviando…' : 'Enviar solicitação'}
        </button>
      </div>
    </form>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// QuestionField — renderiza text / textarea / select
// ═══════════════════════════════════════════════════════════════════════

function QuestionField({
  question,
  value,
  onChange,
}: {
  question: Question
  value: string
  onChange: (v: string) => void
}) {
  const baseInput =
    'w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600'

  const tooShort =
    !!question.minLength && value.trim().length > 0 && value.trim().length < question.minLength

  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">
        {question.label} {question.required && <span className="text-red-400">*</span>}
      </label>
      {question.help && <p className="text-[10px] text-slate-600 mb-1.5">{question.help}</p>}

      {question.kind === 'select' && (
        <select value={value} onChange={e => onChange(e.target.value)} className={baseInput}>
          <option value="">— selecione —</option>
          {question.options?.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )}

      {question.kind === 'text' && (
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={question.placeholder}
          maxLength={500}
          className={baseInput}
        />
      )}

      {question.kind === 'textarea' && (
        <textarea
          rows={3}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={question.placeholder}
          maxLength={2000}
          className={`${baseInput} resize-none`}
        />
      )}

      {tooShort && (
        <p className="text-[10px] text-amber-500 mt-1">
          Mínimo {question.minLength} caracteres ({value.trim().length} digitados).
        </p>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// StepDot — indicador de passo
// ═══════════════════════════════════════════════════════════════════════

function StepDot({ n, label, active, done }: { n: number; label: string; active: boolean; done: boolean }) {
  const cls = done
    ? 'bg-emerald-600 border-emerald-500 text-white'
    : active
      ? 'bg-violet-600 border-violet-500 text-white'
      : 'bg-slate-800 border-slate-700 text-slate-500'
  return (
    <div className="flex items-center gap-2">
      <div className={`w-7 h-7 rounded-full border flex items-center justify-center text-xs font-semibold ${cls}`}>
        {done ? <CheckCircle2 className="w-4 h-4" /> : n}
      </div>
      <span className={`text-xs font-medium ${active || done ? 'text-slate-200' : 'text-slate-500'}`}>{label}</span>
    </div>
  )
}
