import { useMemo, useState } from 'react'
import { FileDown, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import {
  CANONICAL_SECTIONS,
  SECTION_DESCRIPTIONS,
  SECTION_LABELS,
  type QuestionnaireSection,
  downloadQuestionnairePdf,
  pillarToSection,
} from '@/lib/arguiderQuestionnaire'
import { getErrorMessage } from '@/lib/errors'

// MVP 24 Fase 24.5 — painel de questionários canônicos.
// Lê os items pendentes do Arguidor (prop `items`), agrupa por seção
// canônica e oferece botão download por seção. Seção sem items ainda
// pode ser baixada (GP pode usar Complementos). Barra de progresso
// reflete "respondidas vs oferecidas" quando há histórico.

interface GatekeeperItemLite {
  id: string
  item_id: string
  item_type: string
  data: { pillar?: string; category?: string; text?: string; description?: string; skip_count?: number }
  status: string
}

interface Props {
  projectId: string
  items: GatekeeperItemLite[]
}

export default function QuestionnaireDownloadPanel({ projectId, items }: Props) {
  const [downloading, setDownloading] = useState<QuestionnaireSection | null>(null)
  const [errorMsg, setErrorMsg] = useState<string>('')
  const [successMsg, setSuccessMsg] = useState<string>('')

  const pendingBySection = useMemo(() => {
    const buckets: Record<QuestionnaireSection, GatekeeperItemLite[]> = {
      governance: [], architecture: [], capacity: [], security: [], legal: [],
    }
    for (const it of items) {
      if (it.status !== 'pending') continue
      // Classificador canônico SIMPLIFICADO no frontend (backend é fonte de
      // verdade real — aqui é só pra contar preview). Usa pillar se houver,
      // senão governance.
      const pillarLike = it.data?.pillar || it.data?.category || ''
      const section = pillarLike ? pillarToSection(pillarLike) : 'governance'
      buckets[section].push(it)
    }
    return buckets
  }, [items])

  const infoDebtBySection = useMemo(() => {
    const m: Record<QuestionnaireSection, number> = {
      governance: 0, architecture: 0, capacity: 0, security: 0, legal: 0,
    }
    for (const list of Object.values(pendingBySection)) {
      for (const it of list as GatekeeperItemLite[]) {
        const skip = Number(it.data?.skip_count || 0)
        if (skip >= 2) {
          const pillarLike = it.data?.pillar || it.data?.category || ''
          const section = pillarLike ? pillarToSection(pillarLike) : 'governance'
          m[section] += 1
        }
      }
    }
    return m
  }, [pendingBySection])

  const handleDownload = async (section: QuestionnaireSection) => {
    setDownloading(section)
    setErrorMsg('')
    setSuccessMsg('')
    try {
      await downloadQuestionnairePdf(projectId, section)
      setSuccessMsg(
        `PDF da seção "${SECTION_LABELS[section]}" baixado. ` +
        `Responda offline e envie via Ingestão para propagar automaticamente.`,
      )
    } catch (err) {
      setErrorMsg(getErrorMessage(err))
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">
            Questionários Técnicos Retroativos
          </h3>
          <p className="text-slate-500 text-xs">
            Baixe o PDF por seção, responda offline, envie via Ingestão.
            Respostas cascateiam pro backlog, roadmap e stale de scaffolds.
          </p>
        </div>
      </div>

      {errorMsg && (
        <div className="flex items-center gap-2 p-2 rounded bg-red-900/20 border border-red-800/40 text-red-300 text-xs">
          <AlertCircle className="w-3.5 h-3.5" /> {errorMsg}
        </div>
      )}
      {successMsg && (
        <div className="flex items-center gap-2 p-2 rounded bg-emerald-900/20 border border-emerald-800/40 text-emerald-300 text-xs">
          <CheckCircle2 className="w-3.5 h-3.5" /> {successMsg}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {CANONICAL_SECTIONS.map((section) => {
          const pending = pendingBySection[section].length
          const debt = infoDebtBySection[section]
          return (
            <div
              key={section}
              className="p-3 rounded-lg border border-slate-800 bg-slate-950/40"
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0">
                  <p className="text-slate-200 text-sm font-medium">
                    {SECTION_LABELS[section]}
                  </p>
                  <p className="text-slate-500 text-[11px] leading-snug line-clamp-2">
                    {SECTION_DESCRIPTIONS[section]}
                  </p>
                </div>
                <button
                  onClick={() => handleDownload(section)}
                  disabled={downloading === section}
                  className="flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded text-xs bg-indigo-900/30 text-indigo-300 hover:bg-indigo-900/50 disabled:opacity-40 transition-colors"
                  title={`Baixar PDF da seção ${section}`}
                >
                  {downloading === section
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <FileDown className="w-3 h-3" />}
                  PDF
                </button>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                  {pending} pendente{pending === 1 ? '' : 's'}
                </span>
                {debt > 0 && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-800/40"
                    title={`${debt} pergunta(s) com ≥2 rounds ignoradas — viraram dívida no backlog`}
                  >
                    {debt} dívida{debt === 1 ? '' : 's'}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
