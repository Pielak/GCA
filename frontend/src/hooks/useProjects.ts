import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

export interface ProjectRequest {
  id: string
  project_name: string
  project_slug: string
  description?: string
  status: 'pending' | 'approved' | 'rejected' | 'active'
  gp_id: string
  gp_email?: string
  created_at: string
  approved_at?: string
  rejected_reason?: string
}

export type DeliverableType = 'new_system' | 'mobile_app' | 'module' | 'enhancement' | 'integration' | 'modernization' | 'etl' | 'maintenance'

export interface CreateProjectInput {
  project_name: string
  project_slug: string
  description?: string
  deliverable_type: DeliverableType
}

export const usePendingProjects = () => {
  const toast = useToast()

  return useQuery({
    queryKey: ['projects', 'pending'],
    queryFn: async () => {
      try {
        const response = await apiClient.get<any>('/admin/projects/pending')

        // Handle nested format
        if (Array.isArray(response.data)) {
          return response.data
        } else if (response.data?.projects && Array.isArray(response.data.projects)) {
          return response.data.projects
        }
        return response.data
      } catch (error: unknown) {
        toast.error(getErrorMessage(error))
        throw error
      }
    },
    staleTime: 1000 * 60, // 1 minute
    refetchInterval: 1000 * 30, // Auto-refresh every 30 seconds
  })
}

export const useAllProjects = () => {
  const toast = useToast()

  return useQuery({
    queryKey: ['projects', 'all'],
    queryFn: async () => {
      try {
        const response = await apiClient.get<any>('/api/v1/projects')

        // Handle both array and nested formats
        if (Array.isArray(response.data)) {
          return response.data
        } else if (response.data?.projects && Array.isArray(response.data.projects)) {
          return response.data.projects
        }
        return response.data
      } catch (error: unknown) {
        toast.error(getErrorMessage(error))
        throw error
      }
    },
    staleTime: 1000 * 60, // 1 minute
  })
}

export const useCreateProject = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (input: CreateProjectInput) => {
      try {
        const response = await apiClient.post('/admin/projects', input)
        return response.data
      } catch (error: unknown) {
        throw error
      }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success(`Projeto "${data.project_name}" criado com sucesso`)
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })
}

export const useApproveProject = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (projectId: string) => {
      try {
        const response = await apiClient.post(`/admin/projects/${projectId}/approve`, {})
        return response.data
      } catch (error: unknown) {
        throw error
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Projeto aprovado com sucesso')
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })
}

export const useRejectProject = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async ({ projectId, reason }: { projectId: string; reason: string }) => {
      try {
        const response = await apiClient.post(`/admin/projects/${projectId}/reject`, {
          reason,
        })
        return response.data
      } catch (error: unknown) {
        throw error
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Projeto rejeitado')
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })
}
