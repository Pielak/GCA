import { useState } from 'react'
import { Save, Send, Loader2, AlertCircle, CheckCircle2, ChevronDown, ChevronUp, HelpCircle } from 'lucide-react'
import { useTechnicalQuestionnaire } from '@/hooks/useTechnicalQuestionnaire'
import { useToast } from '@/hooks/useToast'

interface TechnicalQuestionnaireFormProps {
  projectId?: string
  onSubmitted?: (questionnaireId: string) => void | Promise<void>
}

// Schema das perguntas técnicas (importado do backend, mas aqui simplificado para o frontend)
const TECHNICAL_QUESTIONS = [
  {
    numero: 'Q1',
    pergunta: 'Qual é o escopo principal do projeto técnico?',
    tipo: 'dropdown',
    secao: 'A.1',
    obrigatoria: true,
    help: 'Identifica se você está construindo algo novo, melhorando um sistema existente ou apenas corrigindo bugs',
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
    help: 'Define a urgência do projeto e ajuda a planejar recursos e metodologia',
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
    help: 'Determina se a aplicação precisa crescer horizontalmente (múltiplas instâncias) ou apenas verticalmente',
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
    help: 'Escolhe entre banco relacional (transações ACID), NoSQL (flexibilidade), ou outras abordagens',
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
    help: 'Exemplos: Python/FastAPI, Node.js/Express, Java/Spring, Go, C#/.NET',
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
    help: 'Exemplos: React, Vue, Angular, Svelte, ou aplicação desktop/mobile',
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
    help: 'Número de requisições HTTP/segundo. Afeta escolha de cache, load balancing, DB',
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
    help: 'Redis para cache em memória, CDN para assets, Memcached para sessões',
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
    help: 'Para processar tarefas assíncronas: envio de emails, processamento de imagens, notificações',
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
    help: '99.9% = ~8h downtime/ano; 99.99% = ~52min/ano. Afeta redundância e failover',
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
    help: 'CRM, ERP, payment gateways, SMS, analytics, etc. Determina APIs a usar',
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
    help: 'REST (mais comum), GraphQL (mais eficiente), gRPC (performático), Webhooks (eventos)',
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
    help: 'Autenticação (OAuth, JWT), autorização (RBAC), encryption, compliance (HIPAA, PCI-DSS)',
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
    help: 'Exemplos: 100ms, 500ms, 1s. Afeta arquitetura (sync vs async), escolha de DB',
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
    help: 'LGPD (Brasil), GDPR (Europa), HIPAA (saúde EUA), SOC 2 (auditoria)',
    opcoes: ['LGPD', 'GDPR', 'HIPAA', 'SOC 2', 'Nenhuma'],
    visibleIf: [],
    revela: [],
  },
]

