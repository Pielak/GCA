import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { GitBranch, Plus, Trash2, Play, Loader2, CheckCircle, AlertTriangle, Clock, RefreshCw, Eye, EyeOff, BarChart3, X, ChevronDown, ChevronRight, FileText, Shield, Layers, FolderTree, BookOpen } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'
import { formatDateTimeBR } from '@/lib/datetime'

interface AnalysisResult {
  stack: Record<string, any>
  vulnerabilities: Record<string, any>
  compatibility: Record<string, any>
  gca_overall_status: string | null
  risk_level: string | null
  categories: Array<{
    category: string
    summary: string
    metrics: Record<string, any>
    files_analyzed: number
    ai_provider: string
  }>
  roadmap: Array<{
    step_number: number
    title: string
    description: string
    effort_hours: number
    status: string
  }>
  injected_documents: Array<{
    id: string
    filename: string
    file_type: string
    source_url: string
    created_at: string
  }>
}

interface ExternalRepo {
  id: string
  repo_url: string
  provider: string
  branch: string
  status: string
  last_read_at: string | null
  files_total: number
  files_processed: number
  files_skipped: number
  error_message: string | null
  created_at: string
  analysis_phase: number
  analysis_phase_label: string | null
  analysis_progress: number
  compatibility_status: string | null
}

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  pending: { label: 'Pendente', bg: 'bg-slate-500/20', text: 'text-slate-400' },
  reading: { label: 'Lendo...', bg: 'bg-blue-500/20', text: 'text-blue-300' },
  completed: { label: 'Concluído', bg: 'bg-emerald-500/20', text: 'text-emerald-300' },
  partial: { label: 'Parcial', bg: 'bg-amber-500/20', text: 'text-amber-300' },
  error: { label: 'Erro', bg: 'bg-red-500/20', text: 'text-red-300' },
}

const PROVIDER_ICONS: Record<string, string> = {
  github: 'GH',
  gitlab: 'GL',
  bitbucket: 'BB',
}

