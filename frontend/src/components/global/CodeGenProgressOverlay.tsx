import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, AlertTriangle, X, ArrowRight, GripVertical } from 'lucide-react'
import { useCodeGenProgressStore } from '@/stores/codeGenProgressStore'

const POS_STORAGE_KEY = 'gca:codegen-overlay-pos'
const OVERLAY_W = 360
const OVERLAY_H_APPROX = 180  // altura típica — usado só pra clamp inicial; flex layout determina o real

interface OverlayPosition {
  x: number  // distância da borda esquerda
  y: number  // distância do topo
}

function loadPersistedPos(): OverlayPosition | null {
  try {
    const raw = localStorage.getItem(POS_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
      return { x: parsed.x, y: parsed.y }
    }
  } catch { /* ignore */ }
  return null
}

function persistPos(pos: OverlayPosition) {
  try {
    localStorage.setItem(POS_STORAGE_KEY, JSON.stringify(pos))
  } catch { /* ignore */ }
}

function defaultPos(): OverlayPosition {
  // Mesma posição visual do antigo `fixed bottom-4 right-4`.
  return {
    x: Math.max(16, window.innerWidth - OVERLAY_W - 16),
    y: Math.max(16, window.innerHeight - OVERLAY_H_APPROX - 16),
  }
}

function clampToViewport(pos: OverlayPosition, height: number): OverlayPosition {
  const maxX = Math.max(0, window.innerWidth - OVERLAY_W)
  const maxY = Math.max(0, window.innerHeight - height)
  return {
    x: Math.min(Math.max(0, pos.x), maxX),
    y: Math.min(Math.max(0, pos.y), maxY),
  }
}

/**
 * MVP 30 — overlay global de progresso de geração de scaffold.
 *
 * Renderizado no layout raiz do projeto. Aparece quando
 * `codeGenProgressStore.active === true` OU quando há resultado recente
 * ainda não dispensado. Permite ao usuário navegar livre enquanto a
 * geração roda — o for-loop vive no store, não no componente do
 * CodeGenerator.
 */
