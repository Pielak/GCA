import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Clock, CheckCircle, Circle, ArrowRight, GitCommit, FileText, Tag } from 'lucide-react';
import { HelpTooltip } from '@/components/ui/HelpTooltip';

const DECISIONS = [
  { id: 'd1', type: 'ADR', title: 'ADR-001: Adoção de JWT RS256 para autenticação', status: 'approved', author: 'Bruno Alves', date: '2026-01-25', description: 'Decisão de usar JWT com RS256 ao invés de HS256 para suporte a múltiplos serviços sem compartilhamento de segredo.' },
  { id: 'd2', type: 'ADR', title: 'ADR-002: PostgreSQL com schema isolado por projeto', status: 'approved', author: 'Bruno Alves', date: '2026-01-26', description: 'Multi-tenancy via schema separation no PostgreSQL 16.' },
  { id: 'd3', type: 'Requisito', title: 'RF-042: Módulo de autoatendimento — critério de aceite', status: 'pending', author: 'Carla Sousa', date: '2026-03-20', description: 'Critério de aceite formal do módulo de autoatendimento ainda não aprovado.' },
  { id: 'd4', type: 'Override', title: 'Override Gatekeeper — Pilar de Segurança', status: 'pending', author: '—', date: '—', description: 'Aguarda justificativa técnica formal do Tech Lead para aprovação com override.' },
];

const MILESTONES = [
  { id: 'm1', phase: 1, label: 'Fase 1 — Governança Base', status: 'done', date: '2026-01-22', items: ['Autenticação JWT', 'RBAC global', 'Bootstrap administrativo', 'Health checks'] },
  { id: 'm2', phase: 2, label: 'Fase 2 — OCG e Provisionamento', status: 'done', date: '2026-01-28', items: ['OCG Wizard', 'Questionário técnico', 'Provisionamento compensatório'] },
  { id: 'm3', phase: 3, label: 'Fase 3 — Ingestão e Merge', status: 'done', date: '2026-02-15', items: ['Upload de artefatos', 'Pré-triagem PII', 'Quarentena LGPD', 'Merge Engine'] },
  { id: 'm4', phase: 4, label: 'Fase 4 — Arguição', status: 'done', date: '2026-03-01', items: ['Arguidor Técnico', 'Respostas versionadas', 'Reabertura de ciclo'] },
  { id: 'm5', phase: 5, label: 'Fase 5 — Code Generator', status: 'active', date: '2026-04-15', items: ['Code Generator', 'Revisão humana', 'Integração ao repositório'] },
  { id: 'm6', phase: 6, label: 'Fase 6 — QA Readiness', status: 'pending', date: '2026-05-20', items: ['Executor isolado', 'Imagens por stack', 'Evidências', 'Dashboard QA'] },
  { id: 'm7', phase: 7, label: 'Fase 7 — Docs e Auditoria', status: 'pending', date: '2026-06-30', items: ['Documentação Viva', 'Roadmap', 'Auditoria global', 'Alertas operacionais'] },
];

const statusStyle = (s: string) => {
  if (s === 'done') return 'text-emerald-400 border-emerald-600';
  if (s === 'active') return 'text-violet-400 border-violet-600';
  return 'text-slate-600 border-slate-700';
};

/** Derive active phase from MILESTONES data (no mock dependency) */
const currentPhase = MILESTONES.find(m => m.status === 'active')?.phase ?? 1;
const doneCount = MILESTONES.filter(m => m.status === 'done').length;
const progressPercent = Math.round((doneCount / MILESTONES.length) * 100);

