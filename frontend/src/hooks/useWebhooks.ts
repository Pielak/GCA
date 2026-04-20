import { useMutation } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

export interface WebhookTestResponse {
  status: string
  message: string
  status_code?: number
  response_time?: number
}

export const useTestWebhook = () => {
  const toast = useToast()

  return useMutation({
    mutationFn: async ({
      integrationType,
      webhookUrl,
    }: {
      integrationType: string
      webhookUrl: string
    }) => {
      try {
        const response = await apiClient.post<WebhookTestResponse>(
          '/admin/integrations/webhook-test',
          {
            integration_type: integrationType,
            webhook_url: webhookUrl,
          }
        )
        return response.data
      } catch (error: unknown) {
        throw error
      }
    },
    onSuccess: (data) => {
      if (data.status === 'success' || data.status_code === 200) {
        toast.success(`Webhook testado com sucesso! (${data.response_time}ms)`)
      } else {
        toast.warning(`Webhook retornou: ${data.message}`)
      }
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })
}