export function CodeGenProgressOverlay() {
  const navigate = useNavigate()
  const params = useParams<{ id: string }>()
  const currentProjectIdFromRoute = params.id

  const active = useCodeGenProgressStore((s) => s.active)
  const projectId = useCodeGenProgressStore((s) => s.projectId)
  const projectName = useCodeGenProgressStore((s) => s.projectName)
  const snapshot = useCodeGenProgressStore((s) => s.snapshot)
  const errorMessage = useCodeGenProgressStore((s) => s.errorMessage)
  const finishedAt = useCodeGenProgressStore((s) => s.finishedAt)
  const startedAt = useCodeGenProgressStore((s) => s.startedAt)
  const dismiss = useCodeGenProgressStore((s) => s.dismiss)

  const planSummary = snapshot?.plan_summary || null

  const stats = useMemo(() => {
    const items = snapshot?.items || []
    const total = items.length
    const done = items.filter(i => i.status === 'done').length
    const generating = items.filter(i => i.status === 'generating').length
    const errors = items.filter(i => i.status === 'failed').length
    const pending = items.filter(i => i.status === 'pending').length
    const pct = total > 0 ? Math.round((done / total) * 100) : 0
    return { total, done, generating, errors, pending, pct }
  }, [snapshot])

  const phaseLabel = (() => {
    if (!snapshot) return 'Iniciando'
    if (snapshot.status === 'pending') return 'Na fila'
    if (snapshot.status === 'planning') return 'Planejando arquivos'
    if (snapshot.status === 'generating') return 'Gerando código'
    if (snapshot.status === 'completed') return stats.errors === 0 ? 'Geração concluída' : `Concluída com ${stats.errors} erro(s)`
    if (snapshot.status === 'failed') return 'Falhou'
    if (snapshot.status === 'applied') return 'Aplicado no Git'
    return snapshot.status
  })()

  // Posição arrastável persistida em localStorage. Default = bottom-right
  // (mesma posição visual do antigo `fixed bottom-4 right-4`).
  const [pos, setPos] = useState<OverlayPosition>(() => loadPersistedPos() ?? defaultPos())
  const overlayRef = useRef<HTMLDivElement | null>(null)
  const dragState = useRef<{ offsetX: number; offsetY: number } | null>(null)

  // Mantém dentro da viewport ao redimensionar a janela.
  useEffect(() => {
    const onResize = () => {
      const h = overlayRef.current?.offsetHeight || OVERLAY_H_APPROX
      setPos(prev => clampToViewport(prev, h))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    // Só arrasta com botão primário do mouse / touch.
    if (e.button !== 0) return
    const rect = overlayRef.current?.getBoundingClientRect()
    if (!rect) return
    dragState.current = {
      offsetX: e.clientX - rect.left,
      offsetY: e.clientY - rect.top,
    }
    // Captura o ponteiro pra arrastar mesmo se sair do elemento.
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    e.preventDefault()
  }, [])

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragState.current) return
    const h = overlayRef.current?.offsetHeight || OVERLAY_H_APPROX
    const next = clampToViewport(
      {
        x: e.clientX - dragState.current.offsetX,
        y: e.clientY - dragState.current.offsetY,
      },
      h,
    )
    setPos(next)
  }, [])

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragState.current) return
    dragState.current = null
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    persistPos(pos)
  }, [pos])

  const shouldShow = active || (finishedAt && !active)
  if (!shouldShow) return null
  if (!projectId || !projectName) return null

  const onCurrentProject = currentProjectIdFromRoute === projectId
  const elapsed = startedAt
    ? Math.round(((finishedAt || Date.now()) - startedAt) / 1000)
    : 0

  const goToCodeGen = () => {
    if (onCurrentProject) return
    navigate(`/projects/${projectId}/codegen`)
  }

  const isDone = !active && finishedAt !== null

  return (
    <div
      ref={overlayRef}
      className="fixed z-50 w-[360px] bg-slate-900 border border-violet-700/50 rounded-xl shadow-2xl shadow-violet-900/30 overflow-hidden select-none"
      style={{ left: pos.x, top: pos.y }}
      role="status"
      aria-live="polite"
    >
      <div
        className="px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-2 cursor-move touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        title="Arraste para reposicionar"
      >
        <div className="flex items-center gap-2 min-w-0">
          <GripVertical className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
          {active && <Loader2 className="w-4 h-4 text-violet-400 animate-spin flex-shrink-0" />}
          {isDone && stats.errors === 0 && <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />}
          {isDone && stats.errors > 0 && <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />}
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-semibold text-slate-200 truncate">{phaseLabel}</span>
            <span className="text-[10px] text-slate-500 truncate">{projectName}</span>
          </div>
        </div>
        {isDone && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); dismiss() }}
            onPointerDown={(e) => e.stopPropagation()}
            className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors flex-shrink-0 cursor-pointer"
            title="Dispensar"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div className="px-4 py-3">
        {stats.total === 0 ? (
          <div className="text-xs text-slate-400">
            {errorMessage || 'Consultando OCG e stack pra listar os arquivos do scaffold...'}
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between text-xs text-slate-300 mb-1.5">
              <span>
                <strong className="text-violet-300">{stats.done}</strong>
                <span className="text-slate-500"> / {stats.total} arquivos</span>
                {stats.errors > 0 && (
                  <span className="text-amber-400 ml-2">{stats.errors} erro(s)</span>
                )}
              </span>
              <span className="text-[10px] text-slate-500">{elapsed}s</span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${isDone && stats.errors === 0 ? 'bg-emerald-500' : isDone && stats.errors > 0 ? 'bg-amber-500' : 'bg-violet-500'}`}
                style={{ width: `${stats.pct}%` }}
              />
            </div>
            {planSummary && (
              <p className="text-[10px] text-slate-500 mt-2 line-clamp-2">{planSummary}</p>
            )}
          </>
        )}

        {errorMessage && (
          <div className="mt-2 text-[11px] text-red-400 bg-red-950/30 border border-red-900/40 rounded px-2 py-1">
            {errorMessage}
          </div>
        )}

        {!onCurrentProject && (
          <button
            type="button"
            onClick={goToCodeGen}
            className="mt-3 w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-violet-600/20 hover:bg-violet-600/30 border border-violet-700/40 text-xs text-violet-300 transition-colors"
          >
            Abrir Geração de Código
            <ArrowRight className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  )
}
