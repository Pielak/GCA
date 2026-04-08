import { useState } from 'react'
import { Card, Input, Button, Badge } from '@/components/common'
import {
  useUpdateSMTPSettings,
  useUpdateIAProviderSettings,
  useTestSMTP,
  useTestIAProvider,
  useTestN8N,
} from '@/hooks/useSettings'
import { Mail, Zap, Grid, AlertCircle, CheckCircle } from 'lucide-react'

type SettingsTab = 'smtp' | 'ia' | 'n8n'

export const SettingsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('smtp')

  // SMTP Settings
  const [smtpServer, setSmtpServer] = useState('smtp.gmail.com')
  const [smtpPort, setSmtpPort] = useState(587)
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpUseTLS, setSmtpUseTLS] = useState(true)

  // IA Provider Settings
  const [selectedProvider, setSelectedProvider] = useState<'anthropic' | 'openai' | 'grok' | 'deepseek'>('anthropic')
  const [iaApiKey, setIaApiKey] = useState('')
  const [iaModel, setIaModel] = useState('')

  // N8N Settings
  const [n8nUrl, setN8nUrl] = useState('https://app.n8n.cloud')
  const [n8nApiKey, setN8nApiKey] = useState('')

  // Mutations
  const smtpMutation = useUpdateSMTPSettings()
  const iaMutation = useUpdateIAProviderSettings()
  const testSmtpMutation = useTestSMTP()
  const testIAMutation = useTestIAProvider()
  const testN8nMutation = useTestN8N()

  const handleSaveSMTP = async () => {
    await smtpMutation.mutateAsync({
      smtp_server: smtpServer,
      smtp_port: smtpPort,
      smtp_user: smtpUser,
      smtp_password: smtpPassword,
      smtp_use_tls: smtpUseTLS,
    })
  }

  const handleSaveIAProvider = async () => {
    await iaMutation.mutateAsync({
      provider: selectedProvider,
      api_key: iaApiKey,
      model: iaModel,
      enabled: true,
    })
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-white mb-8">Parametrização do GCA</h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('smtp')}
          className={`px-4 py-3 font-medium transition ${
            activeTab === 'smtp'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          <Mail className="inline mr-2" size={18} />
          SMTP
        </button>
        <button
          onClick={() => setActiveTab('ia')}
          className={`px-4 py-3 font-medium transition ${
            activeTab === 'ia'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          <Zap className="inline mr-2" size={18} />
          IA Providers
        </button>
        <button
          onClick={() => setActiveTab('n8n')}
          className={`px-4 py-3 font-medium transition ${
            activeTab === 'n8n'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          <Grid className="inline mr-2" size={18} />
          N8N
        </button>
      </div>

      {/* SMTP Configuration */}
      {activeTab === 'smtp' && (
        <div className="space-y-6">
          <Card title="Configuração SMTP">
            <div className="bg-blue-900 border border-blue-700 rounded-lg p-4 mb-6">
              <p className="text-blue-300 text-sm flex items-start gap-2">
                <AlertCircle size={18} className="flex-shrink-0 mt-0.5" />
                SMTP é necessário para enviar emails de credenciais aos GPs e para notificações do sistema.
              </p>
            </div>

            <div className="space-y-4">
              <Input
                label="Servidor SMTP"
                value={smtpServer}
                onChange={(e) => setSmtpServer(e.target.value)}
                placeholder="smtp.gmail.com"
              />

              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Porta SMTP"
                  type="number"
                  value={smtpPort.toString()}
                  onChange={(e) => setSmtpPort(Number(e.target.value))}
                  placeholder="587"
                />
                <div>
                  <label className="block text-gray-300 text-sm font-medium mb-2">Segurança</label>
                  <select
                    value={smtpUseTLS ? 'tls' : 'ssl'}
                    onChange={(e) => setSmtpUseTLS(e.target.value === 'tls')}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="tls">TLS (587)</option>
                    <option value="ssl">SSL (465)</option>
                  </select>
                </div>
              </div>

              <Input
                label="Usuário SMTP"
                value={smtpUser}
                onChange={(e) => setSmtpUser(e.target.value)}
                placeholder="seu-email@gmail.com"
              />

              <Input
                label="Senha/App Password"
                type="password"
                value={smtpPassword}
                onChange={(e) => setSmtpPassword(e.target.value)}
                placeholder="••••••••••••••••"
              />

              <div className="flex gap-2 pt-4">
                <Button
                  variant="primary"
                  onClick={handleSaveSMTP}
                  loading={smtpMutation.isPending}
                >
                  Salvar Configuração
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => testSmtpMutation.mutate()}
                  loading={testSmtpMutation.isPending}
                >
                  Enviar Email de Teste
                </Button>
              </div>
            </div>
          </Card>

          <Card title="Instruções para Gmail">
            <div className="space-y-3 text-sm text-gray-300">
              <ol className="list-decimal list-inside space-y-2">
                <li>Acesse <a href="https://myaccount.google.com" target="_blank" rel="noopener noreferrer" className="text-blue-400">myaccount.google.com</a></li>
                <li>Vá em Segurança e ative Autenticação de 2 Fatores</li>
                <li>Em "Senhas de app", selecione Mail e dispositivo</li>
                <li>Google gera uma senha de 16 caracteres</li>
                <li>Cole a senha acima em "Senha/App Password"</li>
              </ol>
            </div>
          </Card>
        </div>
      )}

      {/* IA Providers Configuration */}
      {activeTab === 'ia' && (
        <div className="space-y-6">
          <Card title="Provedores de IA">
            <div className="bg-blue-900 border border-blue-700 rounded-lg p-4 mb-6">
              <p className="text-blue-300 text-sm flex items-start gap-2">
                <AlertCircle size={18} className="flex-shrink-0 mt-0.5" />
                Você pode configurar múltiplos provedores (Claude, GPT-4, Grok, DeepSeek) para geração de código.
              </p>
            </div>

            {/* Provider Selection */}
            <div className="mb-6">
              <label className="block text-gray-300 text-sm font-medium mb-3">Selecione um provedor</label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {['anthropic', 'openai', 'grok', 'deepseek'].map((provider) => (
                  <button
                    key={provider}
                    onClick={() => setSelectedProvider(provider as any)}
                    className={`p-3 rounded-lg border-2 transition text-sm font-medium ${
                      selectedProvider === provider
                        ? 'border-blue-500 bg-blue-900 text-white'
                        : 'border-gray-600 bg-gray-700 text-gray-300 hover:border-gray-500'
                    }`}
                  >
                    {provider === 'anthropic' && 'Claude'}
                    {provider === 'openai' && 'GPT-4'}
                    {provider === 'grok' && 'Grok'}
                    {provider === 'deepseek' && 'DeepSeek'}
                  </button>
                ))}
              </div>
            </div>

            {/* Provider Details */}
            <div className="space-y-4">
              <div className="bg-gray-700 rounded-lg p-4">
                {selectedProvider === 'anthropic' && (
                  <div className="space-y-2 text-sm">
                    <p className="text-gray-300"><span className="font-medium">Preço:</span> $0.003 entrada / $0.015 saída</p>
                    <p className="text-gray-400">Console: console.anthropic.com</p>
                  </div>
                )}
                {selectedProvider === 'openai' && (
                  <div className="space-y-2 text-sm">
                    <p className="text-gray-300"><span className="font-medium">Preço:</span> $0.005 entrada / $0.015 saída</p>
                    <p className="text-gray-400">Console: platform.openai.com</p>
                  </div>
                )}
                {selectedProvider === 'grok' && (
                  <div className="space-y-2 text-sm">
                    <p className="text-gray-300"><span className="font-medium">Preço:</span> $0.002 entrada / $0.010 saída</p>
                    <p className="text-gray-400">Console: console.x.ai</p>
                  </div>
                )}
                {selectedProvider === 'deepseek' && (
                  <div className="space-y-2 text-sm">
                    <p className="text-gray-300"><span className="font-medium">Preço:</span> $0.0005 entrada / $0.002 saída (MAIS BARATO)</p>
                    <p className="text-gray-400">Console: platform.deepseek.com</p>
                  </div>
                )}
              </div>

              <Input
                label="API Key"
                type="password"
                value={iaApiKey}
                onChange={(e) => setIaApiKey(e.target.value)}
                placeholder="Sua API Key aqui"
              />

              <Input
                label="Modelo"
                value={iaModel}
                onChange={(e) => setIaModel(e.target.value)}
                placeholder={
                  selectedProvider === 'anthropic' ? 'claude-opus-4-1' :
                  selectedProvider === 'openai' ? 'gpt-4-turbo-preview' :
                  selectedProvider === 'grok' ? 'grok-1' :
                  'deepseek-chat'
                }
              />

              <div className="flex gap-2 pt-4">
                <Button
                  variant="primary"
                  onClick={handleSaveIAProvider}
                  loading={iaMutation.isPending}
                >
                  Salvar {selectedProvider}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => testIAMutation.mutate(selectedProvider)}
                  loading={testIAMutation.isPending}
                >
                  Testar Conexão
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* N8N Configuration */}
      {activeTab === 'n8n' && (
        <Card title="Configuração N8N">
          <div className="bg-blue-900 border border-blue-700 rounded-lg p-4 mb-6">
            <p className="text-blue-300 text-sm flex items-start gap-2">
              <AlertCircle size={18} className="flex-shrink-0 mt-0.5" />
              N8N executa web scraping de tecnologias para gerar recomendações de stack automáticas baseadas na linguagem escolhida.
            </p>
          </div>

          <div className="space-y-4">
            <Input
              label="URL do Servidor N8N"
              value={n8nUrl}
              onChange={(e) => setN8nUrl(e.target.value)}
              placeholder="https://app.n8n.cloud ou http://seu-servidor-n8n:5678"
            />

            <Input
              label="API Key N8N"
              type="password"
              value={n8nApiKey}
              onChange={(e) => setN8nApiKey(e.target.value)}
              placeholder="n8n_xxxxxxxxxxxxx"
            />

            <div className="flex gap-2 pt-4">
              <Button
                variant="primary"
                onClick={() => {/* TODO: Implement save */}}
                disabled
              >
                Salvar Configuração
              </Button>
              <Button
                variant="secondary"
                onClick={() => testN8nMutation.mutate()}
                loading={testN8nMutation.isPending}
              >
                Testar Conexão
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Status Summary */}
      <Card title="Status de Configuração" className="mt-8">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-gray-300">SMTP</span>
            <Badge variant={smtpPassword ? 'success' : 'warning'}>
              {smtpPassword ? 'Configurado' : 'Pendente'}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-300">IA Providers</span>
            <Badge variant={iaApiKey ? 'success' : 'warning'}>
              {iaApiKey ? 'Configurado' : 'Pendente'}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-300">N8N</span>
            <Badge variant={n8nApiKey ? 'success' : 'warning'}>
              {n8nApiKey ? 'Configurado' : 'Pendente'}
            </Badge>
          </div>
        </div>
      </Card>
    </div>
  )
}
