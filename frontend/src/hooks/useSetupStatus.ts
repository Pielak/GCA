import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

export interface SetupStatus {
  repo_configured: boolean
  llm_configured: boolean
  questionnaire_submitted: boolean
  ready_to_activate: boolean
}

export const useSetupStatus = (projectId: string | undefined) => {
  return useQuery<SetupStatus>({
    queryKey: ['project-setup-status', projectId],
    queryFn: async () => {
      const res = await apiClient.get<SetupStatus>(`/projects/${projectId}/setup-status`)
      return res.data
    },
    enabled: !!projectId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
}
