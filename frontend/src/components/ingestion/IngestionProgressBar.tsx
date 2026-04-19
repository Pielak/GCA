import { useEffect, useState } from 'react'
import type { ArguiderStage } from '@/hooks/useIngestion'

/**
 * MVP 8 Fase 1 — barra de progresso real do pipeline de ingestão.
 *
 * Substitui o status textual "Processando" estático por barra com:
 *  - porcentagem vinda do backend (bucket por estágio)
 *  - texto do estágio atual em português
 *  - relógio de tempo decorrido no estágio (evidência de que está vivo)
 *
 * Sem animação fake — a barra só avança quando o backend atualiza a
 * coluna `arguider_progress_percent`. Isso evita a falsa percepção de
 * progresso quando na verdade o pipeline está travado.
 */

interface Props {
  stage: ArguiderStage | undefined
  percent: number
  stageUpdatedAt: string | null
}

const STAGE_LABELS: Record<ArguiderStage, string> = {
  queued: 'Na fila',
  extracting_text: 'Extraindo texto',
  analyzing: 'Analisando com IA',
  updating_ocg: 'Atualizando OCG',
  regenerating_backlog: 'Regenerando backlog',
  completed: 'Concluído',
  failed: 'Falhou',
}

function formatElapsed(iso: string | null): string {
  if (!iso) return ''
  const started = new Date(iso).getTime()
  const elapsed = Math.max(0, Date.now() - started)
  const s = Math.floor(elapsed / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  return `${m}m${rem.toString().padStart(2, '0')}s`
}

export function IngestionProgressBar({ stage, percent, stageUpdatedAt }: Props) {
  const [, forceTick] = useState(0)

  // Re-renderiza a cada 1s só pra atualizar o relógio de tempo decorrido.
  // Não chama API — só troca texto do relógio local.
  useEffect(() => {
    const id = setInterval(() => forceTick(v => v + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const label = stage ? STAGE_LABELS[stage] : 'Processando'
  const clamped = Math.min(100, Math.max(0, percent))
  const elapsed = formatElapsed(stageUpdatedAt)

  return (
    <div className="w-full">
      <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-amber-500 transition-all duration-500 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className="flex items-center justify-between mt-1 text-[10px] text-slate-500">
        <span>{label}</span>
        <span className="tabular-nums">
          {clamped}%{elapsed ? ` · ${elapsed}` : ''}
        </span>
      </div>
    </div>
  )
}
