import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FolderOpen, Users, CheckCircle2, AlertTriangle, Key, Loader2, Settings, Save,
  Cpu, Eye, EyeOff, Zap, Star, TestTube2, CircleCheck, CircleX,
} from 'lucide-react'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiClient } from '@/lib/api'
import { HelpTooltip } from '@/components/ui/HelpTooltip'

interface DashboardMetrics {
  totalProjects: number
  activeProjects: number
  degradedProjects: number
  totalUsers: number
  inactiveUsers: number
  statusDistribution: { name: string; value: number; color: string }[]
  gatekeeperScores: { name: string; score: number; fill: string }[]
  recentProjects: { id: string; name: string; status: string; phase: number; outputProfile: string }[]
  criticalCredentials: { name: string; project: string; status: string }[]
  recentAudit: { id: string; detail: string; level: string; timestamp: string }[]
}

function KPICard({ icon, label, value, sub, color }: { icon: React.ReactNode; label: string; value: number | string; sub: string; color: string }) {
  const bg: Record<string, string> = {
    indigo: 'bg-indigo-900/20 border-indigo-800/30',
    emerald: 'bg-emerald-900/20 border-emerald-800/30',
    amber: 'bg-amber-900/20 border-amber-800/30',
    blue: 'bg-blue-900/20 border-blue-800/30',
  }
  return (
    <div className={`${bg[color] || 'bg-slate-800 border-slate-700'} border rounded-xl p-4`}>
      <div className="p-2 rounded-lg bg-slate-800/60 w-fit">{icon}</div>
      <div className="mt-3">
        <p className="text-2xl font-semibold text-slate-100">{value}</p>
        <p className="text-slate-300 text-xs font-medium mt-0.5">{label}</p>
        <p className="text-slate-500 text-xs">{sub}</p>
      </div>
    </div>
  )
}

interface GCASettings {
  pillar_weights: Record<string, number>
  score_thresholds: Record<string, number>
  agent_config: Record<string, string | number>
}

