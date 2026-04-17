// Mapa Q_ID → rótulo humano curto das 49 perguntas do questionário técnico.
// Espelho de `BLOCKS` em backend/app/services/questionnaire_pdf_service.py.
// Usado para renderizar findings do TechnologyVerificationService de forma
// legível ("Q30 — Requisitos backend") em vez de só código.

export const QUESTION_LABELS: Record<string, string> = {
  '1': 'Nome do projeto',
  '2': 'Slug do projeto',
  '3': 'Altera projeto existente?',
  '4': 'Detalhamento da iniciativa',
  '5': 'Criticidade do projeto',
  '6': 'Classificação da informação',
  '7': 'Nome do sistema existente',
  '8': 'Repositório principal',
  '9': 'Repositórios adicionais',
  '10': 'Nível de acesso ao repositório',
  '11': 'Objetivo da alteração',
  '12': 'Autoriza análise automática?',
  '13': 'Escopo da análise automática',
  '14': 'Relatório técnico esperado',
  '15': 'Entregável principal',
  '16': 'Perfil arquitetural',
  '17': 'Modelo de execução',
  '18': 'Multi-tenant?',
  '19': 'Alta disponibilidade?',
  '20': 'Processamento assíncrono/jobs?',
  '21': 'Projeto terá frontend?',
  '22': 'Tipo de frontend',
  '23': 'Stack frontend',
  '24': 'Linguagem frontend',
  '25': 'Requisitos frontend',
  '26': 'Projeto terá backend?',
  '27': 'Linguagem backend',
  '28': 'Framework backend',
  '29': 'Tipo de backend',
  '30': 'Requisitos backend',
  '31': 'Banco de dados principal',
  '32': 'Perfil de uso do banco',
  '33': 'Redis?',
  '34': 'Finalidade do Redis',
  '35': 'Mensageria?',
  '36': 'Finalidade da mensageria',
  '37': 'Usa n8n?',
  '38': 'Finalidade do n8n',
  '39': 'Projeto utilizará IA?',
  '40': 'Finalidade da IA',
  '41': 'Provedor de IA',
  '42': 'Restrições de envio de dados à IA',
  '43': 'Controles de segurança obrigatórios',
  '44': 'Observabilidade exigida',
  '45': 'Tipos mínimos de teste exigidos',
  '46': 'Quality gate automatizado?',
  '47': 'Evidência formal de QA?',
  '48': 'Entregáveis esperados do pipeline',
  '49': 'Formato de retorno desejado',
}

export function questionLabel(id: string): string {
  const label = QUESTION_LABELS[id]
  return label ? `Q${id} — ${label}` : `Q${id}`
}
