import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

export interface PipelineQuestion {
  id: string
  source: string
  document_id: string
  document_name: string
  route_map_id: string
  question_text: string
  rationale: string
  answer_type: string
  answer_options: string[] | null
  category: string | null
  severity: string | null
  status: 'pending' | 'answered'
  answer_text: string | null
}

interface PipelineQuestionsResponse {
  pending_questions: PipelineQuestion[]
  answered_questions: PipelineQuestion[]
}

export function usePipelineQuestions(projectId: string | undefined) {
  const toast = useToast()

  const query = useQuery({
    queryKey: ['pipeline-questions', projectId],
    queryFn: async () => {
      const res = await apiClient.get<PipelineQuestionsResponse>(
        `/projects/${projectId}/pipeline-questions`
      )
      return res.data
    },
    enabled: !!projectId,
    refetchInterval: 1000 * 30, // 30s polling
    staleTime: 1000 * 10,
  })

  const answerMutation = useMutation({
    mutationFn: async (answers: Record<string, string>) => {
      const res = await apiClient.post(
        `/projects/${projectId}/pipeline-questions/answers`,
        { answers }
      )
      return res.data
    },
    onSuccess: () => {
      toast.success('Respostas enviadas. Pipeline retomado.')
    },
    onError: (err: unknown) => {
      toast.error(`Falha ao enviar respostas: ${getErrorMessage(err)}`)
    },
  })

  return {
    pendingQuestions: query.data?.pending_questions ?? [],
    answeredQuestions: query.data?.answered_questions ?? [],
    isLoading: query.isLoading,
    submitAnswers: answerMutation.mutateAsync,
    isSubmitting: answerMutation.isPending,
    refetch: query.refetch,
  }
}
