import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Settings, Brain, GitBranch, Plug, Layers, Shield, FileText, TestTube2, Users, Activity, History, Check, ChevronDown, ChevronRight, Edit2, Info } from 'lucide-react';
import { getProjectById, getUserById } from '../../data/mockData';
import { StatusBadge, RoleBadge } from '../../components/ui/StatusBadge';

const DIMENSIONS = [
  { key: 'identity', label: 'Identidade', icon: Settings, color: 'indigo' },
  { key: 'ai', label: 'Credenciais de IA', icon: Brain, color: 'violet' },
  { key: 'repo', label: 'Repositório', icon: GitBranch, color: 'blue' },
  { key: 'integrations', label: 'Integrações', icon: Plug, color: 'cyan' },
  { key: 'stack', label: 'Stack e Infraestrutura', icon: Layers, color: 'teal' },
  { key: 'compliance', label: 'ComplianceProfile', icon: Shield, color: 'amber' },
  { key: 'artifacts', label: 'Artefatos Ativos', icon: FileText, color: 'orange' },
  { key: 'qa', label: 'Seleção QA', icon: TestTube2, color: 'emerald' },
  { key: 'team', label: 'Equipe e RBAC', icon: Users, color: 'pink' },
  { key: 'delivery', label: 'Estado de Entrega', icon: Activity, color: 'red' },
  { key: 'history', label: 'Histórico', icon: History, color: 'slate' },
];

const colorClass: Record<string, string> = {
  indigo: 'bg-indigo-900/20 border-indigo-800/30 text-indigo-400',
  violet: 'bg-violet-900/20 border-violet-800/30 text-violet-400',
  blue: 'bg-blue-900/20 border-blue-800/30 text-blue-400',
  cyan: 'bg-cyan-900/20 border-cyan-800/30 text-cyan-400',
  teal: 'bg-teal-900/20 border-teal-800/30 text-teal-400',
  amber: 'bg-amber-900/20 border-amber-800/30 text-amber-400',
  orange: 'bg-orange-900/20 border-orange-800/30 text-orange-400',
  emerald: 'bg-emerald-900/20 border-emerald-800/30 text-emerald-400',
  pink: 'bg-pink-900/20 border-pink-800/30 text-pink-400',
  red: 'bg-red-900/20 border-red-800/30 text-red-400',
  slate: 'bg-slate-800 border-slate-700 text-slate-400',
};

