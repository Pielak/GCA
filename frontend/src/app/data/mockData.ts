export type ProjectStatus = 'draft' | 'provisioning' | 'provisioning_failed' | 'active' | 'degraded' | 'suspended' | 'archived';
export type ArtifactStatus = 'uploaded' | 'extracted' | 'pii_quarantine' | 'classified' | 'pending_review' | 'merged' | 'rejected' | 'superseded';
export type GatekeeperStatus = 'not_started' | 'in_progress' | 'blocked' | 'approved' | 'approved_with_override';
export type CodeGenStatus = 'requested' | 'drafting' | 'in_review' | 'approved' | 'rejected' | 'pushed' | 'failed';
export type TestStatus = 'queued' | 'running' | 'passed' | 'failed' | 'blocked' | 'waived';
export type WebhookStatus = 'pending_setup' | 'active' | 'invalid' | 'suspended';
export type CredentialStatus = 'valid' | 'warning' | 'expired' | 'suspected' | 'rotated' | 'disabled';
export type UserRole = 'admin' | 'gp' | 'tech_lead' | 'senior_dev' | 'pleno_dev' | 'qa' | 'compliance' | 'stakeholder';
export type OutputProfile = 'web_app' | 'api' | 'desktop' | 'mobile' | 'improvement' | 'new_feature';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
  active: boolean;
  createdAt: string;
}

export interface TeamMember {
  userId: string;
  role: UserRole;
  capabilities?: string[];
}

export interface PillarScore {
  pillar: string;
  score: number;
  maxScore: number;
  status: 'ok' | 'warning' | 'blocker';
  notes?: string;
}

export interface Artifact {
  id: string;
  name: string;
  type: string;
  status: ArtifactStatus;
  hash: string;
  size: string;
  uploadedBy: string;
  uploadedAt: string;
  piiFlags?: string[];
  version: number;
}

export interface CodeGenRequest {
  id: string;
  title: string;
  description: string;
  status: CodeGenStatus;
  requestedBy: string;
  requestedAt: string;
  approvedBy?: string;
  language: string;
  lines?: number;
  commitHash?: string;
}

export interface TestExecution {
  id: string;
  name: string;
  type: string;
  status: TestStatus;
  duration?: string;
  coverage?: number;
  startedAt: string;
  finishedAt?: string;
  evidence?: string;
}

export interface AuditEvent {
  id: string;
  projectId?: string;
  projectName?: string;
  action: string;
  actor: string;
  actorRole: string;
  target: string;
  detail: string;
  timestamp: string;
  hash: string;
  prevHash: string;
  level: 'info' | 'warning' | 'critical';
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: ProjectStatus;
  outputProfile: OutputProfile;
  phase: number;
  stack: {
    language: string;
    framework: string;
    database: string;
    frontend?: string;
    messaging?: string;
  };
  gpId: string;
  team: TeamMember[];
  gatekeeper: {
    score: number;
    status: GatekeeperStatus;
    pillars: PillarScore[];
  };
  repository?: {
    url: string;
    branch: string;
    docBranch: string;
    webhook: WebhookStatus;
    provider: 'github' | 'gitlab' | 'bitbucket';
  };
  ai: {
    provider: string;
    model: string;
    tokensUsed: number;
    tokenLimit: number;
    costEstimated: number;
  };
  credentials: { name: string; type: string; status: CredentialStatus; expiresAt?: string }[];
  artifacts: Artifact[];
  codeGenRequests: CodeGenRequest[];
  testExecutions: TestExecution[];
  requestedBy: string;
  requestedAt: string;
  createdAt: string;
  activatedAt?: string;
  legacyRepo?: string;
  pendingIssues: number;
  ocgComplete: boolean;
  questionnaireComplete: boolean;
}