export function RoadmapPage() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<'timeline' | 'decisions'>('timeline');

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-1.5">
            Roadmap do Projeto
            <HelpTooltip text="O Roadmap é a visão macro do projeto organizada em fases de desenvolvimento. É gerado automaticamente pelo GCA a partir do OCG, que define quais módulos existem, suas dependências e complexidade estimada (alta/média/baixa = Fase 1/2/3). Atualiza-se em tempo real: módulo aprovado no Gatekeeper → fica verde; módulo bloqueado → fica vermelho. É a principal ferramenta de acompanhamento para o GP e para o cliente." />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Evolução de requisitos, decisões arquiteturais e vínculos históricos</p>
        </div>
        {/* Barra de progresso geral */}
        <div className="flex items-center gap-3 min-w-[200px]">
          <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
            <div className="h-full bg-violet-600 rounded-full transition-all duration-500" style={{ width: `${progressPercent}%` }} />
          </div>
          <span className="text-xs text-slate-400 font-medium whitespace-nowrap">{doneCount}/{MILESTONES.length} fases ({progressPercent}%)</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-slate-800">
        {(['timeline', 'decisions'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${activeTab === tab ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
          >
            {tab === 'timeline' ? 'Timeline de Fases' : 'Decisões e ADRs'}
          </button>
        ))}
        <HelpTooltip text="Alterna entre visualização em cards agrupados por fase (padrão, ideal para acompanhamento visual) e tabela detalhada com filtros (ideal para projetos grandes com muitos módulos ou para exportação em PDF). Ambas as vistas refletem o mesmo estado em tempo real." />
      </div>

      {activeTab === 'timeline' && (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[18px] top-4 bottom-4 w-0.5 bg-slate-800" />
          <div className="space-y-4">
            {MILESTONES.map(ms => {
              const isActive = ms.phase === currentPhase;
              const isDone = ms.phase < currentPhase;
              const isPending = ms.phase > currentPhase;
              return (
                <div key={ms.id} className="flex gap-4">
                  {/* Node */}
                  <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center flex-shrink-0 z-10 ${isDone ? 'bg-emerald-900/40 border-emerald-600' : isActive ? 'bg-violet-900/40 border-violet-600 ring-4 ring-violet-600/10' : 'bg-slate-900 border-slate-700'}`}>
                    {isDone ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : isActive ? <span className="w-2.5 h-2.5 rounded-full bg-violet-400 animate-pulse" /> : <Circle className="w-4 h-4 text-slate-600" />}
                  </div>
                  {/* Content */}
                  <div className={`flex-1 p-4 rounded-xl border mb-1 ${isDone ? 'border-slate-800 opacity-75' : isActive ? 'border-violet-600/40 bg-violet-950/10' : 'border-slate-800'}`}>
                    <div className="flex items-start justify-between mb-2 flex-wrap gap-2">
                      <div>
                        <p className={`text-sm font-medium ${isDone ? 'text-slate-300' : isActive ? 'text-violet-300' : 'text-slate-500'}`}>{ms.label}</p>
                        <p className="text-slate-500 text-xs mt-0.5">{ms.date}</p>
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded ${isDone ? 'bg-emerald-900/30 text-emerald-400' : isActive ? 'bg-violet-900/30 text-violet-400' : 'bg-slate-800 text-slate-600'}`}>
                        {isDone ? 'Concluída' : isActive ? 'Em andamento' : 'Pendente'}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {ms.items.map(item => (
                        <span key={item} className="flex items-center gap-1 text-xs text-slate-500 bg-slate-800/70 px-2 py-0.5 rounded">
                          <GitCommit className="w-3 h-3" />{item}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {activeTab === 'decisions' && (
        <div className="space-y-4">
          {DECISIONS.map(dec => (
            <div key={dec.id} className={`p-5 rounded-xl border ${dec.status === 'approved' ? 'border-emerald-800/30 bg-emerald-950/5' : 'border-amber-800/20 bg-amber-950/5'}`}>
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                  <Tag className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${dec.type === 'ADR' ? 'bg-violet-900/40 text-violet-400' : dec.type === 'Override' ? 'bg-amber-900/40 text-amber-400' : 'bg-blue-900/40 text-blue-400'}`}>{dec.type}</span>
                  <p className="text-slate-200 text-sm font-medium">{dec.title}</p>
                </div>
                <span className={`text-xs flex-shrink-0 ${dec.status === 'approved' ? 'text-emerald-400' : 'text-amber-400'}`}>{dec.status === 'approved' ? 'Aprovado' : 'Pendente'}</span>
              </div>
              <p className="text-slate-400 text-sm leading-relaxed">{dec.description}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                <span>{dec.author}</span>
                {dec.date !== '—' && <><span>·</span><span>{dec.date}</span></>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