export function OCGPage() {
  const { id } = useParams<{ id: string }>();
  const project = getProjectById(id!);
  const [expanded, setExpanded] = useState<string | null>('identity');
  if (!project) return null;

  const gp = getUserById(project.gpId);

  const renderContent = (key: string) => {
    switch (key) {
      case 'identity':
        return (
          <div className="grid grid-cols-2 gap-4">
            <OCGField label="Nome" value={project.name} />
            <OCGField label="Slug" value={project.slug} mono />
            <OCGField label="Descrição" value={project.description} full />
            <OCGField label="OutputProfile" value={project.outputProfile} />
            <OCGField label="Status" value={<StatusBadge status={project.status} />} />
            <OCGField label="Metodologia" value="Ágil (Scrum)" />
          </div>
        );
      case 'ai':
        return (
          <div className="grid grid-cols-2 gap-4">
            <OCGField label="Provedor" value={project.ai.provider} />
            <OCGField label="Modelo" value={project.ai.model} mono />
            <OCGField label="Tokens usados" value={project.ai.tokensUsed.toLocaleString('pt-BR')} />
            <OCGField label="Limite de tokens" value={project.ai.tokenLimit.toLocaleString('pt-BR')} />
            <OCGField label="Custo estimado" value={`R$ ${project.ai.costEstimated.toFixed(2)}`} />
            <OCGField label="Política de envio externo" value="Mascaramento obrigatório de PII antes do envio" full />
            <OCGField label="Retenção" value="Sem retenção de prompt pelo provedor" />
            <OCGField label="Fallback" value="Modo degradado sem IA" />
          </div>
        );
      case 'repo':
        return project.repository ? (
          <div className="grid grid-cols-2 gap-4">
            <OCGField label="URL" value={project.repository.url} mono full />
            <OCGField label="Branch principal" value={project.repository.branch} mono />
            <OCGField label="Branch docs" value={project.repository.docBranch} mono />
            <OCGField label="Provedor" value={project.repository.provider} />
            <OCGField label="Webhook" value={<StatusBadge status={project.repository.webhook} />} />
            <OCGField label="Política de merge" value="PR obrigatório com revisão" />
          </div>
        ) : <p className="text-slate-500 text-sm">Repositório não configurado.</p>;
      case 'stack':
        return (
          <div className="grid grid-cols-2 gap-4">
            <OCGField label="Linguagem" value={project.stack.language} />
            <OCGField label="Framework" value={project.stack.framework} />
            <OCGField label="Banco de dados" value={project.stack.database} />
            {project.stack.frontend && <OCGField label="Frontend" value={project.stack.frontend} />}
            {project.stack.messaging && <OCGField label="Mensageria" value={project.stack.messaging} />}
            <OCGField label="Containerização" value="Docker + Docker Compose" />
          </div>
        );
      case 'compliance':
        return (
          <div className="grid grid-cols-2 gap-4">
            <OCGField label="LGPD" value="Aplicável · Quarentena PII ativa" />
            <OCGField label="OWASP Top 10" value="Proteções obrigatórias" />
            <OCGField label="Mascaramento" value="Regex + dicionários + regras Admin" />
            <OCGField label="Retenção de dados" value="90 dias para logs; artefatos: 2 anos" full />
            <OCGField label="NIST alignment" value="Moderado" />
            <OCGField label="Audit trail" value="Append-only com hash encadeado" />
          </div>
        );
      case 'team':
        return (
          <div className="space-y-2">
            {project.team.map(m => {
              const user = getUserById(m.userId);
              return user ? (
                <div key={m.userId} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/40">
                  <div className="w-7 h-7 rounded-full bg-indigo-700/50 flex items-center justify-center text-white text-xs font-semibold">{user.name.charAt(0)}</div>
                  <div className="flex-1">
                    <p className="text-slate-200 text-sm">{user.name}</p>
                    <p className="text-slate-500 text-xs">{user.email}</p>
                  </div>
                  <RoleBadge role={m.role} />
                  {m.capabilities && m.capabilities.length > 0 && (
                    <div className="flex gap-1">{m.capabilities.map(cap => <span key={cap} className="text-xs text-indigo-400 bg-indigo-900/20 px-1.5 py-0.5 rounded">{cap}</span>)}</div>
                  )}
                </div>
              ) : null;
            })}
          </div>
        );
      case 'delivery':
        return (
          <div className="grid grid-cols-2 gap-4">
            <OCGField label="Fase atual" value={`${project.phase}`} />
            <OCGField label="Score Gatekeeper" value={`${project.gatekeeper.score}/100`} />
            <OCGField label="Status Gatekeeper" value={<StatusBadge status={project.gatekeeper.status} />} />
            <OCGField label="OCG Completo" value={project.ocgComplete ? '✓ Sim' : '✗ Não'} />
            <OCGField label="Questionário técnico" value={project.questionnaireComplete ? '✓ Sim' : '✗ Não'} />
            <OCGField label="Pendências" value={project.pendingIssues.toString()} />
          </div>
        );
      case 'history':
        return (
          <div className="space-y-3">
            {[
              { date: '2026-04-01', actor: gp?.name ?? '—', action: 'OCG atualizado: modelo de IA alterado para gpt-4o', hash: 'sha256:ocghist003' },
              { date: '2026-03-22', actor: 'Bruno Alves', action: 'Stack atualizada: mensageria Kafka adicionada', hash: 'sha256:ocghist002' },
              { date: project.createdAt.split('T')[0], actor: 'Admin GCA', action: 'OCG criado e provisionamento iniciado', hash: 'sha256:ocghist001' },
            ].map((ev, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-slate-800/30">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 flex-shrink-0" />
                <div>
                  <p className="text-slate-300 text-sm">{ev.action}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-slate-500 text-xs">{ev.actor}</span>
                    <span className="text-slate-600">·</span>
                    <span className="text-slate-500 text-xs">{ev.date}</span>
                    <span className="text-slate-600">·</span>
                    <code className="text-indigo-400 text-xs">{ev.hash}</code>
                  </div>
                </div>
              </div>
            ))}
          </div>
        );
      default:
        return <p className="text-slate-500 text-sm">Conteúdo desta dimensão a ser detalhado.</p>;
    }
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">OCG — Objeto de Contexto Global</h2>
          <p className="text-slate-500 text-sm mt-0.5">Nenhum módulo opera sobre um projeto sem antes ler seu OCG.</p>
        </div>
        <div className="flex items-center gap-2">
          {project.ocgComplete ? (
            <span className="flex items-center gap-1.5 text-emerald-400 text-sm"><Check className="w-4 h-4" /> OCG Completo</span>
          ) : (
            <span className="flex items-center gap-1.5 text-amber-400 text-sm"><Info className="w-4 h-4" /> OCG Incompleto</span>
          )}
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 border border-indigo-600/30 text-indigo-400 text-sm hover:bg-indigo-600/30 transition-colors">
            <Edit2 className="w-3.5 h-3.5" /> Editar OCG
          </button>
        </div>
      </div>

      {DIMENSIONS.map(dim => {
        const Icon = dim.icon;
        const isOpen = expanded === dim.key;
        return (
          <div key={dim.key} className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setExpanded(isOpen ? null : dim.key)}
              className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-800/40 transition-colors"
            >
              <div className={`w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0 ${colorClass[dim.color]}`}>
                <Icon className="w-4 h-4" />
              </div>
              <span className="text-slate-200 text-sm font-medium flex-1 text-left">{dim.label}</span>
              {isOpen ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
            </button>
            {isOpen && (
              <div className="px-5 pb-5 border-t border-slate-800">
                <div className="pt-4">{renderContent(dim.key)}</div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function OCGField({ label, value, mono = false, full = false }: { label: string; value: React.ReactNode; mono?: boolean; full?: boolean }) {
  return (
    <div className={`${full ? 'col-span-2' : ''}`}>
      <p className="text-slate-500 text-xs mb-1">{label}</p>
      {typeof value === 'string' ? (
        <p className={`text-sm ${mono ? 'font-mono text-indigo-300' : 'text-slate-200'}`}>{value}</p>
      ) : value}
    </div>
  );
}