export const USERS: User[] = [
  { id: 'u1', name: 'Rafael Mendes', email: 'rafael@gca.dev', role: 'admin', active: true, createdAt: '2025-01-10' },
  { id: 'u2', name: 'Carla Sousa', email: 'carla@gca.dev', role: 'gp', active: true, createdAt: '2025-01-15' },
  { id: 'u3', name: 'Bruno Alves', email: 'bruno@gca.dev', role: 'tech_lead', active: true, createdAt: '2025-02-01' },
  { id: 'u4', name: 'Fernanda Lima', email: 'fernanda@gca.dev', role: 'senior_dev', active: true, createdAt: '2025-02-10' },
  { id: 'u5', name: 'Diego Costa', email: 'diego@gca.dev', role: 'pleno_dev', active: true, createdAt: '2025-02-15' },
  { id: 'u6', name: 'Isabela Rocha', email: 'isabela@gca.dev', role: 'qa', active: true, createdAt: '2025-03-01' },
  { id: 'u7', name: 'Marcos Pinto', email: 'marcos@gca.dev', role: 'compliance', active: true, createdAt: '2025-03-10' },
  { id: 'u8', name: 'Ana Ferreira', email: 'ana@gca.dev', role: 'stakeholder', active: true, createdAt: '2025-03-15' },
  { id: 'u9', name: 'Pedro Nunes', email: 'pedro@gca.dev', role: 'gp', active: true, createdAt: '2025-03-20' },
  { id: 'u10', name: 'Juliana Melo', email: 'juliana@gca.dev', role: 'tech_lead', active: false, createdAt: '2025-04-01' },
];

const PILLARS: PillarScore[] = [
  { pillar: 'Completude de Requisitos', score: 82, maxScore: 100, status: 'ok', notes: 'Todos os requisitos funcionais documentados.' },
  { pillar: 'Clareza Técnica', score: 74, maxScore: 100, status: 'warning', notes: 'Algumas especificações de API precisam de detalhamento.' },
  { pillar: 'Consistência Documental', score: 91, maxScore: 100, status: 'ok', notes: 'Sem conflitos críticos entre artefatos.' },
  { pillar: 'Cobertura de Segurança', score: 55, maxScore: 100, status: 'blocker', notes: 'Modelo de ameaças não aprovado. Blocker ativo.' },
  { pillar: 'Conformidade (Compliance)', score: 88, maxScore: 100, status: 'ok', notes: 'LGPD e OWASP revisados.' },
  { pillar: 'Viabilidade de Implementação', score: 79, maxScore: 100, status: 'ok', notes: 'Stack definida e validada.' },
  { pillar: 'Qualidade e Testabilidade', score: 67, maxScore: 100, status: 'warning', notes: 'Plano de QA incompleto.' },
];

const PILLARS_OK: PillarScore[] = PILLARS.map(p => ({ ...p, score: p.score + 15 > 100 ? 100 : p.score + 15, status: 'ok' as const, notes: 'Aprovado.' }));

