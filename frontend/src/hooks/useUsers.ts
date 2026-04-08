import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

export interface User {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  is_active: boolean
  created_at: string
}

export interface UsersResponse {
  users: User[]
  total: number
  page: number
  page_size: number
}

export const useUsers = (page: number = 1, filter: 'all' | 'active' | 'inactive' = 'all') => {
  const toast = useToast()

  return useQuery({
    queryKey: ['users', page, filter],
    queryFn: async () => {
      try {
        const response = await apiClient.get<any>('/admin/users', {
          params: {
            page,
            page_size: 20,
            ...(filter !== 'all' && { is_active: filter === 'active' }),
          },
        })

        // Backend returns nested format: { users: [...], count: n }
        if (response.data?.users && Array.isArray(response.data.users)) {
          return {
            users: response.data.users,
            total: response.data.count,
            page,
            page_size: 20,
          } as UsersResponse
        }

        return response.data as UsersResponse
      } catch (error: any) {
        toast.error(error.message || 'Erro ao carregar usuários')
        throw error
      }
    },
    staleTime: 1000 * 60, // 1 minute
  })
}

export const useLockUser = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (userId: string) => {
      try {
        const response = await apiClient.post(`/admin/users/${userId}/lock`, {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success('Usuário bloqueado com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao bloquear usuário')
    },
  })
}

export const useUnlockUser = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (userId: string) => {
      try {
        const response = await apiClient.post(`/admin/users/${userId}/unlock`, {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success('Usuário desbloqueado com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao desbloquear usuário')
    },
  })
}

export const useResetPassword = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (userId: string) => {
      try {
        const response = await apiClient.post(`/admin/users/${userId}/reset-password`, {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success('Senha resetada com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao resetar senha')
    },
  })
}
