/**
 * DesignShowcasePage — Demonstração do design system GCA
 * Esta página serve como referência visual e teste dos componentes.
 * Acessível em /design-showcase (admin only).
 */
import { useState, useEffect } from 'react'
import {
  PipelineProgress, OperationBar, PulseIndicator,
  PageTransition, SkeletonPulse, StepToast
} from '@/components/ui/PipelineProgress'
import {
  Play, RotateCcw, Shield, Cpu, Database, GitBranch,
  FileText, TestTube2, Eye, Zap, CheckCircle2, Package
} from 'lucide-react'

const PIPELINE_STEPS = [
  { label: 'Ingestão', description: 'Processando documentos enviados' },
  { label: 'Gatekeeper', description: 'Avaliando 7 pilares de qualidade' },
  { label: 'OCG', description: 'Gerando contexto global do projeto' },
  { label: 'Arguidor', description: 'IA analisando lacunas e riscos' },
  { label: 'CodeGen', description: 'Gerando código com base no OCG' },
  { label: 'QA', description: 'Verificando cobertura de testes' },
  { label: 'Review', description: 'Aguardando aprovação humana' },
]

const OPERATION_DEMOS = [
  { message: 'Analisando documento', detail: 'requisitos_funcionais_v3.pdf — 42 páginas', progress: undefined },
  { message: 'Provisionando tenant', detail: 'Criando schema proj_internet_banking_v3', progress: 35 },
  { message: 'Gerando OCG', detail: 'Pilar P3 — Funcionalidades e Escopo', progress: 72 },
  { message: 'Executando testes', detail: '47/84 testes concluídos', progress: 56 },
]

