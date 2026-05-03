import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

export interface TechnicalQuestionnaireData {
  responses: Record<string, unknown>
  submit?: boolean
}

// MVP 35: status canônico = draft → validated → submitted | archived (DBA-M3)
//   draft     = rascunho/auto-save (sem Validar Escopo OK)
//   validated = passou Validar Escopo, pré-submit
//   submitted = terminal, dispara personas
//   archived  = deletado via Ingestão (volta projeto a setup)
export type QuestionnaireStatus = 'draft' | 'validated' | 'submitted' | 'archived'

export interface TechnicalQuestionnaireDetailResponse {
  id: string
  project_id: string
  status: QuestionnaireStatus
  responses: Record<string, unknown>
  progress_percent: number
  visible_questions: string[]
  created_at: string
  updated_at: string
  submitted_at?: string
  submitted_by?: string
  validated_at?: string
  validated_by?: string
}

export interface ValidationResponse {
  is_valid: boolean
  progress_percent: number
  visible_questions: string[]
  conflicts: string[]
  // MVP 35: campos canônicos novos (defaults para retrocompat)
  warnings?: string[]
  info?: string[]
  rules_evaluated?: number
  evaluated_at_ms?: number
  persisted?: boolean
}

// MVP 35: regra do catálogo (single source of truth via GET /rules)
export interface ValidationRule {
  id: string
  theme: 'nosql_acid' | 'stack' | 'fe_be' | 'compliance' | 'infra'
  when: Record<string, unknown>
  verdict: 'ok' | 'warning' | 'conflict'
  severity: 'info' | 'warning' | 'error'
  message: string
  suggestions: string[]
  affected_fields: string[]
}

export interface RulesCatalogResponse {
  rules: ValidationRule[]
  count: number
  themes: string[]
}

const AUTO_SAVE_DELAY_MS = 2000

