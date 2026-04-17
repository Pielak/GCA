import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, GitBranch, Zap, ClipboardList, ArrowRight } from 'lucide-react'
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
  icon: React.ComponentType<{ className?: string }>
  to: (id: string) => string
}

const STEPS: Step[] = [
  {
    n: 1,
    key: 'repo_configured',
    label: 'Repositório com PAT',
    description: 'Conecte o repositório Git do projeto (GitHub/GitLab/Bitbucket) com Personal Access Token.',
    icon: GitBranch,
    to: (id) => `/projects/${id}/repository`,
  },
  {
    n: 2,
    key: 'llm_configured',
    label: 'Provedor IA + API Key',
    description: 'Escolha o provedor (Anthropic/OpenAI/Gemini/DeepSeek/Grok) e forneça sua chave.',
    icon: Zap,
    to: (id) => `/projects/${id}/settings`,
  },
  {
    n: 3,
    key: 'questionnaire_submitted',
    label: 'Questionário Técnico',
    description: 'Baixe o PDF editável, preencha offline e faça upload para gerar o contexto OCG.',
    icon: ClipboardList,
    to: (id) => `/projects/${id}/questionnaire`,
  },
]

export function SetupChecklist({ projectId, status }: Props) {
  const doneCount = STEPS.filter(s => status[s.key]).length
  const allDone = doneCount === STEPS.length

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
          : 'Complete os 3 passos na ordem para habilitar Ingestão, Arguidor, CodeGen e demais etapas.'}
      </p>

      <ol className="space-y-2.5">
        {STEPS.map((s) => {
          const done = status[s.key]
          const Icon = s.icon
          return (
            <li key={s.key}>
              <Link
                to={s.to(projectId)}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                  done
                    ? 'border-emerald-800/40 bg-emerald-950/10 hover:bg-emerald-950/20'
                    : 'border-slate-700 hover:border-violet-600/50 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex-shrink-0">
                  {done
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    : <Circle className="w-5 h-5 text-slate-500" />}
                </div>
                <Icon className={`w-4 h-4 flex-shrink-0 ${done ? 'text-emerald-400' : 'text-violet-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${done ? 'text-emerald-200' : 'text-slate-200'}`}>
                    {s.n}. {s.label}
                  </p>
                  <p className="text-xs text-slate-500 truncate">{s.description}</p>
                </div>
                {!done && <ArrowRight className="w-4 h-4 text-slate-500 flex-shrink-0" />}
              </Link>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
