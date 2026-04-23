import { useState } from 'react'
import { useOCGDeltaForDocument, type OCGPillarDelta } from '@/hooks/useIngestion'

/**
 * MVP 27 Fase 1 — Impacto do documento no OCG (antes/depois por pilar).
 *
 * Accordion que mostra, quando aberto, o delta concreto que este documento
 * causou no OCG: overall score antes/depois, e cada um dos 7 pilares com
 * score anterior, novo e delta em pontos. Cores: verde = +, vermelho = -,
 * cinza = neutro/não tocado.
 *
 * Lê do endpoint GET /projects/:pid/ingestion/:did/ocg-delta (ingestion_router.py).
 * Backend calcula os deltas a partir dos snapshots em ocg_delta_log — zero
 * lógica de comparação no cliente.
 */

interface Props {
  projectId: string
  documentId: string
  enabled?: boolean
}

const PILLAR_LABELS: Record<number, string> = {
  1: 'P1 Caso de Negócio',
  2: 'P2 Compliance',
  3: 'P3 Escopo',
  4: 'P4 NFR',
  5: 'P5 Arquitetura',
  6: 'P6 Dados',
  7: 'P7 Segurança',
}

function deltaClass(d: number | null | undefined): string {
  if (d === null || d === undefined || d === 0) return 'text-slate-500'
  if (d > 0) return 'text-emerald-400'
  return 'text-red-400'
}

function deltaSymbol(d: number | null | undefined): string {
  if (d === null || d === undefined) return '—'
  if (d === 0) return '—'
  const sign = d > 0 ? '+' : ''
  return `${sign}${d.toFixed(1)} pt`
}

function formatScore(s: number | null | undefined): string {
  if (s === null || s === undefined) return '—'
  return s.toFixed(1)
}

function PillarRow({ p }: { p: OCGPillarDelta }) {
  const label = PILLAR_LABELS[p.pillar] ?? p.key
  return (
    <div className="grid grid-cols-[1.4fr_0.7fr_0.7fr_0.9fr] gap-3 items-center py-1.5 px-3 rounded hover:bg-slate-800/30 text-xs">
      <span className="text-slate-300 font-medium">{label}</span>
      <span className="text-slate-400 tabular-nums text-right">{formatScore(p.score_before)}</span>
      <span className="text-slate-200 tabular-nums text-right">{formatScore(p.score_after)}</span>
      <span className={`tabular-nums text-right font-semibold ${deltaClass(p.delta)}`}>
        {deltaSymbol(p.delta)}
      </span>
    </div>
  )
}

export function OCGDeltaCard({ projectId, documentId, enabled = true }: Props) {
  const [open, setOpen] = useState(false)
  const { data, isLoading, error } = useOCGDeltaForDocument(projectId, documentId, enabled && open)

  const hasDelta = data?.has_delta === true
  const overallDelta = data?.overall_delta ?? null

  const borderClass = !open
    ? 'border-slate-700'
    : !hasDelta
      ? 'border-slate-700'
      : overallDelta !== null && overallDelta > 0
        ? 'border-emerald-500/40'
        : overallDelta !== null && overallDelta < 0
          ? 'border-red-500/40'
          : 'border-slate-700'

  return (
    <div className={`border rounded-lg bg-slate-900/40 ${borderClass}`}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-800/40"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-200">Impacto no OCG</span>
          <span className="text-[10px] text-slate-500">
            (antes × depois por pilar)
          </span>
          {open && hasDelta && overallDelta !== null && (
            <span className={`text-[11px] font-semibold ${deltaClass(overallDelta)}`}>
              Overall {deltaSymbol(overallDelta)}
            </span>
          )}
        </div>
        <span className="text-xs text-slate-400">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-slate-800">
          {isLoading && (
            <div className="text-xs text-slate-500 py-2">Carregando delta...</div>
          )}

          {error && (
            <div className="text-xs text-red-400 py-2">
              Erro ao carregar delta do OCG.
            </div>
          )}

          {!isLoading && !error && data && !hasDelta && (
            <div className="text-xs text-slate-400 py-3 leading-relaxed">
              {data.message ?? 'O OCG ainda não foi atualizado com base neste documento.'}
            </div>
          )}

          {!isLoading && !error && data && hasDelta && (
            <div className="pt-2 space-y-3">
              <div className="flex items-center justify-between bg-slate-800/40 px-3 py-2 rounded">
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-slate-400">
                    v{data.version_from} → <span className="text-slate-200 font-semibold">v{data.version_to}</span>
                  </span>
                  {data.trigger_source && (
                    <span className="text-[10px] px-2 py-0.5 rounded border border-slate-700 text-slate-400">
                      {data.trigger_source}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs tabular-nums">
                  <span className="text-slate-500">Overall</span>
                  <span className="text-slate-400">{formatScore(data.overall_before)}</span>
                  <span className="text-slate-500">→</span>
                  <span className="text-slate-200 font-semibold">{formatScore(data.overall_after)}</span>
                  <span className={`font-semibold ${deltaClass(overallDelta)}`}>
                    {deltaSymbol(overallDelta)}
                  </span>
                </div>
              </div>

              <div>
                <div className="grid grid-cols-[1.4fr_0.7fr_0.7fr_0.9fr] gap-3 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 border-b border-slate-800">
                  <span>Pilar</span>
                  <span className="text-right">Antes</span>
                  <span className="text-right">Depois</span>
                  <span className="text-right">Δ</span>
                </div>
                <div className="divide-y divide-slate-800/60">
                  {(data.pillars ?? []).map(p => (
                    <PillarRow key={p.pillar} p={p} />
                  ))}
                </div>
              </div>

              {data.created_at && (
                <div className="text-[10px] text-slate-600 text-right pt-1">
                  Aplicado em {new Date(data.created_at).toLocaleString('pt-BR')}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
