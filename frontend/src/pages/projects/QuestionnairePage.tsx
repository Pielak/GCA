import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  ClipboardList, Download, FileUp, Loader2, CheckCircle2,
  AlertTriangle, AlertCircle, Clock, Lightbulb, ShieldAlert, Wand2,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { questionLabel } from '@/data/questionLabels'
import { QUESTION_SCHEMA, type QuestionDef } from '@/data/questionSchema'

/**
 * QuestionnairePage — fluxo único PDF-only (estratégia B, DT-015 fechada).
 *
 * O GP baixa o PDF editável (AcroForm com 49 perguntas), preenche offline
 * no seu tempo, e faz upload. O backend roda o pipeline de validação
 * tecnológica (8 fases) e, se aprovado, dispara a geração do OCG via 8
 * agentes IA. O PDF NÃO é ingerido como documento — é apenas transporte
 * de respostas (evita falso-positivo de PII no detector de ingestão).
 */

// ─── Types ─────────────────────────────────────────────────────────

interface BlockingIssue {
  severity: 'blocker' | 'critical' | 'warning'
  rule_id: string | null
  title: string
  description: string
  affected_questions: string[]
  suggestion: string
  pillar?: string | null
}

interface ExistingQuestionnaire {
  id: string
  status: string
  approved: boolean
  adherence_score: number | null
  submitted_at: string | null
  analyzed_at: string | null
  observations: string | null
  blocking_issues?: BlockingIssue[]
  // Respostas atuais (q_id → string ou lista). Usadas para pré-preencher
  // o painel de correção inline sem exigir novo upload de PDF.
  responses?: Record<string, string | string[]>
}

// ─── Component ─────────────────────────────────────────────────────

