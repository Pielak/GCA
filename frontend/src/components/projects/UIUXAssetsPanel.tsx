import { useState, useRef, useEffect } from 'react'
import {
  Loader2, Upload, Image as ImageIcon, FileCode, Palette, CheckCircle2, AlertCircle, ExternalLink,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

/**
 * UIUXAssetsPanel — caminho pragmático para popular `design_tokens` do OCG.
 *
 * Substitui o DesignTokensEditor de campo manual (dev/tech lead não preenche
 * paletas hex à mão). 3 vetores complementares:
 *   1. Upload de logomarca (PNG/SVG/JPG/WebP até 2MB).
 *   2. Upload de CSS (até 1MB) — backend extrai paleta+tipografia via regex.
 *   3. Templates planos (slate/violet/emerald) — fallback quando cliente
 *      não tem identidade visual ainda.
 *
 * Para projetos puramente backend/sistemas sem UI, basta não usar nada.
 * Para identidade rica, ingerir doc UI/UX completo pela aba Ingestão —
 * personas UX/UI consolidam em STACK_RECOMMENDATION.frontend.design_tokens.
 */

interface Props {
  projectId: string
}

interface Tokens {
  palette?: { top?: string[]; by_role?: Record<string, string> }
  typography?: { families?: string[]; sizes_px?: number[] }
  source?: string
  generated_at?: string
}

const TEMPLATES = [
  { id: 'plain_slate',   label: 'Slate (corporativo neutro)',  swatch: ['#0f172a', '#475569', '#334155'] },
  { id: 'plain_violet',  label: 'Violet (tech moderno)',       swatch: ['#7c3aed', '#a78bfa', '#0f0f1a'] },
  { id: 'plain_emerald', label: 'Emerald (saúde/financeiro)',  swatch: ['#10b981', '#34d399', '#064e3b'] },
] as const

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => {
      const result = r.result as string
      // remove "data:image/png;base64,"
      resolve(result.split(',')[1] || '')
    }
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

export default function UIUXAssetsPanel({ projectId }: Props) {
  const [tokens, setTokens] = useState<Tokens>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string>('')
  const [success, setSuccess] = useState<string>('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [cssText, setCssText] = useState<string>('')
  const [cssFile, setCssFile] = useState<File | null>(null)
  const logoRef = useRef<HTMLInputElement>(null)
  const cssRef = useRef<HTMLInputElement>(null)

  const loadTokens = async () => {
    try {
      const r = await apiClient.get(`/projects/${projectId}/ocg/design-tokens`)
      setTokens(r.data?.design_tokens || {})
    } catch { /* ignora */ }
    setLoading(false)
  }
  useEffect(() => { loadTokens() }, [projectId])

  const handleCssFile = async (f: File | null) => {
    setCssFile(f)
    if (f) {
      const text = await f.text()
      setCssText(text.slice(0, 1024 * 1024)) // 1MB max
    }
  }

  const submit = async (apply_template?: string) => {
    setSubmitting(true); setError(''); setSuccess('')
    const body: any = {}
    try {
      if (logoFile) {
        body.logo_filename = logoFile.name
        body.logo_base64 = await fileToBase64(logoFile)
      }
      if (cssText.trim()) {
        body.css_content = cssText
      }
      if (apply_template) body.apply_template = apply_template
      const r = await apiClient.post(`/projects/${projectId}/ui-ux/assets`, body)
      setSuccess(r.data?.message || 'Aplicado.')
      setLogoFile(null); setCssFile(null); setCssText('')
      if (logoRef.current) logoRef.current.value = ''
      if (cssRef.current) cssRef.current.value = ''
      await loadTokens()
    } catch (err: any) {
      setError(err?.response?.data?.detail?.errors?.[0]?.message || getErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const hasAnything =
    !!(tokens.palette?.by_role && Object.keys(tokens.palette.by_role).length) ||
    !!(tokens.palette?.top && tokens.palette.top.length) ||
    !!(tokens.typography?.families && tokens.typography.families.length)

  if (loading) {
    return <div className="text-slate-400 text-sm flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Carregando...</div>
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="text-slate-400 text-sm">
          Configure a identidade visual do projeto sem precisar editar valores hex à mão.
          O CodeGen lê <code className="text-slate-300">STACK_RECOMMENDATION.frontend.design_tokens</code> daqui.
          Para projetos puramente backend, deixe vazio — não bloqueia geração.
        </p>
      </div>

      {/* Estado atual resumido */}
      <div className={`p-3 rounded-lg border ${hasAnything ? 'bg-emerald-900/10 border-emerald-800/40' : 'bg-slate-800/40 border-slate-700'}`}>
        <div className="flex items-center gap-2 mb-2">
          {hasAnything
            ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            : <AlertCircle className="w-4 h-4 text-slate-500" />}
          <span className="text-sm font-medium text-slate-200">
            {hasAnything ? `Identidade visual configurada (source: ${tokens.source || 'unknown'})` : 'Sem identidade visual ainda'}
          </span>
        </div>
        {hasAnything && (
          <div className="space-y-2">
            {tokens.palette?.by_role && Object.keys(tokens.palette.by_role).length > 0 && (
              <div>
                <div className="text-[10px] uppercase text-slate-500 mb-1">Cores por papel</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(tokens.palette.by_role).map(([role, hex]) => (
                    <div key={role} className="flex items-center gap-1.5 text-[11px]">
                      <span className="w-4 h-4 rounded border border-slate-700" style={{ backgroundColor: hex }} />
                      <span className="text-slate-400">{role}:</span>
                      <span className="text-slate-300 font-mono">{hex}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {tokens.typography?.families && tokens.typography.families.length > 0 && (
              <div className="text-xs text-slate-400">
                <span className="text-slate-500">Tipografia: </span>
                {tokens.typography.families.join(', ')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Vetor 1: Logomarca */}
      <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
        <div className="flex items-center gap-2 mb-2">
          <ImageIcon className="w-4 h-4 text-violet-400" />
          <h4 className="text-slate-200 text-sm font-semibold">Logomarca</h4>
          <span className="text-[10px] text-slate-500">PNG/SVG/JPG/WebP até 2MB — opcional</span>
        </div>
        <input ref={logoRef} type="file" accept=".png,.svg,.jpg,.jpeg,.webp"
          onChange={e => setLogoFile(e.target.files?.[0] || null)}
          className="block w-full text-xs text-slate-400 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700"
        />
        {logoFile && (
          <div className="text-[11px] text-slate-500 mt-1">{logoFile.name} · {(logoFile.size / 1024).toFixed(1)}KB</div>
        )}
      </div>

      {/* Vetor 2: CSS */}
      <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
        <div className="flex items-center gap-2 mb-2">
          <FileCode className="w-4 h-4 text-violet-400" />
          <h4 className="text-slate-200 text-sm font-semibold">CSS de identidade</h4>
          <span className="text-[10px] text-slate-500">Backend extrai paleta + tipografia automaticamente</span>
        </div>
        <input ref={cssRef} type="file" accept=".css"
          onChange={e => handleCssFile(e.target.files?.[0] || null)}
          className="block w-full text-xs text-slate-400 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 mb-2"
        />
        <div className="text-[10px] text-slate-600 mb-1">Ou cole inline:</div>
        <textarea value={cssText} onChange={e => setCssText(e.target.value)}
          placeholder=":root { --color-primary: #0f172a; --color-secondary: #475569; ... } body { font-family: 'Inter'; }"
          rows={4}
          className="w-full text-[11px] font-mono bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-300 focus:outline-none focus:border-violet-500"
        />
      </div>

      {/* Botão submit (logo + CSS) */}
      <button
        onClick={() => submit()}
        disabled={submitting || (!logoFile && !cssText.trim())}
        className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
        Aplicar logomarca + CSS
      </button>

      {/* Vetor 3: templates planos */}
      <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
        <div className="flex items-center gap-2 mb-3">
          <Palette className="w-4 h-4 text-violet-400" />
          <h4 className="text-slate-200 text-sm font-semibold">Ou aplique um template plano</h4>
          <span className="text-[10px] text-slate-500">Quando cliente ainda não tem identidade definida</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {TEMPLATES.map(t => (
            <button key={t.id} onClick={() => submit(t.id)} disabled={submitting}
              className="flex items-center gap-2 p-2 rounded border border-slate-700 hover:border-violet-500/50 hover:bg-slate-800/40 disabled:opacity-50">
              <div className="flex gap-0.5">
                {t.swatch.map((c, i) => (
                  <span key={i} className="w-4 h-4 rounded border border-slate-700" style={{ backgroundColor: c }} />
                ))}
              </div>
              <span className="text-xs text-slate-300">{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Vetor 4: doc UI/UX rico */}
      <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700">
        <div className="flex items-start gap-2">
          <ExternalLink className="w-3.5 h-3.5 text-slate-500 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-slate-400">
            Para identidade rica (manual de marca, design system completo, wireframes),
            ingerir documento dedicado pela aba <a href={`/projects/${projectId}/ingestion`} className="text-violet-400 hover:underline">Ingestão</a>.
            Personas UX/UI consolidam em <code className="text-slate-300">STACK_RECOMMENDATION.frontend</code>.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-2 rounded bg-red-950/30 border border-red-900/40 text-xs text-red-400">{error}</div>
      )}
      {success && (
        <div className="p-2 rounded bg-emerald-950/30 border border-emerald-900/40 text-xs text-emerald-400">{success}</div>
      )}

      {/* Editor avançado (DesignTokensEditor antigo) — opt-in */}
      <details className="text-xs text-slate-500" open={showAdvanced} onToggle={(e: any) => setShowAdvanced(e.currentTarget.open)}>
        <summary className="cursor-pointer hover:text-slate-300">Editor avançado (campo a campo)</summary>
        {showAdvanced && (
          <div className="mt-3 p-3 rounded border border-slate-800 bg-slate-900/40">
            <p className="text-[11px] text-slate-500 italic mb-2">Para ajustes finos manuais — geralmente não é necessário.</p>
            <a href="#" onClick={(e) => { e.preventDefault(); window.location.hash = 'design-tokens-legacy' }}
              className="text-violet-400 hover:underline text-xs">Abrir editor legado →</a>
          </div>
        )}
      </details>
    </div>
  )
}
