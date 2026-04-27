import { useCallback, useState } from 'react'
import { Save, Send, Loader2, AlertCircle, CheckCircle2, Image as ImageIcon, X, HelpCircle } from 'lucide-react'
import { useInitialQuestionnaire, type InitialQuestionnaireData } from '@/hooks/useInitialQuestionnaire'

interface InitialQuestionnaireFormProps {
  projectId?: string
}

export function InitialQuestionnaireForm({ projectId }: InitialQuestionnaireFormProps) {
  const {
    formData,
    updateField,
    submit,
    saveNow,
    isLoading,
    isSaving,
    hasUnsavedChanges,
    status,
    error,
  } = useInitialQuestionnaire(projectId)

  const [expandedSection, setExpandedSection] = useState<string | null>('A')
  const [tooltipVisible, setTooltipVisible] = useState<string | null>(null)
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})

  // Calcular progresso: quantos campos foram preenchidos
  const countFilledFields = () => {
    let filled = 0
    let total = 0
    sections.forEach((section) => {
      section.fields.forEach((field) => {
        total++
        const value = formData[field.key as keyof InitialQuestionnaireData]
        if (value !== null && value !== undefined && value !== '' && (!Array.isArray(value) || value.length > 0)) {
          filled++
        }
      })
    })
    return { filled, total }
  }

  const { filled, total } = countFilledFields()
  const progress = (filled / total) * 100

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-blue-500" size={24} />
        <span className="ml-2">Carregando questionário...</span>
      </div>
    )
  }

  const handleArrayFieldChange = (field: keyof InitialQuestionnaireData, value: string) => {
    const items = value
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
    updateField(field, items)
  }

  const validateField = (fieldKey: string, value: unknown) => {
    const errors = { ...validationErrors }

    // Validar campos numéricos
    if (fieldKey === 'q3_volume' && value !== '' && value !== null) {
      const num = Number(value)
      if (isNaN(num) || num <= 0) {
        errors[fieldKey] = 'Deve ser um número maior que 0'
      } else {
        delete errors[fieldKey]
      }
    }

    if (fieldKey === 'q4_months' && value !== '' && value !== null) {
      const num = Number(value)
      if (isNaN(num) || num <= 0) {
        errors[fieldKey] = 'Deve ser um número maior que 0'
      } else {
        delete errors[fieldKey]
      }
    }

    // Validar que pelo menos 1 item foi selecionado em tags importantes
    if ((fieldKey === 'q6_integrations' || fieldKey === 'q12_sensitive_data' || fieldKey === 'q14_compliance') && Array.isArray(value)) {
      if (value.length === 0) {
        errors[fieldKey] = 'Selecione pelo menos uma opção'
      } else {
        delete errors[fieldKey]
      }
    }

    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>, questionId: string) => {
    const file = e.target.files?.[0]
    if (!file) return

    // TODO: Upload to backend and get URL
    // For now, create a placeholder data URL
    const reader = new FileReader()
    reader.onload = (event) => {
      const url = event.target?.result as string
      const currentImages = (formData.question_images || {})[questionId] || []
      updateField('question_images', {
        ...formData.question_images,
        [questionId]: [...currentImages, url],
      })
    }
    reader.readAsDataURL(file)
  }

  const handleRemoveImage = (questionId: string, index: number) => {
    const images = (formData.question_images || {})[questionId] || []
    const updated = images.filter((_, i) => i !== index)
    updateField('question_images', {
      ...formData.question_images,
      [questionId]: updated,
    })
  }

  const isSubmitted = status === 'submitted' || status === 'validated'

  const sections = [
    {
      id: 'A',
      title: 'Seção A: Contexto do Projeto',
      fields: [
        {
          key: 'q1_name',
          label: 'Q1. Nome e Objetivo do Projeto',
          help: 'Exemplo: "Sistema de Agendamento SaaS para clínicas de saúde — permite pacientes marcar consultas online, médicos gerenciar agenda, e recepcionistas confirmar"',
        },
        {
          key: 'q1_objective',
          label: 'Objetivo Principal',
          help: 'Responda em 1-2 linhas: qual é o problema que você está resolvendo? Para quem? Por quê?',
          type: 'textarea',
        },
        {
          key: 'q2_type',
          label: 'Q2. Tipo de Projeto',
          help: 'Escolha uma opção',
          type: 'select',
          options: [
            { value: 'novo_sistema', label: 'Novo sistema (do zero)' },
            { value: 'refactor', label: 'Refactor de existente' },
            { value: 'feature_nova', label: 'Feature nova em sistema existente' },
            { value: 'manutencao', label: 'Manutenção/bugfix' },
          ],
        },
        {
          key: 'q3_users',
          label: 'Q3. Usuários Finais',
          help: 'Exemplo: "Pacientes, médicos, recepcionistas" — liste os roles principais com 1-3 palavras cada',
        },
        {
          key: 'q3_volume',
          label: 'Quantos usuários simultâneos esperados?',
          type: 'number',
          help: 'Número: pico esperado de sessões simultâneas (ex: 100, 1000, 10000)',
        },
        {
          key: 'q4_months',
          label: 'Q4. Prazo em Meses',
          type: 'number',
          help: 'Quantos meses até primeira release?',
        },
        {
          key: 'q4_target_date',
          label: 'Data Alvo (opcional)',
          type: 'date',
        },
      ],
    },
    {
      id: 'B',
      title: 'Seção B: Requisitos Funcionais',
      fields: [
        {
          key: 'q5_flows',
          label: 'Q5. Fluxos Principais (3-5)',
          help: 'Um fluxo por linha. Ex: "Usuário faz login → vê dashboard → exporta relatório"',
          type: 'textarea',
        },
        {
          key: 'q6_integrations',
          label: 'Q6. Integrações Externas',
          help: 'Separadas por vírgula. Ex: "sms, google_calendar, slack"',
          type: 'tags',
        },
        {
          key: 'q6_integrations_detail',
          label: 'Detalhes de Integrações',
          type: 'textarea',
          help: 'Especifique providers e requisitos de cada integração',
        },
        {
          key: 'q7_frequency',
          label: 'Q7. Frequência de Transações',
          type: 'select',
          options: [
            { value: 'centenas_dia', label: 'Centenas/dia' },
            { value: 'milhares_dia', label: 'Milhares/dia' },
            { value: 'dezenas_milhares', label: 'Dezenas de milhares/dia' },
            { value: 'centenas_milhares_hora', label: 'Centenas de milhares/hora' },
          ],
        },
        {
          key: 'q8_reports',
          label: 'Q8. Relatórios e Analytics',
          help: 'Que dados/dashboards o usuário precisa?',
          type: 'textarea',
        },
        {
          key: 'q9_rules',
          label: 'Q9. Regras de Negócio Complexas',
          help: 'Validações, workflows, cálculos especiais',
          type: 'textarea',
        },
      ],
    },
    {
      id: 'C',
      title: 'Seção C: Requisitos Não-Funcionais',
      fields: [
        {
          key: 'q10_performance',
          label: 'Q10. Performance - Latência Aceitável',
          type: 'select',
          options: [
            { value: 'nao_critica', label: 'Não crítica (segundos OK)' },
            { value: 'importante_100_500ms', label: 'Importante (100-500ms)' },
            { value: 'critica_100ms', label: 'Crítica (<100ms)' },
            { value: 'ultra_critica_50ms', label: 'Ultra-crítica (<50ms)' },
          ],
        },
        {
          key: 'q11_uptime',
          label: 'Q11. Disponibilidade - Uptime Crítico',
          type: 'select',
          options: [
            { value: '99', label: '99%' },
            { value: '99.5', label: '99.5%' },
            { value: '99.9', label: '99.9%' },
            { value: '99.99', label: '99.99%' },
            { value: '99.999', label: '99.999%' },
          ],
        },
        {
          key: 'q12_sensitive_data',
          label: 'Q12. Dados Sensíveis?',
          help: 'Separe por vírgula. Ex: "dados_pessoais, dados_saude"',
          type: 'tags',
        },
        {
          key: 'q13_scalability',
          label: 'Q13. Escalabilidade - Crescimento Esperado',
          type: 'select',
          options: [
            { value: 'estavel', label: 'Estável (mesma escala)' },
            { value: 'modesto', label: 'Modesto (2-3x em 2 anos)' },
            { value: 'agressivo', label: 'Agressivo (10x em 6-12 meses)' },
            { value: 'exponencial', label: 'Exponencial (pode viralizar)' },
          ],
        },
        {
          key: 'q14_compliance',
          label: 'Q14. Compliance e Auditoria',
          help: 'Separadas por vírgula. Ex: "lgpd, gdpr"',
          type: 'tags',
        },
        {
          key: 'q15_longevity',
          label: 'Q15. Longevidade - Quanto Tempo Este Sistema Vai Rodar?',
          type: 'select',
          options: [
            { value: 'mvp_curto', label: 'MVP curto (3-6 meses)' },
            { value: 'medio_prazo', label: 'Médio prazo (2-3 anos)' },
            { value: 'longo_prazo', label: 'Longo prazo (5-10 anos)' },
            { value: 'permanente', label: 'Permanente (crítico)' },
          ],
        },
      ],
    },
    {
      id: 'D',
      title: 'Seção D: Contexto Técnico',
      fields: [
        {
          key: 'q16_stack',
          label: 'Q16. Preferência de Stack',
          help: 'Ex: "Backend: Python/FastAPI, Frontend: React, DB: PostgreSQL"',
          type: 'textarea',
        },
        {
          key: 'q17_existing_infra',
          label: 'Q17. Infraestrutura Existente',
          help: 'Ex: "AWS, Docker, Jenkins"',
          type: 'textarea',
        },
        {
          key: 'q18_constraints',
          label: 'Q18. Constraints Técnicos Conhecidos',
          help: 'Ex: "Sem GPL, rodar on-prem, limite de memória"',
          type: 'textarea',
        },
      ],
    },
    {
      id: 'E',
      title: 'Seção E: Visão do GCA',
      fields: [
        {
          key: 'q19_gca_expectations',
          label: 'Q19. O Que Você Espera que o GCA Faça?',
          help: 'Separe por vírgula. Ex: "codigo_completo, documentacao"',
          type: 'tags',
        },
        {
          key: 'q20_risks',
          label: 'Q20. Maiores Incertezas/Riscos',
          help: 'Quais são seus principais pontos de risco?',
          type: 'textarea',
        },
      ],
    },
  ]

  return (
    <div className="space-y-6">
      {/* Progress Bar */}
      {!isSubmitted && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-700">Progresso: {filled}/{total} campos preenchidos</p>
            <span className="text-xs text-slate-500">{Math.round(progress)}%</span>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                progress < 50 ? 'bg-amber-500' : progress < 100 ? 'bg-blue-500' : 'bg-green-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Status Bar */}
      {status === 'submitted' && (
        <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 p-4">
          <CheckCircle2 size={20} className="text-green-600" />
          <div>
            <p className="font-semibold text-green-900">Questionário Submetido</p>
            <p className="text-sm text-green-800">As personas estão analisando suas respostas.</p>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 p-4">
          <AlertCircle size={20} className="text-red-600" />
          <p className="text-sm text-red-800">{String(error)}</p>
        </div>
      )}

      {hasUnsavedChanges && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 p-4">
          <Save size={20} className="text-amber-600" />
          <p className="text-sm text-amber-800">Salvando mudanças...</p>
        </div>
      )}

      {/* Sections */}
      <div className="space-y-4">
        {sections.map((section) => (
          <div key={section.id} className="border rounded-lg overflow-hidden">
            {/* Section Header */}
            <button
              onClick={() => setExpandedSection(expandedSection === section.id ? null : section.id)}
              className="w-full bg-gradient-to-r from-slate-50 to-slate-100 px-6 py-4 flex items-center justify-between hover:from-slate-100 hover:to-slate-200 transition-colors"
            >
              <h3 className="font-semibold text-slate-900">{section.title}</h3>
              <span className="text-lg text-slate-500">{expandedSection === section.id ? '−' : '+'}</span>
            </button>

            {/* Section Content */}
            {expandedSection === section.id && (
              <div className="px-6 py-4 space-y-6 bg-white border-t">
                {section.fields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <div className="flex items-center gap-2 group">
                      <label className="block font-medium text-slate-900">{field.label}</label>
                      {field.help && (
                        <div className="relative">
                          <button
                            type="button"
                            onMouseEnter={() => setTooltipVisible(field.key)}
                            onMouseLeave={() => setTooltipVisible(null)}
                            onClick={() => setTooltipVisible(tooltipVisible === field.key ? null : field.key)}
                            className="text-slate-400 hover:text-slate-600 transition-colors"
                          >
                            <HelpCircle size={16} />
                          </button>
                          {tooltipVisible === field.key && (
                            <div className="absolute bottom-full left-0 mb-2 p-2 bg-slate-900 text-white text-xs rounded shadow-lg whitespace-nowrap z-50">
                              {field.help}
                              <div className="absolute top-full left-2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-slate-900" />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    {field.help && <p className="text-xs text-slate-500 italic">{field.help}</p>}

                    {field.type === 'textarea' ? (
                      <textarea
                        value={(formData[field.key as keyof InitialQuestionnaireData] as string) || ''}
                        onChange={(e) => updateField(field.key as keyof InitialQuestionnaireData, e.target.value)}
                        disabled={isSubmitted}
                        rows={3}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50"
                        placeholder="Digite sua resposta..."
                      />
                    ) : field.type === 'select' ? (
                      <select
                        value={(formData[field.key as keyof InitialQuestionnaireData] as string) || ''}
                        onChange={(e) => updateField(field.key as keyof InitialQuestionnaireData, e.target.value)}
                        disabled={isSubmitted}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50"
                      >
                        <option value="">Selecione uma opção...</option>
                        {field.options?.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : field.type === 'number' ? (
                      <div>
                        <input
                          type="number"
                          value={(formData[field.key as keyof InitialQuestionnaireData] as number) || ''}
                          onChange={(e) => {
                            updateField(field.key as keyof InitialQuestionnaireData, parseInt(e.target.value) || '')
                            validateField(field.key, parseInt(e.target.value) || '')
                          }}
                          disabled={isSubmitted}
                          className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:border-transparent disabled:bg-slate-50 transition-colors ${
                            validationErrors[field.key]
                              ? 'border-red-400 focus:ring-red-500'
                              : 'border-slate-300 focus:ring-blue-500'
                          }`}
                        />
                        {validationErrors[field.key] && (
                          <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
                            <AlertCircle size={12} /> {validationErrors[field.key]}
                          </p>
                        )}
                      </div>
                    ) : field.type === 'date' ? (
                      <input
                        type="date"
                        value={(formData[field.key as keyof InitialQuestionnaireData] as string) || ''}
                        onChange={(e) => updateField(field.key as keyof InitialQuestionnaireData, e.target.value)}
                        disabled={isSubmitted}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50"
                      />
                    ) : field.type === 'tags' ? (
                      <div>
                        <input
                          type="text"
                          value={((formData[field.key as keyof InitialQuestionnaireData] as string[]) || []).join(', ')}
                          onChange={(e) => {
                            handleArrayFieldChange(field.key as keyof InitialQuestionnaireData, e.target.value)
                            const items = e.target.value
                              .split(',')
                              .map((s) => s.trim())
                              .filter((s) => s.length > 0)
                            validateField(field.key, items)
                          }}
                          disabled={isSubmitted}
                          placeholder="Separadas por vírgula"
                          className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:border-transparent disabled:bg-slate-50 transition-colors ${
                            validationErrors[field.key]
                              ? 'border-red-400 focus:ring-red-500'
                              : 'border-slate-300 focus:ring-blue-500'
                          }`}
                        />
                        {validationErrors[field.key] && (
                          <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
                            <AlertCircle size={12} /> {validationErrors[field.key]}
                          </p>
                        )}
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={(formData[field.key as keyof InitialQuestionnaireData] as string) || ''}
                        onChange={(e) => updateField(field.key as keyof InitialQuestionnaireData, e.target.value)}
                        disabled={isSubmitted}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50"
                        placeholder="Digite sua resposta..."
                      />
                    )}

                    {/* Image Upload for this question */}
                    {!isSubmitted && (
                      <div className="space-y-2">
                        <label className="text-xs text-slate-600 flex items-center gap-2">
                          <ImageIcon size={14} />
                          Anexar imagem (opcional)
                        </label>
                        <input
                          type="file"
                          accept="image/*"
                          onChange={(e) => handleImageUpload(e, field.key)}
                          className="text-sm"
                        />
                        {(formData.question_images?.[field.key] || []).length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-2">
                            {(formData.question_images?.[field.key] || []).map((url, idx) => (
                              <div key={idx} className="relative group">
                                <img
                                  src={url}
                                  alt={`${field.key}-${idx}`}
                                  className="h-16 w-16 object-cover rounded border border-slate-200"
                                />
                                <button
                                  onClick={() => handleRemoveImage(field.key, idx)}
                                  className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                  <X size={12} />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Action Buttons */}
      {!isSubmitted && (
        <div className="flex gap-4 sticky bottom-0 bg-white border-t p-4">
          <button
            onClick={saveNow}
            disabled={isSaving || !hasUnsavedChanges}
            className="flex items-center gap-2 px-4 py-2 bg-slate-200 text-slate-900 rounded-lg hover:bg-slate-300 disabled:opacity-50"
          >
            {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Salvar Agora
          </button>

          <button
            onClick={submit}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            Submeter para Personas
          </button>
        </div>
      )}
    </div>
  )
}
