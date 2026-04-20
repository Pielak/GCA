import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { GitBranch, Check, AlertTriangle, Loader2, RefreshCw, Trash2, Eye, EyeOff, Shield } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface GitStatus {
  connected: boolean
  provider: string | null
  repository_url: string | null
  branch: string | null
  last_verified: string | null
  last_commit_at: string | null
  // DT-026: outros projetos apontando para o mesmo repo. Se preenchido,
  // há violação de compartimentalização (contrato §2.2) — GP deve
  // desconectar ou apontar para repo isolado.
  shared_with?: string[]
}

const PROVIDER_OPTIONS = [
  { value: 'github', label: 'GitHub' },
  { value: 'gitlab', label: 'GitLab' },
  { value: 'bitbucket', label: 'Bitbucket' },
]

export function RepositoryPage() {
  const { id: projectId } = useParams<{ id: string }>()
  // O badge ✓/○ da aba Questionário + barra de progresso em Configurações
  // dependem de `useSetupStatus`. React Query faz cache por 30s — quando
  // conectamos/desconectamos repo, temos que invalidar explicitamente,
  // senão o GP vê "2/3 passos" mesmo após configurar.
  const queryClient = useQueryClient()
  const invalidateSetup = () => {
    queryClient.invalidateQueries({ queryKey: ['project-setup-status', projectId] })
  }
  const [status, setStatus] = useState<GitStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [verifying, setVerifying] = useState(false)

  // Form
  const [provider, setProvider] = useState('github')
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [pat, setPat] = useState('')
  const [showPat, setShowPat] = useState(false)

  // Toast
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const loadStatus = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/git/status`)
      setStatus(res.data)
      if (res.data.connected) {
        setProvider(res.data.provider || 'github')
        setRepoUrl(res.data.repository_url || '')
        setBranch(res.data.branch || 'main')
      }
    } catch {
      setStatus({ connected: false, provider: null, repository_url: null, branch: null, last_verified: null, last_commit_at: null })
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadStatus() }, [loadStatus])

  const handleConnect = async () => {
    if (!repoUrl.trim() || !pat.trim()) {
      showToast('Preencha a URL do repositório e o token de acesso', 'error')
      return
    }
    setSaving(true)
    try {
      await apiClient.post(`/projects/${projectId}/git/connect`, {
        provider,
        repository_url: repoUrl.trim(),
        pat: pat.trim(),
        default_branch: branch.trim() || 'main',
      })
      showToast('Repositório conectado com sucesso', 'success')
      setPat('')
      await loadStatus()
      invalidateSetup()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao conectar repositório', 'error')
    }
    setSaving(false)
  }

  const handleVerify = async () => {
    setVerifying(true)
    try {
      const res = await apiClient.post(`/projects/${projectId}/git/verify`)
      if (res.data.success) {
        showToast('Conexão verificada com sucesso', 'success')
      } else {
        showToast(res.data.message || 'Falha na verificação', 'error')
      }
      await loadStatus()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro na verificação', 'error')
    }
    setVerifying(false)
  }

  const handleDisconnect = async () => {
    if (!confirm('Tem certeza que deseja desconectar o repositório? Esta ação não apaga dados do repositório.')) return
    try {
      await apiClient.delete(`/projects/${projectId}/git/disconnect`)
      showToast('Repositório desconectado', 'success')
      setRepoUrl('')
      setPat('')
      setBranch('main')
      await loadStatus()
      invalidateSetup()
    } catch (err: unknown) {
      showToast(getErrorMessage(err) || 'Erro ao desconectar', 'error')
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  const isConnected = status?.connected === true

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold text-slate-100">Repositório do Projeto</h2>
        <p className="text-slate-500 text-sm mt-0.5">
          O repositório é a fonte de verdade do projeto — artefatos, documentação e código gerado são armazenados aqui.
        </p>
      </div>

      {/* Alerta bloqueante */}
      {!isConnected && (
        <div className="bg-red-900/20 border border-red-800/40 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-red-300 text-sm font-semibold">Repositório não configurado — Bloqueante</p>
            <p className="text-red-400/80 text-xs mt-1">
              O projeto não pode avançar sem um repositório configurado. Configure abaixo para desbloquear
              as seções de Ingestão, Gatekeeper, Arguidor e Geração de Código.
            </p>
          </div>
        </div>
      )}

      {/* Alerta de compartilhamento — viola compartimentalização §2.2.
          Só aparece quando o repo deste projeto também está conectado em
          outros projetos. Casos existentes (criados antes do fix DT-026). */}
      {isConnected && (status?.shared_with?.length ?? 0) > 0 && (
        <div className="bg-amber-900/20 border border-amber-500/40 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-amber-200 text-sm font-semibold">
              Repositório compartilhado com outro projeto — compartimentalização quebrada
            </p>
            <p className="text-amber-200/80 text-xs mt-1 leading-snug">
              Este repositório também está conectado ao(s) projeto(s):{' '}
              <span className="font-semibold text-amber-100">
                {status!.shared_with!.join(', ')}
              </span>.
              Isso viola o contrato §2.2 (isolamento entre projetos) — código, docs e
              deliverables gerados por um projeto ficam visíveis para a equipe do outro
              via commits do GCA.
            </p>
            <p className="text-amber-200/80 text-xs mt-2 leading-snug">
              <span className="font-semibold">Correção:</span> desconecte este projeto do repositório
              (botão lixeira ao lado) e aponte para um repositório dedicado,
              ou desconecte o outro projeto se este for o dono correto.
            </p>
          </div>
        </div>
      )}

      {/* Status atual */}
      {isConnected && (
        <div className="bg-emerald-900/20 border border-emerald-800/40 rounded-xl p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-900/40 border border-emerald-700/40 flex items-center justify-center">
                <Check className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-emerald-300 text-sm font-semibold">Repositório Conectado</p>
                <p className="text-slate-400 text-xs mt-0.5">{status.repository_url}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleVerify}
                disabled={verifying}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded-lg hover:bg-slate-700 transition-colors"
              >
                {verifying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                Verificar Conexão
              </button>
              <button
                onClick={handleDisconnect}
                className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                title="Desconectar repositório"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
            <div>
              <span className="text-slate-500 text-xs">Provider</span>
              <p className="text-slate-200 text-sm capitalize">{status.provider}</p>
            </div>
            <div>
              <span className="text-slate-500 text-xs">Branch Principal</span>
              <p className="text-slate-200 text-sm">{status.branch}</p>
            </div>
            <div>
              <span className="text-slate-500 text-xs">Última Verificação</span>
              <p className="text-slate-200 text-sm">{status.last_verified ? new Date(status.last_verified).toLocaleString('pt-BR') : '—'}</p>
            </div>
            <div>
              <span className="text-slate-500 text-xs">Último Commit</span>
              <p className="text-slate-200 text-sm">{status.last_commit_at ? new Date(status.last_commit_at).toLocaleString('pt-BR') : '—'}</p>
            </div>
          </div>
        </div>
      )}

      {/* Formulário de configuração */}
      {!isConnected && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <h3 className="text-slate-200 text-sm font-semibold flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-violet-400" />
            Configurar Repositório
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-slate-400 text-xs block mb-1">Provider</label>
              <select
                value={provider}
                onChange={e => setProvider(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-600"
              >
                {PROVIDER_OPTIONS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Branch Principal</label>
              <input
                value={branch}
                onChange={e => setBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
              />
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs block mb-1">URL do Repositório</label>
            <input
              value={repoUrl}
              onChange={e => setRepoUrl(e.target.value)}
              placeholder="https://github.com/sua-org/seu-projeto"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
            />
          </div>

          <div>
            <label className="text-slate-400 text-xs block mb-1">Token de Acesso (PAT)</label>
            <div className="relative">
              <input
                type={showPat ? 'text' : 'password'}
                value={pat}
                onChange={e => setPat(e.target.value)}
                placeholder="ghp_... ou glpat-..."
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-600"
              />
              <button
                type="button"
                onClick={() => setShowPat(!showPat)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showPat ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-slate-600 text-xs mt-1">O token deve ter permissão de leitura e escrita. É armazenado criptografado.</p>
          </div>

          <div className="flex justify-end">
            <button
              onClick={handleConnect}
              disabled={!repoUrl.trim() || !pat.trim() || saving}
              className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
              Conectar e Verificar
            </button>
          </div>
        </div>
      )}

      {/* Boas práticas */}
      <div className="bg-slate-900/50 border border-slate-800/50 rounded-xl p-5">
        <h3 className="text-slate-300 text-sm font-semibold mb-3">Boas Práticas</h3>
        <ul className="space-y-2 text-slate-500 text-xs">
          <li className="flex items-start gap-2"><span className="text-violet-400 mt-0.5">•</span>Use branch protection na branch principal (main/master)</li>
          <li className="flex items-start gap-2"><span className="text-violet-400 mt-0.5">•</span>Crie um token com escopo mínimo necessário (read/write no repositório)</li>
          <li className="flex items-start gap-2"><span className="text-violet-400 mt-0.5">•</span>Mantenha README atualizado com a estrutura do projeto</li>
          <li className="flex items-start gap-2"><span className="text-violet-400 mt-0.5">•</span>O GCA criará pastas para documentação, código e testes automaticamente</li>
        </ul>
      </div>
    </div>
  )
}
