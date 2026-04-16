/**
 * SolicitarProjetoPage — formulário público de solicitação de novo projeto.
 *
 * Acessível sem login a partir do link no LoginPage. Submete via POST
 * /api/v1/public/project-requests; admin aprova/rejeita em
 * Admin → Gestão de Projetos.
 */
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Loader2, ArrowLeft, CheckCircle2, FilePlus } from 'lucide-react'
import { apiClient } from '@/lib/api'

const DELIVERABLE_TYPES = [
  { value: 'new_system', label: 'Novo sistema' },
  { value: 'mobile_app', label: 'Aplicativo mobile' },
  { value: 'module', label: 'Módulo / extensão' },
  { value: 'enhancement', label: 'Melhoria em sistema existente' },
  { value: 'integration', label: 'Integração' },
  { value: 'modernization', label: 'Modernização / refatoração' },
  { value: 'etl', label: 'ETL / pipeline de dados' },
  { value: 'maintenance', label: 'Sustentação evolutiva' },
]

export function SolicitarProjetoPage() {
  const navigate = useNavigate()
  const [requesterName, setRequesterName] = useState('')
  const [requesterEmail, setRequesterEmail] = useState('')
  const [projectName, setProjectName] = useState('')
  const [description, setDescription] = useState('')
  const [deliverableType, setDeliverableType] = useState('new_system')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<{ id: string; slug: string } | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await apiClient.post('/public/project-requests', {
        requester_name: requesterName.trim(),
        requester_email: requesterEmail.trim().toLowerCase(),
        project_name: projectName.trim(),
        description: description.trim(),
        deliverable_type: deliverableType,
      })
      setSuccess({ id: res.data.id, slug: res.data.slug })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : (err?.message || 'Falha ao enviar solicitação'))
    } finally {
      setSubmitting(false)
    }
  }

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

  return (
    <div className="min-h-screen bg-[#0a0a1f] flex items-center justify-center p-6">
      <div className="bg-[#1c1c34]/90 backdrop-blur-xl border border-violet-500/20 rounded-2xl p-8 max-w-lg w-full">
        <Link to="/login" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-violet-400 mb-4">
          <ArrowLeft className="w-3 h-3" />
          Voltar ao login
        </Link>

        <div className="flex items-center gap-2 mb-1">
          <FilePlus className="w-5 h-5 text-violet-400" />
          <h1 className="text-xl font-semibold text-slate-100">Solicitar novo projeto</h1>
        </div>
        <p className="text-slate-500 text-xs mb-6">
          Preencha os campos abaixo. O administrador receberá sua solicitação e aprovará (ou rejeitará) em seguida.
          Você será notificado por email.
        </p>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Seu nome *</label>
            <input
              type="text"
              required
              minLength={2}
              maxLength={255}
              value={requesterName}
              onChange={e => setRequesterName(e.target.value)}
              placeholder="Ex: Maria Silva"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Seu email *</label>
            <input
              type="email"
              required
              value={requesterEmail}
              onChange={e => setRequesterEmail(e.target.value)}
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
              value={projectName}
              onChange={e => setProjectName(e.target.value)}
              placeholder="Ex: Webapp de previsão do tempo"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Tipo de entregável *</label>
            <select
              value={deliverableType}
              onChange={e => setDeliverableType(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
            >
              {DELIVERABLE_TYPES.map(d => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Descrição breve (opcional)</label>
            <textarea
              maxLength={2000}
              rows={4}
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Conte rapidamente o objetivo, escopo principal, e quem vai usar."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600 resize-none"
            />
            <p className="text-[10px] text-slate-600 mt-1">{description.length}/2000 — quanto mais contexto, melhor a aprovação inicial.</p>
          </div>

          {error && (
            <div className="px-3 py-2 bg-red-900/30 border border-red-700 rounded text-xs text-red-300">
              ⚠ {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !requesterName || !requesterEmail || !projectName}
            className="w-full bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-3 text-sm font-semibold flex items-center justify-center gap-2 transition-colors"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? 'Enviando…' : 'Enviar solicitação'}
          </button>
        </form>
      </div>
    </div>
  )
}
