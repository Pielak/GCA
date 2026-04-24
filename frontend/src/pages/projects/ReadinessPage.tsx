/**
 * ReadinessPage — Definition of Done por projeto.
 *
 * Mostra cada entregável declarado em OCG.DELIVERABLES com status,
 * evidência e ações: re-verificar, atestar manualmente.
 */
import { useEffect, useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import {
  CheckCircle2, XCircle, Clock, Loader2, RefreshCw, FilePen,
  AlertCircle, FileCheck2, Hand, Code, FileText, FlaskConical,
  Settings, MoreHorizontal, Package, Download,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { PageTransition, SkeletonPulse } from '@/components/ui/PipelineProgress'
import { getErrorMessage } from '@/lib/errors'
import { formatDateTimeBR } from '@/lib/datetime'

interface Deliverable {
  id: string
  name: string
  category: string
  kind: string
  status: 'declared' | 'generating' | 'present' | 'verified' | 'waived' | 'missing' | 'manual_only' | 'error'
  evidence_type: string | null
  evidence_ref: string | null
  verification_method: string | null
  last_verified_at: string | null
  verified_by: string | null
  notes: string | null
  auto_verifiable: boolean
}

interface ReadinessPayload {
  deliverables: Deliverable[]
  summary: {
    total_active: number
    total_with_waived: number
    verified: number
    by_status: Record<string, number>
    by_category: Record<string, number>
    readiness_pct: number
  }
}

const statusMeta: Record<Deliverable['status'], { label: string; color: string; icon: React.ComponentType<{ className?: string }> }> = {
  verified:    { label: 'Verificado',     color: 'bg-emerald-900/30 border-emerald-700 text-emerald-300', icon: CheckCircle2 },
  present:     { label: 'Presente',       color: 'bg-blue-900/30 border-blue-700 text-blue-300',         icon: FileCheck2 },
  declared:    { label: 'Declarado',      color: 'bg-slate-800 border-slate-700 text-slate-400',          icon: Clock },
  generating:  { label: 'Gerando',        color: 'bg-violet-900/30 border-violet-700 text-violet-300',   icon: Loader2 },
  manual_only: { label: 'Manual',          color: 'bg-amber-900/30 border-amber-700 text-amber-300',     icon: Hand },
  missing:     { label: 'Faltando',       color: 'bg-red-900/30 border-red-700 text-red-300',            icon: XCircle },
  waived:      { label: 'Dispensado',      color: 'bg-slate-800/50 border-slate-700 text-slate-500',      icon: AlertCircle },
  error:       { label: 'Erro',           color: 'bg-orange-900/30 border-orange-700 text-orange-300',   icon: AlertCircle },
}

const categoryIcon: Record<string, React.ComponentType<{ className?: string }>> = {
  doc: FileText, code: Code, test: FlaskConical, process: Settings, config: Settings, other: MoreHorizontal,
}

interface Release {
  id: string
  version: number
  status: 'generating' | 'ready' | 'failed'
  readiness_pct: number | null
  size_bytes: number | null
  sha256: string | null
  created_at: string | null
  completed_at: string | null
  error_message: string | null
}

const RELEASE_THRESHOLD = 90  // %

export function ReadinessPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [data, setData] = useState<ReadinessPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState(false)
  const [verifyingOne, setVerifyingOne] = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [attestModal, setAttestModal] = useState<Deliverable | null>(null)
  const [releases, setReleases] = useState<Release[]>([])
  const [creatingRelease, setCreatingRelease] = useState(false)
  const [releaseError, setReleaseError] = useState<string | null>(null)

  const load = async () => {
    if (!projectId) return
    try {
      const [statusRes, releasesRes] = await Promise.all([
        apiClient.get(`/projects/${projectId}/deliverables`),
        apiClient.get(`/projects/${projectId}/releases`).catch(() => ({ data: { releases: [] } })),
      ])
      setData(statusRes.data)
      setReleases(releasesRes.data?.releases || [])
    } catch (e) {
      console.error('readiness.load_error', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [projectId])

  const createRelease = async () => {
    if (!projectId || creatingRelease) return
    setCreatingRelease(true)
    setReleaseError(null)
    try {
      const res = await apiClient.post(`/projects/${projectId}/releases`, null, {
        params: { threshold: RELEASE_THRESHOLD },
      })
      // Sucesso: re-fetch lista de releases
      await load()
      // Auto-download do bundle recém-criado
      if (res.data?.version) {
        const dl = `/api/v1/projects/${projectId}/releases/${res.data.version}/download`
        window.open(dl, '_blank')
      }
    } catch (e: unknown) {
      setReleaseError(getErrorMessage(e))
    } finally {
      setCreatingRelease(false)
    }
  }

  const downloadRelease = (version: number) => {
    if (!projectId) return
    window.open(`/api/v1/projects/${projectId}/releases/${version}/download`, '_blank')
  }

  const verifyAll = async () => {
    if (!projectId || verifying) return
    setVerifying(true)
    try {
      await apiClient.post(`/projects/${projectId}/deliverables/verify-all`)
      await load()
    } finally {
      setVerifying(false)
    }
  }

  // DT-056: botão Sync para popular o registry a partir de OCG.DELIVERABLES.
  // Antes a UI dizia "Sincronize do OCG" sem botão — instrução órfã.
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const syncFromOCG = async () => {
    if (!projectId || syncing) return
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await apiClient.post(`/projects/${projectId}/deliverables/sync`, {})
      const c = res.data?.counters || {}
      const inserted = c.inserted ?? 0
      const reactivated = c.reactivated ?? 0
      const waived = c.waived ?? 0
      const kept = c.kept ?? 0
      setSyncMsg(`Sync: +${inserted} novo(s), ${reactivated} reativado(s), ${waived} arquivado(s), ${kept} mantido(s).`)
      await load()
    } catch (e: unknown) {
      setSyncMsg(getErrorMessage(e))
    } finally {
      setSyncing(false)
    }
  }

  const verifyOne = async (deliverableId: string) => {
    if (!projectId) return
    setVerifyingOne(deliverableId)
    try {
      await apiClient.post(`/projects/${projectId}/deliverables/${deliverableId}/verify`)
      await load()
    } finally {
      setVerifyingOne(null)
    }
  }

  const filtered = useMemo(() => {
    if (!data) return []
    if (filterStatus === 'all') return data.deliverables
    return data.deliverables.filter(d => d.status === filterStatus)
  }, [data, filterStatus])

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <SkeletonPulse className="h-8 w-64" />
        <SkeletonPulse className="h-32 w-full rounded-xl" />
        <SkeletonPulse className="h-16 w-full" />
      </div>
    )
  }

  if (!data) {
    return <div className="p-6 text-slate-400">Falha ao carregar dados de readiness.</div>
  }

  const pct = data.summary.readiness_pct
  const pctColor = pct >= 90 ? 'text-emerald-400' : pct >= 70 ? 'text-blue-400' : pct >= 50 ? 'text-amber-400' : 'text-red-400'
  const ringColor = pct >= 90 ? 'stroke-emerald-400' : pct >= 70 ? 'stroke-blue-400' : pct >= 50 ? 'stroke-amber-400' : 'stroke-red-400'

  return (
    <PageTransition>
      <div className="p-6 space-y-6">
        {/* Header + gauge */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <div className="flex items-start justify-between gap-6">
            <div className="flex-1">
              <h1 className="text-xl font-semibold text-slate-100">Definition of Done</h1>
              <p className="text-slate-500 text-sm mt-1">
                Entregáveis declarados em OCG.DELIVERABLES e seu status atual.
                Threshold para Release Bundle: <span className="text-slate-300">90%</span>.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {/* DT-056: botão Sync — extrai DELIVERABLES do OCG e popula o registry */}
                <button
                  onClick={syncFromOCG}
                  disabled={syncing}
                  title="Sincroniza a lista de entregáveis a partir de OCG.DELIVERABLES (Q48 do questionário). Necessário antes do primeiro 'Verificar tudo'."
                  className="flex items-center gap-2 px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 rounded-lg transition-colors"
                >
                  {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  {syncing ? 'Sincronizando…' : 'Sincronizar do OCG'}
                </button>
                <button
                  onClick={verifyAll}
                  disabled={verifying}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg transition-colors"
                >
                  {verifying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  {verifying ? 'Verificando…' : 'Verificar tudo'}
                </button>
                {data && (
                  <button
                    onClick={createRelease}
                    disabled={creatingRelease || data.summary.readiness_pct < RELEASE_THRESHOLD}
                    title={data.summary.readiness_pct < RELEASE_THRESHOLD
                      ? `Readiness ${data.summary.readiness_pct}% < ${RELEASE_THRESHOLD}% — atinja o threshold para liberar`
                      : 'Gerar Release Bundle (zip + manifest + release notes)'}
                    className="flex items-center gap-2 px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                  >
                    {creatingRelease ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Package className="w-3.5 h-3.5" />}
                    {creatingRelease ? 'Gerando bundle…' : 'Gerar Release Bundle'}
                  </button>
                )}
              </div>
              {releaseError && (
                <div className="mt-3 px-3 py-2 bg-red-900/30 border border-red-700 rounded text-xs text-red-300">
                  ⚠ {releaseError}
                </div>
              )}
              {syncMsg && (
                <div className="mt-3 px-3 py-2 bg-slate-800/50 border border-slate-700 rounded text-xs text-slate-300">
                  {syncMsg}
                </div>
              )}
            </div>

            {/* Gauge SVG */}
            <div className="relative flex items-center justify-center w-32 h-32 flex-shrink-0">
              <svg className="w-32 h-32 -rotate-90">
                <circle cx="64" cy="64" r="54" stroke="currentColor" strokeWidth="10" fill="none" className="text-slate-800" />
                <circle
                  cx="64" cy="64" r="54"
                  stroke="currentColor" strokeWidth="10" fill="none"
                  className={ringColor}
                  strokeDasharray={`${(pct / 100) * 339} 339`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={`text-2xl font-bold ${pctColor}`}>{pct.toFixed(0)}%</span>
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Readiness</span>
              </div>
            </div>
          </div>

          {/* Mini-summary */}
          <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap gap-x-6 gap-y-2 text-xs">
            <span className="text-slate-400">
              Total: <span className="text-slate-200 font-semibold">{data.summary.total_active}</span>
            </span>
            <span className="text-emerald-400">
              ✓ Verified: <span className="font-semibold">{data.summary.by_status.verified || 0}</span>
            </span>
            <span className="text-blue-400">
              Present: <span className="font-semibold">{data.summary.by_status.present || 0}</span>
            </span>
            <span className="text-amber-400">
              Manual: <span className="font-semibold">{data.summary.by_status.manual_only || 0}</span>
            </span>
            <span className="text-red-400">
              ✗ Missing: <span className="font-semibold">{data.summary.by_status.missing || 0}</span>
            </span>
            {(data.summary.by_status.error || 0) > 0 && (
              <span className="text-orange-400">
                ⚠ Erro: <span className="font-semibold">{data.summary.by_status.error}</span>
              </span>
            )}
          </div>
        </div>

        {/* Filtros */}
        <div className="flex gap-2 flex-wrap">
          {(['all', 'verified', 'present', 'missing', 'manual_only', 'error', 'declared', 'waived'] as const).map(s => {
            const count = s === 'all' ? data.summary.total_with_waived : (data.summary.by_status[s] || 0)
            const active = filterStatus === s
            return (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={`px-3 py-1 text-xs rounded-md border transition-colors ${
                  active ? 'bg-violet-600 border-violet-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-600'
                }`}
              >
                {s === 'all' ? 'Todos' : statusMeta[s as Deliverable['status']].label} ({count})
              </button>
            )
          })}
        </div>

        {/* Lista */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              {filterStatus === 'all' ? 'Nenhum entregável registrado. Sincronize do OCG.' : 'Nenhum entregável neste filtro.'}
            </div>
          ) : (
            <ul className="divide-y divide-slate-800">
              {filtered.map(d => {
                const meta = statusMeta[d.status]
                const Icon = meta.icon
                const CatIcon = categoryIcon[d.category] || MoreHorizontal
                return (
                  <li key={d.id} className="px-5 py-3 flex items-start gap-3 hover:bg-slate-800/30">
                    <CatIcon className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-slate-200 text-sm font-medium">{d.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 font-mono">{d.kind}</span>
                      </div>
                      {d.evidence_ref && (
                        <div className="text-[11px] text-slate-500 mt-1 truncate">
                          📎 <span className="font-mono">{d.evidence_ref}</span>
                          {d.verification_method && <span className="ml-2 text-slate-600">({d.verification_method})</span>}
                        </div>
                      )}
                      {d.notes && (
                        <div className="text-[11px] text-slate-500 italic mt-1">{d.notes}</div>
                      )}
                      {d.last_verified_at && (
                        <div className="text-[10px] text-slate-600 mt-1">
                          Verificado em {formatDateTimeBR(d.last_verified_at)}
                        </div>
                      )}
                    </div>
                    <div className={`flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] ${meta.color} flex-shrink-0`}>
                      <Icon className={`w-3 h-3 ${d.status === 'generating' ? 'animate-spin' : ''}`} />
                      {meta.label}
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      {d.status !== 'waived' && d.auto_verifiable && (
                        <button
                          onClick={() => verifyOne(d.id)}
                          disabled={verifyingOne === d.id}
                          className="p-1.5 rounded text-slate-500 hover:text-violet-400 hover:bg-violet-900/20 disabled:opacity-50"
                          title="Verificar agora"
                        >
                          {verifyingOne === d.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {d.status !== 'waived' && d.status !== 'verified' && (
                        <button
                          onClick={() => setAttestModal(d)}
                          className="p-1.5 rounded text-slate-500 hover:text-amber-400 hover:bg-amber-900/20"
                          title="Atestar manualmente"
                        >
                          <FilePen className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Releases anteriores */}
        {releases.length > 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-800 flex items-center gap-2">
              <Package className="w-4 h-4 text-emerald-400" />
              <h2 className="text-sm font-semibold text-slate-200">Releases anteriores ({releases.length})</h2>
            </div>
            <ul className="divide-y divide-slate-800">
              {releases.map(r => (
                <li key={r.id} className="px-5 py-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="text-slate-200 text-sm font-mono font-semibold">v{r.version}</span>
                      {r.status === 'ready' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 border border-emerald-700 text-emerald-300">
                          ✓ ready
                        </span>
                      )}
                      {r.status === 'generating' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/30 border border-violet-700 text-violet-300 flex items-center gap-1">
                          <Loader2 className="w-2.5 h-2.5 animate-spin" /> gerando
                        </span>
                      )}
                      {r.status === 'failed' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/30 border border-red-700 text-red-300">
                          ✗ failed
                        </span>
                      )}
                      {r.readiness_pct !== null && (
                        <span className="text-[11px] text-slate-500">
                          readiness: <span className="text-slate-300 font-semibold">{r.readiness_pct}%</span>
                        </span>
                      )}
                      {r.size_bytes && (
                        <span className="text-[11px] text-slate-500">
                          {(r.size_bytes / 1024).toFixed(1)} KB
                        </span>
                      )}
                    </div>
                    {r.created_at && (
                      <div className="text-[10px] text-slate-600 mt-1">
                        {formatDateTimeBR(r.created_at)}
                        {r.sha256 && <span className="ml-3 font-mono">sha256: {r.sha256.slice(0, 12)}…</span>}
                      </div>
                    )}
                    {r.error_message && (
                      <div className="text-[11px] text-red-400 mt-1">⚠ {r.error_message}</div>
                    )}
                  </div>
                  {r.status === 'ready' && (
                    <button
                      onClick={() => downloadRelease(r.version)}
                      className="p-2 rounded text-slate-500 hover:text-emerald-400 hover:bg-emerald-900/20"
                      title="Baixar zip"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Modal de atestação */}
        {attestModal && (
          <AttestModal
            projectId={projectId!}
            deliverable={attestModal}
            onClose={() => setAttestModal(null)}
            onSuccess={async () => { setAttestModal(null); await load() }}
          />
        )}
      </div>
    </PageTransition>
  )
}


function AttestModal({ projectId, deliverable, onClose, onSuccess }: {
  projectId: string
  deliverable: Deliverable
  onClose: () => void
  onSuccess: () => void
}) {
  const [note, setNote] = useState('')
  const [evidenceRef, setEvidenceRef] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!note.trim()) {
      setError('Note é obrigatório')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/deliverables/${deliverable.id}/attest`, {
        note: note.trim(),
        evidence_ref: evidenceRef.trim() || null,
      })
      onSuccess()
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-lg" onClick={e => e.stopPropagation()}>
        <h3 className="text-slate-100 font-semibold text-base mb-1">Atestar entregável</h3>
        <p className="text-slate-500 text-xs mb-4">{deliverable.name}</p>

        <label className="block text-xs text-slate-400 mb-1">Note (obrigatória)</label>
        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          rows={4}
          placeholder="Ex: Aprovado pelo board em 2026-04-15. Acta em #12345."
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600 mb-3"
        />

        <label className="block text-xs text-slate-400 mb-1">Referência de evidência (opcional)</label>
        <input
          type="text"
          value={evidenceRef}
          onChange={e => setEvidenceRef(e.target.value)}
          placeholder="https://wiki/acta-12345 ou caminho/local"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600 mb-4"
        />

        {error && <div className="text-red-400 text-xs mb-3">{error}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">
            Cancelar
          </button>
          <button
            onClick={submit}
            disabled={submitting || !note.trim()}
            className="px-3 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg flex items-center gap-2"
          >
            {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Atestar
          </button>
        </div>
      </div>
    </div>
  )
}
