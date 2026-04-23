import { apiClient } from './api'

// MVP 24 Fase 24.5 — helpers compartilhados entre Gatekeeper e Arguider.

export type QuestionnaireSection =
  | 'governance'
  | 'architecture'
  | 'capacity'
  | 'security'
  | 'legal'

export const CANONICAL_SECTIONS: QuestionnaireSection[] = [
  'governance', 'architecture', 'capacity', 'security', 'legal',
]

export const SECTION_LABELS: Record<QuestionnaireSection, string> = {
  governance:   'Governança (GP / Tech Lead)',
  architecture: 'Arquitetura e Design',
  capacity:     'Capacity / Performance',
  security:     'Segurança',
  legal:        'Compliance Legal',
}

export const SECTION_DESCRIPTIONS: Record<QuestionnaireSection, string> = {
  governance:   'Decisões, stakeholders, priorização — dependem do GP/TL.',
  architecture: 'Padrões arquiteturais, camadas, dependências, modelo de dados.',
  capacity:     'Latência, throughput, escala, disponibilidade, recuperação.',
  security:     'Autenticação, CWE, vault, dados sensíveis.',
  legal:        'LGPD, GDPR, compliance setorial, jurisdição.',
}

//: Mapeamento canônico pilar → seção. Usado pelo Gatekeeper para abrir
//: o questionário certo a partir do pilar com score baixo.
const PILLAR_TO_SECTION: Record<string, QuestionnaireSection> = {
  P1: 'governance',   // Caso de Negócio
  P2: 'legal',        // Regras e Compliance
  P3: 'governance',   // Funcionalidades e Escopo
  P4: 'capacity',     // Requisitos Não-Funcionais
  P5: 'architecture', // Arquitetura e Design
  P6: 'architecture', // Dados e Persistência
  P7: 'security',     // Segurança e Proteção
}

export function pillarToSection(pillarLabel: string): QuestionnaireSection {
  // Extrai P1..P7 do início da string — aceita "P1", "P1 - Caso", "P1. Caso", "p1"
  const m = /^[Pp]([1-7])/.exec((pillarLabel || '').trim())
  if (m) {
    const key = `P${m[1]}`
    return PILLAR_TO_SECTION[key] || 'governance'
  }
  return 'governance'
}

//: Dispara download do PDF editável. Browser decide salvar.
export async function downloadQuestionnairePdf(
  projectId: string, section: QuestionnaireSection,
): Promise<void> {
  const res = await apiClient.get<Blob>(
    `/projects/${projectId}/arguider/questionnaire.pdf`,
    { params: { section }, responseType: 'blob' },
  )
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `questionario_${section}_${projectId}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
