import { useState } from 'react'
import { Loader2, X, AlertTriangle, Clock, Sparkles, FileText, Cpu, Info } from 'lucide-react'
import { useTestSpecDetail, type TestSpecType } from '@/hooks/useTestSpecs'

/**
 * MVP 10 Fase 10.5 — Modal de detalhe do TestSpec.
 *
 * Mostra conteúdo markdown em plain text formatado por parágrafos
 * (como o stakeholder pediu) + seção "Como foi criado" com provenance
 * completa: OCG version, questionário, ingestões, LLM, prompt_hash,
 * timestamp.
 *
 * Markdown NÃO é parseado (plain text por escolha do stakeholder —
 * simplicidade + transparência sobre o que o LLM produziu).
 */

const SPEC_TYPE_LABEL: Record<TestSpecType, string> = {
  unit: 'Unitários',
  integration: 'Integração',
  security: 'Segurança',
  compliance: 'Compliance',
  e2e: 'E2E',
}

const SPEC_TYPE_STYLE: Record<TestSpecType, string> = {
  unit: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50',
  integration: 'bg-sky-900/30 text-sky-300 border-sky-700/50',
  security: 'bg-red-900/30 text-red-300 border-red-700/50',
  compliance: 'bg-amber-900/30 text-amber-300 border-amber-700/50',
  e2e: 'bg-violet-900/30 text-violet-300 border-violet-700/50',
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'Rascunho',
  approved: 'Aprovado',
  rejected: 'Rejeitado',
  stale: 'Desatualizado',
}

interface Props {
  projectId: string
  specId: string
  onClose: () => void
}

