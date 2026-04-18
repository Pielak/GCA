// Metadados dos 7 pilares do OCG.
// Alinhado com `gca-ocg-engine` skill (contrato soberano) e a
// classificação usada pelos agents do pipeline de OCG.
//
// Chaves no OCG variam (P1, P1_Business, p1_business, etc). A função
// `pillarKey(raw)` normaliza para o id curto "P1".."P7" antes de
// consultar o mapa.

export interface PillarMeta {
  id: string       // "P1".."P7"
  name: string     // Nome curto para o header
  description: string  // Explicação para tooltip / card
  weight: number   // Peso no composite score (%), conforme contrato
  blocking: boolean  // Bloqueia aprovação se score < 70
}

export const PILLAR_META: Record<string, PillarMeta> = {
  P1: {
    id: 'P1',
    name: 'Caso de Negócio',
    description: 'Viabilidade, valor esperado e ROI. Por que este projeto existe, quem ganha com ele, qual problema resolve.',
    weight: 10,
    blocking: false,
  },
  P2: {
    id: 'P2',
    name: 'Regras e Compliance',
    description: 'LGPD, GDPR, auditoria, retenção de dados, consentimento. Requisitos regulatórios e políticas internas aplicáveis.',
    weight: 15,
    blocking: true,  // < 70 bloqueia
  },
  P3: {
    id: 'P3',
    name: 'Funcionalidades e Escopo',
    description: 'O que o sistema faz. Features, casos de uso, fronteiras do escopo e entregas esperadas.',
    weight: 20,
    blocking: false,
  },
  P4: {
    id: 'P4',
    name: 'Requisitos Não-Funcionais',
    description: 'Performance, disponibilidade, escalabilidade, observabilidade, usabilidade. Como o sistema se comporta.',
    weight: 20,
    blocking: false,
  },
  P5: {
    id: 'P5',
    name: 'Arquitetura e Design',
    description: 'Stack técnica, perfil arquitetural, padrões (monólito/microserviços/etc), integrações e decisões de alto nível.',
    weight: 15,
    blocking: false,
  },
  P6: {
    id: 'P6',
    name: 'Dados e Persistência',
    description: 'Banco principal, modelo de dados, cache, mensageria, estratégia de backup e classificação da informação.',
    weight: 10,
    blocking: false,
  },
  P7: {
    id: 'P7',
    name: 'Segurança e Proteção',
    description: 'Autenticação, autorização, criptografia em trânsito/repouso, secrets, trilhas de auditoria e mitigação de ameaças.',
    weight: 10,
    blocking: true,  // < 70 bloqueia
  },
}

export const PILLAR_ORDER = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7'] as const

/**
 * Normaliza qualquer variação de chave de pilar para o id curto.
 * Ex: "P1", "P1_Business", "p1", "pillar_1" → "P1"
 * Retorna null se não conseguir identificar.
 */
export function pillarKey(raw: string): string | null {
  if (!raw) return null
  const m = raw.match(/p[_\- ]?([1-7])/i)
  if (!m) return null
  return `P${m[1]}`
}

export function pillarMeta(raw: string): PillarMeta | null {
  const key = pillarKey(raw)
  return key ? PILLAR_META[key] : null
}
