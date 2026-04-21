import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Settings, Cpu, Mail, Loader2, Check, Eye, EyeOff, Zap, Wifi, WifiOff, AlertCircle, GitBranch, ClipboardList, Circle, CheckCircle2, AlertTriangle, Plus, Trash2, Star } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useProjectPermissions } from '@/hooks/useProjectPermissions'
import { useAuthStore } from '@/stores/authStore'
import { useSetupStatus } from '@/hooks/useSetupStatus'
import { RepositoryPage } from '@/pages/projects/RepositoryPage'
import { QuestionnairePage } from '@/pages/projects/QuestionnairePage'
import { getErrorMessage } from '@/lib/errors'

type TabKey = 'llm' | 'smtp' | 'repo' | 'questionario'
const VALID_TABS: TabKey[] = ['llm', 'smtp', 'repo', 'questionario']

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  openai: 'OpenAI (GPT)',
  deepseek: 'DeepSeek',
  grok: 'xAI (Grok)',
  gemini: 'Google (Gemini)',
  ollama: 'Ollama (local)',
}
function providerLabel(p: string): string {
  return PROVIDER_LABELS[p] || p
}

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
  const { data: setupStatus } = useSetupStatus(projectId)
  // Invalidação explícita do setup-status ao mudar config de LLM —
  // senão os badges ✓/○ das tabs e o hero ficam stale (staleTime 30s).
  const queryClient = useQueryClient()
  const invalidateSetup = () => {
    queryClient.invalidateQueries({ queryKey: ['project-setup-status', projectId] })
  }

  // A aba ativa vem de ?tab=... para suportar deep-links da SetupChecklist
  // (passos IA / Repo / Questionário) e dos redirects de /repository, /questionnaire.
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab: TabKey = useMemo(() => {
    const raw = searchParams.get('tab')
    return VALID_TABS.includes(raw as TabKey) ? (raw as TabKey) : 'llm'
  }, [searchParams])
  const setActiveTab = useCallback((t: TabKey) => {
    const next = new URLSearchParams(searchParams)
    if (t === 'llm') next.delete('tab')
    else next.set('tab', t)
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  // Settings data
  const [settings, setSettings] = useState<any>({})

  // LLM form (novo — modo "adicionar novo provider"). O card principal
  // lista os provedores já configurados; este form só é visível quando o
  // user clica em "+ Adicionar provedor".
  const [addingLlm, setAddingLlm] = useState(false)
  const [newLlmProvider, setNewLlmProvider] = useState('anthropic')
  const [newLlmApiKey, setNewLlmApiKey] = useState('')
  const [newLlmModel, setNewLlmModel] = useState('')
  const [newLlmBaseUrl, setNewLlmBaseUrl] = useState('')  // DT-023: só usado quando provider=ollama
  const [showLlmKey, setShowLlmKey] = useState(false)
  const isOllamaSelected = newLlmProvider === 'ollama'

  // Resultados de teste por provider (um dict — cada card tem o seu).
  const [llmTestResults, setLlmTestResults] = useState<Record<string, TestResult>>({})
  const [testingProvider, setTestingProvider] = useState<string | null>(null)
  const [removingProvider, setRemovingProvider] = useState<string | null>(null)
  const [settingDefault, setSettingDefault] = useState<string | null>(null)

  // SMTP form
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('587')
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPass, setSmtpPass] = useState('')
  const [smtpFrom, setSmtpFrom] = useState('')

  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
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
      // Preencher SMTP (LLM agora é multi — estado fica no settings.llm.providers)
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

  const addLlmProvider = async () => {
    // DT-023: validações específicas por provider — Ollama exige base_url,
    // demais exigem api_key. Erro local antes de bater no backend.
    if (isOllamaSelected) {
      const url = newLlmBaseUrl.trim()
      if (!url) {
        showToast('Informe a Base URL do daemon Ollama (ex: http://host.docker.internal:11434)', 'error')
        return
      }
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        showToast('Base URL deve começar com http:// ou https://', 'error')
        return
      }
    } else if (!newLlmApiKey.trim()) {
      showToast('Informe a API Key do provedor', 'error')
      return
    }
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {
        provider: newLlmProvider,
        model_preference: newLlmModel.trim() || undefined,
      }
      if (newLlmApiKey.trim()) {
        payload.api_key = newLlmApiKey.trim()
      }
      if (isOllamaSelected && newLlmBaseUrl.trim()) {
        payload.base_url = newLlmBaseUrl.trim()
      }
      await apiClient.post(`/projects/${projectId}/settings/llm`, payload)
      showToast(`Provedor ${newLlmProvider} adicionado`, 'success')
      setNewLlmApiKey('')
      setNewLlmModel('')
      setNewLlmBaseUrl('')
      setAddingLlm(false)
      await loadSettings()
      invalidateSetup()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao adicionar', 'error')
    }
    setSaving(false)
  }

  const testLlmProvider = async (provider: string) => {
    if (!projectId) return
    setTestingProvider(provider)
    try {
      const res = await apiClient.post<{ ok?: boolean; valid?: boolean; provider?: string; error?: string; latency_ms?: number; model?: string; detail?: string }>(
        `/projects/${projectId}/settings/llm/validate?provider=${encodeURIComponent(provider)}`,
        {},
      )
      const data = res?.data || {}
      let result: TestResult
      if (data.valid === true) {
        result = {
          ok: true,
          message: `Chave aceita. Modelo: ${data.model || '—'} · ${data.latency_ms ?? '?'}ms`,
          provider: data.provider,
          model: data.model,
          latencyMs: data.latency_ms,
        }
      } else if (data.valid === false) {
        result = {
          ok: false,
          message: data.detail || `Erro ao validar (${data.error || 'desconhecido'})`,
          provider: data.provider,
        }
      } else {
        result = {
          ok: null,
          message: data.detail || 'Teste automático não implementado.',
          provider: data.provider,
        }
      }
      setLlmTestResults(prev => ({ ...prev, [provider]: result }))
      await loadSettings() // re-pega last_validated_at/ok atualizados
    } catch (err: unknown) {
      setLlmTestResults(prev => ({
        ...prev,
        [provider]: {
          ok: false,
          message: getErrorMessage(err),
          provider,
        },
      }))
    }
    setTestingProvider(null)
  }

  const setDefaultLlmProvider = async (provider: string) => {
    if (!projectId) return
    setSettingDefault(provider)
    try {
      await apiClient.post(`/projects/${projectId}/settings/llm/providers/${provider}/default`, {})
      showToast(`${provider} definido como padrão do projeto`, 'success')
      await loadSettings()
      invalidateSetup()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao definir padrão', 'error')
    }
    setSettingDefault(null)
  }

  const removeLlmProvider = async (provider: string) => {
    if (!projectId) return
    if (!confirm(`Remover o provedor ${provider}? A chave será apagada do vault do projeto.`)) return
    setRemovingProvider(provider)
    try {
      await apiClient.delete(`/projects/${projectId}/settings/llm/providers/${provider}`)
      showToast(`Provedor ${provider} removido`, 'success')
      setLlmTestResults(prev => {
        const next = { ...prev }
        delete next[provider]
        return next
      })
      await loadSettings()
      invalidateSetup()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao remover', 'error')
    }
    setRemovingProvider(null)
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
      invalidateSetup()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao salvar', 'error')
    }
    setSaving(false)
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
    } catch (err: unknown) {
      setSmtpTestResult({
        ok: false,
        message: getErrorMessage(err),
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

      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-100">Configurações do Projeto</h2>
        {setupStatus?.ready_to_activate && setupStatus?.questionnaire_approved && (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Setup completo — pipeline liberado
          </span>
        )}
      </div>

      {/* HERO de setup — aparece em 2 cenários:
          (a) algum dos 3 passos obrigatórios pendente (ready_to_activate=false)
          (b) questionário submetido mas com bloqueadores (!approved)
          Ambos exigem ação do GP antes do pipeline operar plenamente. */}
      {setupStatus && (!setupStatus.ready_to_activate || !setupStatus.questionnaire_approved) && (() => {
        // O passo "questionário" só é dado como concluído quando ALÉM de
        // submetido, também está aprovado. Isso deixa o badge "done" coerente
        // com o hero — sem enganar o GP que ficou com bloqueadores em aberto.
        const questionnaireDone = setupStatus.questionnaire_submitted && setupStatus.questionnaire_approved
        const items = [
          { key: 'llm', done: setupStatus.llm_configured, label: 'Provedor de IA', icon: Cpu },
          { key: 'repo', done: setupStatus.repo_configured, label: 'Repositório Git', icon: GitBranch },
          { key: 'questionario', done: questionnaireDone, label: 'Questionário Técnico', icon: ClipboardList },
        ]
        const doneCount = items.filter(i => i.done).length
        const nextItem = items.find(i => !i.done)
        const progressPct = (doneCount / items.length) * 100
        return (
          <div className="relative overflow-hidden rounded-2xl border border-amber-500/40 bg-gradient-to-br from-amber-950/60 via-orange-950/40 to-amber-950/30 p-6 shadow-lg shadow-amber-900/20">
            {/* Glow de fundo */}
            <div className="absolute -top-20 -right-20 w-60 h-60 rounded-full bg-amber-500/10 blur-3xl pointer-events-none" />

            <div className="relative flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-amber-500/20 border border-amber-400/40 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-amber-300" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-3 flex-wrap">
                  <h3 className="text-amber-100 text-lg font-bold tracking-tight">
                    Projeto ainda não está operacional
                  </h3>
                  <span className="text-amber-300 text-sm font-semibold tabular-nums">
                    {doneCount}/{items.length} passos
                  </span>
                </div>

                <p className="text-amber-100/80 text-sm mt-1 leading-snug">
                  O pipeline do GCA (<span className="font-semibold text-amber-200">Ingestão, OCG, Gatekeeper, Arguidor, CodeGen, Backlog, Roadmap</span>) fica bloqueado até você completar os 3 passos obrigatórios abaixo. SMTP é opcional e não bloqueia.
                </p>

                {/* Barra de progresso */}
                <div className="mt-4 h-2 bg-amber-950/60 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-400 to-orange-400 rounded-full transition-all duration-500"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>

                {/* Pills por item + CTA */}
                <div className="mt-4 flex items-center gap-2 flex-wrap">
                  {items.map(i => {
                    const Icon = i.icon
                    return (
                      <button
                        key={i.key}
                        onClick={() => setActiveTab(i.key as TabKey)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                          i.done
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20'
                            : 'bg-amber-500/10 border-amber-400/40 text-amber-200 hover:bg-amber-500/20 hover:border-amber-400/60'
                        }`}
                      >
                        {i.done
                          ? <CheckCircle2 className="w-3.5 h-3.5" />
                          : <Circle className="w-3.5 h-3.5" />}
                        <Icon className="w-3 h-3" />
                        {i.label}
                      </button>
                    )
                  })}
                </div>

                {nextItem && (
                  <button
                    onClick={() => setActiveTab(nextItem.key as TabKey)}
                    className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-amber-950 text-sm font-semibold shadow-lg shadow-amber-500/30 transition-all hover:shadow-amber-400/40"
                  >
                    Próximo passo: {nextItem.label}
                    <span aria-hidden>→</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        )
      })()}

      {/* Tabs — parametrização do projeto consolidada aqui (contrato MVP 1). */}
      {/* Badges ✓/○ no label quando o item faz parte do setup obrigatório. */}
      <div className="flex gap-1 border-b border-slate-800 overflow-x-auto">
        <button onClick={() => setActiveTab('llm')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${activeTab === 'llm' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <Cpu className="w-3.5 h-3.5" /> Provedor de IA
          {setupStatus?.llm_configured
            ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            : <Circle className="w-3.5 h-3.5 text-amber-500" />}
        </button>
        <button onClick={() => setActiveTab('smtp')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${activeTab === 'smtp' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <Mail className="w-3.5 h-3.5" /> SMTP
          <span className="text-[10px] text-slate-500 uppercase tracking-wide">opcional</span>
        </button>
        <button onClick={() => setActiveTab('repo')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${activeTab === 'repo' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <GitBranch className="w-3.5 h-3.5" /> Repositório
          {setupStatus?.repo_configured
            ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            : <Circle className="w-3.5 h-3.5 text-amber-500" />}
        </button>
        <button onClick={() => setActiveTab('questionario')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${activeTab === 'questionario' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <ClipboardList className="w-3.5 h-3.5" /> Questionário
          {!setupStatus?.questionnaire_submitted
            ? <Circle className="w-3.5 h-3.5 text-amber-500" />
            : setupStatus?.questionnaire_approved
              ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              : <AlertCircle className="w-3.5 h-3.5 text-amber-400" aria-label="Submetido com pendências" />}
        </button>
      </div>

      {/* Tab: Provedor de IA — lista multi-provider + form "adicionar" */}
      {activeTab === 'llm' && (
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-1">
            <h3 className="text-slate-200 text-sm font-semibold">Provedores de IA do Projeto</h3>
            <p className="text-slate-500 text-xs">
              Você pode configurar múltiplos provedores e trocar o padrão quando quiser.
              O provedor marcado como <span className="text-violet-300 font-medium">Padrão</span> é
              usado pelo Arguidor, Geração de Código, QA e demais módulos do projeto.
              Estas chaves não se misturam com a chave da instância (Admin).
            </p>
          </div>

          {/* Lista de providers configurados */}
          {(settings.llm?.providers?.length ?? 0) === 0 ? (
            <div className="bg-slate-900 border border-dashed border-slate-700 rounded-xl p-6 text-center">
              <Zap className="w-6 h-6 text-slate-600 mx-auto mb-2" />
              <p className="text-slate-400 text-sm">Nenhum provedor configurado.</p>
              <p className="text-slate-500 text-xs mt-1">Adicione o primeiro — ele vira o padrão automaticamente.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {settings.llm.providers.map((p: { provider: string; model?: string; last_validation_ok?: boolean; last_validated_at?: string; is_default?: boolean; api_key_configured?: boolean }) => {
                const testResult = llmTestResults[p.provider]
                const lastOk = p.last_validation_ok
                const lastAt = p.last_validated_at
                const isTesting = testingProvider === p.provider
                const isRemoving = removingProvider === p.provider
                const isSettingDef = settingDefault === p.provider
                return (
                  <div
                    key={p.provider}
                    className={`bg-slate-900 border rounded-xl p-4 space-y-3 ${
                      p.is_default
                        ? 'border-violet-600/50 ring-1 ring-violet-600/20'
                        : 'border-slate-800'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="flex items-start gap-3 min-w-0">
                        <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          p.is_default ? 'bg-violet-600/20 border border-violet-500/40' : 'bg-slate-800 border border-slate-700'
                        }`}>
                          <Cpu className={`w-4 h-4 ${p.is_default ? 'text-violet-300' : 'text-slate-400'}`} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="text-slate-100 text-sm font-semibold">{providerLabel(p.provider)}</p>
                            {p.is_default && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-300 text-[10px] font-semibold uppercase tracking-wide">
                                <Star className="w-3 h-3" /> Padrão
                              </span>
                            )}
                            {p.api_key_configured
                              ? <span className="inline-flex items-center gap-1 text-[11px] text-emerald-300">
                                  <Check className="w-3 h-3" /> chave no vault
                                </span>
                              : <span className="inline-flex items-center gap-1 text-[11px] text-amber-300">
                                  <AlertCircle className="w-3 h-3" /> sem chave salva
                                </span>}
                          </div>
                          <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-2 flex-wrap">
                            <span>Modelo: <span className="text-slate-300">{p.model || 'padrão do provedor'}</span></span>
                            {lastAt && (
                              <>
                                <span>·</span>
                                <span className={lastOk ? 'text-emerald-400' : lastOk === false ? 'text-red-400' : 'text-slate-500'}>
                                  {lastOk ? '✓' : lastOk === false ? '✗' : '—'} última validação: {new Date(lastAt).toLocaleString('pt-BR')}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => testLlmProvider(p.provider)}
                          disabled={isTesting || !canEdit || !p.api_key_configured}
                          title={!p.api_key_configured ? 'Salve a chave antes de testar' : 'Testar conexão'}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 text-xs rounded-lg border border-slate-700 transition-colors"
                        >
                          {isTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
                          Testar
                        </button>
                        {!p.is_default && (
                          <button
                            onClick={() => setDefaultLlmProvider(p.provider)}
                            disabled={isSettingDef || !canEdit || !p.api_key_configured || lastOk === false}
                            title={lastOk === false ? 'Corrija a chave antes de definir como padrão' : 'Definir como padrão do projeto'}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600/20 hover:bg-violet-600/30 disabled:opacity-40 text-violet-200 text-xs rounded-lg border border-violet-500/40 transition-colors"
                          >
                            {isSettingDef ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Star className="w-3.5 h-3.5" />}
                            Padrão
                          </button>
                        )}
                        <button
                          onClick={() => removeLlmProvider(p.provider)}
                          disabled={isRemoving || !canEdit}
                          title="Remover provedor"
                          className="flex items-center gap-1.5 px-2 py-1.5 bg-slate-800 hover:bg-red-600/20 hover:border-red-500/50 disabled:opacity-40 text-slate-400 hover:text-red-300 text-xs rounded-lg border border-slate-700 transition-colors"
                        >
                          {isRemoving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>

                    {testResult && (
                      <div className={`flex items-start gap-2 px-3 py-2 rounded-lg text-xs border ${
                        testResult.ok === true
                          ? 'bg-emerald-900/20 border-emerald-800/40 text-emerald-300'
                          : testResult.ok === false
                            ? 'bg-red-900/20 border-red-800/40 text-red-300'
                            : 'bg-amber-900/20 border-amber-800/40 text-amber-300'
                      }`}>
                        {testResult.ok === true && <Wifi className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                        {testResult.ok === false && <WifiOff className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                        {testResult.ok === null && <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                        <span className="leading-snug">{testResult.message}</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Botão / Form de adicionar */}
          {!addingLlm ? (
            <button
              onClick={() => setAddingLlm(true)}
              disabled={!canEdit}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-slate-900 hover:bg-slate-800/80 border border-dashed border-slate-700 hover:border-violet-600/50 rounded-xl text-slate-300 hover:text-violet-300 text-sm transition-colors disabled:opacity-40"
            >
              <Plus className="w-4 h-4" />
              Adicionar outro provedor
            </button>
          ) : (
            <div className="bg-slate-900 border border-violet-800/40 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-slate-100 text-sm font-semibold">Adicionar provedor</h4>
                <button
                  onClick={() => { setAddingLlm(false); setNewLlmApiKey(''); setNewLlmModel('') }}
                  className="text-slate-500 hover:text-slate-300 text-xs"
                >
                  Cancelar
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-slate-400 text-xs block mb-1">Provedor</label>
                  <select
                    value={newLlmProvider}
                    onChange={e => setNewLlmProvider(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
                  >
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="grok">xAI (Grok)</option>
                    <option value="gemini">Google (Gemini)</option>
                    <option value="ollama">Ollama (local)</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 text-xs block mb-1">Modelo (opcional)</label>
                  <input
                    value={newLlmModel}
                    onChange={e => setNewLlmModel(e.target.value)}
                    placeholder={isOllamaSelected ? 'Ex: llama3.1:8b, qwen2.5-coder:7b' : 'Ex: claude-opus-4-6, gpt-4o, deepseek-chat'}
                    name="llm-model"
                    autoComplete="off"
                    spellCheck={false}
                    data-lpignore="true"
                    data-1p-ignore="true"
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
                  />
                </div>
              </div>

              {/* DT-023: Ollama é local — exige Base URL e dispensa API Key. */}
              {isOllamaSelected && (
                <div>
                  <label className="text-slate-400 text-xs block mb-1">
                    Base URL <span className="text-rose-400">*</span>
                  </label>
                  <input
                    value={newLlmBaseUrl}
                    onChange={e => setNewLlmBaseUrl(e.target.value)}
                    placeholder="http://host.docker.internal:11434"
                    name="llm-base-url"
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
                  />
                  <p className="text-slate-600 text-xs mt-1">
                    Endpoint do daemon Ollama. Como o GCA roda em Docker, o host típico é{' '}
                    <code className="bg-slate-800 px-1 py-0.5 rounded text-slate-400">http://host.docker.internal:11434</code>
                    {' '}(macOS/Windows) ou IP da máquina (Linux).
                  </p>
                </div>
              )}

              <div>
                <label className="text-slate-400 text-xs block mb-1">
                  API Key {isOllamaSelected && <span className="text-slate-500">(opcional para Ollama)</span>}
                </label>
                <div className="relative">
                  <input
                    type={showLlmKey ? 'text' : 'password'}
                    value={newLlmApiKey}
                    onChange={e => setNewLlmApiKey(e.target.value)}
                    placeholder={isOllamaSelected ? 'Bearer token (só se houver reverse proxy)' : 'sk-...'}
                    name="llm-api-key"
                    autoComplete="new-password"
                    spellCheck={false}
                    data-lpignore="true"
                    data-1p-ignore="true"
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
                  />
                  <button
                    type="button"
                    onClick={() => setShowLlmKey(!showLlmKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  >
                    {showLlmKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-slate-600 text-xs mt-1">
                  {isOllamaSelected
                    ? 'Ollama típico não exige autenticação. Use só se houver Bearer token de reverse proxy.'
                    : 'Armazenada criptografada no vault do projeto.'}
                </p>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={addLlmProvider}
                  disabled={saving || !canEdit}
                  className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  Adicionar provedor
                </button>
              </div>
            </div>
          )}
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

      {/* Tab: Repositório — reusa RepositoryPage (que pega projectId do useParams). */}
      {activeTab === 'repo' && (
        <div className="-mx-6 -my-0">
          <RepositoryPage />
        </div>
      )}

      {/* Tab: Questionário — reusa QuestionnairePage. */}
      {activeTab === 'questionario' && (
        <div className="-mx-6 -my-0">
          <QuestionnairePage />
        </div>
      )}
    </div>
  )
}
