import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

export interface TechnicalQuestionnaireData {
  responses: Record<string, unknown>
  submit?: boolean
}

export interface TechnicalQuestionnaireDetailResponse {
  id: string
  project_id: string
  status: 'draft' | 'submitted' | 'validated'
  responses: Record<string, unknown>
  progress_percent: number
  visible_questions: string[]
  created_at: string
  updated_at: string
  submitted_at?: string
  submitted_by?: string
}

export interface ValidationResponse {
  is_valid: boolean
  progress_percent: number
  visible_questions: string[]
  conflicts: string[]
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

  // Validate mutation
  const validateMutation = useMutation({
    mutationFn: async (data: TechnicalQuestionnaireData) => {
      if (!projectId) throw new Error('Project ID missing')
      const res = await apiClient.post<ValidationResponse>(
        `/projects/${projectId}/technical-questionnaire/validate`,
        data
      )
      return res.data
    },
  })

  // Update field with debounced auto-save
  const updateField = useCallback(
    (fieldNumber: string, value: unknown) => {
      const newResponses = {
        ...responses,
        [fieldNumber]: value,
      }
      setResponses(newResponses)
      setHasUnsavedChanges(true)

      // Clear existing timeout
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current)
      }

      // Schedule auto-save
      autoSaveTimeoutRef.current = setTimeout(() => {
        saveMutation.mutate({
          responses: newResponses,
          submit: false,
        })
      }, AUTO_SAVE_DELAY_MS)
    },
    [responses]
  )

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
  }, [responses, saveMutation, refetch])

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
    status: questionnaire?.status || 'draft',
    error: saveMutation.error,
    validationError: validateMutation.error,
  }
}
