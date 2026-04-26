/** G4 — Painel de preview do app gerado.
 *
 * Botão "Preparar Ambiente Local" → backend monta comando shell pronto
 * pra owner colar no terminal. Comando faz git clone + docker compose up.
 * Lista sessões anteriores com status reportado pelo owner.
 */
import { useEffect, useState } from 'react'
import { Loader2, Copy, ExternalLink, Terminal, Square, AlertCircle, CheckCircle2 } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface PreviewSession {
  id: string
  project_id: string
  scaffold_run_id: string | null
  port: number | null
  status: 'prepared' | 'running' | 'stopped' | 'error'
  setup_command: string | null
  preview_url: string | null
  repository_url: string | null
  notes: string | null
  created_at: string
  stopped_at: string | null
}

interface Props {
  projectId: string
}

export function PreviewSessionsPanel({ projectId }: Props) {
  const [sessions, setSessions] = useState<PreviewSession[]>([])
  const [loading, setLoading] = useState(true)
  const [preparing, setPreparing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const refresh = async () => {
    try {
      const res = await apiClient.get<PreviewSession[]>(`/projects/${projectId}/preview`)
      setSessions(res.data || [])
    } catch (err: any) {
      // 403 etc — silencia, lista vazia já é útil
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      await refresh()
      if (cancelled) return
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const handlePrepare = async () => {
    setError(null)
    setPreparing(true)
    try {
      await apiClient.post(`/projects/${projectId}/preview/prepare`)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Falha ao preparar preview.')
    } finally {
      setPreparing(false)
    }
  }

  const handleStatusUpdate = async (sessionId: string, newStatus: 'running' | 'stopped') => {
    try {
      await apiClient.patch(`/preview/${sessionId}/status`, { status: newStatus })
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Falha ao atualizar status.')
    }
  }

  const handleCopy = (text: string, sessionId: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(sessionId)
      setTimeout(() => setCopied(null), 2000)
    })
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando previews…
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
        <h3 className="text-slate-200 font-semibold mb-2 flex items-center gap-2">
          <Terminal className="w-4 h-4 text-emerald-400" /> Preview do app gerado
        </h3>
        <p className="text-slate-400 text-sm mb-3">
          GCA monta o comando shell pra subir o app gerado no seu computador local.
          Você cola no terminal, o app sobe em <code className="text-violet-400">localhost</code>,
          e o navegador abre. Requer <code className="text-violet-400">docker</code> +
          <code className="text-violet-400"> git</code> instalados.
        </p>
        <button
          onClick={handlePrepare}
          disabled={preparing}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
        >
          {preparing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Terminal className="w-4 h-4" />}
          Preparar Ambiente Local
        </button>
        {error && (
          <div className="mt-3 bg-red-950/30 border border-red-900/40 rounded px-3 py-2 text-sm text-red-400 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {sessions.length === 0 ? (
        <p className="text-slate-500 text-sm italic">Nenhuma sessão de preview ainda.</p>
      ) : (
        <div className="space-y-3">
          {sessions.map(s => (
            <div
              key={s.id}
              className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                      s.status === 'running'
                        ? 'bg-emerald-900/40 text-emerald-400'
                        : s.status === 'stopped'
                        ? 'bg-slate-800 text-slate-500'
                        : s.status === 'error'
                        ? 'bg-red-900/40 text-red-400'
                        : 'bg-violet-900/40 text-violet-400'
                    }`}
                  >
                    {s.status === 'running' && <CheckCircle2 className="w-3 h-3" />}
                    {s.status}
                  </span>
                  <span className="text-slate-400 text-xs">
                    porta {s.port} · criada {new Date(s.created_at).toLocaleString('pt-BR')}
                  </span>
                </div>
                {s.preview_url && (
                  <a
                    href={s.preview_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-violet-400 hover:text-violet-300 text-xs inline-flex items-center gap-1"
                  >
                    {s.preview_url} <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>

              {s.setup_command && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-slate-400 text-xs uppercase font-semibold">
                      Comando pra rodar (cole no terminal local)
                    </p>
                    <button
                      onClick={() => handleCopy(s.setup_command!, s.id)}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded transition-colors"
                    >
                      <Copy className="w-3 h-3" /> {copied === s.id ? 'Copiado!' : 'Copiar'}
                    </button>
                  </div>
                  <pre className="bg-slate-950 border border-slate-800 rounded p-2 text-xs text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap break-all">
                    {s.setup_command}
                  </pre>
                </div>
              )}

              {s.status === 'prepared' && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleStatusUpdate(s.id, 'running')}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-emerald-700 hover:bg-emerald-600 text-white rounded transition-colors"
                  >
                    <CheckCircle2 className="w-3 h-3" /> App está rodando
                  </button>
                  <button
                    onClick={() => handleStatusUpdate(s.id, 'stopped')}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors"
                  >
                    <Square className="w-3 h-3" /> Parado
                  </button>
                </div>
              )}
              {s.status === 'running' && (
                <button
                  onClick={() => handleStatusUpdate(s.id, 'stopped')}
                  className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors"
                >
                  <Square className="w-3 h-3" /> Parei o container
                </button>
              )}

              {s.notes && (
                <p className="text-slate-500 text-xs italic">{s.notes}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
