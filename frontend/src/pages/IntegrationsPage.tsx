import { useState } from 'react'
import { Card, Input, Select, Button } from '@/components/common'
import { useTestWebhook } from '@/hooks/useWebhooks'

export const IntegrationsPage: React.FC = () => {
  const [integrationType, setIntegrationType] = useState('teams')
  const [webhookUrl, setWebhookUrl] = useState('')
  const testMutation = useTestWebhook()

  const handleTest = async () => {
    if (!webhookUrl.trim()) {
      return
    }
    await testMutation.mutateAsync({
      integrationType,
      webhookUrl,
    })
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-white mb-8">Integrações</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Webhook Test Form */}
        <Card title="Testar Webhook">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleTest()
            }}
            className="space-y-4"
          >
            <div>
              <label className="block text-gray-300 text-sm font-medium mb-2">
                Tipo de Integração
              </label>
              <select
                value={integrationType}
                onChange={(e) => setIntegrationType(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                <option value="teams">Microsoft Teams</option>
                <option value="slack">Slack</option>
                <option value="discord">Discord</option>
              </select>
            </div>

            <div>
              <label className="block text-gray-300 text-sm font-medium mb-2">
                URL do Webhook
              </label>
              <input
                type="url"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="https://hooks.slack.com/services/..."
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                Cole a URL completa do webhook
              </p>
            </div>

            <Button
              type="submit"
              variant="primary"
              disabled={!webhookUrl.trim()}
              loading={testMutation.isPending}
              className="w-full"
            >
              Testar Webhook
            </Button>

            {testMutation.isSuccess && (
              <div className="bg-green-900 border border-green-700 rounded-lg p-3">
                <p className="text-green-300 text-sm">
                  ✅ Webhook testado com sucesso!
                </p>
              </div>
            )}
          </form>
        </Card>

        {/* Integration Info */}
        <Card title="Integrações Disponíveis">
          <div className="space-y-4">
            <div>
              <h4 className="text-white font-medium mb-1">Microsoft Teams</h4>
              <p className="text-gray-400 text-sm">
                Envie notificações de alertas e eventos para um canal do Teams
              </p>
            </div>
            <div>
              <h4 className="text-white font-medium mb-1">Slack</h4>
              <p className="text-gray-400 text-sm">
                Integre com seu workspace do Slack para monitoramento em tempo real
              </p>
            </div>
            <div>
              <h4 className="text-white font-medium mb-1">Discord</h4>
              <p className="text-gray-400 text-sm">
                Configure webhooks do Discord para notificações customizadas
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
