import { useState, useEffect } from 'react'
import { Loader2, RefreshCw, X, AlertTriangle, FileText } from 'lucide-react'
import { apiClient } from '@/lib/api'

/**
 * MVP 9 Fase 9.2 — Modal de detalhamento on-demand de item do Roadmap.
 *
 * Ao clicar num item, chama endpoint que invoca Ollama do projeto pra
 * gerar what_it_is/prerequisites/missing_inputs/input_examples e seções
 * sugeridas pra template PDF (insumo da Fase 9.5).
 *
 * Cache no backend (details_json em module_candidates). Botão refresh
 * força regeneração.
 */

interface SuggestedField {
  name: string
  from_ocg: string | null
  hint: string | null
}

interface SuggestedSection {
  section: string
  fields: SuggestedField[]
}

interface ModuleDetails {
  what_it_is: string
  prerequisites: string[]
  missing_inputs: string[]
  input_examples: string[]
  suggested_template_sections: SuggestedSection[]
  _cached: boolean
  _generated_at: string | null
  _provider: string | null
  _model: string | null
}

interface Props {
  projectId: string
  moduleId: string
  moduleName: string
  onClose: () => void
}

export function ModuleDetailsModal({ projectId, moduleId, moduleName, onClose }: Props) {
  const [details, setDetails] = useState<ModuleDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = async (refresh: boolean = false) => {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const url = refresh
        ? `/projects/${projectId}/modules/${moduleId}/details?refresh=true`
        : `/projects/${projectId}/modules/${moduleId}/details`
      const res = await apiClient.get<ModuleDetails>(url)
      setDetails(res.data)
    } catch (err: any) {
      const status = err.status
      if (status === 503) {
        setError('Ollama (LLM local) não está configurado para este projeto. Configure em Settings → IA para usar detalhamento on-demand.')
      } else if (status === 404) {
        setError('Módulo não encontrado.')
      } else {
        setError(err.message || 'Erro ao gerar detalhamento.')
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load(false) }, [projectId, moduleId])

  const elapsedLabel = (() => {
    if (!details?._generated_at) return null
    try {
      const ts = new Date(details._generated_at)
      const sec = Math.floor((Date.now() - ts.getTime()) / 1000)
      if (sec < 60) return `há ${sec}s`
      if (sec < 3600) return `há ${Math.floor(sec / 60)}min`
      const days = Math.floor(sec / 86400)
      if (days >= 1) return `há ${days}d`
      return `há ${Math.floor(sec / 3600)}h`
    } catch {
      return null
    }
  })()

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-slate-950 border border-slate-700 rounded-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-slate-800">
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              Detalhamento do item
            </div>
            <h3 className="text-base font-semibold text-slate-100 truncate" title={moduleName}>
              {moduleName}
            </h3>
            {details?._provider && (
              <p className="text-[11px] text-slate-500 mt-1">
                Gerado por {details._provider}
                {details._model ? ` (${details._model})` : ''}
                {details._cached ? ' · cache' : ' · novo'}
                {elapsedLabel ? ` · ${elapsedLabel}` : ''}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1 ml-3">
            <button
              type="button"
              onClick={() => load(true)}
              disabled={loading || refreshing}
              className="p-1.5 rounded text-slate-400 hover:text-violet-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
              title="Regenerar detalhamento (custa uma chamada Ollama)"
            >
              {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800"
              title="Fechar"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading && (
            <div className="flex items-center justify-center py-12 text-slate-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Gerando via Ollama do projeto…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-3 bg-red-500/10 border border-red-500/30 rounded-lg p-4">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}

          {details && !loading && !error && (
            <>
              <Section title="O que é">
                <p className="text-sm text-slate-300 leading-relaxed">
                  {details.what_it_is || '—'}
                </p>
              </Section>

              {details.prerequisites.length > 0 && (
                <Section title="Pré-requisitos">
                  <ul className="text-sm text-slate-300 list-disc list-inside space-y-1">
                    {details.prerequisites.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                </Section>
              )}

              {details.missing_inputs.length > 0 && (
                <Section title="O que falta vir na Ingestão" tone="warning">
                  <ul className="text-sm text-amber-200 list-disc list-inside space-y-1">
                    {details.missing_inputs.map((m, i) => <li key={i}>{m}</li>)}
                  </ul>
                </Section>
              )}

              {details.input_examples.length > 0 && (
                <Section title="Exemplos de documento que viabilizam">
                  <ul className="text-sm text-slate-400 list-disc list-inside space-y-1">
                    {details.input_examples.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </Section>
              )}

              {details.suggested_template_sections.length > 0 && (
                <Section title="Seções do template (preview)" tone="info">
                  <p className="text-[11px] text-slate-500 mb-2 italic">
                    Estas seções entrarão no template PDF a ser gerado na Fase 9.5
                    (em breve). Campos com <span className="text-emerald-400">verde</span> já
                    têm dado no OCG; campos sem dado precisam ser preenchidos pelo GP.
                  </p>
                  <div className="space-y-3">
                    {details.suggested_template_sections.map((s, i) => (
                      <div key={i} className="border border-slate-800 rounded p-3 bg-slate-900/40">
                        <div className="flex items-center gap-2 mb-2">
                          <FileText className="w-3.5 h-3.5 text-slate-500" />
                          <span className="text-xs font-medium text-slate-200">{s.section}</span>
                        </div>
                        <ul className="space-y-1">
                          {s.fields.map((f, fi) => (
                            <li key={fi} className="text-[11px] flex items-start gap-2">
                              <span className="font-mono text-slate-400 min-w-[80px] truncate">{f.name}:</span>
                              <span className={`flex-1 ${f.from_ocg ? 'text-emerald-300' : 'text-amber-300'}`}>
                                {f.from_ocg || (f.hint ? `(faltante — ${f.hint})` : '(faltante)')}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Placeholder para 9.5 */}
              <div className="border border-dashed border-slate-700 rounded p-3 bg-slate-900/30">
                <p className="text-[11px] text-slate-500">
                  📄 <strong>Em breve (Fase 9.5):</strong> botão "Baixar template PDF" (com AcroForm fields,
                  campos pré-preenchidos do OCG e lacunas em cor diferente). GP preenche, faz upload na
                  Ingestão e o item vira "Adicionado" automaticamente.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Section({
  title, children, tone = 'default',
}: {
  title: string
  children: React.ReactNode
  tone?: 'default' | 'warning' | 'info'
}) {
  const titleColor = tone === 'warning' ? 'text-amber-400' : tone === 'info' ? 'text-violet-400' : 'text-slate-400'
  return (
    <div>
      <div className={`text-[10px] uppercase tracking-wide font-medium mb-1.5 ${titleColor}`}>
        {title}
      </div>
      {children}
    </div>
  )
}
