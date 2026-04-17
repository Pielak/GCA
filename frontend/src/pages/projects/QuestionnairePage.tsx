import { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import {
  ClipboardList, Download, FileUp, Loader2, CheckCircle2,
  AlertTriangle, AlertCircle, Clock,
} from 'lucide-react'
import { apiClient } from '@/lib/api'

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

interface ExistingQuestionnaire {
  id: string
  status: string
  approved: boolean
  adherence_score: number | null
  submitted_at: string | null
  analyzed_at: string | null
  observations: string | null
}

// ─── Component ─────────────────────────────────────────────────────

export function QuestionnairePage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [existing, setExisting] = useState<ExistingQuestionnaire | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!projectId) {
      setLoading(false)
      return
    }
    apiClient
      .get(`/projects/${projectId}/questionnaire`)
      .then((res: any) => {
        if (res?.data?.questionnaire) setExisting(res.data.questionnaire)
      })
      .catch(() => { /* sem questionário ainda */ })
      .finally(() => setLoading(false))
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
  return (
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
            <p className="text-xs text-slate-300 mt-2 italic">{q.observations}</p>
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
  if (q.status === 'pending' || q.status === 'submitted') {
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
