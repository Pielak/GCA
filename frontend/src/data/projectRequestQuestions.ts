/**
 * Biblioteca de perguntas obrigatórias por tipo de entregável.
 *
 * Usada no passo 2 do wizard /solicitar-projeto. As respostas viram o seed
 * inicial do OCG após o admin aprovar — é a base de contexto que o Arguidor
 * usa para gerar o primeiro CodeGen sem precisar perguntar tudo de novo.
 *
 * Cada tipo tem 3-5 perguntas curtas (sem questionário longo aqui — o
 * questionário completo de 49Q vem depois, dentro do projeto). Aqui é só
 * o necessário para o admin julgar a solicitação e o Arguidor ter contexto.
 *
 * Tipos suportados:
 *   - new_system | mobile_app | module | enhancement
 *   - integration | modernization | etl | maintenance
 *   - other (sem perguntas type-specific — usa só genéricas)
 */

export type QuestionKind = "text" | "textarea" | "select"

export interface Question {
  id: string
  label: string
  help?: string
  kind: QuestionKind
  required: boolean
  options?: string[] // para select
  placeholder?: string
  minLength?: number
}

// Perguntas comuns a todos os tipos (sempre apresentadas).
export const COMMON_QUESTIONS: Question[] = [
  {
    id: "stakeholders",
    label: "Quem são os stakeholders / patrocinadores principais?",
    kind: "textarea",
    required: true,
    placeholder: "Ex: Diretor de TI (Maria), Gerência Comercial (João)",
    minLength: 10,
  },
  {
    id: "success_criteria",
    label: "Como vocês saberão que o projeto foi um sucesso?",
    help: "Liste 1–3 critérios objetivos.",
    kind: "textarea",
    required: true,
    placeholder: "Ex: Reduzir tempo de cadastro em 50%; suportar 1k usuários simultâneos.",
    minLength: 20,
  },
]

