/**
 * Definição compartilhada das 49 perguntas do Questionário Técnico GCA.
 * Usado por QuestionnairePage e NovoProjetoPage.
 */

export interface QuestionDef {
  id: string
  label: string
  help: string
  type: 'text' | 'single' | 'multi'
  options?: string[]
  placeholder?: string
  conditionalOn?: { question: string; value: string }
  allowNA?: boolean
  linkedTo?: { question: string; value: string; message?: string }
}

export interface BlockDef {
  id: string
  title: string
  description: string
  questions: QuestionDef[]
}

export const NA_VALUE = 'Não se aplica'

export const BLOCKS: BlockDef[] = [
  {
    id: 'A.1',
    title: 'A.1 — Informações Gerais do Projeto',
    description: 'Dados básicos que identificam e contextualizam o projeto.',
    questions: [
      {
        id: '1',
        label: 'Nome do projeto',
        help: 'Informe o nome oficial ou provisório do projeto. Será usado como referência em todos os documentos e telas do GCA.',
        type: 'text',
        placeholder: 'Ex: Portal do Cliente, Sistema de Estoque, E-Commerce',
      },
      {
        id: '2',
        label: 'Slug do projeto',
        help: 'Identificador curto, sem espaços ou caracteres especiais, usado internamente para URLs e schemas do banco. Exemplo: "portal-cliente", "sys-estoque".',
        type: 'text',
        placeholder: 'Ex: portal-cliente (letras minúsculas, hífens)',
      },
      {
        id: '3',
        label: 'O projeto é direcionado a fazer melhorias ou alterar um projeto já existente?',
        help: 'Se "Sim", o bloco A.2 será habilitado para que você informe detalhes do sistema atual. Se "Não", estamos criando algo novo do zero.',
        type: 'single',
        options: ['Sim', 'Não'],
      },
      {
        id: '4',
        label: 'Tipo de iniciativa',
        help: 'Selecione uma ou mais categorias que melhor descrevem o que o projeto pretende entregar. Isso ajuda os agentes de IA a calibrar a análise de escopo.',
        type: 'multi',
        options: ['Novo sistema', 'Melhoria em sistema existente', 'Nova funcionalidade em sistema existente', 'Refatoração técnica', 'Modernização/Migração', 'Integração', 'Automação interna', 'POC/MVP'],
      },
      {
        id: '5',
        label: 'Criticidade do projeto',
        help: 'Qual o impacto no negócio se este projeto falhar ou atrasar? "Baixa" = impacto menor, "Crítica" = pode parar operações ou causar prejuízo significativo.',
        type: 'single',
        options: ['Baixa', 'Média', 'Alta', 'Crítica'],
      },
      {
        id: '6',
        label: 'Classificação da informação',
        help: 'Define o nível de sigilo dos dados que o sistema irá manipular. Afeta diretamente os controles de segurança exigidos pelo Pilar P7.',
        type: 'single',
        options: ['Pública', 'Interna', 'Confidencial', 'Restrita'],
      },
    ],
  },
  {
    id: 'A.2',
    title: 'A.2 — Projetos Existentes',
    description: 'Detalhes do sistema atual. Habilitado apenas se Q3 = "Sim".',
    questions: [
      { id: '7', label: 'Nome do sistema existente', help: 'Nome oficial do sistema que será alterado ou evoluído.', type: 'text', conditionalOn: { question: '3', value: 'Sim' } },
      { id: '8', label: 'Repositório principal', help: 'URL do repositório Git principal do sistema existente.', type: 'text', placeholder: 'https://github.com/org/repo', conditionalOn: { question: '3', value: 'Sim' } },
      { id: '9', label: 'Repositórios adicionais', help: 'Se o sistema é composto por múltiplos repositórios, informe as URLs separadas por vírgula.', type: 'text', placeholder: 'URLs separadas por vírgula (opcional)', conditionalOn: { question: '3', value: 'Sim' }, allowNA: true },
      { id: '10', label: 'Nível de acesso fornecido ao repositório', help: '"Read-only" = apenas leitura. "Read + PR" = permite abrir Pull Requests.', type: 'single', options: ['Read-only', 'Read + metadata', 'Read + PR', 'Outro'], conditionalOn: { question: '3', value: 'Sim' } },
      { id: '11', label: 'Objetivo da alteração', help: 'O que você espera alcançar com a mudança no sistema existente?', type: 'multi', options: ['Correção de bugs', 'Evolução funcional', 'Refatoração', 'Integração com outros sistemas', 'Redução de débito técnico', 'Migração de arquitetura', 'Adequação de segurança/compliance', 'Performance'], conditionalOn: { question: '3', value: 'Sim' } },
      { id: '12', label: 'O tenant autoriza o n8n do GCA a analisar o repositório automaticamente?', help: 'Se "Sim", o n8n fará análise automática do repositório (arquitetura, dependências, riscos).', type: 'single', options: ['Sim', 'Não'], conditionalOn: { question: '3', value: 'Sim' } },
      { id: '13', label: 'Escopo da análise automática do n8n', help: 'Selecione quais aspectos do repositório devem ser analisados automaticamente.', type: 'multi', options: ['Arquitetura atual', 'Linguagens e frameworks', 'Dependências e versões', 'Itens deprecated', 'Pipelines CI/CD', 'Testes existentes', 'Riscos técnicos', 'Documentação ausente', 'Integrações detectadas'], conditionalOn: { question: '3', value: 'Sim' }, linkedTo: { question: '12', value: 'Não', message: 'Análise n8n não autorizada na Q12.' } },
      { id: '14', label: 'Relatório técnico esperado para o GP', help: 'Que tipo de relatório você gostaria de receber sobre o sistema existente?', type: 'multi', options: ['Resumo executivo', 'Arquitetura identificada', 'Stack detectada', 'Riscos técnicos', 'Sugestão de backlog', 'Sugestão de modernização', 'Lacunas de testes', 'Lacunas de documentação'], conditionalOn: { question: '3', value: 'Sim' } },
    ],
  },
  {
    id: 'A.3',
    title: 'A.3 — Perfil de Entrega e Arquitetura',
    description: 'Define o que será entregue, como será estruturado e onde vai rodar.',
    questions: [
      { id: '15', label: 'Entregável principal do projeto', help: 'O que o projeto vai gerar como produto final? Pode ser mais de um.', type: 'multi', options: ['Executável desktop', 'Aplicação web', 'API', 'Microserviço', 'Aplicativo mobile', 'Dashboard', 'Job/Worker', 'CLI', 'Biblioteca/SDK'] },
      { id: '16', label: 'Perfil arquitetural preferido', help: '"Monólito" = tudo junto. "Microserviços" = serviços independentes. Se não tem certeza, selecione as opções que parecem adequadas.', type: 'multi', options: ['Monólito', 'Monólito modular', 'Microserviços', 'Event-driven', 'Hexagonal', 'Clean Architecture', 'Serverless', 'Desktop local'], allowNA: true },
      { id: '17', label: 'Modelo de execução', help: 'Onde o sistema vai rodar? "Stand-alone" = máquina local. "Cloud" = nuvem. "Containerizado" = Docker/Kubernetes.', type: 'single', options: ['Stand-alone', 'On-premises', 'Cloud', 'Híbrido', 'Containerizado', 'Offline com sincronização posterior'] },
      { id: '18', label: 'O projeto precisa de multi-tenant?', help: 'Multi-tenant = múltiplos clientes/organizações usam o mesmo sistema com dados isolados (ex: SaaS).', type: 'single', options: ['Sim', 'Não', 'Talvez', NA_VALUE] },
      { id: '19', label: 'Necessidade de alta disponibilidade?', help: 'O sistema precisa estar no ar 24/7? Implica redundância e custos maiores de infraestrutura.', type: 'single', options: ['Sim', 'Não', 'Futuramente', NA_VALUE] },
      { id: '20', label: 'Necessidade de processamento assíncrono/jobs?', help: 'Tarefas em segundo plano: envio de e-mails em lote, relatórios pesados, importação de dados.', type: 'single', options: ['Sim', 'Não', NA_VALUE] },
    ],
  },
  {
    id: 'A.4',
    title: 'A.4 — Frontend (Interface do Usuário)',
    description: 'Tudo sobre a parte visual que o usuário final vai interagir.',
    questions: [
      { id: '21', label: 'O projeto terá frontend (interface visual)?', help: 'Se "Não", o projeto será apenas backend/API. As perguntas Q22 a Q25 dependem desta resposta.', type: 'single', options: ['Sim', 'Não'] },
      { id: '22', label: 'Tipo de frontend', help: 'SPA = página única (Gmail). SSR = renderização no servidor. PWA = funciona offline.', type: 'multi', options: ['Web SPA', 'SSR', 'PWA', 'Desktop UI', 'Mobile app', 'Painel administrativo', 'Portal autenticado'], linkedTo: { question: '21', value: 'Não', message: 'Projeto sem frontend (Q21).' } },
      { id: '23', label: 'Stack de frontend preferida', help: '"Sem preferência" permite que o GCA recomende a melhor opção.', type: 'multi', options: ['React', 'Vue', 'Angular', 'Next.js', 'Vite + React', 'Electron', 'Flutter', 'React Native', 'Sem preferência'], linkedTo: { question: '21', value: 'Não', message: 'Projeto sem frontend (Q21).' } },
      { id: '24', label: 'Linguagem preferida para o frontend', help: 'TypeScript é recomendado para projetos maiores (tipagem previne erros). JavaScript é mais simples.', type: 'single', options: ['TypeScript', 'JavaScript', 'Outra', NA_VALUE], linkedTo: { question: '21', value: 'Não', message: 'Projeto sem frontend (Q21).' } },
      { id: '25', label: 'Requisitos de frontend', help: '"Responsividade" = funciona em celular e desktop. "Acessibilidade" = atende pessoas com deficiência.', type: 'multi', options: ['Responsividade', 'Acessibilidade (WCAG)', 'Dark theme', 'Formulários complexos', 'Gráficos e dashboards', 'Upload de arquivos', 'Impressão/Exportação PDF', 'Internacionalização (i18n)'], allowNA: true, linkedTo: { question: '21', value: 'Não', message: 'Projeto sem frontend (Q21).' } },
    ],
  },
  {
    id: 'A.5',
    title: 'A.5 — Backend e APIs',
    description: 'O "motor" por trás do sistema: servidor, lógica de negócio e interfaces de dados.',
    questions: [
      { id: '26', label: 'O projeto terá backend (servidor)?', help: 'Se "Não", o projeto será apenas frontend (ex: site estático). Q27 a Q30 dependem desta resposta.', type: 'single', options: ['Sim', 'Não'] },
      { id: '27', label: 'Linguagem backend preferida', help: '"Python" = IA e dados. "Node.js" = tempo real. "Java/C#" = corporativo.', type: 'single', options: ['Python', 'Node.js', 'Java', 'C#', 'Go', 'PHP', 'Kotlin', 'Outra'], linkedTo: { question: '26', value: 'Não', message: 'Projeto sem backend (Q26).' } },
      { id: '28', label: 'Framework backend preferido', help: 'FastAPI/Django = Python. NestJS/Express = Node.js. "Sem preferência" = GCA recomenda.', type: 'multi', options: ['FastAPI', 'Django', 'Flask', 'NestJS', 'Express', 'Spring Boot', 'ASP.NET', 'Quarkus', 'Sem preferência'], linkedTo: { question: '26', value: 'Não', message: 'Projeto sem backend (Q26).' } },
      { id: '29', label: 'Tipo de backend', help: '"REST API" = mais comum. "GraphQL" = consultas flexíveis. "WebSocket" = tempo real.', type: 'multi', options: ['REST API', 'GraphQL', 'gRPC', 'WebSocket', 'Batch', 'Worker', 'BFF', 'Misto'], linkedTo: { question: '26', value: 'Não', message: 'Projeto sem backend (Q26).' } },
      { id: '30', label: 'Requisitos do backend', help: '"RBAC" = controle por papel. "Auditoria" = registro de todas as ações.', type: 'multi', options: ['Autenticação', 'RBAC (controle por papel)', 'Webhooks', 'Jobs em background', 'Auditoria', 'Versionamento de API', 'Rate limiting', 'Observabilidade', 'Integração com IA'], allowNA: true, linkedTo: { question: '26', value: 'Não', message: 'Projeto sem backend (Q26).' } },
    ],
  },
  {
    id: 'A.6',
    title: 'A.6 — Dados, Cache e Mensageria',
    description: 'Banco de dados, cache para performance e comunicação entre serviços.',
    questions: [
      { id: '31', label: 'Banco de dados principal', help: 'PostgreSQL é o mais versátil e recomendado para a maioria dos casos.', type: 'single', options: ['PostgreSQL', 'MySQL', 'SQL Server', 'Oracle', 'MongoDB', 'SQLite', 'Sem preferência'] },
      { id: '32', label: 'Perfil de uso do banco de dados', help: '"Transacional" = muitas escritas/leituras (e-commerce). "Analítico" = relatórios complexos. "Documental" = dados JSON.', type: 'multi', options: ['Transacional', 'Analítico', 'Documental', 'Catálogo', 'Event store', 'Misto'] },
      { id: '33', label: 'Necessidade de Redis (cache em memória)?', help: 'Redis acelera o sistema armazenando dados frequentes na memória RAM.', type: 'single', options: ['Sim', 'Não', 'Talvez', NA_VALUE] },
      { id: '34', label: 'Finalidade do Redis', help: 'Para que o Redis será usado? Pode selecionar múltiplas finalidades.', type: 'multi', options: ['Cache de leitura', 'Sessões', 'Rate limiting', 'Pub/Sub', 'Locks distribuídos', 'Filas leves'], linkedTo: { question: '33', value: 'Não', message: 'Redis não necessário (Q33).' } },
      { id: '35', label: 'Necessidade de mensageria (Kafka, RabbitMQ)?', help: 'Comunicação assíncrona entre partes do sistema. Importante para microserviços.', type: 'single', options: ['Sim', 'Não', 'Talvez', NA_VALUE] },
      { id: '36', label: 'Finalidade da mensageria', help: '"Eventos de domínio" = notificar quando algo acontece. "Background" = tarefas pesadas.', type: 'multi', options: ['Eventos de domínio', 'Integrações assíncronas', 'Processamento em background', 'Orquestração entre serviços', 'Telemetria'], linkedTo: { question: '35', value: 'Não', message: 'Mensageria não necessária (Q35).' } },
      { id: '37', label: 'O projeto usará n8n (automação)?', help: 'n8n é uma ferramenta visual de automação para integrações, relatórios e notificações.', type: 'single', options: ['Sim', 'Não', 'Talvez', NA_VALUE] },
      { id: '38', label: 'Finalidade do n8n', help: 'Para que o n8n será usado? Selecione as automações desejadas.', type: 'multi', options: ['Leitura/análise de repositório legado', 'Automação de integrações', 'Notificações', 'Geração de relatórios', 'ETL (extração e transformação)', 'Disparo de webhooks', 'Aprovações automáticas'], linkedTo: { question: '37', value: 'Não', message: 'n8n não utilizado (Q37).' } },
    ],
  },
  {
    id: 'A.7',
    title: 'A.7 — IA, Segurança e Observabilidade',
    description: 'Uso de inteligência artificial, controles de proteção e monitoramento.',
    questions: [
      { id: '39', label: 'O projeto utilizará Inteligência Artificial?', help: 'Se "Sim", os agentes do GCA considerarão requisitos de IA na arquitetura.', type: 'single', options: ['Sim', 'Não', 'Talvez', NA_VALUE] },
      { id: '40', label: 'Finalidade da IA no projeto', help: '"Geração de código" = IA escreve código. "Chat assistivo" = assistente inteligente.', type: 'multi', options: ['Análise de requisitos', 'Geração de código', 'Documentação técnica', 'Documentação negocial', 'Revisão de código', 'Testes automatizados', 'Classificação de artefatos', 'Chat assistivo'], linkedTo: { question: '39', value: 'Não', message: 'IA não utilizada (Q39).' } },
      { id: '41', label: 'Provedor de IA preferencial', help: '"Anthropic" = Claude. "OpenAI" = GPT. "Sem preferência" = GCA recomenda.', type: 'multi', options: ['Anthropic', 'OpenAI', 'Gemini', 'DeepSeek', 'Grok', 'Outro', 'Sem preferência'], linkedTo: { question: '39', value: 'Não', message: 'IA não utilizada (Q39).' } },
      { id: '42', label: 'Restrições para envio de dados à IA externa', help: '"Mascaramento" = ocultar partes sensíveis. "Bloqueio total" = não enviar nenhum dado.', type: 'multi', options: ['Mascaramento de dados sensíveis', 'Anonimização', 'Bloqueio total de dados sensíveis', 'Envio permitido por política interna', 'Avaliação por tipo de dado'], allowNA: true },
      { id: '43', label: 'Controles de segurança obrigatórios', help: '"JWT" = tokens de autenticação. "MFA" = dois fatores. Afeta o Pilar P7 (Segurança).', type: 'multi', options: ['JWT', 'OAuth2', 'SSO (login único)', 'MFA (autenticação multifator)', 'Criptografia em trânsito (HTTPS)', 'Criptografia em repouso', 'Vault de segredos', 'Rotação de credenciais', 'Trilhas de auditoria'] },
      { id: '44', label: 'Observabilidade exigida', help: '"Logs" = registros de eventos. "Métricas" = CPU, memória, latência. "Alertas" = avisos automáticos.', type: 'multi', options: ['Logs estruturados', 'Métricas', 'Tracing (rastreamento)', 'Health checks', 'Alertas automáticos', 'Dashboard operacional', 'Dashboard executivo'], allowNA: true },
    ],
  },
  {
    id: 'A.8',
    title: 'A.8 — Testes, Validação e Entregáveis',
    description: 'Qualidade, tipos de teste e o que você espera receber do pipeline GCA.',
    questions: [
      { id: '45', label: 'Tipos mínimos de teste exigidos', help: '"Unitários" = funções isoladas. "E2E" = simula o usuário. "Segurança" = vulnerabilidades.', type: 'multi', options: ['Smoke (verificação rápida)', 'Sanity (funcionalidades críticas)', 'Unitários', 'Integração', 'Contrato/API', 'E2E (ponta a ponta)', 'UAT (aceite do usuário)', 'Regressão', 'Segurança', 'SAST/SCA (análise estática)', 'DAST (análise dinâmica)', 'Performance/Carga', 'Stress/Soak', 'Resiliência/Recuperação', 'Backup/Restore', 'Acessibilidade', 'Compatibilidade'] },
      { id: '46', label: 'O projeto terá quality gate automatizado?', help: 'Quality gate bloqueia a entrega se testes falharem ou cobertura estiver abaixo do mínimo.', type: 'single', options: ['Sim', 'Não', NA_VALUE] },
      { id: '47', label: 'O projeto exige evidência formal de QA?', help: 'Documentos comprovando testes executados. Exigido em ambientes regulados (saúde, financeiro).', type: 'single', options: ['Sim', 'Não', NA_VALUE] },
      { id: '48', label: 'Entregáveis esperados do pipeline GCA', help: 'O que o GCA deve gerar? Documentos técnicos, sugestões de arquitetura, planos de teste, etc.', type: 'multi', options: ['Sugestão de arquitetura', 'Sugestão de stack tecnológico', 'Documento técnico consolidado', 'Documento negocial consolidado', 'Gap analysis (análise de lacunas)', 'Backlog inicial sugerido', 'Plano de testes', 'Plano de segurança', 'Plano de observabilidade', 'Plano de deploy'] },
      { id: '49', label: 'Formato de retorno desejado', help: '"Painel no GCA" = visualização direta na plataforma. Pode selecionar múltiplos.', type: 'multi', options: ['Painel no GCA', 'HTML', 'Markdown', 'DOCX', 'PDF', 'JSON estruturado', 'YAML'] },
    ],
  },
]
