import { useMutation } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

export interface SMTPSettings {
  smtp_server: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  smtp_use_tls: boolean
}

export interface IAProviderSettings {
  provider: 'anthropic' | 'openai' | 'grok' | 'deepseek'
  api_key: string
  model: string
  enabled: boolean
}

export interface N8NSettings {
  n8n_server_url: string
  n8n_api_key: string
  enabled: boolean
}

export interface GCASettings {
  smtp?: SMTPSettings
  ia_providers?: IAProviderSettings[]
  n8n?: N8NSettings
}

export const useUpdateSMTPSettings = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async (settings: SMTPSettings) => {
      try {
        const response = await apiClient.post('/admin/settings/smtp', settings)
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: () => {
      toast.success('SMTP configurado com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao configurar SMTP')
    },
  })
}

export const useUpdateIAProviderSettings = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async (settings: IAProviderSettings) => {
      try {
        const response = await apiClient.post('/admin/settings/ia-provider', settings)
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: (data) => {
      if (data.status === 'success') {
        toast.success(`${data.provider} configurado com sucesso`)
      }
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao configurar IA Provider')
    },
  })
}

export const useUpdateN8NSettings = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async (settings: N8NSettings) => {
      try {
        const response = await apiClient.post('/admin/settings/n8n', settings)
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: () => {
      toast.success('N8N configurado com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao configurar N8N')
    },
  })
}

export const useTestSMTP = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async () => {
      try {
        const response = await apiClient.post('/admin/settings/smtp/test', {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: () => {
      toast.success('Email de teste enviado com sucesso!')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao enviar email de teste')
    },
  })
}

export const useTestIAProvider = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async (provider: string) => {
      try {
        const response = await apiClient.post(`/admin/settings/ia-provider/${provider}/test`, {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: (data, provider) => {
      toast.success(`${provider} testado com sucesso`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao testar IA Provider')
    },
  })
}

export const useTestN8N = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async () => {
      try {
        const response = await apiClient.post('/admin/settings/n8n/test', {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: () => {
      toast.success('N8N conectado com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao conectar N8N')
    },
  })
}
