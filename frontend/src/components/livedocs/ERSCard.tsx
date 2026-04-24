import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText, GitCommit, RefreshCw, Loader2, AlertTriangle, CheckCircle2,
  AlertCircle, Sparkles,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'
import { useToast } from '@/hooks/useToast'
import { formatDateTimeBR } from '@/lib/datetime'

// MVP 19 Fase 19.2 — ERS (Especificação de Requisitos de Software)
// vive como arquivo versionado em docs/ERS.md no repositório Git do
// projeto. O GCA gera/regera via endpoint que commita automaticamente.
// Histórico é o git log. Aqui o card mostra:
// - Estado de freshness (nunca gerado, atualizado, desatualizado)
// - Razões pelas quais ficou desatualizado (eventos do pipeline)
// - Último commit (SHA curto) + versão do OCG na época do commit
// - Botão "Regenerar ERS" → dispara commit
// - Nota explicativa quando o projeto não tem repo Git conectado

interface StaleReason {
  event_type: string
  label: string
  since: string
  count: number
}

interface ERSFreshness {
  is_stale: boolean
  ever_generated: boolean
  last_generated_at: string | null
  last_commit_sha: string | null
  last_ocg_version: number | null
  stale_reasons: StaleReason[]
}

interface ERSRegenerateResult {
  success: boolean
  commit_sha: string
  path: string
  ocg_version: number | null
  stale_reasons: string[]
  message: string
}

interface Props {
  projectId: string
}

export function ERSCard({ projectId }: Props) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [lastCommitInfo, setLastCommitInfo] = useState<string | null>(null)

  const { data: freshness, isLoading } = useQuery<ERSFreshness>({
    queryKey: ['ers-freshness', projectId],
    queryFn: async () => {
      const res = await apiClient.get<ERSFreshness>(
        `/projects/${projectId}/docs/ers/freshness`
      )
      return res.data
    },
    refetchInterval: 60_000, // revalida a cada minuto
  })

  const regenerate = useMutation<ERSRegenerateResult, unknown>({
    mutationFn: async () => {
      const res = await apiClient.post<ERSRegenerateResult>(
        `/projects/${projectId}/docs/ers/regenerate`
      )
      return res.data
    },
    onSuccess: (data) => {
      toast.success(`ERS regenerado — commit ${data.commit_sha?.slice(0, 7) || '?'}`)
      setLastCommitInfo(`${data.commit_sha?.slice(0, 7)} · OCG v${data.ocg_version ?? '-'}`)
      queryClient.invalidateQueries({ queryKey: ['ers-freshness', projectId] })
    },
    onError: (err) => {
      toast.error(getErrorMessage(err))
    },
  })

  const regenerating = regenerate.isPending

  // Loading inicial — esqueleto minimalista para não piscar.
  if (isLoading || !freshness) {
    return (
      <section className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          Carregando estado do ERS…
        </div>
      </section>
    )
  }

  // Decide tema visual do card conforme estado.
  const theme = !freshness.ever_generated
    ? {
        border: 'border-slate-700',
        bg: 'bg-slate-900/40',
        icon: <AlertCircle className="w-5 h-5 text-slate-400" />,
        status: 'Nunca gerado',
        statusColor: 'text-slate-300',
      }
    : freshness.is_stale
      ? {
          border: 'border-amber-700/50',
          bg: 'bg-amber-950/20',
          icon: <AlertTriangle className="w-5 h-5 text-amber-400" />,
          status: 'Desatualizado',
          statusColor: 'text-amber-300',
        }
      : {
          border: 'border-emerald-800/40',
          bg: 'bg-emerald-950/10',
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-400" />,
          status: 'Atualizado',
          statusColor: 'text-emerald-300',
        }

  return (
    <section className={`${theme.bg} border ${theme.border} rounded-xl p-4 space-y-3`}>
      {/* Cabeçalho */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          {theme.icon}
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-slate-100 text-sm font-semibold">
                ERS — Especificação de Requisitos de Software
              </h3>
              <span className={`text-[11px] px-2 py-0.5 rounded-full border ${theme.border} ${theme.statusColor}`}>
                {theme.status}
              </span>
            </div>
            <p className="text-slate-500 text-xs mt-1">
              Gerado pelo GCA no padrão IEEE 830. Vive em{' '}
              <code className="text-slate-300 bg-slate-800/60 px-1.5 py-0.5 rounded text-[11px]">
                docs/ERS.md
              </code>{' '}
              no repositório Git do projeto. Histórico: <code className="text-slate-300 text-[11px]">git log -p docs/ERS.md</code>.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => regenerate.mutate()}
          disabled={regenerating}
          className="flex items-center gap-2 text-xs px-3 py-2 rounded bg-violet-600/30 border border-violet-500/40 text-violet-100 hover:bg-violet-600/50 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
          title="Regenera o ERS e commita docs/ERS.md no repositório do projeto"
        >
          {regenerating ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Regenerando…
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              {freshness.ever_generated ? 'Regenerar ERS' : 'Gerar ERS'}
            </>
          )}
        </button>
      </div>

      {/* Info do último commit */}
      {freshness.ever_generated && (
        <div className="flex items-center gap-2 text-[11px] text-slate-500 pt-1 border-t border-slate-800/60 flex-wrap">
          <GitCommit className="w-3.5 h-3.5" />
          <span>
            Último commit: <code className="text-slate-300 bg-slate-800/60 px-1 rounded">{freshness.last_commit_sha?.slice(0, 7) || '—'}</code>
          </span>
          {freshness.last_ocg_version !== null && (
            <span>
              · OCG v{freshness.last_ocg_version}
            </span>
          )}
          {freshness.last_generated_at && (
            <span>
              · {formatDateTimeBR(freshness.last_generated_at)}
            </span>
          )}
          {lastCommitInfo && (
            <span className="text-emerald-400">· {lastCommitInfo} (desta sessão)</span>
          )}
        </div>
      )}

      {/* Lista de razões stale */}
      {freshness.is_stale && freshness.stale_reasons.length > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded p-2.5">
          <p className="text-amber-200 text-[11px] font-medium mb-1.5">
            Eventos desde o último regen que afetam o ERS:
          </p>
          <ul className="space-y-0.5">
            {freshness.stale_reasons.map((r) => (
              <li key={r.event_type} className="text-amber-300/80 text-[11px] flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-amber-400" />
                {r.label}
                {r.count > 1 && <span className="text-amber-500/70">×{r.count}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Nota para primeiro uso */}
      {!freshness.ever_generated && (
        <div className="bg-slate-800/30 border border-slate-700/40 rounded p-2.5 text-[11px] text-slate-400">
          <FileText className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />
          Gerar o ERS pela primeira vez criará o arquivo{' '}
          <code className="bg-slate-800 px-1 rounded">docs/ERS.md</code> no repositório do projeto com um commit canônico.
          Pré-requisito: repositório Git conectado em{' '}
          <strong>Configurações → Repositório</strong>.
        </div>
      )}

      {/* Mensagem de erro da última tentativa */}
      {regenerate.isError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded p-2.5 text-[11px] text-red-300">
          {getErrorMessage(regenerate.error)}
        </div>
      )}
    </section>
  )
}
