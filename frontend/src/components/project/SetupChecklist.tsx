import { Link } from 'react-router-dom'
import {
  CheckCircle2, Circle, Lock, GitBranch, Zap, ClipboardList, ArrowRight, Mail,
} from 'lucide-react'
import type { SetupStatus } from '@/hooks/useSetupStatus'

interface Props {
  projectId: string
  status: SetupStatus
}

interface Step {
  n: number
  key: keyof Pick<SetupStatus, 'repo_configured' | 'llm_configured' | 'questionnaire_submitted'>
  label: string
  description: string
  rationale: string
  icon: React.ComponentType<{ className?: string }>
  to: (id: string) => string
}

// Ordem obrigatória — cada passo depende lógicamente do anterior:
// 1. IA  — sem chave, a geração do OCG (pipeline 8 agentes) não roda.
// 2. Git — repo + PAT viabiliza ingestão de repos externos e CodeGen futuro.
// 3. Questionário — dispara geração do OCG; precisa de IA configurada.
//
// SMTP por projeto (DT-016) fica como passo 3 no roadmap, antes do
// questionário — escopo MVP 5 (Hardening). Aparece aqui como preview locked.
const STEPS: Step[] = [
  {
    n: 1,
    key: 'llm_configured',
    label: 'Provedor IA + API Key',
    description: 'Escolha o provedor (Anthropic/OpenAI/Gemini/DeepSeek/Grok) e informe sua chave.',
    rationale: 'Pré-requisito de tudo. Sem IA configurada, o OCG não é gerado quando você enviar o questionário.',
    icon: Zap,
    to: (id) => `/projects/${id}/settings`,
  },
  {
    n: 2,
    key: 'repo_configured',
    label: 'Repositório Git + PAT',
    description: 'Conecte o repositório (GitHub/GitLab/Bitbucket) com Personal Access Token.',
    rationale: 'Necessário para ingestão de repos externos e CodeGen. Mesmo sem PAT, o OCG inicial roda — mas CodeGen e merge dependem dele.',
    icon: GitBranch,
    to: (id) => `/projects/${id}/repository`,
  },
  {
    n: 3,
    key: 'questionnaire_submitted',
    label: 'Questionário Técnico (PDF)',
    description: 'Baixe o PDF editável, preencha offline e envie. 49 perguntas que alimentam o OCG.',
    rationale: 'Dispara a geração do OCG (pipeline de 8 agentes IA). Precisa dos passos 1 e 2 completos para ser útil.',
    icon: ClipboardList,
    to: (id) => `/projects/${id}/questionnaire`,
  },
]

export function SetupChecklist({ projectId, status }: Props) {
  const doneCount = STEPS.filter((s) => status[s.key]).length
  const allDone = doneCount === STEPS.length

  // Índice do primeiro passo pendente — usado para destacar só ele e
  // "bloquear" visualmente os passos à frente (enforcement sequencial).
  const currentStepIdx = STEPS.findIndex((s) => !status[s.key])

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-slate-100 text-base font-semibold">Setup do Projeto</h3>
        <span className={`text-xs ${allDone ? 'text-emerald-400' : 'text-amber-400'}`}>
          {doneCount}/{STEPS.length} concluídos
        </span>
      </div>
      <p className="text-slate-400 text-xs mb-5">
        {allDone
          ? 'Pré-requisitos completos. Pipeline habilitado.'
          : 'Complete os passos na ordem abaixo — cada um depende do anterior.'}
      </p>

      <ol className="space-y-2.5">
        {STEPS.map((s, idx) => {
          const done = status[s.key]
          const isCurrent = idx === currentStepIdx
          const isLocked = !done && !isCurrent && currentStepIdx !== -1 && idx > currentStepIdx

          const Icon = s.icon

          // Locked: aparece desabilitado + cadeado; não navega.
          if (isLocked) {
            return (
              <li key={s.key}>
                <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-800/60 bg-slate-950/40 opacity-60 cursor-not-allowed">
                  <Lock className="w-5 h-5 text-slate-600 flex-shrink-0" />
                  <Icon className="w-4 h-4 flex-shrink-0 text-slate-600" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-500">
                      {s.n}. {s.label}
                    </p>
                    <p className="text-xs text-slate-600 truncate">
                      Complete o passo {s.n - 1} primeiro.
                    </p>
                  </div>
                </div>
              </li>
            )
          }

          return (
            <li key={s.key}>
              <Link
                to={s.to(projectId)}
                className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                  done
                    ? 'border-emerald-800/40 bg-emerald-950/10 hover:bg-emerald-950/20'
                    : isCurrent
                      ? 'border-violet-600/60 bg-violet-950/10 hover:bg-violet-950/20 ring-1 ring-violet-600/30'
                      : 'border-slate-700 hover:border-violet-600/50 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex-shrink-0 mt-0.5">
                  {done
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    : <Circle className={`w-5 h-5 ${isCurrent ? 'text-violet-400' : 'text-slate-500'}`} />}
                </div>
                <Icon className={`w-4 h-4 flex-shrink-0 mt-1 ${
                  done ? 'text-emerald-400' : isCurrent ? 'text-violet-400' : 'text-slate-500'
                }`} />
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${
                    done ? 'text-emerald-200' : isCurrent ? 'text-violet-200' : 'text-slate-200'
                  }`}>
                    {s.n}. {s.label}
                    {isCurrent && (
                      <span className="ml-2 text-[10px] font-normal text-violet-400 uppercase tracking-wide">
                        próximo
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">{s.description}</p>
                  {isCurrent && (
                    <p className="text-[11px] text-violet-300/80 mt-1.5 leading-snug">
                      <span className="font-semibold">Por quê:</span> {s.rationale}
                    </p>
                  )}
                </div>
                {!done && <ArrowRight className={`w-4 h-4 flex-shrink-0 mt-1 ${
                  isCurrent ? 'text-violet-400' : 'text-slate-500'
                }`} />}
              </Link>
            </li>
          )
        })}

        {/* Preview do próximo passo futuro: SMTP por projeto (DT-016, MVP 5) */}
        <li>
          <div className="flex items-start gap-3 p-3 rounded-lg border border-dashed border-slate-800/60 bg-slate-950/30">
            <Lock className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
            <Mail className="w-4 h-4 flex-shrink-0 mt-1 text-slate-600" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-500">
                SMTP do projeto
                <span className="ml-2 text-[10px] font-normal text-slate-600 uppercase tracking-wide">
                  em breve
                </span>
              </p>
              <p className="text-xs text-slate-600 mt-0.5">
                Configuração SMTP própria para convites e notificações do projeto
                (compartimentalização operacional).
              </p>
            </div>
          </div>
        </li>
      </ol>
    </div>
  )
}
