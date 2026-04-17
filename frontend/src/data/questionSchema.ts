// Schema completo das 49 perguntas do questionário técnico do GCA.
// Espelho de `BLOCKS` em backend/app/services/questionnaire_pdf_service.py.
// Usado pelo editor inline de correção — quando o GP precisa ajustar uma
// resposta apontada como bloqueador, o componente renderiza o input
// apropriado a partir deste schema sem exigir novo upload de PDF.
//
// Tipos:
//  - text  : input de texto livre
//  - single: dropdown (uma opção)
//  - multi : checkboxes (várias opções)

export type QuestionType = 'text' | 'single' | 'multi'

export interface QuestionDef {
  id: string
  type: QuestionType
  label: string
  options?: string[]
}

export const QUESTION_SCHEMA: Record<string, QuestionDef> = {
  '1': { id: '1', type: 'text', label: 'Nome do projeto' },
  '2': { id: '2', type: 'text', label: 'Slug do projeto (ex: portal-cliente)' },
  '3': { id: '3', type: 'single', label: 'O projeto altera um projeto já existente?', options: ['Sim', 'Não'] },
  '4': { id: '4', type: 'multi', label: 'Detalhamento da iniciativa', options: ['Novo sistema', 'Melhoria em sistema existente', 'Nova funcionalidade', 'Refatoração técnica', 'Modernização/Migração', 'Integração', 'Automação interna', 'POC/MVP'] },
  '5': { id: '5', type: 'single', label: 'Criticidade do projeto', options: ['Baixa', 'Média', 'Alta', 'Crítica'] },
  '6': { id: '6', type: 'single', label: 'Classificação da informação', options: ['Pública', 'Interna', 'Confidencial', 'Restrita'] },
  '7': { id: '7', type: 'text', label: 'Nome do sistema existente' },
  '8': { id: '8', type: 'text', label: 'Repositório principal (URL)' },
  '9': { id: '9', type: 'text', label: 'Repositórios adicionais (URLs, vírgula)' },
  '10': { id: '10', type: 'single', label: 'Nível de acesso ao repositório', options: ['Read-only', 'Read + metadata', 'Read + PR', 'Outro'] },
  '11': { id: '11', type: 'multi', label: 'Objetivo da alteração', options: ['Correção', 'Evolução funcional', 'Refatoração', 'Integração', 'Débito técnico', 'Migração', 'Segurança/compliance', 'Performance'] },
  '12': { id: '12', type: 'single', label: 'Autoriza análise automática do repositório?', options: ['Sim', 'Não'] },
  '13': { id: '13', type: 'multi', label: 'Escopo da análise automática', options: ['Arquitetura', 'Linguagens/frameworks', 'Dependências', 'Deprecated', 'CI/CD', 'Testes', 'Riscos', 'Doc ausente', 'Integrações'] },
  '14': { id: '14', type: 'multi', label: 'Relatório técnico esperado', options: ['Resumo executivo', 'Arquitetura', 'Stack', 'Riscos', 'Backlog', 'Modernização', 'Lacunas testes', 'Lacunas docs'] },
  '15': { id: '15', type: 'multi', label: 'Entregável principal', options: ['Executável desktop', 'Aplicação web', 'API', 'Microserviço', 'App mobile', 'Dashboard', 'Job/Worker', 'CLI', 'Biblioteca/SDK'] },
  '16': { id: '16', type: 'multi', label: 'Perfil arquitetural', options: ['Monólito', 'Monólito modular', 'Microserviços', 'Event-driven', 'Hexagonal', 'Clean Architecture', 'Serverless', 'Desktop local'] },
  '17': { id: '17', type: 'multi', label: 'Modelo de execução', options: ['Stand-alone', 'On-premises', 'Cloud', 'Híbrido', 'Containerizado', 'Offline + sync'] },
  '18': { id: '18', type: 'single', label: 'Multi-tenant?', options: ['Sim', 'Não', 'Talvez', 'N/A'] },
  '19': { id: '19', type: 'single', label: 'Alta disponibilidade?', options: ['Sim', 'Não', 'Futuramente', 'N/A'] },
  '20': { id: '20', type: 'single', label: 'Processamento assíncrono/jobs?', options: ['Sim', 'Não', 'N/A'] },
  '21': { id: '21', type: 'single', label: 'O projeto terá frontend?', options: ['Sim', 'Não'] },
  '22': { id: '22', type: 'multi', label: 'Tipo de frontend', options: ['Web SPA', 'SSR', 'PWA', 'Desktop UI', 'Mobile app', 'Painel admin', 'Portal autenticado'] },
  '23': { id: '23', type: 'multi', label: 'Stack frontend', options: ['React', 'Vue', 'Angular', 'Next.js', 'Vite+React', 'Electron', 'Flutter', 'React Native', 'Sem preferência'] },
  '24': { id: '24', type: 'single', label: 'Linguagem frontend', options: ['TypeScript', 'JavaScript', 'Outra', 'N/A'] },
  '25': { id: '25', type: 'multi', label: 'Requisitos frontend', options: ['Responsividade', 'Acessibilidade', 'Dark theme', 'Formulários complexos', 'Gráficos', 'Upload arquivos', 'Impressão/PDF', 'i18n'] },
  '26': { id: '26', type: 'single', label: 'O projeto terá backend?', options: ['Sim', 'Não'] },
  '27': { id: '27', type: 'single', label: 'Linguagem backend', options: ['Python', 'Node.js', 'Java', 'C#', 'Go', 'PHP', 'Kotlin', 'Outra'] },
  '28': { id: '28', type: 'multi', label: 'Framework backend', options: ['FastAPI', 'Django', 'Flask', 'NestJS', 'Express', 'Spring Boot', 'ASP.NET', 'Quarkus', 'Sem preferência'] },
  '29': { id: '29', type: 'multi', label: 'Tipo de backend', options: ['REST API', 'GraphQL', 'gRPC', 'WebSocket', 'Batch', 'Worker', 'BFF', 'Misto'] },
  '30': { id: '30', type: 'multi', label: 'Requisitos backend', options: ['Autenticação', 'RBAC', 'Webhooks', 'Jobs', 'Auditoria', 'Versionamento API', 'Rate limiting', 'Observabilidade', 'Integração IA'] },
  '31': { id: '31', type: 'single', label: 'Banco de dados principal', options: ['PostgreSQL', 'MySQL', 'SQL Server', 'Oracle', 'MongoDB', 'SQLite', 'Sem preferência', 'N/A'] },
  '32': { id: '32', type: 'multi', label: 'Perfil de uso do banco', options: ['Transacional', 'Analítico', 'Documental', 'Catálogo', 'Event store', 'Misto'] },
  '33': { id: '33', type: 'single', label: 'Redis (cache em memória)?', options: ['Sim', 'Não', 'Talvez', 'N/A'] },
  '34': { id: '34', type: 'multi', label: 'Finalidade do Redis', options: ['Cache leitura', 'Sessões', 'Rate limiting', 'Pub/Sub', 'Locks', 'Filas leves'] },
  '35': { id: '35', type: 'single', label: 'Mensageria (Kafka, RabbitMQ)?', options: ['Sim', 'Não', 'Talvez', 'N/A'] },
  '36': { id: '36', type: 'multi', label: 'Finalidade da mensageria', options: ['Eventos de domínio', 'Integrações async', 'Background', 'Orquestração', 'Telemetria'] },
  '37': { id: '37', type: 'single', label: 'Usa n8n (automação)?', options: ['Sim', 'Não', 'Talvez', 'N/A'] },
  '38': { id: '38', type: 'multi', label: 'Finalidade do n8n', options: ['Análise de repo', 'Automação', 'Notificações', 'Relatórios', 'ETL', 'Webhooks', 'Aprovações'] },
  '39': { id: '39', type: 'single', label: 'O projeto utilizará IA?', options: ['Sim', 'Não', 'Talvez', 'N/A'] },
  '40': { id: '40', type: 'multi', label: 'Finalidade da IA', options: ['Análise requisitos', 'Geração código', 'Doc técnica', 'Doc negocial', 'Revisão código', 'Testes', 'Classificação', 'Chat'] },
  '41': { id: '41', type: 'multi', label: 'Provedor de IA', options: ['Anthropic', 'OpenAI', 'Gemini', 'DeepSeek', 'Grok', 'Outro', 'Sem preferência'] },
  '42': { id: '42', type: 'multi', label: 'Restrições de envio de dados à IA', options: ['Mascaramento', 'Anonimização', 'Bloqueio total', 'Envio permitido', 'Avaliação por tipo'] },
  '43': { id: '43', type: 'multi', label: 'Controles de segurança obrigatórios', options: ['JWT', 'OAuth2', 'SSO', 'MFA', 'HTTPS', 'Cripto repouso', 'Vault', 'Rotação credenciais', 'Auditoria'] },
  '44': { id: '44', type: 'multi', label: 'Observabilidade exigida', options: ['Logs estruturados', 'Métricas', 'Tracing', 'Health checks', 'Alertas', 'Dashboard ops', 'Dashboard exec'] },
  '45': { id: '45', type: 'multi', label: 'Tipos mínimos de teste exigidos', options: ['Smoke', 'Sanity', 'Unitários', 'Integração', 'Contrato/API', 'E2E', 'UAT', 'Regressão', 'Segurança', 'SAST/SCA', 'DAST', 'Performance', 'Stress', 'Resiliência', 'Backup', 'Acessibilidade', 'Compatibilidade'] },
  '46': { id: '46', type: 'single', label: 'Quality gate automatizado?', options: ['Sim', 'Não', 'N/A'] },
  '47': { id: '47', type: 'single', label: 'Evidência formal de QA?', options: ['Sim', 'Não', 'N/A'] },
  '48': { id: '48', type: 'multi', label: 'Entregáveis esperados do pipeline', options: ['Arquitetura', 'Stack', 'Doc técnico', 'Doc negocial', 'Gap analysis', 'Backlog', 'Plano testes', 'Plano segurança', 'Plano observabilidade', 'Plano deploy'] },
  '49': { id: '49', type: 'multi', label: 'Formato de retorno desejado', options: ['Painel GCA', 'HTML', 'Markdown', 'DOCX', 'PDF', 'JSON', 'YAML'] },
}