export const PROJECTS: Project[] = [
  {
    id: 'proj-001',
    name: 'Portal de Clientes v2',
    slug: 'portal-clientes-v2',
    description: 'Evolução do portal web de clientes com novo design system e módulo de autoatendimento.',
    status: 'active',
    outputProfile: 'web_app',
    phase: 5,
    stack: { language: 'TypeScript', framework: 'React 18 / FastAPI', database: 'PostgreSQL 16', frontend: 'React + Tailwind', messaging: 'Kafka' },
    gpId: 'u2',
    team: [
      { userId: 'u2', role: 'gp' },
      { userId: 'u3', role: 'tech_lead', capabilities: ['APPROVE_CODE', 'OVERRIDE_GATEKEEPER'] },
      { userId: 'u4', role: 'senior_dev', capabilities: ['REQUEST_CODEGEN'] },
      { userId: 'u5', role: 'pleno_dev' },
      { userId: 'u6', role: 'qa', capabilities: ['APPROVE_QUARANTINE'] },
      { userId: 'u7', role: 'compliance' },
    ],
    gatekeeper: {
      score: 72,
      status: 'blocked',
      pillars: PILLARS,
    },
    repository: {
      url: 'https://github.com/empresa/portal-clientes-v2',
      branch: 'main',
      docBranch: 'docs/gca',
      webhook: 'active',
      provider: 'github',
    },
    ai: { provider: 'OpenAI', model: 'gpt-4o', tokensUsed: 128450, tokenLimit: 500000, costEstimated: 3.84 },
    credentials: [
      { name: 'GitHub Token', type: 'repository', status: 'valid', expiresAt: '2026-12-31' },
      { name: 'OpenAI API Key', type: 'ai', status: 'valid' },
      { name: 'PostgreSQL DSN', type: 'database', status: 'valid' },
      { name: 'SMTP Prod', type: 'email', status: 'warning', expiresAt: '2026-05-01' },
    ],
    artifacts: [
      { id: 'art-001', name: 'Especificação Funcional v3.pdf', type: 'PDF', status: 'merged', hash: 'sha256:a1b2c3...', size: '1.2 MB', uploadedBy: 'u2', uploadedAt: '2026-03-10T10:00:00Z', version: 3 },
      { id: 'art-002', name: 'Modelo de Ameaças.docx', type: 'DOCX', status: 'pii_quarantine', hash: 'sha256:d4e5f6...', size: '0.8 MB', uploadedBy: 'u7', uploadedAt: '2026-03-12T14:30:00Z', piiFlags: ['CPF detectado', 'E-mail detectado'], version: 1 },
      { id: 'art-003', name: 'Backlog Técnico.md', type: 'Markdown', status: 'classified', hash: 'sha256:g7h8i9...', size: '0.1 MB', uploadedBy: 'u3', uploadedAt: '2026-03-15T09:00:00Z', version: 1 },
      { id: 'art-004', name: 'Requisitos de Segurança.txt', type: 'TXT', status: 'pending_review', hash: 'sha256:j1k2l3...', size: '0.05 MB', uploadedBy: 'u7', uploadedAt: '2026-03-18T11:00:00Z', version: 1 },
    ],
    codeGenRequests: [
      { id: 'cg-001', title: 'Módulo de Autenticação JWT', description: 'Gerar serviço de autenticação com refresh token, revogação e bcrypt.', status: 'pushed', requestedBy: 'u4', requestedAt: '2026-03-20T08:00:00Z', approvedBy: 'u3', language: 'Python', lines: 342, commitHash: 'abc1234' },
      { id: 'cg-002', title: 'Componente de Dashboard React', description: 'Gerar componente de dashboard com recharts e indicadores do OCG.', status: 'in_review', requestedBy: 'u4', requestedAt: '2026-03-25T10:00:00Z', language: 'TypeScript', lines: 218 },
      { id: 'cg-003', title: 'Schema PostgreSQL inicial', description: 'DDL para tabelas de usuário, projeto e artefato.', status: 'approved', requestedBy: 'u3', requestedAt: '2026-03-28T15:00:00Z', approvedBy: 'u3', language: 'SQL', lines: 87 },
    ],
    testExecutions: [
      { id: 'te-001', name: 'Smoke Tests — Login e Health', type: 'Smoke', status: 'passed', duration: '1m 12s', startedAt: '2026-03-30T09:00:00Z', finishedAt: '2026-03-30T09:01:12Z', evidence: 'smoke-report-001.html', coverage: 0 },
      { id: 'te-002', name: 'Testes Unitários — Services', type: 'Unitário', status: 'passed', duration: '4m 38s', startedAt: '2026-03-30T09:05:00Z', finishedAt: '2026-03-30T09:09:38Z', evidence: 'unit-report-001.xml', coverage: 78 },
      { id: 'te-003', name: 'Testes de Integração — API + DB', type: 'Integração', status: 'failed', duration: '8m 11s', startedAt: '2026-03-30T09:15:00Z', finishedAt: '2026-03-30T09:23:11Z', evidence: 'integration-report-001.html', coverage: 0 },
      { id: 'te-004', name: 'Testes E2E — Fluxo de Login', type: 'E2E', status: 'queued', startedAt: '2026-03-30T10:00:00Z', coverage: 0 },
    ],
    requestedBy: 'u2',
    requestedAt: '2026-01-15T08:00:00Z',
    createdAt: '2026-01-20T10:00:00Z',
    activatedAt: '2026-01-22T14:00:00Z',
    legacyRepo: 'https://github.com/empresa/portal-clientes-v1',
    pendingIssues: 3,
    ocgComplete: true,
    questionnaireComplete: true,
  },
  {
    id: 'proj-002',
    name: 'API de Pagamentos',
    slug: 'api-pagamentos',
    description: 'Nova API RESTful para integração com gateways de pagamento e processamento assíncrono.',
    status: 'active',
    outputProfile: 'api',
    phase: 7,
    stack: { language: 'Python', framework: 'FastAPI', database: 'PostgreSQL 16', messaging: 'Kafka' },
    gpId: 'u9',
    team: [
      { userId: 'u9', role: 'gp' },
      { userId: 'u10', role: 'tech_lead' },
      { userId: 'u4', role: 'senior_dev', capabilities: ['REQUEST_CODEGEN'] },
      { userId: 'u6', role: 'qa', capabilities: ['APPROVE_QUARANTINE'] },
    ],
    gatekeeper: { score: 94, status: 'approved', pillars: PILLARS_OK },
    repository: {
      url: 'https://github.com/empresa/api-pagamentos',
      branch: 'main',
      docBranch: 'docs/gca',
      webhook: 'active',
      provider: 'github',
    },
    ai: { provider: 'Anthropic', model: 'claude-3-5-sonnet', tokensUsed: 89200, tokenLimit: 300000, costEstimated: 2.12 },
    credentials: [
      { name: 'GitHub Token', type: 'repository', status: 'valid', expiresAt: '2027-01-01' },
      { name: 'Anthropic API Key', type: 'ai', status: 'valid' },
      { name: 'PostgreSQL DSN', type: 'database', status: 'valid' },
      { name: 'Stripe API Key', type: 'integration', status: 'valid', expiresAt: '2027-06-01' },
    ],
    artifacts: [
      { id: 'art-010', name: 'Contrato OpenAPI v2.yaml', type: 'YAML', status: 'merged', hash: 'sha256:m4n5o6...', size: '0.3 MB', uploadedBy: 'u10', uploadedAt: '2026-02-10T10:00:00Z', version: 2 },
      { id: 'art-011', name: 'Especificação de Segurança.pdf', type: 'PDF', status: 'merged', hash: 'sha256:p7q8r9...', size: '2.1 MB', uploadedBy: 'u9', uploadedAt: '2026-02-12T14:00:00Z', version: 1 },
      { id: 'art-012', name: 'Plano de QA v1.md', type: 'Markdown', status: 'merged', hash: 'sha256:s1t2u3...', size: '0.2 MB', uploadedBy: 'u6', uploadedAt: '2026-02-15T09:00:00Z', version: 1 },
    ],
    codeGenRequests: [
      { id: 'cg-010', title: 'Service de Processamento Assíncrono', description: 'Worker Kafka para processamento de transações.', status: 'pushed', requestedBy: 'u4', requestedAt: '2026-03-01T10:00:00Z', approvedBy: 'u10', language: 'Python', lines: 512, commitHash: 'def5678' },
      { id: 'cg-011', title: 'Testes Unitários — Payment Service', description: 'pytest com cobertura de 85%.', status: 'pushed', requestedBy: 'u4', requestedAt: '2026-03-10T10:00:00Z', approvedBy: 'u10', language: 'Python', lines: 289, commitHash: 'ghi9012' },
    ],
    testExecutions: [
      { id: 'te-010', name: 'Smoke Tests', type: 'Smoke', status: 'passed', duration: '0m 58s', startedAt: '2026-03-29T08:00:00Z', finishedAt: '2026-03-29T08:00:58Z', evidence: 'smoke-report-010.html', coverage: 0 },
      { id: 'te-011', name: 'Unitários — Completo', type: 'Unitário', status: 'passed', duration: '6m 22s', startedAt: '2026-03-29T08:05:00Z', finishedAt: '2026-03-29T08:11:22Z', coverage: 87 },
      { id: 'te-012', name: 'Integração — Stripe + Kafka', type: 'Integração', status: 'passed', duration: '12m 04s', startedAt: '2026-03-29T08:15:00Z', finishedAt: '2026-03-29T08:27:04Z', coverage: 71 },
      { id: 'te-013', name: 'Segurança — DAST', type: 'Segurança', status: 'passed', duration: '18m 30s', startedAt: '2026-03-29T08:30:00Z', finishedAt: '2026-03-29T08:48:30Z', coverage: 0 },
    ],
    requestedBy: 'u9',
    requestedAt: '2025-12-01T08:00:00Z',
    createdAt: '2025-12-05T10:00:00Z',
    activatedAt: '2025-12-08T14:00:00Z',
    pendingIssues: 0,
    ocgComplete: true,
    questionnaireComplete: true,
  },
  {
    id: 'proj-003',
    name: 'App Mobile RH',
    slug: 'app-mobile-rh',
    description: 'Aplicativo mobile para gestão de ponto, férias e comunicados internos de RH.',
    status: 'provisioning',
    outputProfile: 'mobile',
    phase: 2,
    stack: { language: 'TypeScript', framework: 'React Native', database: 'PostgreSQL 16', frontend: 'React Native' },
    gpId: 'u2',
    team: [
      { userId: 'u2', role: 'gp' },
      { userId: 'u5', role: 'pleno_dev' },
    ],
    gatekeeper: { score: 0, status: 'not_started', pillars: [] },
    ai: { provider: 'OpenAI', model: 'gpt-4o-mini', tokensUsed: 2100, tokenLimit: 200000, costEstimated: 0.08 },
    credentials: [
      { name: 'OpenAI API Key', type: 'ai', status: 'valid' },
    ],
    artifacts: [],
    codeGenRequests: [],
    testExecutions: [],
    requestedBy: 'u2',
    requestedAt: '2026-03-28T08:00:00Z',
    createdAt: '2026-03-30T10:00:00Z',
    pendingIssues: 5,
    ocgComplete: false,
    questionnaireComplete: false,
  },
  {
    id: 'proj-004',
    name: 'Sistema de BI Interno',
    slug: 'sistema-bi-interno',
    description: 'Dashboard analítico para inteligência de negócios consolidando dados de múltiplas fontes.',
    status: 'draft',
    outputProfile: 'web_app',
    phase: 1,
    stack: { language: 'Python', framework: 'FastAPI + Metabase', database: 'PostgreSQL 16', frontend: 'React' },
    gpId: 'u9',
    team: [{ userId: 'u9', role: 'gp' }],
    gatekeeper: { score: 0, status: 'not_started', pillars: [] },
    ai: { provider: '-', model: '-', tokensUsed: 0, tokenLimit: 0, costEstimated: 0 },
    credentials: [],
    artifacts: [],
    codeGenRequests: [],
    testExecutions: [],
    requestedBy: 'u9',
    requestedAt: '2026-04-02T08:00:00Z',
    createdAt: '2026-04-02T08:00:00Z',
    pendingIssues: 0,
    ocgComplete: false,
    questionnaireComplete: false,
  },
  {
    id: 'proj-005',
    name: 'Gateway de Notificações',
    slug: 'gateway-notificacoes',
    description: 'Serviço centralizado de notificações via e-mail, SMS e push para todos os produtos.',
    status: 'degraded',
    outputProfile: 'api',
    phase: 6,
    stack: { language: 'Python', framework: 'FastAPI', database: 'PostgreSQL 16', messaging: 'Kafka' },
    gpId: 'u2',
    team: [
      { userId: 'u2', role: 'gp' },
      { userId: 'u3', role: 'tech_lead' },
      { userId: 'u5', role: 'pleno_dev' },
      { userId: 'u6', role: 'qa' },
    ],
    gatekeeper: { score: 88, status: 'approved', pillars: PILLARS_OK },
    repository: {
      url: 'https://gitlab.com/empresa/gateway-notificacoes',
      branch: 'main',
      docBranch: 'docs/gca',
      webhook: 'invalid',
      provider: 'gitlab',
    },
    ai: { provider: 'OpenAI', model: 'gpt-4o', tokensUsed: 45000, tokenLimit: 300000, costEstimated: 1.35 },
    credentials: [
      { name: 'GitLab Token', type: 'repository', status: 'expired', expiresAt: '2026-03-31' },
      { name: 'OpenAI API Key', type: 'ai', status: 'valid' },
      { name: 'SMTP Prod', type: 'email', status: 'suspected' },
    ],
    artifacts: [
      { id: 'art-020', name: 'Arquitetura do Gateway.pdf', type: 'PDF', status: 'merged', hash: 'sha256:v4w5x6...', size: '1.8 MB', uploadedBy: 'u3', uploadedAt: '2026-02-20T10:00:00Z', version: 1 },
    ],
    codeGenRequests: [
      { id: 'cg-020', title: 'SMS Provider Adapter', description: 'Adapter para integração com Twilio.', status: 'pushed', requestedBy: 'u5', requestedAt: '2026-03-15T10:00:00Z', approvedBy: 'u3', language: 'Python', lines: 198, commitHash: 'jkl3456' },
    ],
    testExecutions: [
      { id: 'te-020', name: 'Smoke Tests', type: 'Smoke', status: 'failed', duration: '2m 10s', startedAt: '2026-03-31T07:00:00Z', finishedAt: '2026-03-31T07:02:10Z', coverage: 0 },
    ],
    requestedBy: 'u2',
    requestedAt: '2025-11-01T08:00:00Z',
    createdAt: '2025-11-05T10:00:00Z',
    activatedAt: '2025-11-08T14:00:00Z',
    pendingIssues: 4,
    ocgComplete: true,
    questionnaireComplete: true,
  },
];

