import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, AlertCircle, Download, Upload, Sparkles, ClipboardList, MessageSquareWarning, RefreshCcw } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useIterativeQuestionnaireStatus } from '@/hooks/useIterativeQuestionnaireStatus'
import { PersonaFollowUpTabs } from '@/components/questionnaire/PersonaFollowUpTabs'
import { QuestionnairePage } from '@/pages/projects/QuestionnairePage'

const PILLAR_LABELS: Record<string, string> = {
  P1_business_case: 'Caso de Negócio',
  P2_business_model: 'Modelo de Negócio',
  P3_scope: 'Escopo',
  P4_quality: 'Qualidade',
  P5_ux: 'UX',
  P6_legal: 'Jurídico',
  P7_security: 'Segurança',
}

type MasterTab = 'initial' | 'personas' | 'pillars'

const MASTER_TABS: { id: MasterTab; label: string; icon: typeof ClipboardList }[] = [
  { id: 'initial',  label: 'Questionário Inicial',     icon: ClipboardList },
  { id: 'personas', label: 'Perguntas das Personas',   icon: MessageSquareWarning },
  { id: 'pillars',  label: 'Iteração de Pilares (OCG)', icon: RefreshCcw },
]

export function IterativeQuestionnairePage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [active, setActive] = useState<MasterTab>('initial')

  return (
    <div className="p-6 max-w-6xl">
      <header className="mb-4">
        <h1 className="text-xl font-semibold text-slate-100 mb-1">Questões em Aberto</h1>
        <p className="text-xs text-slate-500">
          Centraliza tudo que aguarda resposta do GP — questionário inicial,
          perguntas das personas geradas durante ingestão, e iterações de pilares
          deficitários do OCG. Meta: overall ≥ 90 e todos os pilares ≥ 75.
        </p>
      </header>

      {/* Sub-abas mestre */}
      <div className="flex flex-wrap gap-1 border-b border-slate-800 mb-6 -mt-1">
        {MASTER_TABS.map(t => {
          const Icon = t.icon
          const isActive = t.id === active
          return (
            <button
              key={t.id}
              onClick={() => setActive(t.id)}
              className={`px-4 py-2 text-sm rounded-t-md flex items-center gap-2 transition-colors -mb-px border-b-2 ${
                isActive
                  ? 'border-violet-500 text-violet-300 bg-slate-800/40'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {active === 'initial' && projectId && (
        <QuestionnairePage />
      )}

      {active === 'personas' && projectId && (
        <PersonaFollowUpTabs projectId={projectId} />
      )}

      {active === 'pillars' && projectId && (
        <PillarIterationsPanel projectId={projectId} />
      )}
    </div>
  )
}

// ─── Painel "Iteração de Pilares" — extraído do antigo IterativeQuestionnairePage ───

function PillarIterationsPanel({ projectId }: { projectId: string }) {
  const { data, loading } = useIterativeQuestionnaireStatus(projectId)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando status...
      </div>
    )
  }
  if (!data) {
    return <div className="p-8 text-sm text-slate-500">Não foi possível carregar o status.</div>
  }

  const handleGenerate = async () => {
    setGenerating(true); setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/iterative-questionnaire/generate`)
      window.location.reload()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Falha ao gerar iteração')
    } finally {
      setGenerating(false)
    }
  }

  const handleDownload = async () => {
    if (!data.latest_iteration) return
    const res = await apiClient.get(
      `/projects/${projectId}/iterative-questionnaire/${data.latest_iteration.id}/docx`,
      { responseType: 'blob' },
    )
    const url = window.URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `Questoes_Abertas_Iter${data.latest_iteration.iteration}.docx`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">OCG atual</div>
          <div className="text-2xl font-semibold text-slate-100">
            {data.overall !== null ? data.overall.toFixed(1) : '—'}
            <span className="text-xs text-slate-500 ml-1">/100</span>
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Pilares deficitários</div>
          <div className="text-sm text-slate-200">
            {Object.keys(data.deficit_pillars).length === 0
              ? <span className="text-emerald-400">Nenhum</span>
              : Object.entries(data.deficit_pillars).map(([p, s]) => (
                <div key={p} className="flex justify-between">
                  <span>{PILLAR_LABELS[p] || p}</span>
                  <span className="text-amber-400">{(s as number).toFixed(1)}</span>
                </div>
              ))}
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Status</div>
          <div className="text-sm">
            {data.converged && <span className="flex items-center gap-1 text-emerald-400"><CheckCircle2 className="w-4 h-4" /> Convergido</span>}
            {data.has_pending && <span className="flex items-center gap-1 text-amber-400"><AlertCircle className="w-4 h-4" /> Aguardando resposta</span>}
            {!data.has_pending && !data.converged && data.eligible_for_iteration && (
              <span className="text-slate-300">Pronto pra nova iteração</span>
            )}
            {!data.has_pending && !data.converged && !data.eligible_for_iteration && (
              <span className="text-slate-500">Sem ação pendente</span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-950/30 border border-red-900/40 rounded text-xs text-red-400">{error}</div>
      )}

      {data.has_pending && data.latest_iteration && data.latest_iteration.iteration > 1 && (
        <div className="mb-6 px-4 py-3 bg-amber-950/30 border border-amber-700/40 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-amber-300 mb-1">
              Nova iteração de perguntas disponível — Iteração {data.latest_iteration.iteration}
            </div>
            <p className="text-xs text-amber-200/80">
              A análise da última ingestão identificou gaps novos nos pilares deficitários.
              Foram geradas <strong>{data.latest_iteration.question_count}</strong> perguntas
              {data.latest_iteration.target_pillars.length > 0 && (
                <> em <strong>{data.latest_iteration.target_pillars.map(p => PILLAR_LABELS[p] || p).join(', ')}</strong></>
              )}.
              Baixe o formulário, responda e faça upload pela aba Ingestão.
            </p>
          </div>
        </div>
      )}

      {data.eligible_for_iteration && !data.has_pending && (
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="mb-6 inline-flex items-center gap-2 px-4 py-2 rounded-md bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium disabled:opacity-50"
        >
          {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          Gerar nova iteração
        </button>
      )}

      {data.latest_iteration && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-slate-100">
                Iteração {data.latest_iteration.iteration}
                <span className="ml-2 text-[10px] text-slate-500 uppercase">{data.latest_iteration.status}</span>
              </div>
              <div className="text-xs text-slate-500">
                {data.latest_iteration.question_count} pergunta(s) •
                Pilares: {data.latest_iteration.target_pillars.map(p => PILLAR_LABELS[p] || p).join(', ')}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleDownload}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
              >
                <Download className="w-3.5 h-3.5" /> Baixar formulário (.docx)
              </button>
            </div>
          </div>
          {data.latest_iteration.status === 'pending' && (
            <div className="px-4 py-3 text-xs text-slate-300 bg-slate-950/40 border-b border-slate-800 flex items-start gap-2">
              <Upload className="w-3.5 h-3.5 text-violet-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                Preencha o PDF e envie pela aba <strong className="text-slate-100">Ingestão de Documentos</strong>.
                O sistema identifica automaticamente que é resposta desta iteração e atualiza o OCG em seguida.
                {' '}
                <a href={`/projects/${projectId}/ingestion`} className="text-violet-400 hover:text-violet-300 underline">
                  Ir para Ingestão →
                </a>
              </div>
            </div>
          )}
          {data.latest_iteration.overall_after !== null && (
            <div className="px-4 py-2 text-xs text-slate-400 bg-slate-950/40 border-b border-slate-800">
              Overall antes: <strong>{data.latest_iteration.overall_before?.toFixed(1)}</strong> →
              depois: <strong>{data.latest_iteration.overall_after?.toFixed(1)}</strong>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
