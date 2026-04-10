import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Code2, User, Brain, Server, FolderPlus, ChevronRight, ChevronLeft, Check, Loader2, Eye, EyeOff } from 'lucide-react'
import { HelpTooltip } from '@/components/ui/HelpTooltip'

import { getApiBaseUrl } from '@/lib/api'

const API = getApiBaseUrl()

interface StepProps {
  data: FormData
  onChange: (field: string, value: string | boolean | number) => void
  showPasswords: Record<string, boolean>
  togglePassword: (field: string) => void
}

interface FormData {
  admin_name: string
  admin_email: string
  admin_password: string
  admin_password_confirm: string
  llm_provider: string
  llm_api_key: string
  llm_model: string
  n8n_url: string
  n8n_token: string
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  create_test_project: boolean
  test_project_name: string
}

const INITIAL: FormData = {
  admin_name: '',
  admin_email: '',
  admin_password: '',
  admin_password_confirm: '',
  llm_provider: 'anthropic',
  llm_api_key: '',
  llm_model: 'claude-sonnet-4-6',
  n8n_url: '',
  n8n_token: '',
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  create_test_project: false,
  test_project_name: '',
}

const STEPS = ['Administrador', 'Provedor LLM', 'Infraestrutura', 'Projeto de Teste']

function StepAdmin({ data, onChange, showPasswords, togglePassword }: StepProps) {
  return (
    <div className="space-y-5">
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          Nome completo
          <HelpTooltip text="Nome do primeiro administrador desta instalação do GCA. Será exibido no audit log, notificações e relatórios. Use o nome real da pessoa responsável — não um nome genérico como 'admin'." />
        </label>
        <input type="text" value={data.admin_name} onChange={e => onChange('admin_name', e.target.value)}
          className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
          placeholder="Ex: João da Silva" />
      </div>
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          E-mail
          <HelpTooltip text="E-mail de login do administrador. Deve ser um endereço corporativo válido e acessível — será usado para recuperação de senha e notificações críticas do sistema. Não pode ser alterado sem acesso ao banco de dados." />
        </label>
        <input type="email" value={data.admin_email} onChange={e => onChange('admin_email', e.target.value)}
          className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
          placeholder="admin@empresa.com" />
      </div>
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          Senha
          <HelpTooltip text="Mínimo 10 caracteres com pelo menos 1 maiúscula, 1 número e 1 caractere especial. Esta é a senha de acesso à conta de administrador global do GCA — guarde em um gerenciador de senhas corporativo imediatamente após definir." />
        </label>
        <div className="relative">
          <input type={showPasswords.admin_password ? 'text' : 'password'} value={data.admin_password}
            onChange={e => onChange('admin_password', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500 pr-10"
            placeholder="Mínimo 10 caracteres" />
          <button type="button" onClick={() => togglePassword('admin_password')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-violet-400">
            {showPasswords.admin_password ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          Confirmar senha
          <HelpTooltip text="Deve ser idêntica ao campo anterior. Se as senhas não coincidirem, o wizard não avança." />
        </label>
        <div className="relative">
          <input type={showPasswords.admin_password_confirm ? 'text' : 'password'} value={data.admin_password_confirm}
            onChange={e => onChange('admin_password_confirm', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500 pr-10"
            placeholder="Repita a senha" />
          <button type="button" onClick={() => togglePassword('admin_password_confirm')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-violet-400">
            {showPasswords.admin_password_confirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {data.admin_password_confirm && data.admin_password !== data.admin_password_confirm && (
          <p className="text-red-400 text-xs mt-1">As senhas não coincidem</p>
        )}
      </div>
    </div>
  )
}

function StepLLM({ data, onChange, showPasswords, togglePassword }: StepProps) {
  return (
    <div className="space-y-5">
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          Provedor LLM
          <HelpTooltip text="Motor de IA que alimenta o Arguidor (análise de documentos), o Gatekeeper (avaliação de código pelos 7 Pilares) e o CodeGen (geração de módulos). A escolha do provedor afeta custo, qualidade e velocidade. Recomendado: Anthropic (Claude) para maior acurácia na análise de requisitos." />
        </label>
        <select value={data.llm_provider} onChange={e => onChange('llm_provider', e.target.value)}
          className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500">
          <option value="anthropic">Anthropic (Claude)</option>
          <option value="openai">OpenAI (GPT)</option>
          <option value="deepseek">DeepSeek</option>
          <option value="gemini">Google (Gemini)</option>
        </select>
      </div>
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          Chave de API
          <HelpTooltip text="API Key do provedor escolhido. Para Anthropic: obtenha em console.anthropic.com → 'API Keys'. Para OpenAI: platform.openai.com → 'API keys'. A chave é armazenada criptografada no banco (pgp_sym_encrypt) e nunca trafega em plain text nas respostas da API." />
        </label>
        <div className="relative">
          <input type={showPasswords.llm_api_key ? 'text' : 'password'} value={data.llm_api_key}
            onChange={e => onChange('llm_api_key', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500 pr-10"
            placeholder="sk-..." />
          <button type="button" onClick={() => togglePassword('llm_api_key')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-violet-400">
            {showPasswords.llm_api_key ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
          Modelo padrão
          <HelpTooltip text="Modelo específico a usar nas chamadas. Exemplos: 'claude-sonnet-4-6' (Anthropic), 'gpt-4o' (OpenAI), 'deepseek-chat' (DeepSeek). O modelo define custo por token e qualidade das análises. Para projetos críticos, use sempre o modelo mais recente disponível no seu plano." />
        </label>
        <input type="text" value={data.llm_model} onChange={e => onChange('llm_model', e.target.value)}
          className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
          placeholder="claude-sonnet-4-6" />
      </div>
    </div>
  )
}

function StepInfra({ data, onChange, showPasswords, togglePassword }: StepProps) {
  return (
    <div className="space-y-5">
      <p className="text-slate-400 text-sm">Todos os campos são opcionais. Você pode configurar depois em Configurações.</p>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            URL do n8n
            <HelpTooltip text="Endereço do servidor n8n para automações de workflow (ex: https://n8n.empresa.com). O n8n é usado para disparo automático de ingestões, notificações e pipelines de CI. Pode ser deixado em branco e configurado posteriormente em Configurações." />
          </label>
          <input type="url" value={data.n8n_url} onChange={e => onChange('n8n_url', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
            placeholder="https://n8n.empresa.com" />
        </div>
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            Token n8n
            <HelpTooltip text="API Key do n8n para autenticação nas chamadas de webhook. Obtida em n8n → Settings → API. Armazenada criptografada. Sem token, o GCA não consegue disparar workflows automaticamente." />
          </label>
          <div className="relative">
            <input type={showPasswords.n8n_token ? 'text' : 'password'} value={data.n8n_token}
              onChange={e => onChange('n8n_token', e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500 pr-10" />
            <button type="button" onClick={() => togglePassword('n8n_token')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-violet-400">
              {showPasswords.n8n_token ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            SMTP Host
            <HelpTooltip text="Servidor de e-mail para envio de notificações, convites e alertas. Exemplos: 'smtp.gmail.com' (Google), 'smtp.office365.com' (Microsoft). Sem SMTP configurado, nenhum e-mail será enviado pelo GCA — os 11 templates de e-mail ficarão inativos." />
          </label>
          <input type="text" value={data.smtp_host} onChange={e => onChange('smtp_host', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
            placeholder="smtp.gmail.com" />
        </div>
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            SMTP Porta
            <HelpTooltip text="Porta do servidor SMTP. Use 587 para TLS (recomendado) ou 465 para SSL. A porta 25 está bloqueada pela maioria dos provedores de nuvem." />
          </label>
          <input type="number" value={data.smtp_port} onChange={e => onChange('smtp_port', parseInt(e.target.value) || 587)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            Usuário SMTP
            <HelpTooltip text="E-mail ou usuário de autenticação no servidor SMTP. Geralmente é o próprio endereço de e-mail remetente (ex: noreply@suaempresa.com)." />
          </label>
          <input type="text" value={data.smtp_user} onChange={e => onChange('smtp_user', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
            placeholder="noreply@empresa.com" />
        </div>
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            Senha SMTP
            <HelpTooltip text="Senha de autenticação no servidor SMTP. Para Gmail: use uma 'Senha de App' (não a senha da conta Google). Armazenada criptografada." />
          </label>
          <div className="relative">
            <input type={showPasswords.smtp_password ? 'text' : 'password'} value={data.smtp_password}
              onChange={e => onChange('smtp_password', e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500 pr-10" />
            <button type="button" onClick={() => togglePassword('smtp_password')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-violet-400">
              {showPasswords.smtp_password ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function StepTestProject({ data, onChange }: StepProps) {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <input type="checkbox" id="create_test" checked={data.create_test_project}
          onChange={e => onChange('create_test_project', e.target.checked)}
          className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-violet-600 focus:ring-violet-500" />
        <label htmlFor="create_test" className="flex items-center gap-1.5 text-sm font-medium text-slate-300">
          Criar projeto de demonstração
          <HelpTooltip text="Cria um projeto de exemplo pré-configurado para validar o fluxo completo do GCA (Ingestão → Arguidor → Gatekeeper → CodeGen → LiveDocs) sem necessidade de documentação real. Recomendado para a primeira configuração. O projeto pode ser excluído depois pelo Admin." />
        </label>
      </div>
      {data.create_test_project && (
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300 mb-1.5">
            Nome do projeto
            <HelpTooltip text="Nome do projeto de demonstração. Sugestão: 'GCA Demo — [nome da empresa]'. Aparecerá na lista de projetos do dashboard." />
          </label>
          <input type="text" value={data.test_project_name} onChange={e => onChange('test_project_name', e.target.value)}
            className="w-full px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
            placeholder="GCA Demo — Minha Empresa" />
        </div>
      )}
    </div>
  )
}

export function SetupWizardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [data, setData] = useState<FormData>(INITIAL)
  const [loading, setLoading] = useState(false)
  const [checkingSetup, setCheckingSetup] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})

  useEffect(() => {
    fetch(`${API}/api/v1/setup/status`)
      .then(r => r.json())
      .then(d => {
        if (!d.needs_setup) navigate('/login', { replace: true })
        else setCheckingSetup(false)
      })
      .catch(() => setCheckingSetup(false))
  }, [navigate])

  const onChange = (field: string, value: string | boolean | number) => {
    setData(prev => ({ ...prev, [field]: value }))
  }

  const togglePassword = (field: string) => {
    setShowPasswords(prev => ({ ...prev, [field]: !prev[field] }))
  }

  const isStepValid = (s: number): boolean => {
    switch (s) {
      case 0:
        return !!(data.admin_name && data.admin_email && data.admin_password
          && data.admin_password.length >= 10
          && data.admin_password === data.admin_password_confirm)
      case 1:
        return !!(data.llm_provider && data.llm_api_key && data.llm_model)
      case 2:
        return true // tudo opcional
      case 3:
        return !data.create_test_project || !!data.test_project_name
      default:
        return false
    }
  }

  const handleComplete = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/v1/setup/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          admin_name: data.admin_name,
          admin_email: data.admin_email,
          admin_password: data.admin_password,
          llm_provider: data.llm_provider,
          llm_api_key: data.llm_api_key,
          llm_model: data.llm_model,
          n8n_url: data.n8n_url || null,
          n8n_token: data.n8n_token || null,
          smtp_host: data.smtp_host || null,
          smtp_port: data.smtp_port,
          smtp_user: data.smtp_user || null,
          smtp_password: data.smtp_password || null,
          create_test_project: data.create_test_project,
          test_project_name: data.test_project_name || null,
        }),
      })
      if (res.ok) {
        navigate('/login', { replace: true })
      } else {
        const err = await res.json()
        setError(err.detail || 'Erro ao configurar')
      }
    } catch {
      setError('Erro de conexão com o servidor')
    } finally {
      setLoading(false)
    }
  }

  if (checkingSetup) {
    return (
      <div className="min-h-screen bg-[#0D0D18] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
      </div>
    )
  }

  const stepProps: StepProps = { data, onChange, showPasswords, togglePassword }

  return (
    <div className="min-h-screen bg-[#0D0D18] flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-3">
            <Code2 className="w-8 h-8 text-violet-500" />
            <h1 className="text-2xl font-bold text-slate-100">GCA</h1>
          </div>
          <p className="text-slate-400 text-sm">Configuração Inicial</p>
        </div>

        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors
                ${i < step ? 'bg-emerald-600 text-white' : i === step ? 'bg-violet-600 text-white' : 'bg-slate-700 text-slate-400'}`}>
                {i < step ? <Check className="w-4 h-4" /> : i + 1}
              </div>
              <span className={`text-xs hidden sm:block ${i === step ? 'text-violet-400' : 'text-slate-500'}`}>{label}</span>
              {i < STEPS.length - 1 && <div className={`w-8 h-0.5 ${i < step ? 'bg-emerald-600' : 'bg-slate-700'}`} />}
            </div>
          ))}
        </div>

        {/* Card */}
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-slate-100 mb-5 flex items-center gap-2">
            {step === 0 && <><User className="w-5 h-5 text-violet-400" /> Administrador</>}
            {step === 1 && <><Brain className="w-5 h-5 text-violet-400" /> Provedor LLM</>}
            {step === 2 && <><Server className="w-5 h-5 text-violet-400" /> Infraestrutura</>}
            {step === 3 && <><FolderPlus className="w-5 h-5 text-violet-400" /> Projeto de Teste</>}
          </h2>

          {step === 0 && <StepAdmin {...stepProps} />}
          {step === 1 && <StepLLM {...stepProps} />}
          {step === 2 && <StepInfra {...stepProps} />}
          {step === 3 && <StepTestProject {...stepProps} />}

          {error && (
            <div className="mt-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>
          )}

          {/* Navigation */}
          <div className="flex justify-between mt-6 pt-4 border-t border-slate-700">
            <button onClick={() => setStep(s => s - 1)} disabled={step === 0}
              className="flex items-center gap-1.5 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
              <ChevronLeft className="w-4 h-4" /> Voltar
            </button>
            {step < STEPS.length - 1 ? (
              <button onClick={() => setStep(s => s + 1)} disabled={!isStepValid(step)}
                className="flex items-center gap-1.5 px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors">
                Próximo <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button onClick={handleComplete} disabled={loading || !isStepValid(step)}
                className="flex items-center gap-1.5 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                Concluir e Entrar
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
