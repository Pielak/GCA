import { useState } from 'react'
import { Save, Send, Loader2, AlertCircle, CheckCircle2, ChevronDown, ChevronUp, Download } from 'lucide-react'
import { useTechnicalQuestionnaire } from '@/hooks/useTechnicalQuestionnaire'

interface TechnicalQuestionnaireFormProps {
  projectId?: string
  onSubmitted?: () => void | Promise<void>
}

// Schema das perguntas técnicas (importado do backend, mas aqui simplificado para o frontend)
const TECHNICAL_QUESTIONS = [
  {
    numero: 'Q1',
    pergunta: 'Qual é o escopo principal do projeto técnico?',
    tipo: 'dropdown',
    secao: 'A.1',
    obrigatoria: true,
    opcoes: [
      'Novo sistema',
      'Refactor de existente',
      'Feature/módulo novo',
      'Manutenção/bugfix',
      'Outro',
    ],
    visibleIf: [],
    revela: ['Q2', 'Q3'],
  },
  {
    numero: 'Q2',
    pergunta: 'Qual é o prazo esperado para entrega?',
    tipo: 'dropdown',
    secao: 'A.1',
    obrigatoria: true,
    opcoes: [
      'Curto (2-4 semanas)',
      'Médio (1-3 meses)',
      'Longo (3-6 meses)',
      'Indefinido',
    ],
    visibleIf: [{ dependsOn: 'Q1', valor: 'Novo sistema' }],
    revela: [],
  },
  {
    numero: 'Q3',
    pergunta: 'O projeto exigirá escalabilidade horizontal?',
    tipo: 'dropdown',
    secao: 'A.1',
    obrigatoria: true,
    opcoes: ['Não', 'Sim, modesto', 'Sim, agressivo'],
    visibleIf: [],
    revela: ['Q7', 'Q8', 'Q9', 'Q10'],
  },
  {
    numero: 'Q4',
    pergunta: 'Qual é o modelo de armazenamento de dados preferido?',
    tipo: 'dropdown',
    secao: 'A.2',
    obrigatoria: false,
    opcoes: [
      'SQL relacional',
      'NoSQL (MongoDB, DynamoDB)',
      'Graph DB',
      'Data warehouse',
      'Não decidido',
    ],
    visibleIf: [],
    revela: [],
  },
  {
    numero: 'Q5',
    pergunta: 'Qual é o stack tecnológico preferido? (Backend)',
    tipo: 'text',
    secao: 'B.1',
    obrigatoria: false,
    opcoes: [],
    visibleIf: [],
    revela: [],
  },
  {
    numero: 'Q6',
    pergunta: 'Qual é o stack tecnológico preferido? (Frontend)',
    tipo: 'text',
    secao: 'B.1',
    obrigatoria: false,
    opcoes: [],
    visibleIf: [],
    revela: [],
  },
  {
    numero: 'Q7',
    pergunta: 'Qual é o volume esperado de requisições por segundo?',
    tipo: 'text',
    secao: 'B.2',
    obrigatoria: true,
    opcoes: [],
    visibleIf: [{ dependsOn: 'Q3', valor: 'Sim, modesto' }],
    revela: ['Q11'],
  },
  {
    numero: 'Q8',
    pergunta: 'Quais tecnologias de cache são necessárias?',
    tipo: 'multiselect',
    secao: 'B.2',
    obrigatoria: false,
    opcoes: ['Redis', 'Memcached', 'CDN', 'Nenhuma'],
    visibleIf: [{ dependsOn: 'Q3', valor: 'Sim, modesto' }],
    revela: [],
  },
  {
    numero: 'Q9',
    pergunta: 'O projeto precisa de message queue (fila de mensagens)?',
    tipo: 'dropdown',
    secao: 'B.2',
    obrigatoria: false,
    opcoes: ['Não', 'Sim, SQS/SNS', 'Sim, RabbitMQ', 'Sim, Kafka'],
    visibleIf: [{ dependsOn: 'Q3', valor: 'Sim, agressivo' }],
    revela: ['Q12'],
  },
  {
    numero: 'Q10',
    pergunta: 'Qual é o SLA esperado de uptime?',
    tipo: 'dropdown',
    secao: 'B.3',
    obrigatoria: false,
    opcoes: ['99.0%', '99.5%', '99.9%', '99.99%', 'Não crítico'],
    visibleIf: [{ dependsOn: 'Q3', valor: 'Sim, agressivo' }],
    revela: [],
  },
  {
    numero: 'Q11',
    pergunta: 'Quais sistemas externos precisam ser integrados?',
    tipo: 'multiselect',
    secao: 'C.1',
    obrigatoria: false,
    opcoes: [
      'CRM (Salesforce, HubSpot)',
      'ERP (SAP, Oracle)',
      'Payment Gateway',
      'Email/SMS',
      'Analytics',
      'Nenhum',
    ],
    visibleIf: [{ dependsOn: 'Q7', valor: '' }],
    revela: [],
  },
  {
    numero: 'Q12',
    pergunta: 'Qual é o protocolo de integração preferido?',
    tipo: 'dropdown',
    secao: 'C.1',
    obrigatoria: false,
    opcoes: ['REST API', 'GraphQL', 'gRPC', 'Webhooks', 'Não decidido'],
    visibleIf: [{ dependsOn: 'Q9', valor: 'Sim, Kafka' }],
    revela: [],
  },
  {
    numero: 'Q13',
    pergunta: 'Há requisitos de segurança específicos? (ex: OAuth, mTLS, HIPAA)',
    tipo: 'textarea',
    secao: 'C.2',
    obrigatoria: false,
    opcoes: [],
    visibleIf: [],
    revela: [],
  },
  {
    numero: 'Q14',
    pergunta: 'Qual é o tempo máximo aceitável de latência?',
    tipo: 'text',
    secao: 'D.1',
    obrigatoria: false,
    opcoes: [],
    visibleIf: [{ dependsOn: 'Q3', valor: 'Sim, agressivo' }],
    revela: [],
  },
  {
    numero: 'Q15',
    pergunta: 'Há restrições de compliance (LGPD, GDPR, etc)?',
    tipo: 'multiselect',
    secao: 'D.2',
    obrigatoria: false,
    opcoes: ['LGPD', 'GDPR', 'HIPAA', 'SOC 2', 'Nenhuma'],
    visibleIf: [],
    revela: [],
  },
]

