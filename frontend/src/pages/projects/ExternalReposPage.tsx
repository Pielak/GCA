import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { GitBranch, Plus, Trash2, Play, Loader2, CheckCircle, AlertTriangle, Clock, RefreshCw, Eye, EyeOff } from 'lucide-react'
import { apiClient } from '@/lib/api'

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
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao cadastrar repositório', 'error')
    }
    setSaving(false)
  }

  const handleRead = async (repo: ExternalRepo) => {
    setActionLoading(repo.id)
    try {
      await apiClient.post(`/projects/${projectId}/external-repos/${repo.id}/read`)
      showToast(`Leitura iniciada: ${repo.repo_url}`, 'success')
      await loadRepos()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao iniciar leitura', 'error')
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
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao remover', 'error')
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
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-slate-500 text-xs">
                      <span>Branch: {repo.branch}</span>
                      {repo.last_read_at && <span>Última leitura: {new Date(repo.last_read_at).toLocaleString('pt-BR')}</span>}
                      {repo.files_total > 0 && <span>{repo.files_processed}/{repo.files_total} arquivos</span>}
                    </div>
                    {repo.error_message && (
                      <p className="text-red-400 text-xs mt-1">{repo.error_message}</p>
                    )}
                  </div>

                  {/* Progress bar (se em leitura) */}
                  {isReading && repo.files_total > 0 && (
                    <div className="w-24">
                      <div className="h-1.5 bg-slate-700 rounded-full">
                        <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${progress}%` }} />
                      </div>
                      <p className="text-slate-500 text-[10px] text-center mt-0.5">{progress}%</p>
                    </div>
                  )}

                  {/* Ações */}
                  <div className="flex items-center gap-1 flex-shrink-0">
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
    </div>
  )
}
