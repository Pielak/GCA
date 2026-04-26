/** MVP-H — Painel de import nativo de Figma.
 *
 * Owner cola URL Figma + PAT pessoal → backend extrai variables (cores)
 * mapeando pros 16 roles canônicos do MVP 25 + lista frames como specs
 * candidatos a tela do scaffold. PAT vai pro vault, file_key persiste
 * em project_settings setting_type='figma'.
 */
import { useEffect, useState } from 'react'
import { Loader2, ExternalLink, Save, Download, CheckCircle, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface FigmaConfig {
  file_key: string
  has_pat: boolean
  last_imported_at: string | null
  last_status: string | null
}

interface FigmaImportResult {
  file_name: string
  version: string
  palette_by_role: Record<string, string>
  frames: { page_name: string; frame_name: string; suggested_path: string }[]
  raw_variable_count: number
}

interface Props {
  projectId: string
}

export function FigmaImportPanel({ projectId }: Props) {
  const [config, setConfig] = useState<FigmaConfig | null>(null)
  const [loadingConfig, setLoadingConfig] = useState(true)
  const [urlOrKey, setUrlOrKey] = useState('')
  const [pat, setPat] = useState('')
  const [saving, setSaving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<FigmaImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await apiClient.get<FigmaConfig>(
          `/projects/${projectId}/design/figma/config`,
        )
        if (!cancelled) {
          setConfig(res.data)
          setUrlOrKey(res.data.file_key || '')
        }
      } catch (err) {
        // 404 ou outro: deixa config null e form vazio
      } finally {
        if (!cancelled) setLoadingConfig(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const handleSave = async () => {
    setError(null)
    if (!urlOrKey.trim()) {
      setError('Cole URL do Figma ou file_key.')
      return
    }
    if (!pat.trim() || pat.trim().length < 10) {
      setError('PAT inválido (mínimo 10 caracteres).')
      return
    }
    setSaving(true)
    try {
      const res = await apiClient.post<FigmaConfig>(
        `/projects/${projectId}/design/figma/config`,
        { url_or_key: urlOrKey.trim(), pat: pat.trim() },
      )
      setConfig(res.data)
      setPat('')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Falha ao salvar config.')
    } finally {
      setSaving(false)
    }
  }

  const handleImport = async () => {
    setError(null)
    setImportResult(null)
    setImporting(true)
    try {
      const res = await apiClient.post<FigmaImportResult>(
        `/projects/${projectId}/design/figma/import`,
      )
      setImportResult(res.data)
      // Refetch config pra atualizar last_imported_at + last_status
      const cfg = await apiClient.get<FigmaConfig>(
        `/projects/${projectId}/design/figma/config`,
      )
      setConfig(cfg.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Falha ao importar do Figma.')
    } finally {
      setImporting(false)
    }
  }

  if (loadingConfig) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando…
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header com explicação */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
        <h3 className="text-slate-200 font-semibold mb-2 flex items-center gap-2">
          <ExternalLink className="w-4 h-4 text-violet-400" /> Import nativo de Figma
        </h3>
        <p className="text-slate-400 text-sm">
          Cole URL do arquivo Figma + Personal Access Token. O GCA extrai variables (cores)
          mapeando pros 16 roles canônicos (primary, secondary, accent, …) e lista frames
          como specs de tela pro scaffold. PAT é criptografado no vault do projeto.
        </p>
        <a
          href="https://www.figma.com/developers/api#access-tokens"
          target="_blank"
          rel="noopener noreferrer"
          className="text-violet-400 hover:text-violet-300 text-xs inline-flex items-center gap-1 mt-2"
        >
          Como gerar um PAT no Figma <ExternalLink className="w-3 h-3" />
        </a>
      </div>

      {/* Form de configuração */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3">
        <div>
          <label className="text-slate-400 text-xs block mb-1">URL ou file_key Figma</label>
          <input
            type="text"
            value={urlOrKey}
            onChange={e => setUrlOrKey(e.target.value)}
            placeholder="https://www.figma.com/design/abc123def456/Meu-App?node-id=…"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
          />
        </div>
        <div>
          <label className="text-slate-400 text-xs block mb-1">
            Personal Access Token {config?.has_pat && <span className="text-emerald-400">(salvo — re-cole pra trocar)</span>}
          </label>
          <input
            type="password"
            value={pat}
            onChange={e => setPat(e.target.value)}
            placeholder={config?.has_pat ? '•••••••••••• (token salvo)' : 'figd_…'}
            autoComplete="off"
            spellCheck={false}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSave}
            disabled={saving || !urlOrKey.trim() || !pat.trim()}
            className="flex items-center gap-1 px-3 py-2 text-sm bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Salvar Configuração
          </button>
          <button
            onClick={handleImport}
            disabled={importing || !config?.has_pat || !config?.file_key}
            className="flex items-center gap-1 px-3 py-2 text-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
            title={!config?.has_pat ? 'Salve config primeiro' : 'Disparar import via Figma REST API'}
          >
            {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            Importar do Figma
          </button>
        </div>
      </div>

      {/* Status + error */}
      {error && (
        <div className="bg-red-950/30 border border-red-900/40 rounded-lg px-3 py-2 text-sm text-red-400 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
      {config && (config.last_imported_at || config.last_status) && (
        <div className="text-slate-500 text-xs">
          Último import: {config.last_imported_at || '—'} · {config.last_status || ''}
        </div>
      )}

      {/* Resultado do import */}
      {importResult && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-4">
          <div className="flex items-center gap-2 text-slate-200 font-semibold">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            Import concluído — {importResult.file_name} (v{importResult.version})
          </div>

          {/* Palette por role */}
          <div>
            <p className="text-slate-400 text-xs uppercase font-semibold mb-2">
              Palette canônica ({Object.keys(importResult.palette_by_role).length}/16 roles preenchidos)
            </p>
            {Object.keys(importResult.palette_by_role).length === 0 ? (
              <p className="text-slate-500 text-sm italic">
                Nenhuma role detectada. Verifique se o arquivo Figma tem variables COLOR
                com nomes contendo "primary", "secondary", "background" etc.
              </p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {Object.entries(importResult.palette_by_role).map(([role, hex]) => (
                  <div
                    key={role}
                    className="flex items-center gap-2 bg-slate-800/60 border border-slate-700 rounded px-2 py-1.5"
                  >
                    <div
                      className="w-5 h-5 rounded border border-slate-600 flex-shrink-0"
                      style={{ background: hex }}
                    />
                    <div className="min-w-0">
                      <p className="text-slate-300 text-xs font-medium truncate">{role}</p>
                      <p className="text-slate-500 text-[10px] font-mono">{hex}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Frames */}
          <div>
            <p className="text-slate-400 text-xs uppercase font-semibold mb-2">
              Frames ({importResult.frames.length}) — candidatos a tela do scaffold
            </p>
            {importResult.frames.length === 0 ? (
              <p className="text-slate-500 text-sm italic">Nenhum frame top-level encontrado.</p>
            ) : (
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {importResult.frames.map((f, i) => (
                  <div
                    key={`${f.page_name}-${f.frame_name}-${i}`}
                    className="flex items-center justify-between bg-slate-800/40 rounded px-2 py-1 text-xs"
                  >
                    <span className="text-slate-300">
                      <span className="text-slate-500">{f.page_name} /</span> {f.frame_name}
                    </span>
                    <span className="text-violet-400 font-mono">{f.suggested_path}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <p className="text-slate-500 text-xs italic">
            Próxima fase: aplicar palette ao OCG (STACK_RECOMMENDATION.frontend.design_tokens)
            e gerar specs de tela a partir dos frames. Por agora, só preview.
          </p>
        </div>
      )}
    </div>
  )
}