export function TechnicalQuestionnaireForm({ projectId, onSubmitted }: TechnicalQuestionnaireFormProps) {
  const {
    responses,
    updateField,
    visibleQuestions,
    progress,
    validate,
    submit: hookSubmit,
    saveNow,
    isLoading,
    isSaving,
    isValidating,
    hasUnsavedChanges,
    status,
    error,
    validationError,
  } = useTechnicalQuestionnaire(projectId)

  // Wrapper around submit to call onSubmitted callback
  const submit = async () => {
    try {
      await hookSubmit()
      // Chamar callback após sucesso
      if (onSubmitted) {
        await onSubmitted()
      }
    } catch (err) {
      // Erro já é tratado pelo hook
      throw err
    }
  }

  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['A', 'B', 'C', 'D'])
  )
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})

  // Agrupar perguntas por seção
  const sections = Array.from(
    new Map(
      TECHNICAL_QUESTIONS.filter((q) => visibleQuestions.includes(q.numero)).map((q) => [
        q.secao.split('.')[0],
        q.secao,
      ])
    ).values()
  ).map((secao) => ({
    id: secao.split('.')[0],
    title: `Seção ${secao}: ${getSecaoTitle(secao)}`,
    questions: TECHNICAL_QUESTIONS.filter(
      (q) =>
        q.secao.startsWith(secao.split('.')[0]) &&
        visibleQuestions.includes(q.numero)
    ),
  }))

  const toggleSection = (sectionId: string) => {
    const updated = new Set(expandedSections)
    if (updated.has(sectionId)) {
      updated.delete(sectionId)
    } else {
      updated.add(sectionId)
    }
    setExpandedSections(updated)
  }

  const handleValidate = async () => {
    const result = await validate()
    if (!result.is_valid) {
      setValidationErrors(
        result.conflicts.reduce(
          (acc, conflict) => ({
            ...acc,
            [conflict.split(':')[0]]: conflict,
          }),
          {}
        )
      )
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-blue-500" size={24} />
        <span className="ml-2">Carregando questionário...</span>
      </div>
    )
  }

  const isSubmitted = status === 'submitted' || status === 'validated'

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header com status e progresso */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Questionário Técnico Dinâmico</h1>
        <p className="text-gray-600 mb-4">
          {isSubmitted ? (
            <span className="flex items-center text-green-600">
              <CheckCircle2 className="mr-2" size={20} />
              Questionário submetido
            </span>
          ) : (
            'Responda as perguntas abaixo para definir o escopo técnico'
          )}
        </p>

        {/* Barra de progresso */}
        <div className="mb-4">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-medium">Progresso: {progress}%</span>
            {progress >= 80 && (
              <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                Pronto para validar
              </span>
            )}
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Erros de validação */}
        {(error || validationError) && (
          <div className="bg-red-50 border border-red-200 rounded p-4 mb-4 flex items-start gap-3">
            <AlertCircle className="text-red-500 mt-0.5 flex-shrink-0" size={20} />
            <div className="text-sm text-red-700">
              {error?.message || validationError?.message || 'Erro ao salvar questionário'}
            </div>
          </div>
        )}
      </div>

      {/* Seções do questionário */}
      <div className="space-y-4">
        {sections.map((section) => (
          <div key={section.id} className="border rounded-lg">
            {/* Header da seção (clicável para expandir/colapsar) */}
            <button
              onClick={() => toggleSection(section.id)}
              className="w-full flex items-center justify-between p-4 bg-gray-50 hover:bg-gray-100 transition-colors"
            >
              <h2 className="text-lg font-semibold text-gray-900">{section.title}</h2>
              {expandedSections.has(section.id) ? (
                <ChevronUp size={20} />
              ) : (
                <ChevronDown size={20} />
              )}
            </button>

            {/* Conteúdo da seção */}
            {expandedSections.has(section.id) && (
              <div className="p-4 border-t space-y-6">
                {section.questions.map((question) => (
                  <RenderQuestion
                    key={question.numero}
                    question={question}
                    value={responses[question.numero]}
                    onChange={(value) => updateField(question.numero, value)}
                    error={validationErrors[question.numero]}
                    disabled={isSubmitted}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Botões de ação */}
      <div className="mt-8 flex gap-4">
        {!isSubmitted && (
          <>
            <button
              onClick={saveNow}
              disabled={isSaving || !hasUnsavedChanges}
              className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />}
              Salvar
            </button>

            <button
              onClick={handleValidate}
              disabled={isValidating || progress < 80}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isValidating ? <Loader2 className="animate-spin" size={18} /> : <CheckCircle2 size={18} />}
              Validar Escopo
            </button>

            <button
              onClick={submit}
              disabled={isSaving || progress < 80}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
              Submeter
            </button>

            <button
              className="flex items-center gap-2 px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={progress < 80}
            >
              <Download size={18} />
              Exportar PDF
            </button>
          </>
        )}
      </div>

      {hasUnsavedChanges && (
        <div className="mt-4 p-3 bg-yellow-50 text-yellow-700 rounded text-sm flex items-center gap-2">
          <AlertCircle size={16} />
          Você tem alterações não salvas
        </div>
      )}
    </div>
  )
}

function RenderQuestion({ question, value, onChange, error, disabled }: any) {
  switch (question.tipo) {
    case 'text':
      return (
        <div>
          <label className="block text-sm font-medium text-gray-900 mb-2">
            {question.numero}. {question.pergunta}
            {question.obrigatoria && <span className="text-red-500">*</span>}
          </label>
          <input
            type="text"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'textarea':
      return (
        <div>
          <label className="block text-sm font-medium text-gray-900 mb-2">
            {question.numero}. {question.pergunta}
            {question.obrigatoria && <span className="text-red-500">*</span>}
          </label>
          <textarea
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            rows={4}
            className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'dropdown':
      return (
        <div>
          <label className="block text-sm font-medium text-gray-900 mb-2">
            {question.numero}. {question.pergunta}
            {question.obrigatoria && <span className="text-red-500">*</span>}
          </label>
          <select
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione uma opção...</option>
            {question.opcoes.map((opt: string) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'multiselect':
      return (
        <div>
          <label className="block text-sm font-medium text-gray-900 mb-2">
            {question.numero}. {question.pergunta}
            {question.obrigatoria && <span className="text-red-500">*</span>}
          </label>
          <div className="space-y-2">
            {question.opcoes.map((opt: string) => (
              <label key={opt} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={(value || []).includes(opt)}
                  onChange={(e) => {
                    const selected = value || []
                    if (e.target.checked) {
                      onChange([...selected, opt])
                    } else {
                      onChange(selected.filter((s: string) => s !== opt))
                    }
                  }}
                  disabled={disabled}
                  className="rounded"
                />
                <span className="text-sm text-gray-700">{opt}</span>
              </label>
            ))}
          </div>
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'checkbox':
      return (
        <div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={value || false}
              onChange={(e) => onChange(e.target.checked)}
              disabled={disabled}
              className="rounded"
            />
            <span className="text-sm font-medium text-gray-900">
              {question.numero}. {question.pergunta}
              {question.obrigatoria && <span className="text-red-500">*</span>}
            </span>
          </label>
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    default:
      return null
  }
}

function getSecaoTitle(secao: string): string {
  const titles: Record<string, string> = {
    'A.1': 'Contexto Técnico',
    'A.2': 'Armazenamento',
    'B.1': 'Stack',
    'B.2': 'Escalabilidade',
    'B.3': 'Uptime',
    'C.1': 'Integrações',
    'C.2': 'Segurança',
    'D.1': 'Performance',
    'D.2': 'Compliance',
  }
  return titles[secao] || 'Seção'
}
