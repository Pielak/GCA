import { useState, useEffect } from 'react'
import { Loader2, RefreshCw, X, AlertTriangle, FileText, Download, Sparkles, Globe, ExternalLink } from 'lucide-react'
import api, { apiClient } from '@/lib/api'
import { getErrorMessage, getErrorStatus } from '@/lib/errors'
import { formatDateTimeBR } from '@/lib/datetime'

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

interface ReadinessPayload {
  status: 'ready_for_codegen' | 'partial' | 'needs_input' | 'unknown'
  gaps: string[]
  dependencies_inferred: string[]
  evaluated_at: string | null
  provider: string | null
  model: string | null
}

interface ExternalReferencePayload {
  url: string
  fetched: boolean
  fetched_at?: string
  chars?: number
  error?: string
}

interface ModuleDetails {
  what_it_is: string
  prerequisites: string[]
  missing_inputs: string[]
  input_examples: string[]
  suggested_template_sections: SuggestedSection[]
  readiness?: ReadinessPayload | null
  external_reference?: ExternalReferencePayload | null
  _cached: boolean
  _generated_at: string | null
  _provider: string | null
  _model: string | null
}

const READINESS_BADGE: Record<string, { label: string; cls: string }> = {
  ready_for_codegen: { label: '✓ Pronto pra CodeGen', cls: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300' },
  partial: { label: '◐ Parcial — pode iniciar com ressalvas', cls: 'bg-amber-500/15 border-amber-500/40 text-amber-300' },
  needs_input: { label: '⚠ Precisa de input crítico', cls: 'bg-red-500/15 border-red-500/40 text-red-300' },
  unknown: { label: '? Sem contexto suficiente', cls: 'bg-slate-700/40 border-slate-600 text-slate-400' },
}

// B5 (Decisão GP 3 — 2026-05-04): payload UX construtivo quando módulo
// ainda não foi configurado como concreto. Backend retorna 200 com este
// shape em vez de 404 cego. Frontend renderiza wizard de configuração +
// botão pra criar PFQ pendente.
interface NotConfiguredPayload {
  module_status: 'not_configured'
  module_id: string
  project_id: string
  message: string
  raw_error?: string
  suggested_personas: string[]
  suggested_question_text: string
  setup_instructions: string
}

interface Props {
  projectId: string
  moduleId: string
  moduleName: string
  onClose: () => void
}

export function ModuleDetailsModal({ projectId, moduleId, moduleName, onClose }: Props) {
  const [details, setDetails] = useState<ModuleDetails | null>(null)
  const [notConfigured, setNotConfigured] = useState<NotConfiguredPayload | null>(null)
  const [creatingPfq, setCreatingPfq] = useState(false)
  const [pfqCreated, setPfqCreated] = useState<{ pfq_id: string; persona_id: string } | null>(null)
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
      const res = await apiClient.get<ModuleDetails | NotConfiguredPayload>(url)
      // B5: backend pode retornar 200 com module_status='not_configured'
      // (UX construtivo) em vez de 404 cego.
      if ((res.data as NotConfiguredPayload).module_status === 'not_configured') {
        setNotConfigured(res.data as NotConfiguredPayload)
        setDetails(null)
      } else {
        setDetails(res.data as ModuleDetails)
        setNotConfigured(null)
      }
    } catch (err: unknown) {
      // 503 e outros erros reais — repassar mensagem
      setError(getErrorMessage(err))
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
              Gerando detalhamento via LLM do projeto…
            </div>
          )}

          {/* B5 — Wizard UX construtivo quando módulo não está configurado */}
          {notConfigured && !loading && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
                <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 text-sm text-amber-200 leading-relaxed">
                  {notConfigured.message}
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Como configurar</h4>
                <pre className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
                  {notConfigured.setup_instructions}
                </pre>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Persona(s) sugerida(s)</h4>
                <div className="flex flex-wrap gap-2 mb-3">
                  {notConfigured.suggested_personas.map(p => (
                    <span key={p} className="px-2 py-1 bg-violet-500/20 border border-violet-500/40 rounded text-xs text-violet-200 font-mono">
                      {p}
                    </span>
                  ))}
                </div>
                <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Pergunta sugerida</h4>
                <p className="text-sm text-slate-300 leading-relaxed mb-3">
                  {notConfigured.suggested_question_text}
                </p>
                {pfqCreated ? (
                  <div className="bg-emerald-500/10 border border-emerald-500/30 rounded p-3">
                    <p className="text-sm text-emerald-300">
                      ✓ Pergunta criada para persona <strong>{pfqCreated.persona_id}</strong>.
                      Acompanhe em "Questões em Aberto".
                    </p>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={creatingPfq}
                    onClick={async () => {
                      setCreatingPfq(true)
                      try {
                        const res = await apiClient.post<{ pfq_id: string; persona_id: string }>(
                          `/projects/${projectId}/modules/${moduleId}/clarification-request`,
                          {
                            persona_id: notConfigured.suggested_personas[0],
                            question_text: notConfigured.suggested_question_text,
                            context: `Roadmap clarification — item "${moduleName}"`,
                          },
                        )
                        setPfqCreated(res.data)
                      } catch (err) {
                        setError(getErrorMessage(err))
                      } finally {
                        setCreatingPfq(false)
                      }
                    }}
                    className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm text-white font-medium transition-colors"
                    aria-label={`Gerar pergunta para persona ${notConfigured.suggested_personas[0]}`}
                  >
                    {creatingPfq
                      ? <span className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Criando...</span>
                      : `Gerar pergunta em Questões em Aberto (${notConfigured.suggested_personas[0]})`}
                  </button>
                )}
              </div>
            </div>
          )}

          {error && !notConfigured && (
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

              {/* MVP 9 Fase 9.2.ext — WebFetch curado */}
              <ExternalReferenceBlock
                projectId={projectId}
                moduleId={moduleId}
                external={details.external_reference ?? null}
                onChanged={() => load(true)}
              />

              {/* MVP 9 Fase 9.3 — Avaliação Premium de readiness */}
              <ReadinessBlock
                projectId={projectId}
                moduleId={moduleId}
                readiness={details.readiness ?? null}
                onChanged={() => load(false)}
              />

              {/* MVP 9 Fase 9.5.1 — Download do template PDF AcroForm */}
              <div className="border border-violet-500/30 rounded-lg p-4 bg-violet-950/10">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex-1 min-w-[260px]">
                    <p className="text-sm font-medium text-violet-200 flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      Template PDF para preencher
                    </p>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      PDF com AcroForm fields. <span className="text-emerald-300">Verde</span> = já preenchido pelo OCG.
                      <span className="text-amber-300"> Amarelo</span> = lacuna pra você responder.
                      Após preencher, faça upload na aba <strong>Ingestão</strong> — o item será vinculado automaticamente.
                    </p>
                  </div>
                  <DownloadTemplateButton projectId={projectId} moduleId={moduleId} moduleName={moduleName} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function DownloadTemplateButton({
  projectId, moduleId, moduleName,
}: { projectId: string; moduleId: string; moduleName: string }) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handle = async () => {
    setDownloading(true)
    setError(null)
    try {
      const res = await api.get(
        `/projects/${projectId}/modules/${moduleId}/template.pdf`,
        { responseType: 'blob' },
      )
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const safeName = moduleName.replace(/[^a-zA-Z0-9-_]/g, '_').slice(0, 40)
      a.download = `gca-template-${safeName}-${moduleId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: unknown) {
      const status = getErrorStatus(err)
      if (status === 503) {
        setError('Ollama não configurado. Configure em Settings → IA.')
      } else {
        setError(getErrorMessage(err))
      }
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={handle}
        disabled={downloading}
        className="flex items-center gap-2 text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
        {downloading ? 'Gerando…' : 'Baixar template PDF'}
      </button>
      {error && (
        <span className="text-[10px] text-red-300 max-w-[200px] text-right">{error}</span>
      )}
    </div>
  )
}

function ExternalReferenceBlock({
  projectId, moduleId, external, onChanged,
}: {
  projectId: string
  moduleId: string
  external: ExternalReferencePayload | null
  onChanged: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [urlInput, setUrlInput] = useState(external?.url || '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const save = async (urlValue: string | null) => {
    setBusy(true); setErr(null)
    try {
      await api.put(
        `/projects/${projectId}/modules/${moduleId}/external-reference`,
        { url: urlValue },
      )
      setEditing(false)
      onChanged()
    } catch (e: unknown) {
      setErr(getErrorMessage(e))
    } finally { setBusy(false) }
  }

  const fetchNow = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/projects/${projectId}/modules/${moduleId}/fetch-external`)
      onChanged()
    } catch (e: unknown) {
      const det = getErrorMessage(e)
      setErr(det || 'Falha no fetch.')
    } finally { setBusy(false) }
  }

  // Sem URL declarada: oferece input
  if (!external && !editing) {
    return (
      <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/30">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-[260px]">
            <p className="text-sm font-medium text-slate-300 flex items-center gap-2">
              <Globe className="w-4 h-4 text-slate-500" />
              Documentação externa (opcional)
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              Se este item se refere a uma API/serviço com doc pública (ex: DataJud, gov.br),
              declare a URL aqui. O conteúdo enriquece o detalhamento via Ollama.
              GCA <strong>não navega autonomamente</strong> — só URLs declaradas.
            </p>
          </div>
          <button
            type="button"
            onClick={() => { setUrlInput(''); setEditing(true) }}
            className="text-xs px-3 py-1.5 rounded border border-slate-600 hover:border-slate-400 text-slate-300 hover:text-slate-100"
          >
            Declarar URL
          </button>
        </div>
      </div>
    )
  }

  if (editing) {
    return (
      <div className="border border-violet-500/40 rounded-lg p-4 bg-violet-950/10">
        <p className="text-sm font-medium text-violet-200 flex items-center gap-2 mb-2">
          <Globe className="w-4 h-4" />
          URL da documentação externa
        </p>
        <input
          type="url"
          value={urlInput}
          onChange={e => setUrlInput(e.target.value)}
          placeholder="https://..."
          className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:border-violet-500 focus:outline-none"
        />
        <div className="flex gap-2 mt-3 justify-end">
          <button
            type="button"
            onClick={() => { setEditing(false); setErr(null); setUrlInput(external?.url || '') }}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded text-slate-400 hover:text-slate-200"
          >
            Cancelar
          </button>
          {external?.url && (
            <button
              type="button"
              onClick={() => save(null)}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded border border-red-500/40 text-red-300 hover:bg-red-500/10"
            >
              Remover URL
            </button>
          )}
          <button
            type="button"
            onClick={() => save(urlInput.trim() || null)}
            disabled={busy || !urlInput.trim()}
            className="text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Salvar URL'}
          </button>
        </div>
        {err && <p className="text-[10px] text-red-300 mt-2">{err}</p>}
      </div>
    )
  }

  // Tem URL — mostra estado e oferece fetch/edit
  const isError = !!external?.error
  const isFetched = !!external?.fetched
  return (
    <div className={`border rounded-lg p-4 ${
      isError ? 'border-red-500/40 bg-red-950/10' :
      isFetched ? 'border-emerald-500/30 bg-emerald-950/10' :
      'border-slate-700 bg-slate-900/30'
    }`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-[260px]">
          <p className="text-sm font-medium flex items-center gap-2 text-slate-200">
            <Globe className="w-4 h-4" />
            Documentação externa
          </p>
          <a
            href={external?.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-violet-300 hover:text-violet-200 inline-flex items-center gap-1 mt-1 break-all"
          >
            {external?.url}
            <ExternalLink className="w-3 h-3 flex-shrink-0" />
          </a>
          {isFetched && external?.chars && (
            <p className="text-[10px] text-emerald-300 mt-1">
              ✓ {external.chars.toLocaleString('pt-BR')} chars extraídos
              {external.fetched_at && ` · ${formatDateTimeBR(external.fetched_at)}`}
              {' · '}injetados no detalhamento
            </p>
          )}
          {isError && (
            <p className="text-[10px] text-red-300 mt-1">
              ⚠ {external.error}
            </p>
          )}
          {!isFetched && !isError && (
            <p className="text-[10px] text-slate-500 mt-1">
              URL declarada mas não baixada ainda. Clique "Fetch agora" pra puxar e enriquecer detalhamento.
            </p>
          )}
        </div>
        <div className="flex gap-1.5 flex-col">
          <button
            type="button"
            onClick={fetchNow}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50 flex items-center gap-1"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            {isFetched ? 'Re-baixar' : 'Fetch agora'}
          </button>
          <button
            type="button"
            onClick={() => { setUrlInput(external?.url || ''); setEditing(true) }}
            disabled={busy}
            className="text-xs px-2 py-1 rounded text-slate-400 hover:text-slate-200"
          >
            Editar
          </button>
        </div>
      </div>
      {err && <p className="text-[10px] text-red-300 mt-2">{err}</p>}
    </div>
  )
}

function ReadinessBlock({
  projectId, moduleId, readiness, onChanged,
}: {
  projectId: string
  moduleId: string
  readiness: ReadinessPayload | null
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const evaluate = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/projects/${projectId}/modules/${moduleId}/evaluate-readiness`)
      onChanged()
    } catch (e: unknown) {
      const status = getErrorStatus(e)
      if (status === 503) {
        setErr('Provider Premium não configurado. Configure Anthropic ou OpenAI em Settings → IA.')
      } else if (status === 403) {
        setErr('Sem permissão. GP do projeto precisa disparar.')
      } else {
        setErr(getErrorMessage(e))
      }
    } finally { setBusy(false) }
  }

  if (!readiness) {
    return (
      <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/40">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-medium text-slate-200 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-300" />
              Avaliação Premium pendente
            </p>
            <p className="text-[11px] text-slate-400 mt-1">
              Provider Premium ainda não avaliou se este item tem informação
              suficiente pra CodeGen. Roda automaticamente após item virar
              "Adicionado", ou clique pra forçar.
            </p>
          </div>
          <button
            type="button"
            onClick={evaluate}
            disabled={busy}
            className="flex items-center gap-2 text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-white font-medium disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {busy ? 'Avaliando…' : 'Avaliar agora'}
          </button>
        </div>
        {err && <p className="text-[10px] text-red-300 mt-2">{err}</p>}
      </div>
    )
  }

  const badge = READINESS_BADGE[readiness.status] || READINESS_BADGE.unknown
  return (
    <div className={`border rounded-lg p-4 ${badge.cls}`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="text-sm font-semibold flex items-center gap-2">
            <Sparkles className="w-4 h-4" />
            {badge.label}
          </p>
          <p className="text-[10px] opacity-70 mt-1">
            avaliado por {readiness.provider}{readiness.model ? ` (${readiness.model})` : ''}
            {readiness.evaluated_at ? ` · ${formatDateTimeBR(readiness.evaluated_at)}` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={evaluate}
          disabled={busy}
          className="text-[11px] px-2 py-1 rounded border border-current opacity-70 hover:opacity-100 disabled:opacity-30"
          title="Re-avaliar (custa nova chamada Premium)"
        >
          {busy ? '…' : 'Re-avaliar'}
        </button>
      </div>

      {readiness.gaps.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] uppercase tracking-wide opacity-70 mb-1">
            Gaps específicos identificados
          </div>
          <ul className="text-xs space-y-0.5 list-disc list-inside opacity-90">
            {readiness.gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}

      {readiness.dependencies_inferred.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] uppercase tracking-wide opacity-70 mb-1">
            Dependências inferidas (outros módulos)
          </div>
          <div className="flex flex-wrap gap-1">
            {readiness.dependencies_inferred.map((d, i) => (
              <span key={i} className="text-[11px] px-2 py-0.5 rounded bg-black/20 border border-current">
                {d}
              </span>
            ))}
          </div>
        </div>
      )}

      {err && <p className="text-[10px] text-red-300 mt-2">{err}</p>}
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