export function DesignShowcasePage() {
  // Pipeline demo state
  const [pipelineStep, setPipelineStep] = useState(0)
  const [pipelineStatus, setPipelineStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle')
  const [pipelineInterval, setPipelineInterval] = useState<NodeJS.Timeout | null>(null)

  // Operation bar demo state
  const [activeOp, setActiveOp] = useState(0)
  const [opStatus, setOpStatus] = useState<'running' | 'success' | 'error'>('running')

  // Toast demo
  const [showToast, setShowToast] = useState(false)
  const [toastStep, setToastStep] = useState(1)

  const startPipeline = () => {
    setPipelineStep(0)
    setPipelineStatus('running')
    if (pipelineInterval) clearInterval(pipelineInterval)

    let step = 0
    const interval = setInterval(() => {
      step++
      if (step >= PIPELINE_STEPS.length) {
        clearInterval(interval)
        setPipelineStatus('success')
      } else {
        setPipelineStep(step)
      }
    }, 2000)
    setPipelineInterval(interval)
  }

  const resetPipeline = () => {
    if (pipelineInterval) clearInterval(pipelineInterval)
    setPipelineStep(0)
    setPipelineStatus('idle')
  }

  useEffect(() => {
    return () => {
      if (pipelineInterval) clearInterval(pipelineInterval)
    }
  }, [pipelineInterval])

  return (
    <PageTransition>
      <div className="min-h-screen bg-surface-base p-8 space-y-12">
        {/* Noise overlay */}
        <div className="fixed inset-0 bg-noise pointer-events-none z-0" />

        <div className="relative z-10 max-w-5xl mx-auto space-y-12">

          {/* Header */}
          <div className="space-y-2">
            <h1 className="font-display text-display-lg text-ink-primary">
              Design System <span className="bg-gradient-brand bg-clip-text text-transparent">GCA</span>
            </h1>
            <p className="text-ink-secondary text-base max-w-xl">
              Componentes de progresso, micro-interações e feedback visual.
              Cada operação do GCA comunica exatamente o que está acontecendo.
            </p>
          </div>

          {/* ── Section: Pipeline Progress ── */}
          <section className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-display text-display-sm text-ink-primary">Pipeline Progress</h2>
                <p className="text-ink-muted text-sm mt-1">Visualização das etapas do pipeline com animações contextuais</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={startPipeline}
                  disabled={pipelineStatus === 'running'}
                  className="flex items-center gap-1.5 px-4 py-2 bg-brand-500 hover:bg-brand-400 disabled:opacity-40 text-white text-sm font-medium rounded-xl transition-colors shadow-glow-sm"
                >
                  <Play className="w-3.5 h-3.5" /> Iniciar
                </button>
                <button
                  onClick={resetPipeline}
                  className="flex items-center gap-1.5 px-4 py-2 bg-surface-raised border border-edge text-ink-secondary text-sm font-medium rounded-xl hover:border-edge-strong transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Reset
                </button>
              </div>
            </div>

            <div className="bg-surface-raised/60 border border-edge-subtle rounded-2xl p-8 backdrop-blur-sm">
              <PipelineProgress
                steps={PIPELINE_STEPS}
                currentStep={pipelineStep}
                status={pipelineStatus}
              />
            </div>
          </section>

          {/* ── Section: Operation Bars ── */}
          <section className="space-y-6">
            <div>
              <h2 className="font-display text-display-sm text-ink-primary">Operation Bar</h2>
              <p className="text-ink-muted text-sm mt-1">Feedback contextual durante operações — mostra o que está acontecendo e o progresso</p>
            </div>

            <div className="space-y-3">
              {OPERATION_DEMOS.map((op, i) => (
                <div key={i} className={i === activeOp ? 'opacity-100' : 'opacity-40 pointer-events-none'}>
                  <OperationBar
                    message={op.message}
                    detail={op.detail}
                    progress={i === activeOp ? op.progress : 0}
                    status={i === activeOp ? opStatus : 'running'}
                  />
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              {OPERATION_DEMOS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => { setActiveOp(i); setOpStatus('running') }}
                  className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                    i === activeOp
                      ? 'bg-brand-500/20 text-brand-300 border border-brand-500/30'
                      : 'bg-surface-raised text-ink-muted border border-edge-subtle hover:border-edge'
                  }`}
                >
                  Demo {i + 1}
                </button>
              ))}
              <div className="h-px flex-1" />
              <button
                onClick={() => setOpStatus('success')}
                className="px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 hover:bg-emerald-500/15 transition-colors"
              >
                Simular Sucesso
              </button>
              <button
                onClick={() => setOpStatus('error')}
                className="px-3 py-1.5 text-xs rounded-lg bg-red-500/10 text-red-300 border border-red-500/20 hover:bg-red-500/15 transition-colors"
              >
                Simular Erro
              </button>
            </div>
          </section>

          {/* ── Section: Pulse Indicators ── */}
          <section className="space-y-6">
            <div>
              <h2 className="font-display text-display-sm text-ink-primary">Pulse Indicators</h2>
              <p className="text-ink-muted text-sm mt-1">Indicadores mínimos de atividade — o ponto pulsa para comunicar que algo está vivo</p>
            </div>

            <div className="flex flex-wrap gap-3">
              <PulseIndicator message="Pipeline ativo" variant="brand" />
              <PulseIndicator message="3 agentes rodando" variant="accent" />
              <PulseIndicator message="Aguardando aprovação" variant="warning" />
            </div>
          </section>

          {/* ── Section: Skeleton Loading ── */}
          <section className="space-y-6">
            <div>
              <h2 className="font-display text-display-sm text-ink-primary">Skeleton Loading</h2>
              <p className="text-ink-muted text-sm mt-1">Placeholders animados com shimmer — mantém o layout enquanto carrega</p>
            </div>

            <div className="bg-surface-raised/60 border border-edge-subtle rounded-2xl p-6 space-y-4">
              <div className="flex items-center gap-3">
                <SkeletonPulse className="w-10 h-10 rounded-xl" />
                <div className="space-y-2 flex-1">
                  <SkeletonPulse className="h-4 w-48" />
                  <SkeletonPulse className="h-3 w-32" />
                </div>
                <SkeletonPulse className="h-8 w-20 rounded-lg" />
              </div>
              <SkeletonPulse className="h-[1px] w-full" />
              <div className="grid grid-cols-3 gap-4">
                <SkeletonPulse className="h-24 rounded-xl" />
                <SkeletonPulse className="h-24 rounded-xl" />
                <SkeletonPulse className="h-24 rounded-xl" />
              </div>
            </div>
          </section>

          {/* ── Section: Step Toast ── */}
          <section className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-display text-display-sm text-ink-primary">Step Toast</h2>
                <p className="text-ink-muted text-sm mt-1">Feedback flutuante de progresso — aparece ao concluir cada etapa</p>
              </div>
              <button
                onClick={() => {
                  setShowToast(true)
                  setToastStep(prev => prev >= 7 ? 1 : prev + 1)
                  setTimeout(() => setShowToast(false), 3000)
                }}
                className="flex items-center gap-1.5 px-4 py-2 bg-brand-500 hover:bg-brand-400 text-white text-sm font-medium rounded-xl transition-colors shadow-glow-sm"
              >
                <Zap className="w-3.5 h-3.5" /> Disparar Toast
              </button>
            </div>
          </section>

          {/* ── Section: Design Tokens ── */}
          <section className="space-y-6">
            <div>
              <h2 className="font-display text-display-sm text-ink-primary">Surface Layers</h2>
              <p className="text-ink-muted text-sm mt-1">6 camadas de profundidade — do void ao float</p>
            </div>

            <div className="flex gap-2">
              {[
                { name: 'void', color: 'bg-surface-void' },
                { name: 'deep', color: 'bg-surface-deep' },
                { name: 'base', color: 'bg-surface-base' },
                { name: 'raised', color: 'bg-surface-raised' },
                { name: 'overlay', color: 'bg-surface-overlay' },
                { name: 'float', color: 'bg-surface-float' },
              ].map(s => (
                <div key={s.name} className="flex-1 text-center">
                  <div className={`${s.color} h-20 rounded-xl border border-edge-subtle mb-2`} />
                  <p className="text-[10px] text-ink-muted font-mono">{s.name}</p>
                </div>
              ))}
            </div>
          </section>

          {/* ── Section: Color Palette ── */}
          <section className="space-y-6">
            <h2 className="font-display text-display-sm text-ink-primary">Paleta</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-xs text-ink-muted font-medium uppercase tracking-wider">Brand</p>
                <div className="flex gap-1.5">
                  {['bg-brand-900', 'bg-brand-800', 'bg-brand-700', 'bg-brand-600', 'bg-brand-500', 'bg-brand-400', 'bg-brand-300', 'bg-brand-200', 'bg-brand-100'].map(c => (
                    <div key={c} className={`${c} h-10 flex-1 rounded-lg first:rounded-l-xl last:rounded-r-xl`} />
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-ink-muted font-medium uppercase tracking-wider">Accent</p>
                <div className="flex gap-1.5">
                  {['bg-accent-700', 'bg-accent-600', 'bg-accent-500', 'bg-accent-400', 'bg-accent-300', 'bg-accent-200', 'bg-accent-100', 'bg-accent-50'].map(c => (
                    <div key={c} className={`${c} h-10 flex-1 rounded-lg first:rounded-l-xl last:rounded-r-xl`} />
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Footer */}
          <div className="pt-8 border-t border-edge-subtle flex items-center gap-4">
            <p className="text-ink-muted text-xs">GCA Design System "Observatory" v1.0</p>
            <div className="h-px flex-1 bg-gradient-to-r from-edge-subtle to-transparent" />
          </div>
        </div>

        {/* Toast */}
        {showToast && (
          <StepToast
            message={PIPELINE_STEPS[toastStep - 1]?.label || 'Etapa concluída'}
            step={toastStep}
            total={PIPELINE_STEPS.length}
          />
        )}
      </div>
    </PageTransition>
  )
}