function GCASettingsTab() {
  const [weights, setWeights] = useState<Record<string, number>>({ P1: 10, P2: 15, P3: 20, P4: 20, P5: 15, P6: 10, P7: 10 })
  const [thresholds, setThresholds] = useState({ p7_blocking_threshold: 70, ready_threshold: 90, needs_review_threshold: 70, at_risk_threshold: 50 })
  const [agentConfig, setAgentConfig] = useState({ max_retries: 3, timeout_seconds: 300 })
  const [saving, setSaving] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    apiClient.get('/admin/gca/settings').then(res => {
      if (res.data.pillar_weights) setWeights(res.data.pillar_weights)
      if (res.data.score_thresholds) setThresholds(res.data.score_thresholds)
      if (res.data.agent_config) setAgentConfig(prev => ({ ...prev, ...res.data.agent_config }))
    }).catch(() => {})
  }, [])

  const weightsSum = Object.values(weights).reduce((a, b) => a + b, 0)

  const saveWeights = async () => {
    if (weightsSum !== 100) return
    setSaving('weights')
    try {
      await apiClient.put('/admin/gca/settings/pillar-weights', weights)
      setToast('Pesos salvos com sucesso')
      setTimeout(() => setToast(null), 3000)
    } catch { setToast('Erro ao salvar pesos') }
    finally { setSaving(null) }
  }

  const saveThresholds = async () => {
    setSaving('thresholds')
    try {
      await apiClient.put('/admin/gca/settings/thresholds', thresholds)
      setToast('Thresholds salvos com sucesso')
      setTimeout(() => setToast(null), 3000)
    } catch { setToast('Erro ao salvar thresholds') }
    finally { setSaving(null) }
  }

  const pillarNames: Record<string, string> = {
    P1: 'Conformidade', P2: 'Arquitetura', P3: 'Segurança', P4: 'Performance',
    P5: 'Testabilidade', P6: 'Manutenção', P7: 'Documentação',
  }

  return (
    <div className="space-y-6">
      {toast && (
        <div className="p-3 bg-emerald-900/30 border border-emerald-700 rounded-lg text-emerald-300 text-sm">{toast}</div>
      )}

      {/* Pesos dos Pilares */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4 flex items-center gap-1.5">
          Pesos dos Pilares
          <HelpTooltip text="Os pesos definem a contribuição de cada pilar no score geral do Gatekeeper. A soma deve ser sempre exatamente 100%. Aumente o peso dos pilares mais críticos para o seu contexto: projetos financeiros devem ter P3 (Segurança) mais alto; projetos de alta manutenção devem ter P6 (Manutenibilidade) mais alto. Alterações de peso afetam todos os projetos novos imediatamente — avaliações já realizadas não são recalculadas." />
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(weights).map(([key, val]) => (
            <div key={key}>
              <label className="text-slate-400 text-xs mb-1 block">{key} {pillarNames[key]}</label>
              <div className="flex items-center gap-2">
                <input type="number" min={0} max={100} value={val}
                  onChange={e => setWeights(prev => ({ ...prev, [key]: parseInt(e.target.value) || 0 }))}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" />
                <span className="text-slate-500 text-xs">%</span>
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800">
          <span className={`text-sm font-medium ${weightsSum === 100 ? 'text-emerald-400' : 'text-red-400'}`}>
            Soma atual: {weightsSum}% {weightsSum !== 100 && '(deve ser 100)'}
          </span>
          <button onClick={saveWeights} disabled={weightsSum !== 100 || saving === 'weights'}
            className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
            {saving === 'weights' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Salvar Pesos
          </button>
        </div>
      </div>

      {/* Thresholds */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4 flex items-center gap-1.5">
          Thresholds de Score
          <HelpTooltip text="Os thresholds definem as faixas de classificação dos módulos avaliados. P1 Bloqueante: único threshold que impede aprovação — módulos com P1 (Conformidade) abaixo deste valor não podem ser aprovados em hipótese alguma. Os demais thresholds são classificações informativas para o GP e o time. Alterar thresholds não recalcula avaliações passadas." />
        </h3>
        <div className="grid grid-cols-2 gap-4">
          {[
            { key: 'p7_blocking_threshold', label: 'P1 Bloqueante (Conformidade)', desc: '< este → bloqueado' },
            { key: 'ready_threshold', label: 'Pronto para produção', desc: '≥ este → pronto' },
            { key: 'needs_review_threshold', label: 'Necessita revisão', desc: 'entre este e pronto' },
            { key: 'at_risk_threshold', label: 'Em risco', desc: 'entre este e revisão' },
          ].map(t => (
            <div key={t.key}>
              <label className="text-slate-400 text-xs mb-1 block">{t.label}</label>
              <div className="flex items-center gap-2">
                <input type="number" min={0} max={100}
                  value={thresholds[t.key as keyof typeof thresholds]}
                  onChange={e => setThresholds(prev => ({ ...prev, [t.key]: parseInt(e.target.value) || 0 }))}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" />
                <span className="text-slate-500 text-xs whitespace-nowrap">{t.desc}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-end mt-4 pt-3 border-t border-slate-800">
          <button onClick={saveThresholds} disabled={saving === 'thresholds'}
            className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
            {saving === 'thresholds' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Salvar Thresholds
          </button>
        </div>
      </div>

      {/* Agent Config */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4 flex items-center gap-1.5">
          Configuração de Agentes
          <HelpTooltip text="Parâmetros operacionais dos agentes de IA do GCA. MAX_RETRIES: número máximo de retentativas em caso de falha de LLM (padrão: 3). Timeout: tempo máximo de execução por operação antes de considerar falha (padrão: 300 segundos = 5 minutos). Aumentar estes valores melhora a resiliência mas pode aumentar o tempo de resposta." />
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-slate-400 text-xs mb-1 block">MAX_RETRIES (self-healing)</label>
            <div className="flex items-center gap-2">
              <input type="number" min={1} max={10} value={agentConfig.max_retries}
                onChange={e => setAgentConfig(prev => ({ ...prev, max_retries: parseInt(e.target.value) || 3 }))}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" />
              <span className="text-slate-500 text-xs">tentativas</span>
            </div>
          </div>
          <div>
            <label className="text-slate-400 text-xs mb-1 block">Timeout por operação</label>
            <div className="flex items-center gap-2">
              <input type="number" min={30} max={600} value={agentConfig.timeout_seconds}
                onChange={e => setAgentConfig(prev => ({ ...prev, timeout_seconds: parseInt(e.target.value) || 300 }))}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" />
              <span className="text-slate-500 text-xs">segundos</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Provedores de IA
// ============================================================================

interface AIProviderInfo {
  id: string
  name: string
  models: string[]
  default_model: string
  configured: boolean
  enabled: boolean
  key_source: string | null
  masked_key: string | null
  selected_model: string
  is_default: boolean
  tested_at: string | null
  test_status: string | null
}

function AIProvidersTab() {
  const [providers, setProviders] = useState<AIProviderInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [editingProvider, setEditingProvider] = useState<string | null>(null)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [selectedModel, setSelectedModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const loadProviders = useCallback(async () => {
    try {
      const res = await apiClient.get('/admin/gca/ai-providers')
      setProviders(res.data.providers || [])
    } catch {
      setProviders([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadProviders() }, [loadProviders])

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const handleEdit = (p: AIProviderInfo) => {
    setEditingProvider(p.id)
    setApiKeyInput('')
    setSelectedModel(p.selected_model)
    setShowKey(false)
  }

  const handleSave = async (providerId: string) => {
    if (!apiKeyInput.trim()) return
    setSaving(true)
    try {
      await apiClient.put('/admin/gca/ai-providers', {
        provider: providerId,
        api_key: apiKeyInput,
        model: selectedModel || undefined,
        enabled: true,
      })
      showToast('Provedor configurado com sucesso', 'success')
      setEditingProvider(null)
      setApiKeyInput('')
      await loadProviders()
    } catch (err: any) {
      showToast(err.message || 'Erro ao salvar', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async (p: AIProviderInfo) => {
    const key = editingProvider === p.id && apiKeyInput ? apiKeyInput : null
    if (!key && !p.configured) {
      showToast('Configure a API key antes de testar', 'error')
      return
    }
    setTesting(p.id)
    try {
      const res = await apiClient.post('/admin/gca/ai-providers/test', {
        provider: p.id,
        api_key: key || 'use_existing',
        model: editingProvider === p.id ? selectedModel : p.selected_model,
      })
      if (res.data.success) {
        showToast(res.data.message, 'success')
      } else {
        showToast(res.data.message, 'error')
      }
      await loadProviders()
    } catch (err: any) {
      showToast(err.message || 'Erro no teste', 'error')
    } finally {
      setTesting(null)
    }
  }

  const handleSetDefault = async (providerId: string) => {
    try {
      await apiClient.put('/admin/gca/ai-providers/default', { provider: providerId })
      showToast('Provedor padrao definido', 'success')
      await loadProviders()
    } catch (err: any) {
      showToast(err.message || 'Erro', 'error')
    }
  }

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-1 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-violet-400" />
          Provedores de IA
        </h3>
        <p className="text-slate-500 text-xs mb-5">
          Configure as API keys dos provedores de IA para que o pipeline OCG e o Arguidor possam funcionar.
          Pelo menos um provedor deve estar configurado e testado.
        </p>

        <div className="space-y-3">
          {providers.map(p => {
            const isEditing = editingProvider === p.id
            return (
              <div key={p.id} className={`border rounded-xl p-4 transition-colors ${p.is_default ? 'border-violet-600/40 bg-violet-950/10' : 'border-slate-800 bg-slate-900/50'}`}>
                {/* Header */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2.5">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 ${p.configured ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/30' : 'bg-slate-800 text-slate-500 border border-slate-700'}`}>
                      {p.name.charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-slate-200 text-sm font-medium">{p.name}</span>
                        {p.is_default && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-600/20 text-violet-300 flex items-center gap-0.5">
                            <Star className="w-2.5 h-2.5" /> Padrao
                          </span>
                        )}
                        {p.configured && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-600/20 text-emerald-300">
                            Configurado ({p.key_source})
                          </span>
                        )}
                        {p.test_status === 'ok' && (
                          <CircleCheck className="w-3.5 h-3.5 text-emerald-400" />
                        )}
                        {p.test_status === 'error' && (
                          <CircleX className="w-3.5 h-3.5 text-red-400" />
                        )}
                      </div>
                      <p className="text-slate-500 text-xs">
                        Modelo: {p.selected_model}
                        {p.masked_key && <> &middot; Key: {p.masked_key}</>}
                        {p.tested_at && <> &middot; Testado: {new Date(p.tested_at).toLocaleString('pt-BR')}</>}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {p.configured && !p.is_default && (
                      <button onClick={() => handleSetDefault(p.id)}
                        className="px-2.5 py-1 text-xs text-slate-400 hover:text-violet-300 bg-slate-800 border border-slate-700 rounded-lg hover:border-violet-600/30 transition-colors">
                        Definir padrao
                      </button>
                    )}
                    <button onClick={() => handleTest(p)}
                      disabled={testing === p.id || (!p.configured && !isEditing)}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-400 hover:text-emerald-300 bg-slate-800 border border-slate-700 rounded-lg hover:border-emerald-600/30 disabled:opacity-30 transition-colors">
                      {testing === p.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <TestTube2 className="w-3 h-3" />} Testar
                    </button>
                    <button onClick={() => isEditing ? setEditingProvider(null) : handleEdit(p)}
                      className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${isEditing ? 'bg-violet-600/20 border-violet-600/30 text-violet-300' : 'text-slate-400 bg-slate-800 border-slate-700 hover:text-slate-200'}`}>
                      {isEditing ? 'Cancelar' : (p.configured ? 'Alterar key' : 'Configurar')}
                    </button>
                  </div>
                </div>

                {/* Edit form */}
                {isEditing && (
                  <div className="mt-3 pt-3 border-t border-slate-800 space-y-3">
                    <div>
                      <label className="text-slate-400 text-xs mb-1 block">API Key</label>
                      <div className="relative">
                        <input
                          type={showKey ? 'text' : 'password'}
                          value={apiKeyInput}
                          onChange={e => setApiKeyInput(e.target.value)}
                          placeholder={p.configured ? 'Nova API key (deixe vazio para manter)' : 'Cole a API key aqui'}
                          className="w-full px-3 py-2 pr-10 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 placeholder-slate-600"
                        />
                        <button onClick={() => setShowKey(!showKey)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                          {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="text-slate-400 text-xs mb-1 block">Modelo</label>
                      <select
                        value={selectedModel}
                        onChange={e => setSelectedModel(e.target.value)}
                        className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                      >
                        {p.models.map(m => (
                          <option key={m} value={m}>{m}{m === p.default_model ? ' (recomendado)' : ''}</option>
                        ))}
                      </select>
                    </div>
                    <div className="flex justify-end">
                      <button onClick={() => handleSave(p.id)} disabled={!apiKeyInput.trim() || saving}
                        className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Salvar
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Info box */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex items-start gap-3">
        <Zap className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-400 space-y-1">
          <p><strong className="text-slate-300">Por que configurar?</strong> O questionario preenchido pelo GP precisa de um agente de IA para ser avaliado. Sem provedor configurado, o pipeline OCG nao funciona.</p>
          <p><strong className="text-slate-300">Recomendacao:</strong> Configure pelo menos Anthropic (Claude) ou OpenAI (GPT-4). O provedor padrao sera usado para todas as analises automaticas.</p>
          <p><strong className="text-slate-300">Seguranca:</strong> API keys sao armazenadas com mascaramento. Apenas os ultimos 6 caracteres sao exibidos.</p>
        </div>
      </div>
    </div>
  )
}

export function AdminDashboardPage() {
  const navigate = useNavigate()
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'dashboard' | 'settings' | 'ai'>('dashboard')

  useEffect(() => {
    loadMetrics()
  }, [])

  const emptyMetrics: DashboardMetrics = {
    totalProjects: 0, activeProjects: 0, degradedProjects: 0,
    totalUsers: 0, inactiveUsers: 0,
    statusDistribution: [], gatekeeperScores: [],
    recentProjects: [], criticalCredentials: [], recentAudit: [],
  }

  const loadMetrics = async () => {
    try {
      const res = await apiClient.get('/admin/dashboard/metrics')
      setMetrics({ ...emptyMetrics, ...(res.data || {}) })
    } catch {
      setMetrics(emptyMetrics)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
      </div>
    )
  }

  if (!metrics) return null

  const statusDist = metrics.statusDistribution || []
  const gkScores = metrics.gatekeeperScores || []
  const recentProj = metrics.recentProjects || []
  const critCreds = metrics.criticalCredentials || []
  const recentAud = metrics.recentAudit || []

  const pieData = statusDist.length > 0 ? statusDist : [
    { name: 'Sem dados', value: 1, color: '#334155' },
  ]

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Administração GCA</h1>
          <p className="text-slate-500 text-sm mt-0.5">Visão consolidada e configurações do sistema</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-800">
        <button onClick={() => setActiveTab('dashboard')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${activeTab === 'dashboard' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          Dashboard
        </button>
        <button onClick={() => setActiveTab('settings')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${activeTab === 'settings' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <Settings className="w-3.5 h-3.5" /> Configuracoes
        </button>
        <button onClick={() => setActiveTab('ai')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${activeTab === 'ai' ? 'border-violet-500 text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
          <Cpu className="w-3.5 h-3.5" /> Provedores de IA
        </button>
      </div>

      {activeTab === 'ai' && <AIProvidersTab />}
      {activeTab === 'settings' && <GCASettingsTab />}

      {activeTab === 'dashboard' && (<>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard icon={<FolderOpen className="w-5 h-5 text-indigo-400" />} label="Total de Projetos" value={metrics.totalProjects} sub="todos os tenants" color="indigo" />
        <KPICard icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />} label="Projetos Ativos" value={metrics.activeProjects} sub="em operacao" color="emerald" />
        <KPICard icon={<AlertTriangle className="w-5 h-5 text-amber-400" />} label="Degradados" value={metrics.degradedProjects} sub="requerem atencao" color="amber" />
        <KPICard icon={<Users className="w-5 h-5 text-blue-400" />} label="Usuarios" value={metrics.totalUsers} sub={`${metrics.inactiveUsers} inativos`} color="blue" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status Distribution */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-4">Distribuicao de Status</h3>
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={120} height={120}>
              <PieChart>
                <Pie data={pieData} cx={55} cy={55} innerRadius={30} outerRadius={55} paddingAngle={3} dataKey="value">
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2">
              {pieData.map(d => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
                  <span className="text-slate-400 text-xs">{d.name}</span>
                  <span className="text-slate-200 text-xs font-medium ml-auto pl-4">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Gatekeeper Scores */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 lg:col-span-2">
          <h3 className="text-slate-200 text-sm font-semibold mb-4">Score Gatekeeper por Projeto</h3>
          {gkScores.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={gkScores} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '12px' }}
                  formatter={(v: number) => [`${v}/100`, 'Score']}
                />
                <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                  {gkScores.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-slate-500 text-sm py-8 text-center">Nenhum score registrado</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Projects */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-slate-200 text-sm font-semibold">Projetos Recentes</h3>
            <button onClick={() => navigate('/admin/projects')} className="text-xs text-violet-400 hover:text-violet-300 transition-colors">Ver todos</button>
          </div>
          {recentProj.length > 0 ? (
            <div className="space-y-2">
              {recentProj.slice(0, 5).map(p => (
                <div
                  key={p.id}
                  onClick={() => navigate(`/projects/${p.id}`)}
                  className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-800 cursor-pointer transition-colors"
                >
                  <div className="w-8 h-8 rounded-md bg-violet-900/40 border border-violet-800/40 flex items-center justify-center text-violet-400 text-xs font-bold flex-shrink-0">
                    {p.name.charAt(0)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-slate-200 text-xs font-medium truncate">{p.name}</p>
                    <p className="text-slate-500 text-xs">Fase {p.phase} - {p.outputProfile}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    p.status === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                    p.status === 'degraded' ? 'bg-amber-500/20 text-amber-300' :
                    'bg-slate-700 text-slate-400'
                  }`}>{p.status}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm py-4 text-center">Nenhum projeto encontrado</p>
          )}
        </div>

        {/* Alerts + Recent Audit */}
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-slate-200 text-sm font-semibold flex items-center gap-2">
                <Key className="w-4 h-4 text-amber-400" />
                Credenciais com Alerta
              </h3>
              <span className="text-xs text-red-400 font-medium">{critCreds.length} criticas</span>
            </div>
            {critCreds.length === 0 ? (
              <p className="text-slate-500 text-xs">Todas as credenciais estao validas.</p>
            ) : (
              <div className="space-y-2">
                {critCreds.map((c, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded-md bg-red-950/30 border border-red-900/30">
                    <div>
                      <p className="text-slate-300 text-xs font-medium">{c.name}</p>
                      <p className="text-slate-500 text-xs">{c.project}</p>
                    </div>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-300">{c.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-slate-200 text-sm font-semibold">Atividade Recente</h3>
              <button onClick={() => navigate('/admin/audit')} className="text-xs text-violet-400 hover:text-violet-300 transition-colors">Ver trilha</button>
            </div>
            {recentAud.length > 0 ? (
              <div className="space-y-2.5">
                {recentAud.slice(0, 5).map(ev => (
                  <div key={ev.id} className="flex items-start gap-2.5">
                    <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                      ev.level === 'critical' ? 'bg-red-400' : ev.level === 'warning' ? 'bg-amber-400' : 'bg-emerald-400'
                    }`} />
                    <div className="min-w-0">
                      <p className="text-slate-300 text-xs leading-snug">{ev.detail.slice(0, 80)}{ev.detail.length > 80 ? '...' : ''}</p>
                      <p className="text-slate-600 text-xs mt-0.5">{new Date(ev.timestamp).toLocaleString('pt-BR')}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-500 text-xs">Nenhuma atividade recente.</p>
            )}
          </div>
        </div>
      </div>
      </>)}
    </div>
  )
}