export const AUDIT_EVENTS: AuditEvent[] = [
  { id: 'ev-001', projectId: 'proj-001', projectName: 'Portal de Clientes v2', action: 'ARTIFACT_QUARANTINE', actor: 'rafael@gca.dev', actorRole: 'admin', target: 'art-002', detail: 'Artefato "Modelo de Ameaças.docx" entrou em quarentena por PII detectado (CPF, E-mail).', timestamp: '2026-03-12T14:35:00Z', hash: 'sha256:hash001', prevHash: 'sha256:hash000', level: 'warning' },
  { id: 'ev-002', projectId: 'proj-001', projectName: 'Portal de Clientes v2', action: 'CODEGEN_PUSHED', actor: 'carla@gca.dev', actorRole: 'gp', target: 'cg-001', detail: 'Código "Módulo de Autenticação JWT" aprovado e enviado ao repositório. Commit: abc1234.', timestamp: '2026-03-21T10:20:00Z', hash: 'sha256:hash002', prevHash: 'sha256:hash001', level: 'info' },
  { id: 'ev-003', projectId: 'proj-002', projectName: 'API de Pagamentos', action: 'GATEKEEPER_APPROVED', actor: 'rafael@gca.dev', actorRole: 'admin', target: 'proj-002', detail: 'Gatekeeper aprovado com score 94/100. Todos os 7 pilares verificados.', timestamp: '2026-03-05T16:00:00Z', hash: 'sha256:hash003', prevHash: 'sha256:hash002', level: 'info' },
  { id: 'ev-004', action: 'USER_INVITED', actor: 'rafael@gca.dev', actorRole: 'admin', target: 'u10', detail: 'Usuário "Juliana Melo" convidada como Tech Lead global.', timestamp: '2026-03-25T09:00:00Z', hash: 'sha256:hash004', prevHash: 'sha256:hash003', level: 'info' },
  { id: 'ev-005', projectId: 'proj-005', projectName: 'Gateway de Notificações', action: 'CREDENTIAL_EXPIRED', actor: 'sistema', actorRole: 'system', target: 'GitLab Token', detail: 'Credencial GitLab Token expirou em 2026-03-31. Webhook suspenso automaticamente.', timestamp: '2026-03-31T00:01:00Z', hash: 'sha256:hash005', prevHash: 'sha256:hash004', level: 'critical' },
  { id: 'ev-006', projectId: 'proj-001', projectName: 'Portal de Clientes v2', action: 'GATEKEEPER_BLOCKED', actor: 'sistema', actorRole: 'system', target: 'proj-001', detail: 'Gatekeeper bloqueado no pilar "Cobertura de Segurança". Score 55/100. Arguidor acionado.', timestamp: '2026-03-18T14:00:00Z', hash: 'sha256:hash006', prevHash: 'sha256:hash005', level: 'critical' },
  { id: 'ev-007', projectId: 'proj-003', projectName: 'App Mobile RH', action: 'PROJECT_CREATED', actor: 'rafael@gca.dev', actorRole: 'admin', target: 'proj-003', detail: 'Projeto "App Mobile RH" criado e liberado para parametrização.', timestamp: '2026-03-30T10:00:00Z', hash: 'sha256:hash007', prevHash: 'sha256:hash006', level: 'info' },
  { id: 'ev-008', projectId: 'proj-002', projectName: 'API de Pagamentos', action: 'TEST_PASSED', actor: 'sistema', actorRole: 'system', target: 'te-013', detail: 'DAST concluído com sucesso. Nenhuma vulnerabilidade crítica encontrada.', timestamp: '2026-03-29T08:48:30Z', hash: 'sha256:hash008', prevHash: 'sha256:hash007', level: 'info' },
  { id: 'ev-009', action: 'PROJECT_REQUEST', actor: 'pedro@gca.dev', actorRole: 'gp', target: 'proj-004', detail: 'Solicitação de criação do projeto "Sistema de BI Interno" recebida.', timestamp: '2026-04-02T08:00:00Z', hash: 'sha256:hash009', prevHash: 'sha256:hash008', level: 'info' },
  { id: 'ev-010', projectId: 'proj-001', projectName: 'Portal de Clientes v2', action: 'OCG_UPDATED', actor: 'carla@gca.dev', actorRole: 'gp', target: 'proj-001', detail: 'OCG atualizado: modelo de IA alterado para gpt-4o. ComplianceProfile recalculado.', timestamp: '2026-04-01T11:00:00Z', hash: 'sha256:hash010', prevHash: 'sha256:hash009', level: 'info' },
];

export const PENDING_PROJECT_REQUESTS = [
  { id: 'req-001', name: 'Sistema de BI Interno', requestedBy: 'Pedro Nunes', email: 'pedro@gca.dev', outputProfile: 'web_app', requestedAt: '2026-04-02T08:00:00Z', description: 'Dashboard analítico para inteligência de negócios.', status: 'pending' as const },
  { id: 'req-002', name: 'App de Field Service', requestedBy: 'Ana Ferreira', email: 'ana@gca.dev', outputProfile: 'mobile', requestedAt: '2026-04-04T10:00:00Z', description: 'Aplicativo para equipes de campo com geolocalização e checklists.', status: 'pending' as const },
];

export function getUserById(id: string): User | undefined {
  return USERS.find(u => u.id === id);
}

export function getProjectById(id: string): Project | undefined {
  return PROJECTS.find(p => p.id === id);
}
