/**
 * PipelineProgress — Sistema de progresso animado do GCA
 *
 * Não é um spinner. É um indicador vivo que mostra EXATAMENTE o que está
 * acontecendo, com micro-animações que comunicam atividade sem parecer parado.
 *
 * Uso:
 *   <PipelineProgress
 *     steps={[
 *       { label: 'Validando dados', description: 'Verificando campos obrigatórios' },
 *       { label: 'Criando schema', description: 'Provisionando tenant isolado' },
 *       { label: 'Configurando agentes', description: 'Ativando pipeline de IA' },
 *     ]}
 *     currentStep={1}
 *     status="running"
 *   />
 *
 *   <OperationBar message="Analisando documento..." progress={65} />
 */
import { useEffect, useState, useRef } from 'react'
import { Check, Loader2, AlertCircle, Sparkles } from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────

export interface PipelineStep {
  label: string
  description?: string
  icon?: React.ReactNode
}

export type PipelineStatus = 'idle' | 'running' | 'success' | 'error'

interface PipelineProgressProps {
  steps: PipelineStep[]
  currentStep: number
  status: PipelineStatus
  error?: string
}

interface OperationBarProps {
  message: string
  detail?: string
  progress?: number  // 0-100, undefined = indeterminate
  status?: 'running' | 'success' | 'error'
  onComplete?: () => void
}

interface PulseIndicatorProps {
  message: string
  variant?: 'brand' | 'accent' | 'warning'
}

// ─── PipelineProgress ─────────────────────────────────────────────────

