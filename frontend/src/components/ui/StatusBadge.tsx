import React from 'react';
import { ProjectStatus, ArtifactStatus, GatekeeperStatus, CodeGenStatus, TestStatus, WebhookStatus, CredentialStatus } from '../../data/mockData';

type AnyStatus = ProjectStatus | ArtifactStatus | GatekeeperStatus | CodeGenStatus | TestStatus | WebhookStatus | CredentialStatus | string;

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  // Project
  draft: { label: 'Rascunho', className: 'bg-slate-700 text-slate-300' },
  provisioning: { label: 'Provisionando', className: 'bg-blue-900/60 text-blue-300 animate-pulse' },
  provisioning_failed: { label: 'Falha no Prov.', className: 'bg-red-900/60 text-red-300' },
  active: { label: 'Ativo', className: 'bg-emerald-900/60 text-emerald-300' },
  degraded: { label: 'Degradado', className: 'bg-amber-900/60 text-amber-300' },
  suspended: { label: 'Suspenso', className: 'bg-orange-900/60 text-orange-300' },
  archived: { label: 'Arquivado', className: 'bg-slate-800 text-slate-500' },
  // Artifact
  uploaded: { label: 'Enviado', className: 'bg-slate-700 text-slate-300' },
  extracted: { label: 'Extraído', className: 'bg-blue-900/60 text-blue-300' },
  pii_quarantine: { label: 'Quarentena PII', className: 'bg-red-900/60 text-red-300' },
  classified: { label: 'Classificado', className: 'bg-violet-900/60 text-violet-300' },
  pending_review: { label: 'Revisão Pendente', className: 'bg-amber-900/60 text-amber-300' },
  merged: { label: 'Consolidado', className: 'bg-emerald-900/60 text-emerald-300' },
  rejected: { label: 'Rejeitado', className: 'bg-red-900/60 text-red-300' },
  superseded: { label: 'Substituído', className: 'bg-slate-700 text-slate-400' },
  // Gatekeeper
  not_started: { label: 'Não iniciado', className: 'bg-slate-700 text-slate-400' },
  in_progress: { label: 'Em avaliação', className: 'bg-blue-900/60 text-blue-300' },
  blocked: { label: 'Bloqueado', className: 'bg-red-900/60 text-red-300' },
  approved: { label: 'Aprovado', className: 'bg-emerald-900/60 text-emerald-300' },
  approved_with_override: { label: 'Aprovado c/ Override', className: 'bg-amber-900/60 text-amber-300' },
  // CodeGen
  requested: { label: 'Solicitado', className: 'bg-slate-700 text-slate-300' },
  drafting: { label: 'Gerando', className: 'bg-blue-900/60 text-blue-300 animate-pulse' },
  in_review: { label: 'Em revisão', className: 'bg-amber-900/60 text-amber-300' },
  pushed: { label: 'Enviado', className: 'bg-emerald-900/60 text-emerald-300' },
  failed: { label: 'Falhou', className: 'bg-red-900/60 text-red-300' },
  // Test
  queued: { label: 'Na fila', className: 'bg-slate-700 text-slate-300' },
  running: { label: 'Executando', className: 'bg-blue-900/60 text-blue-300 animate-pulse' },
  passed: { label: 'Passou', className: 'bg-emerald-900/60 text-emerald-300' },
  waived: { label: 'Dispensado', className: 'bg-violet-900/60 text-violet-300' },
  // Webhook
  pending_setup: { label: 'Pendente', className: 'bg-amber-900/60 text-amber-300' },
  invalid: { label: 'Inválido', className: 'bg-red-900/60 text-red-300' },
  // Credential
  valid: { label: 'Válida', className: 'bg-emerald-900/60 text-emerald-300' },
  warning: { label: 'Atenção', className: 'bg-amber-900/60 text-amber-300' },
  expired: { label: 'Expirada', className: 'bg-red-900/60 text-red-300' },
  suspected: { label: 'Suspeita', className: 'bg-red-900/60 text-red-300' },
  rotated: { label: 'Rotacionada', className: 'bg-violet-900/60 text-violet-300' },
  disabled: { label: 'Desabilitada', className: 'bg-slate-700 text-slate-500' },
};

interface StatusBadgeProps {
  status: AnyStatus;
  size?: 'sm' | 'md';
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? { label: status, className: 'bg-slate-700 text-slate-300' };
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-xs';
  return (
    <span className={`inline-flex items-center rounded-md font-medium ${sizeClass} ${config.className}`}>
      {config.label}
    </span>
  );
}

export function RoleBadge({ role }: { role: string }) {
  const config: Record<string, { label: string; className: string }> = {
    admin: { label: 'Admin GCA', className: 'bg-indigo-900/60 text-indigo-300' },
    gp: { label: 'Ger. de Projeto', className: 'bg-blue-900/60 text-blue-300' },
    tech_lead: { label: 'Tech Lead', className: 'bg-violet-900/60 text-violet-300' },
    senior_dev: { label: 'Dev Sênior', className: 'bg-cyan-900/60 text-cyan-300' },
    pleno_dev: { label: 'Dev Pleno', className: 'bg-teal-900/60 text-teal-300' },
    qa: { label: 'QA Engineer', className: 'bg-emerald-900/60 text-emerald-300' },
    compliance: { label: 'Compliance', className: 'bg-amber-900/60 text-amber-300' },
    stakeholder: { label: 'Stakeholder', className: 'bg-slate-700 text-slate-300' },
  };
  const c = config[role] ?? { label: role, className: 'bg-slate-700 text-slate-300' };
  return <span className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ${c.className}`}>{c.label}</span>;
}