export function TechnicalQuestionnaireForm({ projectId, onSubmitted }: TechnicalQuestionnaireFormProps) {
  const toast = useToast()
  const {
    responses,
    updateField,
    visibleQuestions,
    progress,
    validate,
    submit: hookSubmit,
    saveNow: hookSaveNow,
    isLoading,
    isSaving,
    isValidating,
    hasUnsavedChanges,
    status,
    error,
    validationError,
  } = useTechnicalQuestionnaire(projectId)

  // Wrapper around saveNow with toast
  const saveNow = async () => {
    try {
      await hookSaveNow()
      toast.success('Questionário salvo')
    } catch (err) {
      toast.error('Erro ao salvar questionário')
      throw err
    }
  }

  // Wrapper around submit to call onSubmitted callback with toast
  const submit = async () => {
    try {
      const questionnaireId = await hookSubmit()
      toast.success('Questionário submetido com sucesso!')
      // Chamar callback após sucesso, passando o ID do questionário
      if (onSubmitted && questionnaireId) {
        await onSubmitted(questionnaireId)
      }
    } catch (err) {
      toast.error('Erro ao submeter questionário')
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
    try {
      const result = await validate()
      if (result.is_valid) {
        toast.success('Escopo validado com sucesso!')
        setValidationErrors({})
      } else {
        toast.warning(`Escopo inválido: ${result.conflicts.length} conflito(s)`)
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
    } catch (err) {
      toast.error('Erro ao validar escopo')
      throw err
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
                    disabled={false}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Botões de ação */}
      <div className="mt-8 flex gap-4">
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
          disabled={isValidating || progress < 70}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isValidating ? <Loader2 className="animate-spin" size={18} /> : <CheckCircle2 size={18} />}
          Validar Escopo
        </button>

        <button
          onClick={submit}
          disabled={isSaving || progress < 70}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
          Submeter
        </button>

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
  const [showHelp, setShowHelp] = useState(false)

  switch (question.tipo) {
    case 'text':
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <label className="block text-sm font-medium text-white">
              {question.numero}. {question.pergunta}
              {question.obrigatoria && <span className="text-red-500">*</span>}
            </label>
            {question.help && (
              <div className="relative">
                <button
                  type="button"
                  onMouseEnter={() => setShowHelp(true)}
                  onMouseLeave={() => setShowHelp(false)}
                  className="text-blue-500 hover:text-blue-700 focus:outline-none"
                  title={question.help}
                >
                  <HelpCircle className="w-4 h-4" />
                </button>
                {showHelp && (
                  <div className="absolute bottom-full left-0 mb-2 w-48 bg-blue-50 border border-blue-300 rounded-lg p-2 text-xs text-blue-900 z-10">
                    {question.help}
                  </div>
                )}
              </div>
            )}
          </div>
          <input
            type="text"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 border rounded-lg text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'textarea':
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <label className="block text-sm font-medium text-white">
              {question.numero}. {question.pergunta}
              {question.obrigatoria && <span className="text-red-500">*</span>}
            </label>
            {question.help && (
              <div className="relative">
                <button
                  type="button"
                  onMouseEnter={() => setShowHelp(true)}
                  onMouseLeave={() => setShowHelp(false)}
                  className="text-blue-500 hover:text-blue-700 focus:outline-none"
                  title={question.help}
                >
                  <HelpCircle className="w-4 h-4" />
                </button>
                {showHelp && (
                  <div className="absolute bottom-full left-0 mb-2 w-48 bg-blue-50 border border-blue-300 rounded-lg p-2 text-xs text-blue-900 z-10">
                    {question.help}
                  </div>
                )}
              </div>
            )}
          </div>
          <textarea
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            rows={4}
            className="w-full px-3 py-2 border border-blue-300 text-gray-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 disabled:bg-gray-100"
          />
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'dropdown':
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <label className="block text-sm font-medium text-white">
              {question.numero}. {question.pergunta}
              {question.obrigatoria && <span className="text-red-500">*</span>}
            </label>
            {question.help && (
              <div className="relative">
                <button
                  type="button"
                  onMouseEnter={() => setShowHelp(true)}
                  onMouseLeave={() => setShowHelp(false)}
                  className="text-blue-500 hover:text-blue-700 focus:outline-none"
                  title={question.help}
                >
                  <HelpCircle className="w-4 h-4" />
                </button>
                {showHelp && (
                  <div className="absolute bottom-full left-0 mb-2 w-48 bg-blue-50 border border-blue-300 rounded-lg p-2 text-xs text-blue-900 z-10">
                    {question.help}
                  </div>
                )}
              </div>
            )}
          </div>
          <select
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 border border-blue-300 text-gray-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 disabled:bg-gray-100"
          >
            <option value="">Selecione uma opção...</option>
            {question.opcoes.map((opt: string) => (
              <option key={opt} value={opt} className={value === opt ? 'bg-green-100 text-green-700' : ''}>
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
          <div className="flex items-center gap-2 mb-2">
            <label className="block text-sm font-medium text-white">
              {question.numero}. {question.pergunta}
              {question.obrigatoria && <span className="text-red-500">*</span>}
            </label>
            {question.help && (
              <div className="relative">
                <button
                  type="button"
                  onMouseEnter={() => setShowHelp(true)}
                  onMouseLeave={() => setShowHelp(false)}
                  className="text-blue-500 hover:text-blue-700 focus:outline-none"
                  title={question.help}
                >
                  <HelpCircle className="w-4 h-4" />
                </button>
                {showHelp && (
                  <div className="absolute bottom-full left-0 mb-2 w-48 bg-blue-50 border border-blue-300 rounded-lg p-2 text-xs text-blue-900 z-10">
                    {question.help}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="space-y-2">
            {question.opcoes.map((opt: string) => {
              const isChecked = (value || []).includes(opt)
              return (
                <label
                  key={opt}
                  className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${
                    isChecked
                      ? 'bg-green-100 border border-green-500'
                      : 'bg-blue-50 border border-blue-300 hover:bg-blue-100'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => {
                      const selected = value || []
                      if (e.target.checked) {
                        onChange([...selected, opt])
                      } else {
                        onChange(selected.filter((s: string) => s !== opt))
                      }
                    }}
                    disabled={disabled}
                    className="rounded accent-green-600"
                  />
                  <span className={`text-sm font-medium ${
                    isChecked ? 'text-green-700' : 'text-gray-900'
                  }`}>
                    {opt}
                  </span>
                </label>
              )
            })}
          </div>
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'multiselect_with_other':
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <label className="block text-sm font-medium text-white">
              {question.numero}. {question.pergunta}
              {question.obrigatoria && <span className="text-red-500">*</span>}
            </label>
            {question.help && (
              <div className="relative">
                <button
                  type="button"
                  onMouseEnter={() => setShowHelp(true)}
                  onMouseLeave={() => setShowHelp(false)}
                  className="text-blue-500 hover:text-blue-700 focus:outline-none"
                  title={question.help}
                >
                  <HelpCircle className="w-4 h-4" />
                </button>
                {showHelp && (
                  <div className="absolute bottom-full left-0 mb-2 w-48 bg-blue-50 border border-blue-300 rounded-lg p-2 text-xs text-blue-900 z-10">
                    {question.help}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="space-y-2">
            {question.opcoes.map((opt: string) => {
              const isChecked = (value || []).includes(opt)
              const isOtherChecked = Array.isArray(value) &&
                value.some((v: any) => typeof v === 'string' && v.startsWith('Outro:'))

              return (
                <div key={opt}>
                  <label
                    className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${
                      isChecked || (opt === 'Outro' && isOtherChecked)
                        ? 'bg-green-100 border border-green-500'
                        : 'bg-blue-50 border border-blue-300 hover:bg-blue-100'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked || (opt === 'Outro' && isOtherChecked)}
                      onChange={(e) => {
                        const selected = Array.isArray(value) ? [...value] : []
                        if (opt === 'Outro') {
                          // Remove any existing "Outro: ..." entry
                          const filtered = selected.filter((v: any) => !v.startsWith('Outro:'))
                          if (e.target.checked) {
                            onChange([...filtered, 'Outro:'])
                          } else {
                            onChange(filtered)
                          }
                        } else {
                          if (e.target.checked && !selected.includes(opt)) {
                            onChange([...selected, opt])
                          } else {
                            onChange(selected.filter((s: any) => s !== opt))
                          }
                        }
                      }}
                      disabled={disabled}
                      className="rounded accent-green-600"
                    />
                    <span className={`text-sm font-medium ${
                      isChecked || (opt === 'Outro' && isOtherChecked) ? 'text-green-700' : 'text-gray-900'
                    }`}>
                      {opt}
                    </span>
                  </label>

                  {opt === 'Outro' && isOtherChecked && (
                    <input
                      type="text"
                      placeholder="Descreva outras opções..."
                      value={(() => {
                        const outro = (value || []).find((v: any) => typeof v === 'string' && v.startsWith('Outro:'))
                        return outro ? outro.substring(6).trim() : ''
                      })()}
                      onChange={(e) => {
                        const selected = (value || []).filter((v: any) => !v.startsWith('Outro:'))
                        const texto = e.target.value.trim()
                        if (texto) {
                          onChange([...selected, `Outro: ${texto}`])
                        } else {
                          onChange([...selected, 'Outro:'])
                        }
                      }}
                      disabled={disabled}
                      className="ml-6 mt-1 w-full px-2 py-1 border border-gray-300 rounded text-sm text-gray-900"
                    />
                  )}
                </div>
              )
            })}
          </div>
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      )

    case 'checkbox':
      return (
        <div>
          <div className={`flex items-center gap-2 p-2 rounded-lg transition-colors ${
            value
              ? 'bg-green-100 border border-green-500'
              : 'bg-blue-50 border border-blue-300'
          }`}>
            <input
              type="checkbox"
              checked={value || false}
              onChange={(e) => onChange(e.target.checked)}
              disabled={disabled}
              className="rounded accent-green-600"
            />
            <div className="flex items-center gap-2">
              <span className={`text-sm font-medium ${
                value ? 'text-green-700' : 'text-white'
              }`}>
                {question.numero}. {question.pergunta}
                {question.obrigatoria && <span className="text-red-500">*</span>}
              </span>
              {question.help && (
                <div className="relative">
                  <button
                    type="button"
                    onMouseEnter={() => setShowHelp(true)}
                    onMouseLeave={() => setShowHelp(false)}
                    className="text-blue-500 hover:text-blue-700 focus:outline-none"
                    title={question.help}
                  >
                    <HelpCircle className="w-4 h-4" />
                  </button>
                  {showHelp && (
                    <div className="absolute bottom-full left-0 mb-2 w-48 bg-blue-50 border border-blue-300 rounded-lg p-2 text-xs text-blue-900 z-10">
                      {question.help}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
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