// Perguntas específicas por tipo.
export const TYPE_QUESTIONS: Record<string, Question[]> = {
  new_system: [
    {
      id: "target_audience",
      label: "Quem usará o sistema? (público-alvo)",
      kind: "text",
      required: true,
      placeholder: "Ex: Vendedores externos da empresa",
    },
    {
      id: "expected_users",
      label: "Volume esperado de usuários simultâneos",
      kind: "select",
      required: true,
      options: ["até 50", "50–500", "500–5.000", "5.000+"],
    },
    {
      id: "auth_required",
      label: "Necessita autenticação / login?",
      kind: "select",
      required: true,
      options: ["Não", "Sim — usuário e senha", "Sim — SSO corporativo (SAML/OIDC)"],
    },
    {
      id: "hosting",
      label: "Onde será hospedado?",
      kind: "select",
      required: true,
      options: ["Cloud pública (AWS/Azure/GCP)", "On-premise (servidor próprio)", "Ainda não decidido"],
    },
  ],

  mobile_app: [
    {
      id: "platform",
      label: "Plataforma alvo",
      kind: "select",
      required: true,
      options: ["Android apenas", "iOS apenas", "Ambos (cross-platform)"],
    },
    {
      id: "offline_support",
      label: "Precisa funcionar offline?",
      kind: "select",
      required: true,
      options: ["Não", "Parcialmente (alguns recursos)", "Sim, totalmente"],
    },
    {
      id: "device_features",
      label: "Quais recursos do dispositivo são usados?",
      help: "Câmera, GPS, push notifications, biometria, NFC, etc.",
      kind: "textarea",
      required: true,
      placeholder: "Ex: GPS para rota e câmera para QR code.",
      minLength: 10,
    },
    {
      id: "backend_status",
      label: "Backend / API",
      kind: "select",
      required: true,
      options: ["Já existe — vamos integrar", "Será construído junto", "Ainda não decidido"],
    },
  ],

  module: [
    {
      id: "host_system",
      label: "Sistema hospedeiro / ecossistema",
      help: "Onde o módulo vai rodar? (ex: SAP, Salesforce, Chrome, WordPress)",
      kind: "text",
      required: true,
      placeholder: "Ex: Extensão para Google Chrome",
    },
    {
      id: "distribution",
      label: "Como será distribuído / instalado?",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Publicar na Chrome Web Store; instalar via marketplace.",
      minLength: 10,
    },
    {
      id: "host_apis",
      label: "Que APIs ou pontos de extensão do hospedeiro serão usados?",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Chrome Storage API, content_scripts em páginas X.",
      minLength: 10,
    },
  ],

  enhancement: [
    {
      id: "current_system",
      label: "Sistema atual a ser melhorado",
      help: "Nome, propósito e escala (quantos usuários, há quanto tempo no ar).",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Portal de RH interno, ~300 usuários, 4 anos no ar.",
      minLength: 20,
    },
    {
      id: "current_stack",
      label: "Stack tecnológica atual",
      help: "Linguagens, frameworks, banco de dados.",
      kind: "text",
      required: true,
      placeholder: "Ex: PHP 7.4 + MySQL + jQuery",
    },
    {
      id: "improvements",
      label: "O que precisa ser melhorado ou adicionado?",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Adicionar tela de relatórios; performance da tela X; nova integração.",
      minLength: 30,
    },
  ],

  integration: [
    {
      id: "source_systems",
      label: "Sistema(s) de origem",
      kind: "textarea",
      required: true,
      placeholder: "Ex: ERP TOTVS Protheus (versão 12)",
      minLength: 10,
    },
    {
      id: "target_systems",
      label: "Sistema(s) de destino",
      kind: "textarea",
      required: true,
      placeholder: "Ex: CRM Salesforce + Data Warehouse interno",
      minLength: 10,
    },
    {
      id: "sync_mode",
      label: "Modo de sincronização",
      kind: "select",
      required: true,
      options: ["Tempo-real (event-driven)", "Quase-real (polling alguns minutos)", "Batch diário", "Batch sob demanda"],
    },
    {
      id: "data_volume",
      label: "Volume estimado por execução",
      kind: "select",
      required: true,
      options: ["Baixo (<1k registros)", "Médio (1k–100k)", "Alto (100k–10M)", "Muito alto (>10M)"],
    },
  ],

  modernization: [
    {
      id: "legacy_stack",
      label: "Stack legada (a ser substituída)",
      kind: "text",
      required: true,
      placeholder: "Ex: COBOL + DB2 em mainframe",
    },
    {
      id: "target_stack",
      label: "Stack alvo desejada (se já decidida)",
      help: "Se ainda não decidiu, escreva 'a definir'.",
      kind: "text",
      required: true,
      placeholder: "Ex: Java 21 + PostgreSQL em containers",
    },
    {
      id: "migration_strategy",
      label: "Estratégia de migração preferida",
      kind: "select",
      required: true,
      options: ["Big-bang (substituição completa)", "Strangler fig (incremental por módulo)", "Lift-and-shift (só infra)", "A definir"],
    },
    {
      id: "downtime_tolerance",
      label: "Tolerância a downtime",
      kind: "select",
      required: true,
      options: ["Zero (24/7)", "Pequena janela noturna", "Fim de semana", "Sem restrição"],
    },
  ],

  etl: [
    {
      id: "sources",
      label: "Fontes de dados",
      kind: "textarea",
      required: true,
      placeholder: "Ex: API X, banco Oracle Y, planilhas em S3.",
      minLength: 10,
    },
    {
      id: "destinations",
      label: "Destinos de dados",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Data warehouse Snowflake; relatórios em Power BI.",
      minLength: 10,
    },
    {
      id: "frequency",
      label: "Periodicidade",
      kind: "select",
      required: true,
      options: ["Tempo-real (streaming)", "Horário", "Diário", "Semanal", "Sob demanda"],
    },
    {
      id: "data_quality",
      label: "Há regras de qualidade / validação obrigatórias?",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Sem nulos em campo X; deduplicação por CPF; conversão de moeda BRL→USD.",
      minLength: 10,
    },
  ],

  maintenance: [
    {
      id: "system_to_maintain",
      label: "Sistema a ser mantido",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Portal interno de pedidos, Java 8, em produção desde 2018.",
      minLength: 20,
    },
    {
      id: "demand_types",
      label: "Tipos de demanda esperados",
      kind: "textarea",
      required: true,
      placeholder: "Ex: Bugs (40%), pequenas melhorias (40%), regulatório (20%).",
      minLength: 10,
    },
    {
      id: "sla",
      label: "SLA / criticidade do sistema",
      kind: "select",
      required: true,
      options: ["Baixa (resolução em dias)", "Média (resolução em horas úteis)", "Alta (24/7, resposta < 1h)"],
    },
  ],

  // "other" não tem perguntas type-specific — só as comuns.
  other: [],
}

export function getQuestionsForType(deliverableType: string): Question[] {
  const typeQs = TYPE_QUESTIONS[deliverableType] || []
  return [...typeQs, ...COMMON_QUESTIONS]
}
