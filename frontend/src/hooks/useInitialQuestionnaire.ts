import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

export interface InitialQuestionnaireData {
  // Seção A: Contexto
  q1_name?: string
  q1_objective?: string
  q2_type?: string
  q3_users?: string
  q3_volume?: number
  q4_months?: number
  q4_target_date?: string

  // Seção B: Requisitos Funcionais
  q5_flows?: string
  q6_integrations?: string[]
  q6_integrations_detail?: string
  q7_frequency?: string
  q8_reports?: string
  q9_rules?: string

  // Seção C: RNFs
  q10_performance?: string
  q11_uptime?: string
  q12_sensitive_data?: string[]
  q13_scalability?: string
  q14_compliance?: string[]
  q15_longevity?: string

  // Seção D: Técnico
  q16_stack?: string
  q17_existing_infra?: string
  q18_constraints?: string

  // Seção E: GCA Vision
  q19_gca_expectations?: string[]
  q20_risks?: string

  // Attachments
  question_images?: Record<string, string[]>

  // Control
  submit?: boolean
}

export interface InitialQuestionnaireResponse {
  id: string
  project_id: string
  status: 'draft' | 'submitted' | 'validated'
  created_at: string
  updated_at: string
  submitted_at?: string
  submitted_by?: string
}

const AUTO_SAVE_DELAY_MS = 2000

export function useInitialQuestionnaire(projectId?: string) {
  const [formData, setFormData] = useState<InitialQuestionnaireData>({})
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const autoSaveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Fetch questionnaire
  const { data: questionnaire, isLoading, refetch } = useQuery({
    queryKey: ['initial-questionnaire', projectId],
    queryFn: async () => {
      if (!projectId) return null
      const res = await apiClient.get<InitialQuestionnaireResponse>(
        `/projects/${projectId}/initial-questionnaire`
      )
      return res.data
    },
    enabled: !!projectId,
  })

  // Initialize form when questionnaire loads
  useEffect(() => {
    if (questionnaire) {
      setFormData(questionnaire as InitialQuestionnaireData)
      setHasUnsavedChanges(false)
    }
  }, [questionnaire])

  // Auto-save mutation
  const saveMutation = useMutation({
    mutationFn: async (data: InitialQuestionnaireData) => {
      if (!projectId) throw new Error('Project ID missing')
      const res = await apiClient.patch<InitialQuestionnaireResponse>(
        `/projects/${projectId}/initial-questionnaire`,
        data
      )
      return res.data
    },
  })

  // Handle field changes with debounced auto-save
  const updateField = useCallback(
    (field: keyof InitialQuestionnaireData, value: unknown) => {
      setFormData((prev) => ({
        ...prev,
        [field]: value,
      }))
      setHasUnsavedChanges(true)

      // Clear existing timeout
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current)
      }

      // Schedule auto-save
      autoSaveTimeoutRef.current = setTimeout(() => {
        saveMutation.mutate({
          ...formData,
          [field]: value,
          submit: false,
        })
        setHasUnsavedChanges(false)
      }, AUTO_SAVE_DELAY_MS)
    },
    [formData]
  )

  // Submit questionnaire
  const submit = useCallback(async () => {
    await saveMutation.mutateAsync({
      ...formData,
      submit: true,
    })
    setHasUnsavedChanges(false)
    await refetch()
  }, [formData, saveMutation, refetch])

  // Save immediately without auto-save delay
  const saveNow = useCallback(async () => {
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current)
    }
    await saveMutation.mutateAsync({
      ...formData,
      submit: false,
    })
    setHasUnsavedChanges(false)
  }, [formData, saveMutation])

  return {
    formData,
    updateField,
    submit,
    saveNow,
    isLoading,
    isSaving: saveMutation.isPending,
    hasUnsavedChanges,
    status: questionnaire?.status || 'draft',
    error: saveMutation.error,
  }
}