export function useTechnicalQuestionnaire(projectId?: string) {
  const [responses, setResponses] = useState<Record<string, unknown>>({})
  const [visibleQuestions, setVisibleQuestions] = useState<string[]>([])
  const [progress, setProgress] = useState(0)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const autoSaveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Fetch questionnaire
  const { data: questionnaire, isLoading, refetch } = useQuery({
    queryKey: ['technical-questionnaire', projectId],
    queryFn: async () => {
      if (!projectId) return null
      const res = await apiClient.get<TechnicalQuestionnaireDetailResponse>(
        `/projects/${projectId}/technical-questionnaire`
      )
      return res.data
    },
    enabled: !!projectId,
  })

  // Initialize form when questionnaire loads
  useEffect(() => {
    if (questionnaire) {
      setResponses(questionnaire.responses || {})
      setVisibleQuestions(questionnaire.visible_questions || [])
      setProgress(questionnaire.progress_percent || 0)
      setHasUnsavedChanges(false)
    }
  }, [questionnaire])

  // Auto-save mutation
  const saveMutation = useMutation({
    mutationFn: async (data: TechnicalQuestionnaireData) => {
      if (!projectId) throw new Error('Project ID missing')
      const res = await apiClient.patch<any>(
        `/projects/${projectId}/technical-questionnaire`,
        data
      )
      return res.data
    },
    onSuccess: (data) => {
      setHasUnsavedChanges(false)
      if (data.progress_percent !== undefined) {
        setProgress(data.progress_percent)
      }
      if (data.visible_questions !== undefined) {
        setVisibleQuestions(data.visible_questions)
      }
    },
  })

  // Validate mutation (Validar Escopo botão — persist=true)
  const validateMutation = useMutation({
    mutationFn: async (data: TechnicalQuestionnaireData) => {
      if (!projectId) throw new Error('Project ID missing')
      const res = await apiClient.post<ValidationResponse>(
        `/projects/${projectId}/technical-questionnaire/validate?persist=true`,
        data
      )
      return res.data
    },
  })

  // MVP 35: Inline preview validation — chamada por validate-on-blur (persist=false).
  // NÃO promove status='validated' nem dispara persistência. Só retorna conflicts/warnings.
  const validateInlineMutation = useMutation({
    mutationFn: async (data: TechnicalQuestionnaireData) => {
      if (!projectId) throw new Error('Project ID missing')
      const res = await apiClient.post<ValidationResponse>(
        `/projects/${projectId}/technical-questionnaire/validate?persist=false`,
        data
      )
      return res.data
    },
  })

  // Estado inline: último resultado de validate-on-blur (warnings/conflicts atuais)
  const [inlineConflicts, setInlineConflicts] = useState<string[]>([])
  const [inlineWarnings, setInlineWarnings] = useState<string[]>([])
  const [inlineInfo, setInlineInfo] = useState<string[]>([])
  const validateOnBlurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Update field with debounced auto-save + validate-on-blur (MVP 35).
  // 2 timeouts independentes:
  //   - autoSave (2s): persiste responses no draft
  //   - validateOnBlur (800ms): roda RulesEvaluator preview (sem persist)
  const updateField = useCallback(
    (fieldNumber: string, value: unknown) => {
      const newResponses = {
        ...responses,
        [fieldNumber]: value,
      }
      setResponses(newResponses)
      setHasUnsavedChanges(true)

      // Reset auto-save (2s debounce)
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current)
      }
      autoSaveTimeoutRef.current = setTimeout(() => {
        saveMutation.mutate({
          responses: newResponses,
          submit: false,
        })
      }, AUTO_SAVE_DELAY_MS)

      // Reset validate-on-blur (800ms debounce — mais rápido que auto-save)
      if (validateOnBlurTimeoutRef.current) {
        clearTimeout(validateOnBlurTimeoutRef.current)
      }
      validateOnBlurTimeoutRef.current = setTimeout(async () => {
        try {
          const result = await validateInlineMutation.mutateAsync({
            responses: newResponses,
            submit: false,
          })
          setInlineConflicts(result.conflicts || [])
          setInlineWarnings(result.warnings || [])
          setInlineInfo(result.info || [])
        } catch {
          // Silencioso — validate-on-blur não bloqueia UX
        }
      }, 800)
    },
    [responses, validateInlineMutation, saveMutation]
  )

  // MVP 35 — Carrega catálogo de regras 1× no mount (single source of truth)
  const { data: rulesCatalog } = useQuery<RulesCatalogResponse>({
    queryKey: ['technical-questionnaire-rules'],
    queryFn: async () => {
      const res = await apiClient.get<RulesCatalogResponse>(
        `/projects/technical-questionnaire/rules`
      )
      return res.data
    },
    staleTime: 5 * 60 * 1000, // 5min cache (regras quase nunca mudam em runtime)
  })

  // Validate questionnaire
  const validate = useCallback(async () => {
    const result = await validateMutation.mutateAsync({
      responses,
      submit: false,
    })
    setVisibleQuestions(result.visible_questions)
    setProgress(result.progress_percent)
    return result
  }, [responses, validateMutation])

  // Submit questionnaire
  const submit = useCallback(async () => {
    const result = await saveMutation.mutateAsync({
      responses,
      submit: true,
    })
    // onSuccess callback já chama setHasUnsavedChanges(false)
    await refetch()
    // Retorna o ID do questionário
    return questionnaire?.id || result.id
  }, [responses, saveMutation, refetch, questionnaire])

  // Save immediately without auto-save delay
  const saveNow = useCallback(async () => {
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current)
    }
    const result = await saveMutation.mutateAsync({
      responses,
      submit: false,
    })
    setProgress(result.progress_percent)
    setVisibleQuestions(result.visible_questions)
    setHasUnsavedChanges(false)
  }, [responses, saveMutation])

  return {
    responses,
    updateField,
    visibleQuestions,
    progress,
    validate,
    submit,
    saveNow,
    isLoading,
    isSaving: saveMutation.isPending,
    isValidating: validateMutation.isPending,
    hasUnsavedChanges,
    status: (questionnaire?.status || 'draft') as QuestionnaireStatus,
    error: saveMutation.error,
    validationError: validateMutation.error,
    // MVP 35 — exposição inline + catalogo
    inlineConflicts,
    inlineWarnings,
    inlineInfo,
    rulesCatalog: rulesCatalog?.rules || [],
  }
}
