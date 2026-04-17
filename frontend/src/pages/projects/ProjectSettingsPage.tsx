import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Settings, Cpu, Mail, Loader2, Check, Eye, EyeOff, Zap, Wifi, WifiOff, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useProjectPermissions } from '@/hooks/useProjectPermissions'
import { useAuthStore } from '@/stores/authStore'

// Resultado do teste de conexão — `ok=null` significa "provedor válido mas
// sem teste real implementado" (ex: gemini/ollama). A UI distingue isso
// do ok=false (chave rejeitada) para não confundir o GP.
type TestResult = {
  ok: boolean | null
  message: string
  provider?: string
  model?: string | null
  latencyMs?: number
} | null

export function ProjectSettingsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { can } = useProjectPermissions()
  const canEdit = can('project:edit')
  const currentUserEmail = useAuthStore((s) => s.user?.email || '')
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'llm' | 'smtp' | 'n8n'>('llm')

  // Settings data
  const [settings, setSettings] = useState<any>({})

  // LLM form
  const [llmProvider, setLlmProvider] = useState('anthropic')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [showLlmKey, setShowLlmKey] = useState(false)

  // SMTP form
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('587')
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPass, setSmtpPass] = useState('')
  const [smtpFrom, setSmtpFrom] = useState('')

  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [testingLlm, setTestingLlm] = useState(false)
  const [llmTestResult, setLlmTestResult] = useState<TestResult>(null)
  const [testingSmtp, setTestingSmtp] = useState(false)
  const [smtpTestResult, setSmtpTestResult] = useState<TestResult>(null)

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const loadSettings = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/settings`)
      const data = res.data
      setSettings(data)

      // Preencher LLM
      if (data.llm) {
        setLlmProvider(data.llm.provider || 'anthropic')
        setLlmModel(data.llm.model || '')
      }
      // Preencher SMTP
      if (data.smtp) {
        setSmtpHost(data.smtp.host || '')
        setSmtpPort(String(data.smtp.port || 587))
        setSmtpUser(data.smtp.user || '')
        setSmtpFrom(data.smtp.from_email || '')
      }
    } catch { /* sem settings */ }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadSettings() }, [loadSettings])

  const saveLlm = async () => {
    if (!llmApiKey.trim() && !settings.llm?.api_key_configured) {
      showToast('Informe a API Key do provedor de IA', 'error')
      return
    }
    setSaving(true)
    try {
      await apiClient.post(`/projects/${projectId}/settings/llm`, {
        provider: llmProvider,
        api_key: llmApiKey.trim() || undefined,
        model: llmModel.trim() || undefined,
      })
      showToast('Provedor de IA configurado com sucesso', 'success')
      setLlmApiKey('')
      await loadSettings()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar', 'error')
    }
    setSaving(false)
  }

  const saveSmtp = async () => {
    setSaving(true)
    try {
      await apiClient.post(`/projects/${projectId}/settings/smtp`, {
        host: smtpHost.trim(),
        port: parseInt(smtpPort) || 587,
        user: smtpUser.trim(),
        password: smtpPass.trim() || undefined,
        from_email: smtpFrom.trim(),
      })
      showToast('SMTP configurado com sucesso', 'success')
      setSmtpPass('')
      await loadSettings()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar', 'error')
    }
    setSaving(false)
  }

  const testLlm = async () => {
    if (!projectId) return
    setTestingLlm(true)
    setLlmTestResult(null)
    try {
      const res: any = await apiClient.post(`/projects/${projectId}/settings/llm/validate`, {})
      const data = res?.data || {}
      if (data.valid === true) {
        setLlmTestResult({
          ok: true,
          message: `Chave aceita pelo ${data.provider}. Modelo: ${data.model || '—'} · ${data.latency_ms ?? '?'}ms`,
          provider: data.provider,
          model: data.model,
          latencyMs: data.latency_ms,
        })
      } else if (data.valid === false) {
        setLlmTestResult({
          ok: false,
          message: data.detail || `Erro ao validar (${data.error || 'desconhecido'})`,
          provider: data.provider,
        })
      } else {
        // valid === null (provider_supported=false)
        setLlmTestResult({
          ok: null,
          message: data.detail || 'Teste automático não implementado para este provedor.',
          provider: data.provider,
        })
      }
    } catch (err: any) {
      setLlmTestResult({
        ok: false,
        message: err?.response?.data?.detail || err?.message || 'Falha ao contatar o servidor',
      })
    }
    setTestingLlm(false)
  }

  const testSmtp = async () => {
    if (!projectId) return
    if (!currentUserEmail) {
      setSmtpTestResult({ ok: false, message: 'Não foi possível identificar seu email para receber o teste.' })
      return
    }
    setTestingSmtp(true)
    setSmtpTestResult(null)
    try {
      await apiClient.post(`/projects/${projectId}/settings/smtp/test`, {
        to_email: currentUserEmail,
      })
      setSmtpTestResult({
        ok: true,
        message: `Email de teste enviado para ${currentUserEmail}. Verifique sua caixa nos próximos minutos.`,
      })
    } catch (err: any) {
      setSmtpTestResult({
        ok: false,
        message: err?.response?.data?.detail || err?.message || 'Falha ao enviar email de teste',
      })
    }
    setTestingSmtp(false)
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold text-slate-100">Configurações do Projeto</h2>
        <p className="text-slate-500 text-sm mt-0.5">
          Configure o provedor de IA, SMTP e integrações para este projeto.
          Estas configurações são compartimentalizadas — não afetam outros projetos.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-800">
        <button onClick={() => setActiveTab('llm')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${activeTab === 'llm' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <Cpu className="w-3.5 h-3.5" /> Provedor de IA
        </button>
        <button onClick={() => setActiveTab('smtp')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${activeTab === 'smtp' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <Mail className="w-3.5 h-3.5" /> SMTP
        </button>
      </div>

      {/* Tab: Provedor de IA */}
      {activeTab === 'llm' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <h3 className="text-slate-200 text-sm font-semibold">Provedor de IA do Projeto</h3>
          <p className="text-slate-500 text-xs">
            Esta chave é usada pelo Arguidor, Geração de Código, QA e outros módulos do projeto.
            É diferente da chave do Admin (usada apenas para avaliação do questionário externo).
          </p>

          {settings.llm?.api_key_configured && (
            <div className="flex items-center gap-2 px-3 py-2 bg-emerald-900/20 border border-emerald-800/40 rounded-lg">
              <Check className="w-4 h-4 text-emerald-400" />
              <span className="text-emerald-300 text-xs">Chave configurada ({settings.llm.provider}) — {settings.llm.masked_key}</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-slate-400 text-xs block mb-1">Provedor</label>
              <select value={llmProvider} onChange={e => setLlmProvider(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600">
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI (GPT)</option>
                <option value="deepseek">DeepSeek</option>
                <option value="grok">xAI (Grok)</option>
                <option value="gemini">Google (Gemini)</option>
              </select>
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Modelo (opcional)</label>
              <input value={llmModel} onChange={e => setLlmModel(e.target.value)}
                placeholder="Ex: claude-sonnet-4-6, gpt-4o"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs block mb-1">API Key {settings.llm?.api_key_configured ? '(deixe vazio para manter a atual)' : ''}</label>
            <div className="relative">
              <input type={showLlmKey ? 'text' : 'password'} value={llmApiKey} onChange={e => setLlmApiKey(e.target.value)}
                placeholder={settings.llm?.api_key_configured ? 'Manter chave atual...' : 'sk-...'}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
              <button type="button" onClick={() => setShowLlmKey(!showLlmKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                {showLlmKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-slate-600 text-xs mt-1">Armazenada criptografada no vault do projeto.</p>
          </div>

          {llmTestResult && (
            <div className={`flex items-start gap-2 px-3 py-2 rounded-lg text-xs border ${
              llmTestResult.ok === true
                ? 'bg-emerald-900/20 border-emerald-800/40 text-emerald-300'
                : llmTestResult.ok === false
                  ? 'bg-red-900/20 border-red-800/40 text-red-300'
                  : 'bg-amber-900/20 border-amber-800/40 text-amber-300'
            }`}>
              {llmTestResult.ok === true && <Wifi className="w-4 h-4 flex-shrink-0 mt-0.5" />}
              {llmTestResult.ok === false && <WifiOff className="w-4 h-4 flex-shrink-0 mt-0.5" />}
              {llmTestResult.ok === null && <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
              <span className="leading-snug">{llmTestResult.message}</span>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button onClick={testLlm} disabled={testingLlm || !settings.llm?.api_key_configured || !canEdit}
              title={!settings.llm?.api_key_configured ? 'Salve uma chave antes de testar' : 'Testar conexão com o provedor'}
              className="flex items-center gap-1.5 px-4 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 text-sm rounded-lg border border-slate-700 transition-colors">
              {testingLlm ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wifi className="w-4 h-4" />}
              Testar conexão
            </button>
            <button onClick={saveLlm} disabled={saving || !canEdit}
              className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Salvar Provedor de IA
            </button>
          </div>
        </div>
      )}

      {/* Tab: SMTP */}
      {activeTab === 'smtp' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <h3 className="text-slate-200 text-sm font-semibold">Configuração SMTP do Projeto</h3>
          <p className="text-slate-500 text-xs">Usado para notificações por email dentro do projeto (convites, alertas).</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-slate-400 text-xs block mb-1">Servidor SMTP</label>
              <input value={smtpHost} onChange={e => setSmtpHost(e.target.value)} placeholder="smtp.gmail.com"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Porta</label>
              <input value={smtpPort} onChange={e => setSmtpPort(e.target.value)} placeholder="587"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Usuário</label>
              <input value={smtpUser} onChange={e => setSmtpUser(e.target.value)} placeholder="email@empresa.com"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Senha {settings.smtp?.password_configured ? '(manter)' : ''}</label>
              <input type="password" value={smtpPass} onChange={e => setSmtpPass(e.target.value)}
                placeholder={settings.smtp?.password_configured ? 'Manter senha atual...' : 'Senha do SMTP'}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs block mb-1">Email Remetente</label>
            <input value={smtpFrom} onChange={e => setSmtpFrom(e.target.value)} placeholder="noreply@empresa.com"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600" />
          </div>

          {smtpTestResult && (
            <div className={`flex items-start gap-2 px-3 py-2 rounded-lg text-xs border ${
              smtpTestResult.ok === true
                ? 'bg-emerald-900/20 border-emerald-800/40 text-emerald-300'
                : 'bg-red-900/20 border-red-800/40 text-red-300'
            }`}>
              {smtpTestResult.ok ? <Wifi className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <WifiOff className="w-4 h-4 flex-shrink-0 mt-0.5" />}
              <span className="leading-snug">{smtpTestResult.message}</span>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button onClick={testSmtp} disabled={testingSmtp || !settings.smtp?.password_configured || !canEdit}
              title={!settings.smtp?.password_configured ? 'Salve credenciais SMTP antes de testar' : `Enviar email de teste para ${currentUserEmail}`}
              className="flex items-center gap-1.5 px-4 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 text-sm rounded-lg border border-slate-700 transition-colors">
              {testingSmtp ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
              Enviar email de teste
            </button>
            <button onClick={saveSmtp} disabled={saving || !canEdit}
              className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Salvar SMTP
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
