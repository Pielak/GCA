import { useState } from 'react'
import {
  X, Loader2, ChevronDown, ChevronRight, BookOpen,
  AlertTriangle, FileText, Layers, Network,
} from 'lucide-react'
import { useLiveDocDetail, type LiveDocType } from '@/hooks/useLiveDocs'
import { formatDateTimeBR } from '@/lib/datetime'

/**
 * MVP 10 Fase 10.7 — Modal de LiveDoc.
 *
 * Mostra conteúdo completo como texto simples (preserva parágrafos) +
 * provenance collapsible (OCG, LLM, ingestões, prompt_hash) — transparência
 * sobre como a doc foi criada.
 *
 * Sem approve/reject — docs são geradas sob demanda, não passam por
 * workflow de aprovação como TestSpecs (ver Fase 10.6).
 */

const TYPE_META: Record<LiveDocType, { label: string; icon: React.ReactNode; note: string }> = {
  module_doc: {
    label: 'Documentação de módulo',
    icon: <FileText className="w-4 h-4 text-violet-300" />,
    note: 'Gerada via Ollama local (§6.2 baixa criticidade).',
  },
  index: {
    label: 'Índice executivo',
    icon: <BookOpen className="w-4 h-4 text-violet-300" />,
    note: 'Consolidado via Premium (§6.3 alta criticidade).',
  },
  architecture: {
    label: 'Arquitetura',
    icon: <Network className="w-4 h-4 text-violet-300" />,
    note: 'Consolidado via Premium (§6.3 alta criticidade).',
  },
}

interface Props {
  projectId: string
  docId: string
  onClose: () => void
}

export function LiveDocModal({ projectId, docId, onClose }: Props) {
  const { data: doc, isLoading } = useLiveDocDetail(projectId, docId)
  const [provOpen, setProvOpen] = useState(false)

  return (
    <div
      className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-slate-800">
          <div className="flex items-start gap-3">
            {doc && TYPE_META[doc.doc_type]?.icon}
            <div>
              <h2 className="text-slate-100 font-semibold text-base">
                {doc ? TYPE_META[doc.doc_type]?.label || doc.doc_type : 'LiveDoc'}
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {doc ? TYPE_META[doc.doc_type]?.note : '—'}
              </p>
              {doc?.is_stale && (
                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-300">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {doc.stale_reason || 'OCG evoluiu desde a geração — considere regerar.'}
                </div>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 transition-colors"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {isLoading && (
            <div className="flex items-center justify-center py-10 text-slate-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Carregando documento…
            </div>
          )}

          {doc && (
            <>
              {/* Conteúdo */}
              <div className="bg-slate-950/60 border border-slate-800 rounded p-4">
                <div className="flex items-center gap-2 mb-2 text-[11px] text-slate-500 uppercase tracking-wide">
                  <Layers className="w-3 h-3" />
                  Conteúdo
                  <span className="text-slate-600">
                    ({doc.content.length.toLocaleString('pt-BR')} chars)
                  </span>
                </div>
                <pre className="text-[12px] text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                  {doc.content || '(vazio)'}
                </pre>
              </div>

              {/* Provenance */}
              <div className="border border-slate-800 rounded bg-slate-950/40">
                <button
                  type="button"
                  onClick={() => setProvOpen((v) => !v)}
                  className="w-full flex items-center gap-2 px-4 py-2 text-[11px] text-slate-400 uppercase tracking-wide hover:bg-slate-900/40"
                >
                  {provOpen ? (
                    <ChevronDown className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5" />
                  )}
                  Como foi criado (provenance)
                </button>

                {provOpen && (
                  <div className="px-4 pb-4 pt-2 space-y-1.5 text-[11px]">
                    <ProvRow label="Versão do OCG (na geração)" value={doc.ocg_version_at_generation ?? '—'} />
                    <ProvRow label="Versão atual do OCG" value={doc.current_ocg_version ?? '—'} />
                    <ProvRow label="LLM" value={
                      doc.generator_provider
                        ? `${doc.generator_provider} / ${doc.generator_model || '—'}`
                        : '—'
                    } />
                    <ProvRow
                      label="Gerado em"
                      value={doc.generated_at ? formatDateTimeBR(doc.generated_at) : '—'}
                    />
                    {doc.provenance?.questionnaire_id && (
                      <ProvRow label="Questionário" value={doc.provenance.questionnaire_id.slice(0, 8) + '…'} />
                    )}
                    {doc.provenance?.ingested_doc_ids && (
                      <ProvRow
                        label="Documentos ingeridos considerados"
                        value={`${doc.provenance.ingested_doc_ids.length} doc(s)`}
                      />
                    )}
                    {doc.provenance?.neighbors_considered && doc.provenance.neighbors_considered.length > 0 && (
                      <ProvRow
                        label="Módulos vizinhos considerados"
                        value={`${doc.provenance.neighbors_considered.length} módulo(s)`}
                      />
                    )}
                    {doc.provenance?.modules_considered && doc.provenance.modules_considered.length > 0 && (
                      <ProvRow
                        label="Módulos no contexto"
                        value={`${doc.provenance.modules_considered.length} módulo(s)`}
                      />
                    )}
                    {doc.provenance?.prompt_hash && (
                      <ProvRow label="Prompt hash" value={<code className="text-slate-300">{doc.provenance.prompt_hash}</code>} />
                    )}
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

function ProvRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-slate-500 min-w-[210px]">{label}:</span>
      <span className="text-slate-300">{value}</span>
    </div>
  )
}