export function PipelineProgress({ steps, currentStep, status, error }: PipelineProgressProps) {
  return (
    <div className="w-full py-2">
      {/* Progress track */}
      <div className="relative flex items-center justify-between">
        {/* Background line */}
        <div className="absolute top-4 left-4 right-4 h-[2px] bg-edge-subtle" />

        {/* Animated fill line */}
        <div
          className="absolute top-4 left-4 h-[2px] transition-all duration-700 ease-out"
          style={{
            width: `calc(${Math.min((currentStep / (steps.length - 1)) * 100, 100)}% - 32px)`,
            background: status === 'error'
              ? '#ef4444'
              : 'linear-gradient(90deg, #7038e0, #8550f6, #00b8cc)',
          }}
        >
          {/* Traveling pulse on the line */}
          {status === 'running' && (
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-12 h-[2px]">
              <div
                className="w-full h-full rounded-full"
                style={{
                  background: 'linear-gradient(90deg, transparent, #8550f6, #00b8cc)',
                  animation: 'travelPulse 1.5s ease-in-out infinite',
                }}
              />
            </div>
          )}
        </div>

        {/* Step indicators */}
        {steps.map((step, i) => {
          const isCompleted = i < currentStep
          const isCurrent = i === currentStep
          const isFuture = i > currentStep
          const isError = isCurrent && status === 'error'
          const isSuccess = isCurrent && status === 'success'

          return (
            <div key={i} className="relative flex flex-col items-center z-10" style={{ flex: 1 }}>
              {/* Circle */}
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center
                  transition-all duration-500 ease-out
                  ${isCompleted
                    ? 'bg-brand-500 border-2 border-brand-400 shadow-glow-sm scale-100'
                    : isCurrent && status === 'running'
                      ? 'bg-surface-raised border-2 border-brand-400 shadow-glow-brand scale-110'
                      : isError
                        ? 'bg-red-500/20 border-2 border-red-400 scale-110'
                        : isSuccess
                          ? 'bg-emerald-500/20 border-2 border-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.3)] scale-110'
                          : 'bg-surface-raised border-2 border-edge scale-100'
                  }
                `}
              >
                {isCompleted ? (
                  <Check className="w-3.5 h-3.5 text-white animate-fade-in" />
                ) : isCurrent && status === 'running' ? (
                  <Loader2 className="w-3.5 h-3.5 text-brand-300 animate-spin" />
                ) : isError ? (
                  <AlertCircle className="w-3.5 h-3.5 text-red-300 animate-fade-in" />
                ) : isSuccess ? (
                  <Sparkles className="w-3.5 h-3.5 text-emerald-300 animate-fade-in" />
                ) : (
                  <span className="w-2 h-2 rounded-full bg-ink-muted" />
                )}
              </div>

              {/* Label */}
              <p
                className={`
                  mt-3 text-xs font-medium text-center max-w-[100px] transition-colors duration-300
                  ${isCompleted ? 'text-brand-300'
                    : isCurrent ? 'text-ink-primary'
                    : 'text-ink-muted'}
                `}
              >
                {step.label}
              </p>

              {/* Description (only current step) */}
              {isCurrent && step.description && (
                <p className="mt-1 text-[10px] text-ink-secondary text-center max-w-[120px] animate-fade-in">
                  {step.description}
                </p>
              )}
            </div>
          )
        })}
      </div>

      {/* Error message */}
      {status === 'error' && error && (
        <div className="mt-4 bg-red-500/8 border border-red-500/15 rounded-xl px-4 py-3 animate-fade-up">
          <p className="text-red-300 text-xs">{error}</p>
        </div>
      )}

      <style>{`
        @keyframes travelPulse {
          0%, 100% { opacity: 0.3; transform: translateX(-100%); }
          50% { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  )
}

// ─── OperationBar — barra de progresso contextual ─────────────────────

export function OperationBar({ message, detail, progress, status = 'running', onComplete }: OperationBarProps) {
  const [visible, setVisible] = useState(false)
  const [dots, setDots] = useState('')
  const prevStatus = useRef(status)

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true))
  }, [])

  // Animated dots for running state
  useEffect(() => {
    if (status !== 'running') return
    const interval = setInterval(() => {
      setDots(d => d.length >= 3 ? '' : d + '.')
    }, 500)
    return () => clearInterval(interval)
  }, [status])

  // Auto-dismiss on success
  useEffect(() => {
    if (prevStatus.current === 'running' && status === 'success') {
      const timer = setTimeout(() => {
        setVisible(false)
        setTimeout(() => onComplete?.(), 300)
      }, 2000)
      return () => clearTimeout(timer)
    }
    prevStatus.current = status
  }, [status, onComplete])

  const barColor = status === 'error'
    ? 'from-red-500 to-red-400'
    : status === 'success'
      ? 'from-emerald-500 to-emerald-400'
      : 'from-brand-500 via-brand-400 to-accent-500'

  return (
    <div
      className={`
        w-full overflow-hidden rounded-xl border transition-all duration-300
        ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2'}
        ${status === 'error' ? 'border-red-500/20 bg-red-500/5'
          : status === 'success' ? 'border-emerald-500/20 bg-emerald-500/5'
          : 'border-edge-brand bg-surface-raised/80'}
      `}
    >
      {/* Progress bar — top edge */}
      <div className="h-[3px] w-full bg-surface-void/50 relative overflow-hidden">
        {progress !== undefined ? (
          // Determinate
          <div
            className={`h-full bg-gradient-to-r ${barColor} transition-all duration-500 ease-out`}
            style={{ width: `${progress}%` }}
          />
        ) : (
          // Indeterminate — traveling bar
          <div
            className={`h-full bg-gradient-to-r ${barColor} absolute`}
            style={{
              width: '40%',
              animation: 'indeterminate 1.8s ease-in-out infinite',
            }}
          />
        )}
      </div>

      {/* Content */}
      <div className="px-4 py-3 flex items-center gap-3">
        {status === 'running' ? (
          <div className="relative">
            <div className="w-5 h-5 rounded-full border-2 border-brand-400/30 border-t-brand-400 animate-spin" />
          </div>
        ) : status === 'success' ? (
          <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center animate-fade-in">
            <Check className="w-3 h-3 text-emerald-400" />
          </div>
        ) : (
          <AlertCircle className="w-5 h-5 text-red-400 animate-fade-in" />
        )}

        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium truncate ${
            status === 'success' ? 'text-emerald-300'
            : status === 'error' ? 'text-red-300'
            : 'text-ink-primary'
          }`}>
            {message}{status === 'running' ? dots : ''}
          </p>
          {detail && (
            <p className="text-[11px] text-ink-muted mt-0.5 truncate">{detail}</p>
          )}
        </div>

        {progress !== undefined && status === 'running' && (
          <span className="text-xs font-mono text-brand-300 tabular-nums">
            {Math.round(progress)}%
          </span>
        )}
      </div>

      <style>{`
        @keyframes indeterminate {
          0% { left: -40%; }
          100% { left: 100%; }
        }
      `}</style>
    </div>
  )
}

// ─── PulseIndicator — indicador mínimo de atividade ───────────────────

export function PulseIndicator({ message, variant = 'brand' }: PulseIndicatorProps) {
  const colors = {
    brand: { dot: 'bg-brand-400', text: 'text-brand-300', ring: 'bg-brand-400/30' },
    accent: { dot: 'bg-accent-400', text: 'text-accent-300', ring: 'bg-accent-400/30' },
    warning: { dot: 'bg-amber-400', text: 'text-amber-300', ring: 'bg-amber-400/30' },
  }
  const c = colors[variant]

  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-raised/60 border border-edge-subtle">
      <span className="relative flex h-2.5 w-2.5">
        <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${c.ring} opacity-75`} />
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${c.dot}`} />
      </span>
      <span className={`text-xs font-medium ${c.text}`}>{message}</span>
    </div>
  )
}

// ─── PageTransition — wrapper de entrada de página ────────────────────

export function PageTransition({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), delay)
    return () => clearTimeout(timer)
  }, [delay])

  return (
    <div
      className={`transition-all duration-500 ease-out ${
        mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'
      }`}
    >
      {children}
    </div>
  )
}

// ─── SkeletonPulse — placeholder animado durante carregamento ─────────

export function SkeletonPulse({ className = '' }: { className?: string }) {
  return (
    <div
      className={`rounded-lg bg-surface-raised relative overflow-hidden ${className}`}
    >
      <div
        className="absolute inset-0"
        style={{
          background: 'linear-gradient(90deg, transparent, rgba(112, 56, 224, 0.06), transparent)',
          animation: 'shimmer 2s linear infinite',
          backgroundSize: '200% 100%',
        }}
      />
    </div>
  )
}

// ─── StepToast — feedback flutuante de etapa concluída ────────────────

export function StepToast({ message, step, total }: { message: string; step: number; total: number }) {
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-fade-up">
      <div className="flex items-center gap-3 bg-surface-overlay/95 backdrop-blur-md border border-edge-brand rounded-2xl px-5 py-3 shadow-elevated">
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-5 rounded-full bg-brand-500/20 flex items-center justify-center">
            <Check className="w-3 h-3 text-brand-300" />
          </div>
          <span className="text-sm text-ink-primary font-medium">{message}</span>
        </div>
        <div className="h-4 w-px bg-edge" />
        <span className="text-xs text-ink-muted font-mono">{step}/{total}</span>
        {/* Mini progress bar */}
        <div className="w-16 h-1.5 rounded-full bg-surface-void overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-500 to-accent-500 transition-all duration-500"
            style={{ width: `${(step / total) * 100}%` }}
          />
        </div>
      </div>
    </div>
  )
}
