import { useState } from 'react'
import { useExtractionReport } from '@/hooks/useIngestion'

/**
 * MVP 8 Fase 5 — relatório de extração.
 *
 * Card expansível que mostra o que o pipeline entendeu do documento:
 * parágrafos, tabelas, camadas PDF usadas, primeiros RFs/RNFs/módulos
 * detectados. Permite o GP confirmar se o doc foi bem interpretado
 * ANTES de investir tokens do Arguidor em cima de texto mal extraído.
 *
 * Se warnings estão presentes, o card fica amarelo (at_risk). Se o
 * extractor falhou em todas as camadas (ok=false), fica vermelho.
 */

interface Props {
  projectId: string
  documentId: string
  /** Permite esconder o card quando o doc está em pending/processing
   *  (não faz sentido mostrar report antes da extração terminar). */
  enabled?: boolean
}

function Stat({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${warn ? 'text-amber-400' : 'text-slate-200'}`}>
        {value}
      </span>
    </div>
  )
}

function Chip({ text, color = 'slate' }: { text: string; color?: 'slate' | 'violet' | 'emerald' | 'amber' }) {
  const palette: Record<string, string> = {
    slate: 'bg-slate-800/60 text-slate-300 border-slate-700',
    violet: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
    emerald: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
    amber: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[11px] border ${palette[color]}`}>
      {text}
    </span>
  )
}

export function ExtractionReportCard({ projectId, documentId, enabled = true }: Props) {
  const [open, setOpen] = useState(false)
  const { data: report, isLoading, error } = useExtractionReport(projectId, documentId, enabled && open)

  // Borda colorida por severidade do resultado
  const borderClass = !open
    ? 'border-slate-700'
    : report && !report.ok
      ? 'border-red-500/40'
      : report && report.warnings.length > 0
        ? 'border-amber-500/40'
        : 'border-emerald-500/30'

  return (
    <div className={`border rounded-lg bg-slate-900/40 ${borderClass}`}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-800/40"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-200">Relatório de extração</span>
          <span className="text-[10px] text-slate-500">
            (o que o GCA entendeu do documento)
          </span>
        </div>
        <span className="text-xs text-slate-400">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-3 border-t border-slate-800">
          {isLoading && (
            <p className="text-xs text-slate-500 py-2">Calculando relatório…</p>
          )}

          {error && (
            <p className="text-xs text-red-400 py-2">
              Falha ao gerar relatório: {(error as any)?.message || 'erro desconhecido'}
            </p>
          )}

          {report && (
            <>
              {!report.ok && (
                <div className="bg-red-500/10 border border-red-500/30 rounded p-2">
                  <p className="text-xs text-red-300 font-medium">
                    Nenhum texto foi extraído deste documento.
                  </p>
                  <p className="text-[11px] text-red-300/70 mt-1">
                    O Arguidor vai operar sobre conteúdo vazio — considere
                    reenviar o arquivo em outro formato.
                  </p>
                </div>
              )}

              {/* Estatísticas */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <Stat label="Caracteres" value={report.chars.toLocaleString('pt-BR')} />
                <Stat label="Parágrafos" value={report.paragraphs} />
                <Stat
                  label="Tabelas detectadas"
                  value={report.tables_detected}
                  warn={report.file_type === 'docx' && report.tables_detected === 0 && report.chars > 5000}
                />
                <Stat label="Caixas de texto" value={report.text_boxes} />

                {report.file_type === 'pdf' && (
                  <>
                    <Stat label="Camadas PDF usadas" value={report.pdf_layers.join(', ') || '—'} />
                    <Stat label="Páginas com texto" value={report.pdf_pages_with_text} />
                    <Stat label="Campos AcroForm" value={report.acroform_fields} />
                  </>
                )}
                {report.file_type !== 'pdf' && (
                  <Stat label="Headers/Footers" value={report.headers_footers} />
                )}
              </div>

              {/* RFs / RNFs / Módulos detectados */}
              {report.requirements_functional.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    Requisitos funcionais detectados (primeiros {report.requirements_functional.length})
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {report.requirements_functional.map(rf => (
                      <Chip key={rf} text={rf} color="violet" />
                    ))}
                  </div>
                </div>
              )}

              {report.requirements_non_functional.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    Requisitos não-funcionais detectados
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {report.requirements_non_functional.map(rnf => (
                      <Chip key={rnf} text={rnf} color="emerald" />
                    ))}
                  </div>
                </div>
              )}

              {report.module_hints.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    Módulos sugeridos pelo texto
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {report.module_hints.map((m, i) => (
                      <Chip key={i} text={m} />
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {report.warnings.length > 0 && (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wide text-amber-300 mb-1">
                    Avisos do pipeline
                  </div>
                  <ul className="text-[11px] text-amber-200/90 space-y-0.5 list-disc list-inside">
                    {report.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Preview de texto */}
              {report.text_sample && (
                <details className="text-[11px] text-slate-400">
                  <summary className="cursor-pointer text-slate-500">Preview (500 chars)</summary>
                  <pre className="mt-1 p-2 bg-slate-950/60 rounded overflow-x-auto whitespace-pre-wrap font-mono text-[10px] text-slate-300">
                    {report.text_sample}
                  </pre>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
