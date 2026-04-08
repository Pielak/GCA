import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

export interface AccessAttempt {
  id: string
  user_id: string
  user_email?: string
  attempt_number: number
  blocked: boolean
  blocked_at?: string
  created_at: string
}

export const useSuspiciousAccess = (blockedOnly: boolean = true) => {
  const toast = useToast()

  return useQuery({
    queryKey: ['suspicious-access', blockedOnly],
    queryFn: async () => {
      try {
        const response = await apiClient.get<any>('/admin/suspicious-access')

        // Handle both array and nested object response format
        let data: AccessAttempt[] = []

        if (Array.isArray(response.data)) {
          data = response.data
        } else if (response.data?.suspicious_accesses && Array.isArray(response.data.suspicious_accesses)) {
          // Backend returns nested format: { suspicious_accesses: [...] }
          data = response.data.suspicious_accesses.map((item: any) => ({
            id: item.access_attempt_id || item.id,
            user_id: item.user_id,
            user_email: item.user_email,
            attempt_number: item.attempt_number,
            blocked: item.blocked,
            blocked_at: item.blocked_at,
            created_at: item.created_at,
          }))
        }

        if (blockedOnly) {
          return data.filter(a => a.blocked)
        }
        return data
      } catch (error: any) {
        toast.error(error.message || 'Erro ao carregar acessos suspeitos')
        throw error
      }
    },
    staleTime: 1000 * 60, // 1 minute
  })
}

export const useUnblockAccess = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (attemptId: string) => {
      try {
        const response = await apiClient.post(`/admin/suspicious-access/${attemptId}/unblock`, {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suspicious-access'] })
      toast.success('Acesso desbloqueado com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao desbloquear acesso')
    },
  })
}