export function ExternalReposPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [repos, setRepos] = useState<ExternalRepo[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  // Formulário
  const [showForm, setShowForm] = useState(false)
  const [repoUrl, setRepoUrl] = useState('')
  const [provider, setProvider] = useState('github')
  const [branch, setBranch] = useState('main')
  const [accessToken, setAccessToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [saving, setSaving] = useState(false)

  // Análise
  const [analysisData, setAnalysisData] = useState<AnalysisResult | null>(null)
  const [showAnalysis, setShowAnalysis] = useState<string | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('stack')

  // Toast
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const loadRepos = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/external-repos`)
      setRepos(res.data.repos || [])
    } catch { setRepos([]) }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadRepos() }, [loadRepos])

  // Polling: atualizar a cada 3s quando algum repo está em análise
  useEffect(() => {
    const hasReading = repos.some(r => r.status === 'reading')
    if (!hasReading) return
    const interval = setInterval(loadRepos, 3000)
    return () => clearInterval(interval)
  }, [repos, loadRepos])

  const loadAnalysis = async (repoId: string) => {
    if (!projectId) return
    if (showAnalysis === repoId) {
      setShowAnalysis(null)
      setAnalysisData(null)
      return
    }
    setAnalysisLoading(true)
    setShowAnalysis(repoId)
    setActiveTab('stack')
    try {
      const res = await apiClient.get(`/projects/${projectId}/external-repos/${repoId}/analysis`)
      setAnalysisData(res.data)
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao carregar análise', 'error')
      setShowAnalysis(null)
    }
    setAnalysisLoading(false)
  }

  const handleAdd = async () => {
    if (!repoUrl.trim()) return
    setSaving(true)
    try {
      await apiClient.post(`/projects/${projectId}/external-repos`, {
        repo_url: repoUrl.trim(),
        provider,
        branch: branch.trim() || 'main',
        access_token: accessToken.trim() || undefined,
      })
      showToast('Repositório cadastrado com sucesso', 'success')
      setShowForm(false)
      setRepoUrl('')
      setAccessToken('')
      setBranch('main')
      await loadRepos()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao cadastrar repositório', 'error')
    }
    setSaving(false)
  }

  const handleRead = async (repo: ExternalRepo) => {
    setActionLoading(repo.id)
    try {
      await apiClient.post(`/projects/${projectId}/external-repos/${repo.id}/read`)
      showToast(`Leitura iniciada: ${repo.repo_url}`, 'success')
      await loadRepos()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao iniciar leitura', 'error')
    }
    setActionLoading(null)
  }

  const handleDelete = async (repo: ExternalRepo) => {
    if (!confirm(`Remover repositório "${repo.repo_url}"?`)) return
    setActionLoading(repo.id)
    try {
      await apiClient.delete(`/projects/${projectId}/external-repos/${repo.id}`)
      showToast('Repositório removido', 'success')
      await loadRepos()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao remover', 'error')
    }
    setActionLoading(null)
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Repositórios Externos</h2>
          <p className="text-slate-500 text-sm mt-0.5">
            Cadastre repositórios para o GCA analisar e importar como documentação do projeto.
            O acesso é somente leitura (read-only).
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Adicionar Repositório
        </button>
      </div>

      {/* Formulário de cadastro */}
      {showForm && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 space-y-4">
          <h3 className="text-slate-200 text-sm font-semibold">Novo Repositório</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-slate-400 text-xs block mb-1">URL do Repositório</label>
              <input
                value={repoUrl}
                onChange={e => setRepoUrl(e.target.value)}
                placeholder="https://github.com/org/repo"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 text-xs block mb-1">Provider</label>
                <select
                  value={provider}
                  onChange={e => setProvider(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
                >
                  <option value="github">GitHub</option>
                  <option value="gitlab">GitLab</option>
                  <option value="bitbucket">Bitbucket</option>
                </select>
              </div>
              <div>
                <label className="text-slate-400 text-xs block mb-1">Branch</label>
                <input
                  value={branch}
                  onChange={e => setBranch(e.target.value)}
                  placeholder="main"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs block mb-1">Token de Acesso (read-only)</label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={accessToken}
                onChange={e => setAccessToken(e.target.value)}
                placeholder="ghp_... ou glpat-... (opcional para repos públicos)"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-slate-600 text-xs mt-1">O token é armazenado criptografado e usado apenas para leitura.</p>
          </div>

          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200">
              Cancelar
            </button>
            <button
              onClick={handleAdd}
              disabled={!repoUrl.trim() || saving}
              className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Cadastrar
            </button>
          </div>
        </div>
      )}

      {/* Lista de repositórios */}
      {repos.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <GitBranch className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-slate-300 font-semibold mb-2">Nenhum repositório cadastrado</h3>
          <p className="text-slate-500 text-sm max-w-md mx-auto">
            Adicione repositórios externos para que o GCA analise o código, documentação, configurações
            e testes existentes. Esses dados enriquecem o OCG do projeto.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {repos.map(repo => {
            const st = STATUS_CONFIG[repo.status] || STATUS_CONFIG.pending
            const isReading = repo.status === 'reading'
            const progress = repo.files_total > 0 ? Math.round((repo.files_processed / repo.files_total) * 100) : 0

            return (
              <div key={repo.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <div className="flex items-center gap-4">
                  {/* Provider icon */}
                  <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 text-xs font-bold flex-shrink-0">
                    {PROVIDER_ICONS[repo.provider] || '??'}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-slate-200 text-sm font-medium truncate">{repo.repo_url}</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${st.bg} ${st.text}`}>{st.label}</span>
                      {repo.status === 'completed' && repo.compatibility_status && (
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          repo.compatibility_status === 'compatível' ? 'bg-emerald-500/20 text-emerald-400' :
                          repo.compatibility_status === 'requer_adaptação' ? 'bg-amber-500/20 text-amber-400' :
                          'bg-red-500/20 text-red-400'
                        }`}>
                          {repo.compatibility_status === 'compatível' ? '✅ Compatível' :
                           repo.compatibility_status === 'requer_adaptação' ? '⚠️ Requer Adaptação' :
                           '❌ Incompatível'}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-slate-500 text-xs">
                      <span>Branch: {repo.branch}</span>
                      {repo.last_read_at && <span>Última leitura: {formatDateTimeBR(repo.last_read_at)}</span>}
                      {repo.files_total > 0 && !isReading && <span>{repo.files_processed}/{repo.files_total} arquivos</span>}
                    </div>
                    {repo.error_message && (
                      <p className="text-red-400 text-xs mt-1">{repo.error_message}</p>
                    )}
                  </div>

                  {/* Progress bar (se em leitura) */}
                  {isReading && (
                    <div className="w-48 flex-shrink-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-blue-300 text-[10px] font-medium truncate max-w-[140px]">
                          {repo.analysis_phase_label || 'Iniciando...'}
                        </span>
                        <span className="text-blue-400 text-[10px] font-bold ml-1">
                          {repo.analysis_progress || 0}%
                        </span>
                      </div>
                      <div className="h-2 bg-slate-700/80 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all duration-700 ease-out"
                          style={{ width: `${repo.analysis_progress || 2}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-slate-500 text-[9px]">
                          Fase {repo.analysis_phase || 1}/6
                        </span>
                        {repo.files_total > 0 && (
                          <span className="text-slate-500 text-[9px]">
                            {repo.files_processed}/{repo.files_total} arquivos
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Ações */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {repo.status === 'completed' && (
                      <button
                        onClick={() => loadAnalysis(repo.id)}
                        disabled={analysisLoading && showAnalysis === repo.id}
                        className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                          showAnalysis === repo.id
                            ? 'bg-violet-600/30 border border-violet-500/40 text-violet-300'
                            : 'bg-violet-500/20 border border-violet-600/30 text-violet-400 hover:bg-violet-500/30'
                        }`}
                        title="Ver análise do repositório"
                      >
                        {analysisLoading && showAnalysis === repo.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <BarChart3 className="w-3.5 h-3.5" />
                        )}
                        Ver Análise
                      </button>
                    )}
                    <button
                      onClick={() => handleRead(repo)}
                      disabled={isReading || actionLoading === repo.id}
                      className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 text-xs rounded-lg hover:bg-emerald-600/30 disabled:opacity-30 transition-colors"
                      title="Ler dados do repositório"
                    >
                      {isReading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                      {isReading ? 'Lendo...' : 'Ler Dados'}
                    </button>
                    <button
                      onClick={() => handleDelete(repo)}
                      disabled={actionLoading === repo.id}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-900/20 disabled:opacity-30 transition-colors"
                      title="Remover repositório"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Painel de análise */}
      {showAnalysis && (
        <div className="bg-dark-200/50 border border-slate-700/50 rounded-xl overflow-hidden">
          {/* Header do painel */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700/50">
            <h3 className="text-white text-sm font-semibold flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-violet-400" />
              Resultado da Análise
            </h3>
            <button
              onClick={() => { setShowAnalysis(null); setAnalysisData(null) }}
              className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-dark-200 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-700/50 px-2">
            {[
              { key: 'stack', label: 'Stack Detectado', icon: Layers },
              { key: 'security', label: 'Segurança', icon: Shield },
              { key: 'compatibility', label: 'Compatibilidade GCA', icon: CheckCircle },
              { key: 'categories', label: 'Categorias', icon: FolderTree },
              { key: 'documents', label: 'Documentos', icon: BookOpen },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 ${
                  activeTab === tab.key
                    ? 'border-violet-500 text-violet-300'
                    : 'border-transparent text-slate-400 hover:text-slate-300'
                }`}
              >
                <tab.icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Conteúdo da tab */}
          <div className="p-5">
            {analysisLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
              </div>
            ) : !analysisData ? (
              <p className="text-slate-400 text-sm text-center py-8">Nenhum dado de análise disponível.</p>
            ) : (
              <>
                {/* Tab 1: Stack Detectado */}
                {activeTab === 'stack' && (() => {
                  // Stack vem do backend em formato livre — usar acesso defensivo.
                  const stack = (analysisData.stack || {}) as Record<string, unknown> & {
                    language?: string | { primary?: string }
                    primary_language?: string
                    files_total?: number
                    repository?: { files_total?: number }
                    has_docker?: boolean
                    has_dockerfile?: boolean
                    has_tests?: boolean
                    has_ci_cd?: boolean
                    has_cicd?: boolean
                    frameworks?: Array<string | { name?: string; version?: string }>
                  }
                  const language =
                    typeof stack.language === 'string'
                      ? stack.language
                      : stack.language?.primary || stack.primary_language || '-'
                  const filesTotal =
                    stack.files_total ?? stack.repository?.files_total ?? '-'
                  const hasDocker = stack.has_docker ?? stack.has_dockerfile ?? false
                  const hasTests = stack.has_tests ?? false
                  const hasCi = stack.has_ci_cd ?? stack.has_cicd ?? false
                  const frameworks: Array<string> = Array.isArray(stack.frameworks)
                    ? stack.frameworks.map((fw) =>
                        typeof fw === 'string'
                          ? fw
                          : fw?.version
                            ? `${fw.name} ${fw.version}`
                            : fw?.name || JSON.stringify(fw)
                      )
                    : []
                  return (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        {[
                          { label: 'Linguagem', value: language },
                          { label: 'Arquivos Total', value: filesTotal },
                          { label: 'Docker', value: hasDocker ? 'Sim' : 'Não' },
                          { label: 'Testes', value: hasTests ? 'Sim' : 'Não' },
                          { label: 'CI/CD', value: hasCi ? 'Sim' : 'Não' },
                        ].map(item => (
                          <div key={item.label} className="bg-dark-200 rounded-lg p-3">
                            <p className="text-slate-400 text-xs">{item.label}</p>
                            <p className="text-white text-sm font-medium mt-0.5">{String(item.value)}</p>
                          </div>
                        ))}
                      </div>
                      {frameworks.length > 0 && (
                        <div>
                          <p className="text-slate-400 text-xs mb-2">Frameworks Detectados</p>
                          <div className="flex flex-wrap gap-2">
                            {frameworks.map((fw, i) => (
                              <span key={i} className="px-2.5 py-1 bg-violet-500/20 text-violet-300 text-xs rounded-full">
                                {fw}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })()}

                {/* Tab 2: Segurança */}
                {activeTab === 'security' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <span className="text-slate-400 text-xs">Nível de Risco:</span>
                      <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                        analysisData.risk_level === 'low' ? 'bg-emerald-500/20 text-emerald-400'
                        : analysisData.risk_level === 'medium' ? 'bg-amber-500/20 text-amber-400'
                        : analysisData.risk_level === 'high' ? 'bg-red-500/20 text-red-400'
                        : 'bg-dark-200 text-slate-400'
                      }`}>
                        {analysisData.risk_level === 'low' ? 'Baixo'
                         : analysisData.risk_level === 'medium' ? 'Médio'
                         : analysisData.risk_level === 'high' ? 'Alto'
                         : analysisData.risk_level || 'N/A'}
                      </span>
                    </div>
                    {analysisData.vulnerabilities?.items && Array.isArray(analysisData.vulnerabilities.items) ? (
                      <div className="space-y-2">
                        {analysisData.vulnerabilities.items.map((vuln: { severity?: string; description?: string; name?: string; recommended_version?: string }, i: number) => (
                          <div key={i} className="bg-dark-200 rounded-lg p-3 flex items-start gap-3">
                            <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 mt-0.5 ${
                              vuln.severity === 'critical' ? 'bg-red-500/20 text-red-400'
                              : vuln.severity === 'high' ? 'bg-amber-500/20 text-amber-400'
                              : vuln.severity === 'medium' ? 'bg-amber-500/20 text-amber-400'
                              : 'bg-dark-200 text-slate-400'
                            }`}>
                              {vuln.severity || 'info'}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-white text-sm">{vuln.description || vuln.name || 'Vulnerabilidade detectada'}</p>
                              {vuln.recommended_version && (
                                <p className="text-slate-400 text-xs mt-1">Versão recomendada: {vuln.recommended_version}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-400 text-sm">Nenhuma vulnerabilidade identificada.</p>
                    )}
                  </div>
                )}

                {/* Tab 3: Compatibilidade GCA */}
                {activeTab === 'compatibility' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <span className="text-slate-400 text-xs">Status Geral:</span>
                      <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                        analysisData.gca_overall_status === 'compativel' ? 'bg-emerald-500/20 text-emerald-400'
                        : analysisData.gca_overall_status === 'requer_adaptacao' ? 'bg-amber-500/20 text-amber-400'
                        : analysisData.gca_overall_status === 'incompativel' ? 'bg-red-500/20 text-red-400'
                        : 'bg-dark-200 text-slate-400'
                      }`}>
                        {analysisData.gca_overall_status === 'compativel' ? 'Compatível'
                         : analysisData.gca_overall_status === 'requer_adaptacao' ? 'Requer Adaptação'
                         : analysisData.gca_overall_status === 'incompativel' ? 'Incompatível'
                         : analysisData.gca_overall_status || 'N/A'}
                      </span>
                    </div>

                    {analysisData.compatibility?.effort_estimate && (
                      <div className="bg-dark-200 rounded-lg p-3">
                        <p className="text-slate-400 text-xs">Estimativa de Esforço</p>
                        <p className="text-white text-sm font-medium mt-0.5">{analysisData.compatibility.effort_estimate}</p>
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {['backend', 'frontend', 'database'].map(area => {
                        const comp = (analysisData.compatibility || {}) as Record<string, { status?: string; compatible?: boolean; effort?: string; reason?: string; notes?: string } | undefined>
                        const data = comp[area] || comp[`gca_${area}_compatibility`]
                        if (!data) return null
                        const statusText =
                          typeof data.status === 'string'
                            ? data.status
                            : data.compatible === true
                              ? 'Compatível'
                              : data.compatible === false
                                ? 'Incompatível'
                                : 'N/A'
                        const note = data.reason || data.notes
                        return (
                          <div key={area} className="bg-dark-200 rounded-lg p-4">
                            <p className="text-violet-400 text-xs font-semibold uppercase mb-2">{area}</p>
                            <p className="text-white text-sm">{statusText}</p>
                            {note && <p className="text-slate-400 text-xs mt-1">{note}</p>}
                          </div>
                        )
                      })}
                    </div>

                    {analysisData.roadmap && analysisData.roadmap.length > 0 && (
                      <div>
                        <p className="text-slate-300 text-xs font-semibold mb-2">Roadmap de Adaptação</p>
                        <div className="space-y-2">
                          {analysisData.roadmap.map(step => (
                            <div key={step.step_number} className="bg-dark-200 rounded-lg p-3 flex items-start gap-3">
                              <span className="w-6 h-6 rounded-full bg-violet-500/20 text-violet-300 text-xs font-bold flex items-center justify-center flex-shrink-0">
                                {step.step_number}
                              </span>
                              <div className="flex-1 min-w-0">
                                <p className="text-white text-sm font-medium">{step.title}</p>
                                <p className="text-slate-400 text-xs mt-0.5">{step.description}</p>
                                <div className="flex items-center gap-3 mt-1.5">
                                  <span className="text-slate-400 text-[10px]">{step.effort_hours}h estimadas</span>
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                    step.status === 'done' ? 'bg-emerald-500/20 text-emerald-400'
                                    : step.status === 'in_progress' ? 'bg-blue-500/20 text-blue-300'
                                    : 'bg-dark-200 text-slate-400 border border-slate-700/50'
                                  }`}>
                                    {step.status === 'done' ? 'Concluído' : step.status === 'in_progress' ? 'Em andamento' : 'Pendente'}
                                  </span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Tab 4: Categorias */}
                {activeTab === 'categories' && (
                  <div className="space-y-2">
                    {analysisData.categories && analysisData.categories.length > 0 ? (
                      analysisData.categories.map((cat, i) => (
                        <details key={i} className="bg-dark-200 rounded-lg group">
                          <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer text-white text-sm font-medium hover:bg-dark-200/80 rounded-lg transition-colors list-none">
                            <ChevronRight className="w-4 h-4 text-slate-400 group-open:rotate-90 transition-transform" />
                            <span className="flex-1">{cat.category}</span>
                            <span className="text-slate-400 text-xs">{cat.files_analyzed} arquivos</span>
                            {cat.ai_provider && (
                              <span className="text-xs px-2 py-0.5 rounded bg-violet-500/20 text-violet-300">{cat.ai_provider}</span>
                            )}
                          </summary>
                          <div className="px-4 pb-3 pt-0">
                            <p className="text-slate-300 text-sm leading-relaxed">{cat.summary}</p>
                            {cat.metrics && Object.keys(cat.metrics).length > 0 && (
                              <div className="flex flex-wrap gap-2 mt-2">
                                {Object.entries(cat.metrics).map(([k, v]) => (
                                  <span key={k} className="text-xs px-2 py-0.5 bg-dark-200/50 border border-slate-700/50 rounded text-slate-400">
                                    {k}: {String(v)}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </details>
                      ))
                    ) : (
                      <p className="text-slate-400 text-sm text-center py-4">Nenhuma categoria analisada.</p>
                    )}
                  </div>
                )}

                {/* Tab 5: Documentos */}
                {activeTab === 'documents' && (
                  <div className="space-y-2">
                    {analysisData.injected_documents && analysisData.injected_documents.length > 0 ? (
                      analysisData.injected_documents.map(doc => (
                        <div key={doc.id} className="bg-dark-200 rounded-lg p-3 flex items-center gap-3">
                          <FileText className="w-4 h-4 text-violet-400 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-white text-sm truncate">{doc.filename}</p>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 flex-shrink-0">EXTERNO</span>
                            </div>
                            <div className="flex items-center gap-3 mt-0.5 text-slate-400 text-xs">
                              <span>{doc.file_type}</span>
                              {doc.source_url && (
                                <a
                                  href={doc.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="truncate max-w-xs text-violet-300 hover:text-violet-200 underline underline-offset-2"
                                  title={doc.source_url}
                                >
                                  Abrir no repositório ↗
                                </a>
                              )}
                              <span>{formatDateTimeBR(doc.created_at)}</span>
                            </div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-slate-400 text-sm text-center py-4">Nenhum documento injetado.</p>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