export function QuestionnairePage() {
  const { id: projectId } = useParams<{ id: string }>()
  // Invalidação do setup-status ao submeter/corrigir questionário —
  // o badge da tab e o hero refletem imediatamente.
  const queryClient = useQueryClient()
  const invalidateSetup = () => {
    queryClient.invalidateQueries({ queryKey: ['project-setup-status', projectId] })
  }
  const [existing, setExisting] = useState<ExistingQuestionnaire | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchExisting = async () => {
    if (!projectId) return
    try {
      const res: any = await apiClient.get(`/projects/${projectId}/questionnaire`)
      if (res?.data?.questionnaire) setExisting(res.data.questionnaire)
    } catch { /* sem questionário ainda */ }
  }

  useEffect(() => {
    if (!projectId) { setLoading(false); return }
    fetchExisting().finally(() => setLoading(false))
  }, [projectId])

  const handleDownload = async () => {
    if (!projectId) return
    setDownloading(true)
    try {
      const res = await apiClient.get(
        `/projects/${projectId}/questionnaire/pdf`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(new Blob([res.data as BlobPart]))
      const a = document.createElement('a')
      a.href = url
      a.download = `Questionario_GCA_${projectId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      alert(`Erro ao baixar PDF: ${err?.message || 'desconhecido'}`)
    } finally {
      setDownloading(false)
    }
  }

  const handleUpload = async (file: File) => {
    if (!projectId) return
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res: any = await apiClient.post(
        `/projects/${projectId}/questionnaire/upload-pdf`,
        form,
      )
      alert(res?.data?.message || 'Questionário submetido para análise.')
      invalidateSetup()
      window.location.reload()
    } catch (err: any) {
      const detail = err?.data?.detail || err?.message || 'Erro ao processar PDF'
      alert(`Erro: ${detail}`)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // ─── Renderização ────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-600/40 flex items-center justify-center">
          <ClipboardList className="w-5 h-5 text-violet-400" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Questionário Técnico</h1>
          <p className="text-slate-400 text-sm">
            49 perguntas em PDF editável — baixe, preencha offline, envie quando pronto.
          </p>
        </div>
      </div>

      {/* Status card (se já submetido) */}
      {existing && <StatusCard q={existing} />}

      {/* Painel de correção inline — só aparece quando há bloqueadores */}
      {existing && projectId && (existing.blocking_issues?.length ?? 0) > 0 && (
        <InlineFixPanel
          projectId={projectId}
          issues={existing.blocking_issues ?? []}
          currentResponses={existing.responses ?? {}}
          onSaved={async () => { await fetchExisting(); invalidateSetup() }}
        />
      )}

      {/* Ações — SEMPRE disponíveis; reenvio atualiza responses */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <div>
          <h2 className="text-slate-100 text-base font-semibold mb-1">
            {existing ? 'Reenviar questionário' : 'Começar'}
          </h2>
          <p className="text-slate-400 text-xs">
            {existing
              ? 'Você pode reenviar o PDF atualizado. As novas respostas substituem as anteriores.'
              : 'Baixe o PDF, preencha no seu leitor de PDF favorito (Adobe, Preview, Foxit) e envie quando estiver pronto.'}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center justify-center gap-2 px-4 py-3 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {downloading ? 'Baixando…' : 'Baixar PDF editável'}
          </button>

          <label
            className={`flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
              uploading
                ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer'
            }`}
          >
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileUp className="w-4 h-4" />}
            {uploading ? 'Processando…' : 'Enviar PDF preenchido'}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleUpload(f)
              }}
            />
          </label>
        </div>

        <div className="bg-violet-950/20 border border-violet-800/30 rounded-lg p-3 text-xs text-slate-300 space-y-1">
          <p className="font-semibold text-violet-300">Como funciona</p>
          <ol className="list-decimal list-inside space-y-0.5 text-slate-400">
            <li>Baixe o PDF. Ele tem campos editáveis (AcroForm).</li>
            <li>Abra no Adobe Reader ou similar. Preencha as 49 perguntas.</li>
            <li>Salve o PDF preenchido.</li>
            <li>Clique em "Enviar PDF preenchido" e escolha o arquivo salvo.</li>
            <li>O sistema analisa tecnicamente. Se aprovado, gera o OCG automaticamente.</li>
          </ol>
        </div>
      </div>
    </div>
  )
}

// ─── Status card ──────────────────────────────────────────────────

function StatusCard({ q }: { q: ExistingQuestionnaire }) {
  const { icon: Icon, color, bg, border, label, description } = statusDisplay(q)
  const issues = q.blocking_issues || []
  const blockers = issues.filter(i => i.severity === 'blocker')
  const criticals = issues.filter(i => i.severity === 'critical')
  const warnings = issues.filter(i => i.severity === 'warning')
  const hasIssues = issues.length > 0

  return (
    <div className="space-y-4">
      {/* Card-header com status + métricas */}
      <div className={`${bg} ${border} border rounded-xl p-4`}>
        <div className="flex items-start gap-3">
          <Icon className={`w-5 h-5 ${color} flex-shrink-0 mt-0.5`} />
          <div className="flex-1">
            <p className={`text-sm font-semibold ${color}`}>{label}</p>
            <p className="text-xs text-slate-400 mt-0.5">{description}</p>
            {q.submitted_at && (
              <p className="text-[11px] text-slate-500 mt-2">
                Enviado em {new Date(q.submitted_at).toLocaleString('pt-BR')}
                {q.adherence_score !== null && (
                  <>
                    {' · '}Aderência: <span className="font-semibold">{q.adherence_score}%</span>
                  </>
                )}
              </p>
            )}
            {q.observations && (
              <p className="text-xs text-slate-300 mt-2">{q.observations}</p>
            )}
            {hasIssues && (
              <div className="flex gap-3 mt-3 text-[11px]">
                {blockers.length > 0 && (
                  <span className="flex items-center gap-1 text-red-300">
                    <ShieldAlert className="w-3 h-3" />
                    {blockers.length} bloqueador{blockers.length > 1 ? 'es' : ''}
                  </span>
                )}
                {criticals.length > 0 && (
                  <span className="flex items-center gap-1 text-orange-300">
                    <AlertTriangle className="w-3 h-3" />
                    {criticals.length} crítico{criticals.length > 1 ? 's' : ''}
                  </span>
                )}
                {warnings.length > 0 && (
                  <span className="flex items-center gap-1 text-amber-300">
                    <AlertCircle className="w-3 h-3" />
                    {warnings.length} aviso{warnings.length > 1 ? 's' : ''}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Lista estruturada de issues — só quando há. Cada item é um card
          acionável com título humano, perguntas afetadas (com rótulo) e
          sugestão de correção. Substitui a string crua com códigos técnicos. */}
      {hasIssues && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide px-1">
            O que ajustar no seu questionário
          </p>
          {issues.map((issue, idx) => (
            <IssueCard key={`${issue.rule_id}-${idx}`} issue={issue} />
          ))}
        </div>
      )}
    </div>
  )
}

function IssueCard({ issue }: { issue: BlockingIssue }) {
  const severityStyle = {
    blocker: {
      bg: 'bg-red-950/20',
      border: 'border-red-800/40',
      chipBg: 'bg-red-500/20',
      chipText: 'text-red-200',
      label: 'Bloqueador',
      icon: ShieldAlert,
      iconColor: 'text-red-400',
    },
    critical: {
      bg: 'bg-orange-950/20',
      border: 'border-orange-800/40',
      chipBg: 'bg-orange-500/20',
      chipText: 'text-orange-200',
      label: 'Crítico',
      icon: AlertTriangle,
      iconColor: 'text-orange-400',
    },
    warning: {
      bg: 'bg-amber-950/15',
      border: 'border-amber-800/30',
      chipBg: 'bg-amber-500/20',
      chipText: 'text-amber-200',
      label: 'Aviso',
      icon: AlertCircle,
      iconColor: 'text-amber-400',
    },
  }[issue.severity]
  const Icon = severityStyle.icon

  return (
    <div className={`${severityStyle.bg} ${severityStyle.border} border rounded-lg p-3.5`}>
      <div className="flex items-start gap-3">
        <Icon className={`w-4 h-4 ${severityStyle.iconColor} flex-shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${severityStyle.chipBg} ${severityStyle.chipText}`}>
              {severityStyle.label}
            </span>
            <p className="text-sm font-semibold text-slate-100">{issue.title}</p>
          </div>

          {issue.description && (
            <p className="text-xs text-slate-400 mt-1.5 leading-snug">{issue.description}</p>
          )}

          {issue.affected_questions.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Questões afetadas</p>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {issue.affected_questions.map(qid => (
                  <span
                    key={qid}
                    className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-[11px] text-slate-200"
                    title={questionLabel(qid)}
                  >
                    {questionLabel(qid)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {issue.suggestion && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-emerald-300/90">
              <Lightbulb className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-emerald-400" />
              <span className="leading-snug">
                <span className="font-semibold">Como corrigir: </span>
                {issue.suggestion}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function statusDisplay(q: ExistingQuestionnaire) {
  if (q.approved || q.status === 'ok' || q.status === 'ocg_generated') {
    return {
      icon: CheckCircle2,
      color: 'text-emerald-400',
      bg: 'bg-emerald-950/20',
      border: 'border-emerald-800/30',
      label: 'Questionário aprovado',
      description: 'Análise técnica passou. OCG gerado — veja a aba Contexto Global (OCG).',
    }
  }
  if (q.status === 'pending' || q.status === 'submitted' || q.status === 'pending_analysis' || q.status === 'analyzing') {
    return {
      icon: Clock,
      color: 'text-amber-400',
      bg: 'bg-amber-950/20',
      border: 'border-amber-800/30',
      label: 'Em análise',
      description: 'Recebemos seu PDF. A análise tecnológica está em curso. Pode levar alguns minutos.',
    }
  }
  if (q.status === 'incomplete' || q.status === 'revision_needed') {
    return {
      icon: AlertTriangle,
      color: 'text-amber-400',
      bg: 'bg-amber-950/20',
      border: 'border-amber-800/30',
      label: 'Precisa de ajustes',
      description: 'A análise encontrou inconsistências ou campos faltando. Reenvie o PDF corrigido.',
    }
  }
  return {
    icon: AlertCircle,
    color: 'text-red-400',
    bg: 'bg-red-950/20',
    border: 'border-red-800/30',
    label: `Status: ${q.status}`,
    description: 'Houve um problema na análise. Reenvie o PDF ou contate o suporte.',
  }
}

// ─── Painel de correção inline ────────────────────────────────────

/**
 * Painel que permite ao GP editar diretamente as perguntas apontadas como
 * bloqueadoras — sem baixar PDF, re-preencher e re-uploadar.
 *
 * Fluxo:
 *  1. Union de `affected_questions` de todos os issues → lista de QIDs a editar
 *  2. Pré-preenche com `currentResponses[qid]` (state local)
 *  3. GP ajusta só o necessário
 *  4. Submit → POST /projects/:id/questionnaire/correct com só os campos
 *     alterados; backend mergea com responses existentes e re-roda análise
 *  5. `onSaved()` refetcha o questionário → cards reavaliam.
 */
function InlineFixPanel({
  projectId,
  issues,
  currentResponses,
  onSaved,
}: {
  projectId: string
  issues: BlockingIssue[]
  currentResponses: Record<string, string | string[]>
  onSaved: () => void | Promise<void>
}) {
  // QIDs afetados por qualquer issue — ordem mantém aparecimento nos cards
  const affectedQIDs = useMemo(() => {
    const seen = new Set<string>()
    const ordered: string[] = []
    for (const issue of issues) {
      for (const qid of issue.affected_questions) {
        if (!seen.has(qid) && QUESTION_SCHEMA[qid]) {
          seen.add(qid)
          ordered.push(qid)
        }
      }
    }
    return ordered
  }, [issues])

  const [edits, setEdits] = useState<Record<string, string | string[]>>(() => {
    const init: Record<string, string | string[]> = {}
    for (const qid of affectedQIDs) {
      const cur = currentResponses[qid]
      const def = QUESTION_SCHEMA[qid]
      if (cur !== undefined) init[qid] = cur
      else init[qid] = def.type === 'multi' ? [] : ''
    }
    return init
  })
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)

  if (affectedQIDs.length === 0) return null

  const setValue = (qid: string, value: string | string[]) => {
    setEdits(prev => ({ ...prev, [qid]: value }))
  }

  const save = async () => {
    setSaving(true)
    setResult(null)
    try {
      // Envia só as respostas que realmente mudaram, pra reduzir o diff.
      const corrections: Record<string, string | string[]> = {}
      for (const [qid, val] of Object.entries(edits)) {
        const cur = currentResponses[qid]
        const changed = Array.isArray(val) || Array.isArray(cur)
          ? JSON.stringify(val) !== JSON.stringify(cur ?? [])
          : val !== (cur ?? '')
        if (changed) corrections[qid] = val
      }
      if (Object.keys(corrections).length === 0) {
        setResult({ ok: false, message: 'Nenhuma alteração para enviar.' })
        setSaving(false)
        return
      }
      const res: any = await apiClient.post(
        `/projects/${projectId}/questionnaire/correct`,
        { corrections },
      )
      const data = res?.data || {}
      if (data.approved) {
        setResult({ ok: true, message: `Análise aprovada! Aderência ${data.adherence_score}%. OCG será gerado.` })
      } else {
        setResult({
          ok: true,
          message: `Salvo. Agora: ${data.blockers ?? 0} bloqueador(es), ${data.criticals ?? 0} crítico(s). Aderência ${data.adherence_score}%.`,
        })
      }
      await onSaved()
    } catch (err: any) {
      setResult({
        ok: false,
        message: err?.response?.data?.detail || err?.message || 'Falha ao salvar correções',
      })
    }
    setSaving(false)
  }

  return (
    <div className="bg-slate-900 border border-violet-800/40 rounded-xl p-5 space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-violet-600/20 border border-violet-600/40 flex items-center justify-center flex-shrink-0">
          <Wand2 className="w-4.5 h-4.5 text-violet-300" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-slate-100 text-base font-semibold">Corrigir respostas sem baixar o PDF</h3>
          <p className="text-slate-400 text-xs mt-0.5">
            Edite abaixo as {affectedQIDs.length} pergunta(s) apontadas nos bloqueadores.
            Ao salvar, a análise é re-rodada e o status é atualizado — sem precisar baixar, preencher e enviar o PDF de novo.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {affectedQIDs.map(qid => {
          const def = QUESTION_SCHEMA[qid]
          const val = edits[qid] ?? (def.type === 'multi' ? [] : '')
          return (
            <div key={qid} className="bg-slate-950/50 border border-slate-800 rounded-lg p-3">
              <label className="block text-slate-200 text-sm font-medium">
                {questionLabel(qid)}
              </label>
              <div className="mt-2">
                <QuestionInput def={def} value={val} onChange={v => setValue(qid, v)} />
              </div>
            </div>
          )
        })}
      </div>

      {result && (
        <div className={`px-3 py-2 rounded-lg text-xs border ${
          result.ok
            ? 'bg-emerald-900/20 border-emerald-800/40 text-emerald-300'
            : 'bg-red-900/20 border-red-800/40 text-red-300'
        }`}>
          {result.message}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
          {saving ? 'Re-analisando…' : 'Salvar correções e re-analisar'}
        </button>
      </div>
    </div>
  )
}

function QuestionInput({
  def,
  value,
  onChange,
}: {
  def: QuestionDef
  value: string | string[]
  onChange: (v: string | string[]) => void
}) {
  if (def.type === 'text') {
    return (
      <input
        type="text"
        value={typeof value === 'string' ? value : ''}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
      />
    )
  }

  if (def.type === 'single') {
    return (
      <select
        value={typeof value === 'string' ? value : ''}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
      >
        <option value="">Selecione…</option>
        {def.options?.map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    )
  }

  // multi
  const selected = Array.isArray(value) ? value : []
  const toggle = (opt: string) => {
    const next = selected.includes(opt)
      ? selected.filter(x => x !== opt)
      : [...selected, opt]
    onChange(next)
  }
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {def.options?.map(opt => {
        const checked = selected.includes(opt)
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`flex items-center gap-2 px-2.5 py-1.5 text-xs rounded-md border transition-colors text-left ${
              checked
                ? 'bg-violet-600/20 border-violet-500/50 text-violet-200'
                : 'bg-slate-800/50 border-slate-700 text-slate-300 hover:border-slate-600'
            }`}
          >
            <span className={`w-3.5 h-3.5 flex-shrink-0 rounded border flex items-center justify-center ${
              checked ? 'bg-violet-500 border-violet-400' : 'border-slate-500'
            }`}>
              {checked && <CheckCircle2 className="w-3 h-3 text-white" />}
            </span>
            <span className="truncate">{opt}</span>
          </button>
        )
      })}
    </div>
  )
}