export function TestSpecModal({ projectId, specId, onClose }: Props) {
  const { data: spec, isLoading, error } = useTestSpecDetail(projectId, specId)
  const [showProvenance, setShowProvenance] = useState(false)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-950 border border-slate-700 rounded-xl max-w-4xl w-full max-h-[92vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-slate-800">
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              Plano de Testes (TestSpec)
            </div>
            {spec ? (
              <>
                <h3 className="text-base font-semibold text-slate-100 truncate">
                  {spec.module_id
                    ? `Módulo · ${spec.provenance?.module_snapshot?.name || 'sem nome'}`
                    : `Global do projeto`}
                </h3>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded border font-medium ${
                      SPEC_TYPE_STYLE[spec.spec_type as TestSpecType] || 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {SPEC_TYPE_LABEL[spec.spec_type as TestSpecType] || spec.spec_type}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {STATUS_LABEL[spec.status] || spec.status}
                  </span>
                  {spec.is_stale && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      Desatualizado
                    </span>
                  )}
                </div>
              </>
            ) : (
              <h3 className="text-base text-slate-400">Carregando…</h3>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {isLoading && (
            <div className="flex items-center justify-center py-16 text-slate-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Carregando spec…
            </div>
          )}

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-3 text-sm text-red-300">
              {(error as any)?.message || 'Erro ao carregar spec.'}
            </div>
          )}

          {spec && !isLoading && !error && (
            <>
              {/* Stale banner */}
              {spec.is_stale && spec.stale_reason && (
                <div className="bg-amber-500/10 border border-amber-500/40 rounded p-3 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                  <div className="text-[12px] text-amber-200">
                    <strong>Desatualizado.</strong> {spec.stale_reason}{' '}
                    Clique "Regenerar" na aba Testes pra alinhar com o OCG atual.
                  </div>
                </div>
              )}

              {/* Rejection reason se houver */}
              {spec.rejection_reason && (
                <div className="bg-red-500/10 border border-red-500/30 rounded p-3">
                  <div className="text-[10px] uppercase tracking-wide text-red-300 mb-1">
                    Motivo da rejeição
                  </div>
                  <p className="text-[12px] text-red-200 leading-relaxed whitespace-pre-wrap">
                    {spec.rejection_reason}
                  </p>
                </div>
              )}

              {/* Content — plain text formatado por parágrafos */}
              <div>
                <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-2">
                  <FileText className="w-3 h-3" />
                  Conteúdo do plano
                </div>
                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                  {spec.content ? (
                    <pre className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-200 font-sans">
                      {spec.content}
                    </pre>
                  ) : (
                    <p className="text-[12px] text-slate-500 italic">(sem conteúdo)</p>
                  )}
                </div>
              </div>

              {/* Provenance */}
              <div className="border border-slate-800 rounded bg-slate-900/30">
                <button
                  type="button"
                  onClick={() => setShowProvenance((v) => !v)}
                  className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-slate-800/40 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Info className="w-3.5 h-3.5 text-violet-400" />
                    <span className="text-sm font-medium text-slate-200">
                      Como este plano foi criado
                    </span>
                    <span className="text-[11px] text-slate-500">
                      (OCG, questionário, ingestões, LLM)
                    </span>
                  </div>
                  <span className="text-xs text-slate-400">{showProvenance ? '▾' : '▸'}</span>
                </button>

                {showProvenance && (
                  <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-800">
                    <ProvenanceField
                      icon={<Clock className="w-3 h-3" />}
                      label="Geração"
                      value={
                        spec.generated_at
                          ? new Date(spec.generated_at).toLocaleString('pt-BR')
                          : '—'
                      }
                    />
                    <ProvenanceField
                      icon={<Cpu className="w-3 h-3" />}
                      label="LLM"
                      value={
                        spec.generator_provider
                          ? `${spec.generator_provider} (${spec.generator_model || 'default'})`
                          : '—'
                      }
                    />
                    <ProvenanceField
                      icon={<Sparkles className="w-3 h-3" />}
                      label="OCG na geração"
                      value={
                        spec.ocg_version_at_generation !== null
                          ? `v${spec.ocg_version_at_generation}${
                              spec.current_ocg_version && spec.current_ocg_version !== spec.ocg_version_at_generation
                                ? ` (atual: v${spec.current_ocg_version})`
                                : ''
                            }`
                          : 'não registrado'
                      }
                      warn={spec.is_stale}
                    />

                    {spec.provenance?.questionnaire_id && (
                      <ProvenanceField
                        icon={<FileText className="w-3 h-3" />}
                        label="Questionário"
                        value={spec.provenance.questionnaire_id.slice(0, 13) + '…'}
                        mono
                      />
                    )}

                    {spec.provenance?.ingested_doc_ids && spec.provenance.ingested_doc_ids.length > 0 && (
                      <ProvenanceField
                        icon={<FileText className="w-3 h-3" />}
                        label={`Documentos considerados (${spec.provenance.ingested_doc_ids.length})`}
                        value={spec.provenance.ingested_doc_ids.map(d => d.slice(0, 8) + '…').join(', ')}
                        mono
                      />
                    )}

                    {spec.provenance?.neighbors_considered && spec.provenance.neighbors_considered.length > 0 && (
                      <ProvenanceField
                        icon={<FileText className="w-3 h-3" />}
                        label={`Módulos vizinhos no prompt (${spec.provenance.neighbors_considered.length})`}
                        value={`${spec.provenance.neighbors_considered.slice(0, 3).map(i => i.slice(0, 8) + '…').join(', ')}${spec.provenance.neighbors_considered.length > 3 ? ` +${spec.provenance.neighbors_considered.length - 3}` : ''}`}
                        mono
                      />
                    )}

                    {spec.provenance?.modules_considered && spec.provenance.modules_considered.length > 0 && (
                      <ProvenanceField
                        icon={<FileText className="w-3 h-3" />}
                        label={`Módulos do Roadmap no prompt (${spec.provenance.modules_considered.length})`}
                        value={`${spec.provenance.modules_considered.slice(0, 3).map(i => i.slice(0, 8) + '…').join(', ')}${spec.provenance.modules_considered.length > 3 ? ` +${spec.provenance.modules_considered.length - 3}` : ''}`}
                        mono
                      />
                    )}

                    {spec.provenance?.prompt_hash && (
                      <ProvenanceField
                        icon={<Cpu className="w-3 h-3" />}
                        label="Hash do prompt"
                        value={spec.provenance.prompt_hash}
                        mono
                      />
                    )}

                    <p className="text-[10px] text-slate-500 italic pt-2 border-t border-slate-800">
                      Este painel mostra exatamente o contexto usado pelo LLM pra gerar o plano — é a origem auditável do conteúdo acima.
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function ProvenanceField({
  icon, label, value, mono, warn,
}: {
  icon: React.ReactNode
  label: string
  value: string
  mono?: boolean
  warn?: boolean
}) {
  return (
    <div className="flex items-start gap-2">
      <div className="text-slate-500 mt-0.5 flex-shrink-0">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
        <div
          className={`text-[12px] ${warn ? 'text-amber-300' : 'text-slate-300'} ${
            mono ? 'font-mono' : ''
          } break-all`}
        >
          {value}
        </div>
      </div>
    </div>
  )
}
