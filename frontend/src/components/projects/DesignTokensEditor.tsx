import { useEffect, useState } from 'react'
import {
  Loader2, Save, AlertTriangle, CheckCircle2, Plus, Trash2, Palette, Type, Ruler,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'
import { formatDateTimeBR } from '@/lib/datetime'

// MVP 25 Fase 25.5 — editor canônico de design tokens.
// Shape espelha `STACK_RECOMMENDATION.frontend.design_tokens` no OCG
// (ver backend app/services/design_tokens.py). Validação é determinística
// no backend — 422 vem inline via errors[].

const ROLE_NAMES = [
  'primary', 'secondary', 'accent', 'success', 'warning', 'danger', 'error',
  'info', 'muted', 'background', 'foreground', 'text', 'surface', 'border',
  'link', 'brand',
]

interface DesignTokens {
  palette?: {
    top?: string[]
    by_role?: Record<string, string>
    unique_count?: number
  }
  typography?: {
    families?: string[]
    sizes_px?: number[]
    weights?: number[]
    line_heights?: number[]
  }
  spacing_px?: number[]
  radii_px?: number[]
  shadows?: string[]
  source?: 'css_ingested' | 'manual' | 'mixed' | null
  generated_at?: string | null
}

interface ValidationError {
  path: string
  message: string
}

interface Props {
  projectId: string
}

export default function DesignTokensEditor({ projectId }: Props) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [version, setVersion] = useState<number>(0)
  const [tokens, setTokens] = useState<DesignTokens>({})
  const [errors, setErrors] = useState<ValidationError[]>([])
  const [successMsg, setSuccessMsg] = useState<string>('')
  const [loadError, setLoadError] = useState<string>('')

  const load = async () => {
    setLoading(true)
    setLoadError('')
    try {
      const r = await apiClient.get(`/projects/${projectId}/ocg/design-tokens`)
      setTokens(r.data.design_tokens || {})
      setVersion(r.data.ocg_version || 0)
    } catch (err: unknown) {
      setLoadError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [projectId])

  const save = async () => {
    setSaving(true)
    setErrors([])
    setSuccessMsg('')
    try {
      const body = { design_tokens: stripEmpty(tokens) }
      const r = await apiClient.put(
        `/projects/${projectId}/ocg/design-tokens`, body,
      )
      setVersion(r.data.ocg_version)
      setTokens(r.data.design_tokens || {})
      setSuccessMsg(
        r.data.applied
          ? `Tokens salvos. OCG agora está na v${r.data.ocg_version}.`
          : 'Nenhuma mudança detectada (payload idêntico ao atual).',
      )
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (detail?.errors && Array.isArray(detail.errors)) {
        setErrors(detail.errors)
      } else {
        setErrors([{ path: '$', message: getErrorMessage(err) }])
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando tokens...
      </div>
    )
  }
  if (loadError) {
    return (
      <div className="p-3 rounded-lg bg-red-900/20 border border-red-800/40 text-red-300 text-sm">
        Falha ao carregar: {loadError}
      </div>
    )
  }

  const sourceLabel = tokens.source || 'não declarado'
  const sourceColor =
    tokens.source === 'css_ingested' ? 'bg-emerald-900/30 text-emerald-300 border-emerald-800/40'
    : tokens.source === 'mixed' ? 'bg-amber-900/30 text-amber-300 border-amber-800/40'
    : tokens.source === 'manual' ? 'bg-violet-900/30 text-violet-300 border-violet-800/40'
    : 'bg-slate-800 text-slate-500 border-slate-700'

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-slate-300 text-sm">
            Paleta, tipografia e escalas canônicas derivadas da Ingestão
            (CSS/SCSS) ou editadas manualmente pelo GP. Alimentam o prompt
            do CodeGen em vez da IA inventar cores e escalas.
          </p>
          <p className="text-slate-500 text-xs mt-1 flex items-center gap-2">
            OCG atual: v{version}
            <span className={`px-1.5 py-0.5 rounded text-[10px] border ${sourceColor}`}>
              source: {sourceLabel}
            </span>
            {tokens.generated_at && (
              <span className="text-slate-600 text-[10px]">
                · {formatDateTimeBR(tokens.generated_at)}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 border border-violet-600/40 text-violet-200 text-sm hover:bg-violet-600/30 disabled:opacity-40"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Salvar tokens
        </button>
      </div>

      {errors.length > 0 && (
        <div className="p-3 rounded-lg bg-red-900/20 border border-red-800/40 text-red-300 text-sm space-y-1">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="w-4 h-4" /> Payload inválido
          </div>
          {errors.map((e, i) => (
            <div key={i} className="text-xs font-mono">
              <span className="text-red-400">{e.path}</span>: {e.message}
            </div>
          ))}
        </div>
      )}

      {successMsg && (
        <div className="p-3 rounded-lg bg-emerald-900/20 border border-emerald-800/40 text-emerald-300 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {successMsg}
        </div>
      )}

      <PaletteSection
        value={tokens.palette || {}}
        onChange={(v) => setTokens({ ...tokens, palette: v })}
      />
      <TypographySection
        value={tokens.typography || {}}
        onChange={(v) => setTokens({ ...tokens, typography: v })}
      />
      <ScalesSection
        spacing={tokens.spacing_px || []}
        radii={tokens.radii_px || []}
        shadows={tokens.shadows || []}
        onChange={(scales) => setTokens({ ...tokens, ...scales })}
      />
    </div>
  )
}

// Remove chaves totalmente vazias para o backend aceitar como "não declarado"
function stripEmpty(t: DesignTokens): DesignTokens {
  const out: DesignTokens = {}
  if (t.palette && !isEmptyPalette(t.palette)) out.palette = t.palette
  if (t.typography && !isEmptyTypo(t.typography)) out.typography = t.typography
  if (t.spacing_px && t.spacing_px.length) out.spacing_px = t.spacing_px
  if (t.radii_px && t.radii_px.length) out.radii_px = t.radii_px
  if (t.shadows && t.shadows.length) out.shadows = t.shadows
  if (t.source) out.source = t.source
  return out
}

function isEmptyPalette(p: NonNullable<DesignTokens['palette']>): boolean {
  return !(p.top && p.top.length) && !(p.by_role && Object.keys(p.by_role).length)
}

function isEmptyTypo(t: NonNullable<DesignTokens['typography']>): boolean {
  return (
    !(t.families && t.families.length)
    && !(t.sizes_px && t.sizes_px.length)
    && !(t.weights && t.weights.length)
    && !(t.line_heights && t.line_heights.length)
  )
}

function Section({ title, icon, subtitle, children }: {
  title: string
  icon: React.ReactNode
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-800">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <p className="text-slate-200 text-sm font-semibold">{title}</p>
      </div>
      <p className="text-slate-500 text-xs mb-3">{subtitle}</p>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

// ─── Palette ────────────────────────────────────────────────────────


function PaletteSection({ value, onChange }: {
  value: NonNullable<DesignTokens['palette']>
  onChange: (v: DesignTokens['palette']) => void
}) {
  const roles = value.by_role || {}
  const top = value.top || []

  return (
    <Section
      title="Paleta"
      icon={<Palette className="w-4 h-4 text-violet-400" />}
      subtitle="Cores por role canônico + cores livres mais usadas."
    >
      <div>
        <p className="text-slate-400 text-sm mb-2">Roles canônicos</p>
        <div className="space-y-1">
          {Object.entries(roles).map(([role, hex]) => (
            <div key={role} className="flex items-center gap-2">
              <div
                className="w-8 h-8 rounded border border-slate-700 flex-shrink-0"
                style={{ backgroundColor: hex }}
              />
              <select
                value={role}
                onChange={(e) => {
                  const nr = { ...roles }
                  delete nr[role]
                  nr[e.target.value] = hex
                  onChange({ ...value, by_role: nr })
                }}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
              >
                {ROLE_NAMES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <input
                type="text"
                value={hex}
                placeholder="#hex"
                onChange={(e) => {
                  onChange({ ...value, by_role: { ...roles, [role]: e.target.value } })
                }}
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm font-mono"
              />
              <button
                onClick={() => {
                  const nr = { ...roles }
                  delete nr[role]
                  onChange({ ...value, by_role: nr })
                }}
                className="text-red-400 hover:text-red-300"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
        <button
          onClick={() => {
            const available = ROLE_NAMES.find((r) => !(r in roles)) || 'primary'
            onChange({ ...value, by_role: { ...roles, [available]: '#7c3aed' } })
          }}
          className="flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200 mt-2"
        >
          <Plus className="w-3 h-3" /> Adicionar role
        </button>
      </div>

      <div className="pt-3 border-t border-slate-800">
        <p className="text-slate-400 text-sm mb-2">Cores mais usadas (top)</p>
        <div className="flex flex-wrap gap-1.5">
          {top.map((c, i) => (
            <span
              key={`${c}-${i}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-700 bg-slate-900 text-slate-300 text-xs font-mono"
            >
              <span
                className="w-3 h-3 rounded-sm border border-slate-700"
                style={{ backgroundColor: c }}
              />
              {c}
              <button
                onClick={() => onChange({ ...value, top: top.filter((_, j) => j !== i) })}
                className="text-slate-500 hover:text-red-400"
              >×</button>
            </span>
          ))}
          <AddHexButton onAdd={(h) => onChange({ ...value, top: [...top, h] })} />
        </div>
      </div>
    </Section>
  )
}

function AddHexButton({ onAdd }: { onAdd: (hex: string) => void }) {
  const [val, setVal] = useState('')
  return (
    <div className="flex items-center gap-1">
      <input
        type="text"
        value={val}
        placeholder="#hex"
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && val.trim()) {
            onAdd(val.trim())
            setVal('')
          }
        }}
        className="w-24 bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-slate-200 text-xs font-mono"
      />
      <button
        onClick={() => { if (val.trim()) { onAdd(val.trim()); setVal('') } }}
        className="text-xs text-violet-300 hover:text-violet-200"
      >+</button>
    </div>
  )
}

// ─── Typography ─────────────────────────────────────────────────────


function TypographySection({ value, onChange }: {
  value: NonNullable<DesignTokens['typography']>
  onChange: (v: DesignTokens['typography']) => void
}) {
  return (
    <Section
      title="Tipografia"
      icon={<Type className="w-4 h-4 text-violet-400" />}
      subtitle="Famílias, escala de tamanhos, pesos e line-heights."
    >
      <StringArrayEditor
        label="Famílias (ordem de preferência)"
        value={value.families || []}
        placeholder="ex: Inter"
        onChange={(arr) => onChange({ ...value, families: arr })}
      />
      <NumberArrayEditor
        label="Tamanhos (px)"
        value={value.sizes_px || []}
        placeholder="ex: 16"
        onChange={(arr) => onChange({ ...value, sizes_px: arr })}
      />
      <NumberArrayEditor
        label="Pesos (múltiplos de 100, 100–1000)"
        value={value.weights || []}
        placeholder="ex: 400"
        onChange={(arr) => onChange({ ...value, weights: arr })}
      />
      <NumberArrayEditor
        label="Line-heights (0.5 a 4.0)"
        value={value.line_heights || []}
        placeholder="ex: 1.5"
        onChange={(arr) => onChange({ ...value, line_heights: arr })}
        step={0.1}
      />
    </Section>
  )
}

// ─── Scales ─────────────────────────────────────────────────────────


function ScalesSection({ spacing, radii, shadows, onChange }: {
  spacing: number[]
  radii: number[]
  shadows: string[]
  onChange: (s: { spacing_px?: number[]; radii_px?: number[]; shadows?: string[] }) => void
}) {
  return (
    <Section
      title="Escalas"
      icon={<Ruler className="w-4 h-4 text-violet-400" />}
      subtitle="Spacing, border-radius e sombras canônicas."
    >
      <NumberArrayEditor
        label="Spacing (px)"
        value={spacing}
        placeholder="ex: 8"
        onChange={(arr) => onChange({ spacing_px: arr })}
      />
      <NumberArrayEditor
        label="Radii (px)"
        value={radii}
        placeholder="ex: 8"
        onChange={(arr) => onChange({ radii_px: arr })}
      />
      <StringArrayEditor
        label="Sombras (string CSS completa)"
        value={shadows}
        placeholder="0 1px 2px rgba(0,0,0,0.05)"
        onChange={(arr) => onChange({ shadows: arr })}
      />
    </Section>
  )
}

// ─── Primitives ─────────────────────────────────────────────────────


function StringArrayEditor({ label, value, placeholder, onChange }: {
  label: string
  value: string[]
  placeholder?: string
  onChange: (arr: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  return (
    <div>
      <p className="text-slate-400 text-sm mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map((v, i) => (
          <span key={`${v}-${i}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300 text-xs">
            {v}
            <button
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              className="text-slate-500 hover:text-red-400"
            >×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && draft.trim()) {
              onChange([...value, draft.trim()])
              setDraft('')
            }
          }}
          className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
        />
        <button
          onClick={() => { if (draft.trim()) { onChange([...value, draft.trim()]); setDraft('') } }}
          className="px-2 py-1 text-xs rounded bg-slate-700 text-slate-200 hover:bg-slate-600"
        >Adicionar</button>
      </div>
    </div>
  )
}

function NumberArrayEditor({ label, value, placeholder, onChange, step = 1 }: {
  label: string
  value: number[]
  placeholder?: string
  onChange: (arr: number[]) => void
  step?: number
}) {
  const [draft, setDraft] = useState('')
  return (
    <div>
      <p className="text-slate-400 text-sm mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map((v, i) => (
          <span key={`${v}-${i}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300 text-xs font-mono">
            {v}
            <button
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              className="text-slate-500 hover:text-red-400"
            >×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="number"
          step={step}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && draft.trim()) {
              const n = Number(draft)
              if (!isNaN(n)) { onChange([...value, n]); setDraft('') }
            }
          }}
          className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm font-mono"
        />
        <button
          onClick={() => {
            const n = Number(draft)
            if (!isNaN(n) && draft.trim()) { onChange([...value, n]); setDraft('') }
          }}
          className="px-2 py-1 text-xs rounded bg-slate-700 text-slate-200 hover:bg-slate-600"
        >Adicionar</button>
      </div>
    </div>
  )
}
