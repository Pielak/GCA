import { useEffect, useState } from 'react'

const STEPS = [
  'Validando completude do questionario...',
  'Analisando coerencia entre entregaveis e stack...',
  'Verificando uso obrigatorio de IA...',
  'Conferindo seguranca minima e observabilidade...',
  'Preparando parecer tecnico...',
]

interface AnalysisOverlayProps {
  isVisible: boolean
  onComplete: () => void
}

export function AnalysisOverlay({ isVisible, onComplete }: AnalysisOverlayProps) {
  const [step, setStep] = useState(0)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    if (!isVisible) {
      setStep(0)
      setProgress(0)
      return
    }

    const stepDuration = 800
    const totalDuration = STEPS.length * stepDuration

    // Progress bar
    const progressInterval = setInterval(() => {
      setProgress(prev => {
        const next = prev + 2
        return next > 100 ? 100 : next
      })
    }, totalDuration / 50)

    // Steps
    const stepInterval = setInterval(() => {
      setStep(prev => {
        if (prev >= STEPS.length - 1) {
          clearInterval(stepInterval)
          clearInterval(progressInterval)
          setTimeout(onComplete, 400)
          return prev
        }
        return prev + 1
      })
    }, stepDuration)

    return () => {
      clearInterval(progressInterval)
      clearInterval(stepInterval)
    }
  }, [isVisible, onComplete])

  if (!isVisible) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl p-10 max-w-md w-full mx-4 text-center">
        {/* Atom animation */}
        <div className="relative w-32 h-32 mx-auto mb-8">
          {/* Nucleus */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-violet-500 animate-pulse shadow-[0_0_20px_rgba(124,58,237,0.6)]" />

          {/* Orbit 1 */}
          <div className="absolute inset-0 animate-[spin_4s_linear_infinite]">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.6)]" />
          </div>

          {/* Orbit 2 */}
          <div className="absolute inset-2 animate-[spin_3s_linear_infinite_reverse]">
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.6)]" />
          </div>

          {/* Orbit 3 */}
          <div className="absolute inset-4 animate-[spin_5s_linear_infinite]">
            <div className="absolute top-1/2 right-0 -translate-y-1/2 w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.6)]" />
          </div>

          {/* Orbit rings */}
          <div className="absolute inset-0 border border-violet-500/20 rounded-full" />
          <div className="absolute inset-2 border border-emerald-500/15 rounded-full rotate-45" />
          <div className="absolute inset-4 border border-amber-500/10 rounded-full -rotate-12" />
        </div>

        <p className="text-slate-200 text-base font-medium mb-2">Analisando...</p>
        <p className="text-slate-400 text-sm mb-6 h-5">{STEPS[step]}</p>

        {/* Progress bar */}
        <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-violet-600 to-emerald-500 rounded-full transition-all duration-200"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-slate-500 text-xs mt-2">{progress}%</p>
      </div>
    </div>
  )
}
