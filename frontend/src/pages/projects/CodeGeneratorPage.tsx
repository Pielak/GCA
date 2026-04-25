import { useState, useEffect, useCallback, useRef } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import { useParams, useSearchParams, useOutletContext } from 'react-router-dom'
import {
  Code2, Play, Save, GitBranch, GitCommit, Loader2, CheckCircle2, AlertTriangle,
  FolderTree, ChevronRight, ChevronDown, FileCode, FileText, File,
  PanelRightOpen, PanelRightClose, Plus, FolderPlus, TestTube2,
  Shield, RefreshCw, X, Eye, Clock
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { useCodeGenProgressStore } from '@/stores/codeGenProgressStore'
import { OperationBar, PulseIndicator } from '@/components/ui/PipelineProgress'
import { getErrorMessage, getErrorStatus } from '@/lib/errors'

/**
 * Render seguro de campos do STACK_RECOMMENDATION do OCG. Versões mais novas
 * do Arguidor podem retornar OBJETO rico (ex: `database.primary` virou
 * {engine, profile, extensions_recommended, configuration, rationale}).
 * Render direto de objeto explode com React error #31. Aqui extraímos
 * heuristicamente o nome principal pra exibição compacta no header.
 */
function stackFieldText(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(stackFieldText).filter(Boolean).join(', ')
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>
    // Tenta nomes canônicos comuns na ordem de preferência
    for (const key of ['engine', 'name', 'primary', 'framework', 'language', 'value', 'label']) {
      const v = obj[key]
      if (typeof v === 'string') return v
      if (typeof v === 'number') return String(v)
    }
    return ''
  }
  return ''
}

/**
 * DT-089 — Formatter de erros do CodeGenerator com mensagens amigáveis
 * por contexto. Trata 403 de RBAC especificamente (causa mais comum
 * quando user não tem code:write) + fallback genérico pra outros erros.
 */
function formatCodeGenError(err: unknown, action: string): string {
  const status = getErrorStatus(err)
  const msg = getErrorMessage(err)
  if (status === 403) {
    // Backend manda detail claro em PT-BR; aumentamos com dica do fluxo:
    return (
      `${msg}\n\n` +
      `Projetos pequenos podem atribuir múltiplos papéis à mesma pessoa ` +
      `(gp + dev + qa). Peça ao Admin pra adicioná-lo como 'dev' no projeto ` +
      `via Admin → Projetos → Membros.`
    )
  }
  if (status === 400 && /git/i.test(msg)) {
    return (
      `${msg}\n\n` +
      `Configure o repositório Git do projeto em Admin → Projetos antes de ${action}.`
    )
  }
  if (status === 409) {
    return (
      `${msg}\n\n` +
      `Aguarde a outra operação terminar e tente novamente.`
    )
  }
  return `Falha ao ${action}: ${msg}`
}

// ============================================================================
// Tipos
// ============================================================================

interface GitFile {
  name: string
  path: string
  type: 'file' | 'dir'
  size?: number
  children?: GitFile[]
  status?: 'complete' | 'todo' | 'nmi'
}

interface AIReviewResult {
  approved: boolean
  gaps: string[]
  errors: string[]
  warnings: string[]
  suggestions: string[]
}

// ============================================================================
// File Icon Helper
// ============================================================================

function FileIcon({ name, type }: { name: string; type: string }) {
  if (type === 'dir') return <FolderTree className="w-4 h-4 text-amber-400" />
  const ext = name.split('.').pop()?.toLowerCase() || ''
  if (['py', 'ts', 'js', 'java', 'go', 'rs', 'cs'].includes(ext))
    return <FileCode className="w-4 h-4 text-violet-400" />
  if (['md', 'txt', 'json', 'yaml', 'yml'].includes(ext))
    return <FileText className="w-4 h-4 text-blue-400" />
  if (['test', 'spec'].some(t => name.includes(t)))
    return <TestTube2 className="w-4 h-4 text-emerald-400" />
  return <File className="w-4 h-4 text-slate-400" />
}

// ============================================================================
// Tree Node (recursivo)
// ============================================================================

function TreeNode({
  node, depth, onSelect, selectedPath, itemStatus
}: {
  node: GitFile; depth: number; onSelect: (path: string) => void; selectedPath: string;
  // MVP 30 — status de geração por path (scaffold item-a-item)
  itemStatus?: Map<string, 'pending' | 'generating' | 'complete' | 'error'>
}) {
  const [expanded, setExpanded] = useState(depth < 2)

  if (node.type === 'dir') {
    return (
      <div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-1.5 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800/60 rounded transition-colors"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          <FileIcon name={node.name} type="dir" />
          <span className="truncate">{node.name}</span>
        </button>
        {expanded && node.children?.map(child => (
          <TreeNode key={child.path} node={child} depth={depth + 1} onSelect={onSelect} selectedPath={selectedPath} itemStatus={itemStatus} />
        ))}
      </div>
    )
  }

  const isSelected = node.path === selectedPath
  // MVP 30 — ícone derivado do status de geração (scaffold item-a-item)
  const genStatus = itemStatus?.get(node.path)
  let statusIcon: JSX.Element | null = null
  if (genStatus === 'pending') {
    statusIcon = <Clock className="w-3 h-3 text-slate-500 flex-shrink-0" />
  } else if (genStatus === 'generating') {
    statusIcon = <Loader2 className="w-3 h-3 text-violet-400 animate-spin flex-shrink-0" />
  } else if (genStatus === 'complete') {
    statusIcon = <CheckCircle2 className="w-3 h-3 text-emerald-400 flex-shrink-0" />
  } else if (genStatus === 'error') {
    statusIcon = <AlertTriangle className="w-3 h-3 text-red-400 flex-shrink-0" />
  }

  return (
    <button
      onClick={() => onSelect(node.path)}
      className={`w-full flex items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors ${
        isSelected ? 'bg-violet-600/20 text-violet-300' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-300'
      }`}
      style={{ paddingLeft: `${depth * 12 + 20}px` }}
    >
      <FileIcon name={node.name} type="file" />
      <span className="truncate">{node.name}</span>
      {statusIcon}
      {node.status === 'nmi' && <span className="text-[10px] px-1 py-0.5 rounded bg-red-500/20 text-red-400 ml-1 flex-shrink-0">NMI</span>}
      {node.status === 'todo' && <span className="text-[10px] px-1 py-0.5 rounded bg-amber-500/20 text-amber-400 ml-1 flex-shrink-0">TODO</span>}
    </button>
  )
}

// ============================================================================
// AI Review Panel
// ============================================================================

function AIReviewPanel({ review, onDismiss }: { review: AIReviewResult; onDismiss: () => void }) {
  return (
    <div className={`border rounded-lg p-4 mb-4 ${review.approved ? 'bg-emerald-900/20 border-emerald-700/40' : 'bg-red-900/20 border-red-700/40'}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className={`w-5 h-5 ${review.approved ? 'text-emerald-400' : 'text-red-400'}`} />
          <h3 className={`font-semibold text-sm ${review.approved ? 'text-emerald-300' : 'text-red-300'}`}>
            {review.approved ? 'Código Aprovado pela IA' : 'Revisão Necessária'}
          </h3>
        </div>
        <button onClick={onDismiss} className="text-slate-500 hover:text-slate-300"><X className="w-4 h-4" /></button>
      </div>

      {review.errors.length > 0 && (
        <div className="mb-2">
          <p className="text-xs text-red-400 font-medium mb-1">Erros ({review.errors.length})</p>
          {review.errors.map((e, i) => (
            <p key={i} className="text-xs text-red-300 ml-3">• {e}</p>
          ))}
        </div>
      )}
      {review.gaps.length > 0 && (
        <div className="mb-2">
          <p className="text-xs text-amber-400 font-medium mb-1">Gaps ({review.gaps.length})</p>
          {review.gaps.map((g, i) => (
            <p key={i} className="text-xs text-amber-300 ml-3">• {g}</p>
          ))}
        </div>
      )}
      {review.warnings.length > 0 && (
        <div className="mb-2">
          <p className="text-xs text-amber-400 font-medium mb-1">Avisos ({review.warnings.length})</p>
          {review.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-300 ml-3">• {w}</p>
          ))}
        </div>
      )}
      {review.suggestions.length > 0 && (
        <div className="mb-2">
          <p className="text-xs text-blue-400 font-medium mb-1">Sugestões ({review.suggestions.length})</p>
          {review.suggestions.map((s, i) => (
            <p key={i} className="text-xs text-blue-300 ml-3">• {s}</p>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Componente Principal
// ============================================================================

export function CodeGeneratorPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { user } = useAuthStore()
  const outletProjectCtx = useOutletContext<{ projectName?: string } | null>()
  const projectName = outletProjectCtx?.projectName || 'Projeto'

  // Sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [treeLoading, setTreeLoading] = useState(false)
  const [fileTree, setFileTree] = useState<GitFile[]>([])

  // Editor state
  const [selectedFile, setSelectedFile] = useState<string>('')
  const [fileContent, setFileContent] = useState<string>('')
  const [originalContent, setOriginalContent] = useState<string>('')
  const [fileLoading, setFileLoading] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)

  // New file
  const [showNewFile, setShowNewFile] = useState(false)
  const [newFilePath, setNewFilePath] = useState('')

  // Save / AI Review
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [aiReview, setAiReview] = useState<AIReviewResult | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  // Validation state
  type ValIssue = { line: number; column: number; message: string; severity: string }
  const [validationErrors, setValidationErrors] = useState<ValIssue[]>([])
  const [validationBlocked, setValidationBlocked] = useState(false)
  const [validating, setValidating] = useState(false)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null)

  // Run tests
  const [runningTests, setRunningTests] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  // Permissions
  const isDevOrQA = true // TODO: check user.role in project (papéis canônicos: dev, qa)
  const isTestFile = selectedFile.includes('test') || selectedFile.includes('spec')
  const canEdit = isTestFile ? isDevOrQA : isDevOrQA

  // Backlog item auto-generation
  const [searchParams] = useSearchParams()
  const backlogItemId = searchParams.get('backlog_item')
  const [generating, setGenerating] = useState(false)
  const [generatedFromBacklog, setGeneratedFromBacklog] = useState(false)

  // Scaffold state
  const [scaffoldFiles, setScaffoldFiles] = useState<Map<string, { content: string; status: string }>>(new Map())
  // MVP 30 — status por item do scaffold (pending|generating|complete|error)
  const [scaffoldItemStatus, setScaffoldItemStatus] = useState<Map<string, 'pending' | 'generating' | 'complete' | 'error'>>(new Map())
  const [scaffoldPlanSummary, setScaffoldPlanSummary] = useState<string | null>(null)
  const [scaffoldGenerating, setScaffoldGenerating] = useState(false)
  const [scaffoldSummary, setScaffoldSummary] = useState<string | null>(null)
  // MVP 3: preview-apply. pendingApply=true quando há files gerados ainda
  // não commitados (padrão novo desde backend /scaffold default=dry_run).
  const [scaffoldPendingApply, setScaffoldPendingApply] = useState(false)
  const [scaffoldApplying, setScaffoldApplying] = useState(false)
  const [scaffoldRetrying, setScaffoldRetrying] = useState(false)
  const [scaffoldRegenInvalid, setScaffoldRegenInvalid] = useState(false)
  // DT-043: warning de adequação do provider (contrato §7 + §6.2).
  // null = provider adequado; objeto = média/baixa criticidade.
  const [providerWarning, setProviderWarning] = useState<
    { provider: string; recommended: string; reason: string } | null
  >(null)

  // OCG context para referência
  const [ocgContext, setOcgContext] = useState<any>(null)

  useEffect(() => {
    if (!projectId) return
    apiClient.get(`/projects/${projectId}/ocg`).then(res => {
      const ocg = res.data?.ocg
      if (ocg?.ocg_data) {
        const data = typeof ocg.ocg_data === 'string' ? JSON.parse(ocg.ocg_data) : ocg.ocg_data
        setOcgContext({
          stack: data.STACK_RECOMMENDATION || {},
          architecture: data.ARCHITECTURE_OVERVIEW || {},
          testing: data.TESTING_REQUIREMENTS || {},
          overall_score: ocg.overall_score,
          status: ocg.status,
        })
      }
    }).catch(() => {})
  }, [projectId])

  // Camada A do scaffold (2026-04-25) — espelha snapshot do store global.
  // O store agora pollá `/scaffold/runs/{run_id}` e mantém `snapshot` com
  // os items + content já gerados. Sobrevive a refresh/F5/queda de rede via
  // localStorage. Mapeamos o snapshot canônico pros states locais da Page.
  const storeActive = useCodeGenProgressStore((s) => s.active)
  const storeProjectId = useCodeGenProgressStore((s) => s.projectId)
  const storeSnapshot = useCodeGenProgressStore((s) => s.snapshot)
  const storeFinishedAt = useCodeGenProgressStore((s) => s.finishedAt)
  const storeFetchItemContent = useCodeGenProgressStore((s) => s.fetchItemContent)
  const storeHydrate = useCodeGenProgressStore((s) => s.hydrateForProject)

  // Hidratação: ao montar, se há run persistida no localStorage, retoma poll
  useEffect(() => {
    if (!projectId) return
    storeHydrate(projectId, projectName || projectId)
  }, [projectId, projectName, storeHydrate])

  useEffect(() => {
    if (!projectId || storeProjectId !== projectId || !storeSnapshot) return

    setScaffoldGenerating(storeActive)
    setScaffoldPlanSummary(storeSnapshot.plan_summary || '')

    // Status canônico do server: pending/generating/done/failed/skipped
    // Mapeia pro tipo legado da Page: pending/generating/complete/error
    const mapStatus = (s: string): 'pending' | 'generating' | 'complete' | 'error' => {
      if (s === 'done') return 'complete'
      if (s === 'failed' || s === 'skipped') return 'error'
      if (s === 'generating') return 'generating'
      return 'pending'
    }

    const itemStatusMap = new Map<string, 'pending' | 'generating' | 'complete' | 'error'>()
    for (const it of storeSnapshot.items) {
      itemStatusMap.set(it.path, mapStatus(it.status))
    }
    setScaffoldItemStatus(itemStatusMap)

    // Tree: usa items do snapshot (com flag has_content); content é lazy-loaded
    const treeItems = storeSnapshot.items.map(it => ({
      path: it.path,
      content: '',
      status: mapStatus(it.status),
    }))
    setFileTree(buildTreeWithStatus(treeItems))

    // Quando termina, summary + libera apply
    const isCompleted = storeSnapshot.status === 'completed'
    if (!storeActive && storeFinishedAt && isCompleted) {
      const doneCount = storeSnapshot.completed_items
      setScaffoldSummary(
        `${storeSnapshot.plan_summary || `Scaffold com ${storeSnapshot.total_items} arquivos`} — ${doneCount} prontos pra commit. Clique em "Aplicar no Git".`,
      )
      setScaffoldPendingApply(doneCount > 0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, storeActive, storeProjectId, storeSnapshot, storeFinishedAt])

  // Quando user clica em arquivo no tree, carrega content sob demanda do server
  const loadItemContentOnDemand = useCallback(async (path: string) => {
    if (!storeSnapshot) return
    const item = storeSnapshot.items.find(i => i.path === path)
    if (!item || !item.has_content) return
    const content = await storeFetchItemContent(item.id)
    if (content !== null) {
      setScaffoldFiles((prev) => {
        const next = new Map(prev)
        next.set(path, { content, status: item.status === 'done' ? 'complete' : item.status })
        return next
      })
      if (selectedFile === path) {
        setFileContent(content)
        setOriginalContent(content)
        setHasChanges(false)
      }
    }
  }, [storeSnapshot, storeFetchItemContent, selectedFile])

  // ================================================================
  // Gerar Scaffold do Projeto
  // ================================================================

  // Camada A — pipeline persistido via Celery + poll (sobrevive a refresh,
  // queda de rede, queda de eletricidade). Page só dispara start; o resto
  // do ciclo (planning, generating, completed) é gerenciado pelo store.
  const progressStore = useCodeGenProgressStore()

  const handleGenerateScaffold = async () => {
    if (!projectId || progressStore.active) return
    if (scaffoldFiles.size > 0 && !confirm('Isso substituirá o preview atual. Continuar?')) return

    setScaffoldSummary(null)
    setScaffoldFiles(new Map())
    setScaffoldItemStatus(new Map())
    setScaffoldPlanSummary(null)
    setScaffoldPendingApply(false)

    try {
      await progressStore.startScaffold(projectId, projectName)
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 'gerar scaffold'))
    }
  }

  // Camada A — apply server-side: o conteúdo dos arquivos JÁ está em
  // scaffold_run_items.content. POST /scaffold/runs/{id}/apply pega só
  // os items done e commita. Sem payload, sem dependência do estado da
  // page. Sobrevive a refresh entre completed e applied.
  const handleApplyScaffold = async () => {
    if (!projectId || !progressStore.runId || !progressStore.snapshot) return
    if (progressStore.snapshot.status !== 'completed') {
      alert('Aguarde a geração terminar antes de aplicar.')
      return
    }
    const committable = progressStore.snapshot.completed_items
    if (!confirm(`Aplicar ${committable} arquivo(s) no Git? Cada um vira um commit individual.`)) return

    setScaffoldApplying(true)
    try {
      // MVP-E: apply agora é assíncrono. Backend retorna 202 e a task
      // Celery commita os 164 arquivos em background. UI reage ao status
      // 'applying' via polling — apply_committed/apply_failed sobem
      // incrementalmente; quando vira 'applied', summary final aparece.
      const result = await progressStore.apply()
      if (result === null) {
        const msg = useCodeGenProgressStore.getState().errorMessage || 'Falha ao enfileirar apply.'
        alert(msg)
        return
      }
      setScaffoldSummary(
        'Apply enfileirado — backend está commitando arquivos. Acompanhe o progresso na janela flutuante de geração.',
      )
      setScaffoldPendingApply(false)
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 'enfileirar apply'))
    } finally {
      setScaffoldApplying(false)
    }
  }

  const handleRegenerateInvalid = async () => {
    if (!progressStore.runId || !progressStore.snapshot) return
    if (!confirm(
      'Validar e regenerar arquivos com docstring missing?\n\n' +
      'Vai detectar arquivos que falhariam no commit e regerar apenas esses, ' +
      'preservando os já válidos. Pode demorar alguns minutos.',
    )) return

    setScaffoldRegenInvalid(true)
    try {
      const result = await progressStore.regenerateInvalid()
      if (result === null) {
        const msg = useCodeGenProgressStore.getState().errorMessage || 'Falha ao regenerar.'
        alert(msg)
        return
      }
      if (result.items_marked_invalid === 0) {
        setScaffoldSummary(
          `Nenhum arquivo inválido detectado — ${result.items_done_preserved} arquivos OK.`,
        )
      } else {
        setScaffoldSummary(
          `Regenerando ${result.items_marked_invalid} arquivo(s) inválido(s); ${result.items_done_preserved} preservados.`,
        )
        setScaffoldPendingApply(false)
      }
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 'regenerar inválidos'))
    } finally {
      setScaffoldRegenInvalid(false)
    }
  }

  const handleRetryFailedScaffold = async () => {
    if (!progressStore.runId || !progressStore.snapshot) return
    const failed = progressStore.snapshot.failed_items
    if (failed === 0) {
      alert('Nenhum item failed pra re-tentar.')
      return
    }
    if (!confirm(
      `Re-tentar ${failed} item(s) que falharam? ` +
      `Os ${progressStore.snapshot.completed_items} já gerados são preservados — ` +
      `só os falhados são regerados.`,
    )) return

    setScaffoldRetrying(true)
    try {
      const result = await progressStore.retryFailed()
      if (result === null) {
        const msg = useCodeGenProgressStore.getState().errorMessage || 'Falha ao re-tentar items.'
        alert(msg)
        return
      }
      setScaffoldSummary(
        `Re-tentando ${result.items_reset} item(s); ${result.items_done_preserved} preservados.`,
      )
      setScaffoldPendingApply(false)
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 're-tentar items'))
    } finally {
      setScaffoldRetrying(false)
    }
  }

  // ================================================================
  // Auto-generate from backlog item
  // ================================================================
  useEffect(() => {
    if (!backlogItemId || !projectId || generatedFromBacklog) return

    const autoGenerate = async () => {
      setGenerating(true)
      try {
        const res = await apiClient.post(`/projects/${projectId}/backlog/${backlogItemId}/generate-code`)
        setFileContent(res.data.generated_code || '')
        setNewFilePath(res.data.title || 'generated_module')
        setGeneratedFromBacklog(true)
        setHasChanges(true)
      } catch (err: unknown) {
        console.error('Erro ao gerar código:', err)
      } finally {
        setGenerating(false)
      }
    }

    autoGenerate()
  }, [backlogItemId, projectId, generatedFromBacklog])

  // ================================================================
  // Load file tree
  // ================================================================

  const loadTree = useCallback(async () => {
    if (!projectId) return

    // Se já temos scaffold gerado (cache local), usar ele
    if (scaffoldFiles.size > 0) return

    // Helper: checa "tem snapshot do scaffold" no momento exato da decisão
    // de setFileTree. Releitura via getState() pega o estado atual mesmo
    // se hidratação assíncrona populou o snapshot enquanto loadTree estava
    // bloqueado em I/O (git/status + git/tree, ~150-200ms).
    const hasScaffoldSnapshot = () => {
      const s = useCodeGenProgressStore.getState().snapshot
      return !!(s && Array.isArray(s.items) && s.items.length > 0)
    }

    // Guard inicial — se já tem snapshot, nem chama git tree.
    if (hasScaffoldSnapshot()) return

    setTreeLoading(true)
    try {
      const res = await apiClient.get(`/projects/${projectId}/git/status`)
      if (hasScaffoldSnapshot()) return  // snapshot chegou enquanto rodávamos git/status
      if (res.data?.connected) {
        try {
          const treeRes = await apiClient.get(`/projects/${projectId}/git/tree`)
          if (hasScaffoldSnapshot()) return  // idem após git/tree
          const entries = (treeRes.data?.tree || []) as Array<{ path: string; type: string }>
          const filePaths = entries.filter(e => e.type === 'file').map(e => e.path)
          if (filePaths.length > 0) {
            setFileTree(buildTree(filePaths))
          } else {
            setFileTree(getDefaultTree())
          }
        } catch {
          if (hasScaffoldSnapshot()) return
          setFileTree(getDefaultTree())
        }
      } else {
        setFileTree(getDefaultTree())
      }
    } catch {
      if (hasScaffoldSnapshot()) return
      setFileTree(getDefaultTree())
    } finally {
      setTreeLoading(false)
    }
  }, [projectId, scaffoldFiles.size])

  useEffect(() => { loadTree() }, [loadTree])

  // ================================================================
  // Load file content
  // ================================================================

  const handleSelectFile = async (path: string) => {
    if (hasChanges && !confirm('Você tem alterações não salvas. Deseja descartar?')) return
    setSelectedFile(path)
    setFileContent('')
    setOriginalContent('')
    setHasChanges(false)
    setAiReview(null)
    setSaveSuccess(false)

    // Verificar se o arquivo está no scaffold gerado (cache local)
    const scaffoldFile = scaffoldFiles.get(path)
    if (scaffoldFile) {
      setFileContent(scaffoldFile.content)
      setOriginalContent(scaffoldFile.content)
      return
    }

    // Camada A — content lazy-load: se há item no snapshot e tem content,
    // busca do server. Evita carregar ~200 arquivos × ~5kB no payload do GET runs.
    let snapshot = useCodeGenProgressStore.getState().snapshot
    let runItem = snapshot?.items.find(i => i.path === path)

    // Defesa contra snapshot stale (race entre hidratação inicial e mudanças
    // server-side — ex: retry-failed terminou, mas o snapshot Zustand foi
    // tirado durante a janela entre dois poll ticks). Se o item não foi
    // achado OU has_content=false, força refresh do snapshot antes de desistir.
    if (!runItem || !runItem.has_content) {
      try {
        await useCodeGenProgressStore.getState().refresh()
      } catch { /* ignore — segue pro fallback Git */ }
      snapshot = useCodeGenProgressStore.getState().snapshot
      runItem = snapshot?.items.find(i => i.path === path)
    }

    if (runItem && runItem.has_content) {
      setFileLoading(true)
      try {
        // Busca direta + setFileContent imediato. Antes, chamávamos
        // loadItemContentOnDemand que faz `if (selectedFile === path)
        // setFileContent`, mas selectedFile no closure do useCallback é
        // o valor ANTERIOR (setSelectedFile foi enfileirado linhas acima
        // mas ainda não rendeu). Resultado: conteúdo era escrito só no
        // cache, mas o editor mostrava o placeholder vazio até o user
        // sair e voltar.
        const content = await storeFetchItemContent(runItem.id)
        if (content !== null) {
          setScaffoldFiles((prev) => {
            const next = new Map(prev)
            next.set(path, {
              content,
              status: runItem.status === 'done' ? 'complete' : runItem.status,
            })
            return next
          })
          setFileContent(content)
          setOriginalContent(content)
          setHasChanges(false)
        }
      } finally {
        setFileLoading(false)
      }
      return
    }

    setFileLoading(true)
    try {
      // Tentar buscar direto do repo Git (arquivos commitados pelo CodeGen)
      const res = await apiClient.get(`/projects/${projectId}/git/file`, {
        params: { path },
      })
      const content = res.data?.content || ''
      setFileContent(content)
      setOriginalContent(content)
    } catch {
      // Fallback: tentar /livedocs/content para docs markdown específicos
      try {
        const res2 = await apiClient.get(`/projects/${projectId}/livedocs/content`, {
          params: { path },
        })
        const content = res2.data?.content || ''
        setFileContent(content)
        setOriginalContent(content)
      } catch {
        setFileContent('// Arquivo ainda não existe. Escreva o conteúdo e salve.')
        setOriginalContent('')
      }
    } finally {
      setFileLoading(false)
    }
  }

  // ================================================================
  // AI Review before save
  // ================================================================

  const handleAIReviewAndSave = async () => {
    if (!fileContent.trim()) return
    setReviewing(true)
    setAiReview(null)

    try {
      // Chamar API de validação de código pela IA
      const res = await apiClient.post(`/code-generation/validate-provider`, {
        project_id: projectId,
        code: fileContent,
        file_path: selectedFile || newFilePath,
      })

      const review: AIReviewResult = res.data?.review || {
        approved: true, gaps: [], errors: [], warnings: [], suggestions: [],
      }
      setAiReview(review)

      // Se aprovado, salvar automaticamente
      if (review.approved) {
        await commitFile(selectedFile || newFilePath, fileContent)
      }
    } catch {
      // Se endpoint não disponível, salvar diretamente
      await commitFile(selectedFile || newFilePath, fileContent)
    } finally {
      setReviewing(false)
    }
  }

  // ================================================================
  // Commit file to Git
  // ================================================================

  const commitFile = async (path: string, content: string) => {
    setSaving(true)
    try {
      const commitMsg = hasChanges
        ? `[GCA] Atualiza ${path.split('/').pop()}`
        : `[GCA] Cria ${path.split('/').pop()}`

      await apiClient.post(`/projects/${projectId}/git/commit`, {
        file_path: path,
        content,
        message: commitMsg,
      })

      setOriginalContent(content)
      setHasChanges(false)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)

      if (showNewFile) {
        setShowNewFile(false)
        setNewFilePath('')
        loadTree()
      }
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 'salvar arquivo'))
    } finally {
      setSaving(false)
    }
  }

  // ================================================================
  // Validation + Save
  // ================================================================

  const applyMarkers = (errors: ValIssue[]) => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    if (!editor || !monaco) return
    const model = editor.getModel()
    if (!model) return
    const markers = errors.map(e => ({
      startLineNumber: e.line,
      startColumn: e.column,
      endLineNumber: e.line,
      endColumn: e.column + 10,
      message: e.message,
      severity: e.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
    }))
    monaco.editor.setModelMarkers(model, 'gca-validator', markers)
  }

  const handleReviewAndSave = async () => {
    const path = selectedFile || newFilePath
    if (!path) return
    setValidating(true)
    setValidationBlocked(false)
    try {
      const res = await apiClient.post('/code-generation/validate', {
        code: fileContent,
        path,
      })
      const issues = (res.data?.issues || []) as ValIssue[]
      setValidationErrors(issues)
      applyMarkers(issues)
      const hasError = issues.some(i => i.severity === 'error')
      if (hasError) {
        setValidationBlocked(true)
        alert(`Código com ${issues.length} problema(s). Corrija os erros sublinhados em vermelho antes de salvar.`)
        return
      }
      // Validou limpo — commita se houver mudanças, senão só confirma
      if (hasChanges) {
        await commitFile(path, fileContent)
      } else {
        setSaveSuccess(true)
        setTimeout(() => setSaveSuccess(false), 2500)
      }
      applyMarkers([])
      setValidationErrors([])
    } catch (err: unknown) {
      alert(getErrorMessage(err) || 'Falha ao validar código')
    } finally {
      setValidating(false)
    }
  }

  const detectLanguageForMonaco = (path: string): string => {
    if (!path) return 'plaintext'
    const lower = path.toLowerCase()
    if (lower.endsWith('.py')) return 'python'
    if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return 'typescript'
    if (lower.endsWith('.js') || lower.endsWith('.jsx') || lower.endsWith('.mjs')) return 'javascript'
    if (lower.endsWith('.json')) return 'json'
    if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml'
    if (lower.endsWith('.toml') || lower.endsWith('.ini')) return 'ini'
    if (lower.endsWith('.md')) return 'markdown'
    if (lower.endsWith('.go')) return 'go'
    if (lower.endsWith('.java')) return 'java'
    if (lower.endsWith('.sql')) return 'sql'
    if (lower.endsWith('.sh')) return 'shell'
    if (lower.endsWith('.html')) return 'html'
    if (lower.endsWith('.css') || lower.endsWith('.scss')) return 'css'
    if (lower.endsWith('.xml')) return 'xml'
    if (lower.endsWith('dockerfile')) return 'dockerfile'
    return 'plaintext'
  }

  // ================================================================
  // Force save (bypass AI review — com warning)
  // ================================================================

  const handleForceSave = async () => {
    if (!confirm('Salvar sem revisão da IA? Isso será registrado no audit log.')) return
    await commitFile(selectedFile || newFilePath, fileContent)
  }

  // ================================================================
  // Regenerate single file
  // ================================================================

  const [regenerating, setRegenerating] = useState(false)
  const [regenModalOpen, setRegenModalOpen] = useState(false)
  const [regenInstructions, setRegenInstructions] = useState('')

  const openRegenerateModal = () => {
    const path = selectedFile || newFilePath
    if (!path) return
    setRegenInstructions('')
    setRegenModalOpen(true)
  }

  const handleRegenerateFile = async () => {
    const path = selectedFile || newFilePath
    if (!path) return
    setRegenModalOpen(false)
    setRegenerating(true)
    try {
      const res = await apiClient.post('/code-generation/regenerate-file', {
        project_id: projectId,
        path,
        current_content: fileContent || null,
        instructions: regenInstructions.trim() || null,
      })
      const content = res.data?.content ?? ''
      setFileContent(content)
      setOriginalContent(content)
      setHasChanges(false)
      // Limpa markers antigos e estado de bloqueio
      applyMarkers([])
      setValidationErrors([])
      setValidationBlocked(false)
      if (res.data?.committed === false) {
        alert(`Gerado mas não commitado: ${res.data?.commit_error || 'erro desconhecido'}`)
      } else {
        setSaveSuccess(true)
        setTimeout(() => setSaveSuccess(false), 2500)
      }
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 'regenerar arquivo'))
    } finally {
      setRegenerating(false)
    }
  }

  // ================================================================
  // Run tests
  // ================================================================

  const handleRunTests = async () => {
    setRunningTests(true)
    setTestResult(null)
    try {
      const res = await apiClient.get(`/projects/${projectId}/modules/${selectedFile}/tests`)
      setTestResult(JSON.stringify(res.data, null, 2))
    } catch {
      setTestResult('Execução de testes será disponibilizada em versão futura.')
    } finally {
      setRunningTests(false)
    }
  }

  // ================================================================
  // Render
  // ================================================================

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] overflow-hidden">
      {/* Contexto OCG */}
      {ocgContext && (
        <div className="flex items-center gap-4 px-4 py-1.5 bg-slate-900/80 border-b border-slate-800 text-xs">
          <span className="text-slate-500">OCG:</span>
          {ocgContext.stack?.backend && (
            <span className="text-slate-400">Backend: <span className="text-blue-400">{stackFieldText(ocgContext.stack.backend.language)} {stackFieldText(ocgContext.stack.backend.framework)}</span></span>
          )}
          {ocgContext.stack?.frontend && (
            <span className="text-slate-400">Frontend: <span className="text-emerald-400">{stackFieldText(ocgContext.stack.frontend.framework)} {stackFieldText(ocgContext.stack.frontend.language)}</span></span>
          )}
          {ocgContext.stack?.database && (
            <span className="text-slate-400">DB: <span className="text-amber-400">{stackFieldText(ocgContext.stack.database.primary)}</span></span>
          )}
          <span className={`ml-auto px-1.5 py-0.5 rounded text-xs ${
            ocgContext.status === 'READY' ? 'bg-emerald-500/20 text-emerald-300' :
            ocgContext.status === 'NEEDS_REVIEW' ? 'bg-amber-500/20 text-amber-300' :
            'bg-red-500/20 text-red-300'
          }`}>{ocgContext.overall_score?.toFixed(1) || '—'}</span>
        </div>
      )}
      {/* Banner de geracao em andamento */}
      {generating && (
        <div className="px-4 py-3 border-b border-edge-brand">
          <OperationBar
            message="Gerando código via IA"
            detail="Analisando OCG e criando módulo a partir do backlog"
            status="running"
          />
        </div>
      )}

      {/* Banner scaffold em andamento */}
      {scaffoldGenerating && scaffoldItemStatus.size === 0 && (
        <div className="px-4 py-3 border-b border-emerald-700/40">
          <OperationBar
            message="Planejando scaffold"
            detail="Consultando OCG, stack e módulos pra listar arquivos..."
            status="running"
          />
        </div>
      )}

      {/* MVP 30 — progress bar item-a-item */}
      {scaffoldGenerating && scaffoldItemStatus.size > 0 && (() => {
        const statuses = Array.from(scaffoldItemStatus.values())
        const done = statuses.filter(s => s === 'complete').length
        const errors = statuses.filter(s => s === 'error').length
        const total = statuses.length
        const pct = Math.max(0, Math.min(100, (done / Math.max(total, 1)) * 100))
        return (
          <div className="px-4 py-3 border-b border-violet-700/40 bg-slate-900/40">
            <div className="flex items-center justify-between text-xs text-slate-300 mb-1.5">
              <span className="flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 text-violet-400 animate-spin" />
                <span>Gerando arquivo-a-arquivo: <strong className="text-violet-300">{done} / {total}</strong></span>
                {errors > 0 && <span className="text-red-400 ml-2">{errors} erro(s)</span>}
              </span>
              {scaffoldPlanSummary && (
                <span className="text-[10px] text-slate-500 truncate ml-2 max-w-[50%]">{scaffoldPlanSummary}</span>
              )}
            </div>
            <div className="h-1 bg-slate-800 rounded overflow-hidden">
              <div
                className="h-full bg-violet-500 transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })()}

      {/* DT-043: banner de adequação do provider */}
      {providerWarning && !scaffoldGenerating && (
        <div className="flex items-start gap-3 px-4 py-2 bg-amber-900/20 border-b border-amber-700/40">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-xs text-amber-200 leading-snug">
            <strong className="text-amber-300">Provider {providerWarning.provider} pode não ser adequado pra CodeGen.</strong>{' '}
            {providerWarning.reason}{' '}
            <span className="text-amber-400/80">Recomendado: {providerWarning.recommended}.</span>
          </div>
        </div>
      )}

      {/* Resumo do scaffold gerado */}
      {scaffoldSummary && !scaffoldGenerating && (
        <div className="flex items-center gap-3 px-4 py-2 bg-emerald-900/20 border-b border-emerald-700/30">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span className="text-xs text-emerald-300">{scaffoldSummary}</span>
          <span className="text-xs text-slate-500 ml-auto">
            {scaffoldFiles.size} arquivos |
            {' '}{Array.from(scaffoldFiles.values()).filter(f => f.status === 'complete').length} completos,
            {' '}{Array.from(scaffoldFiles.values()).filter(f => f.status === 'todo').length} TODO,
            {' '}{Array.from(scaffoldFiles.values()).filter(f => f.status === 'nmi').length} NMI
          </span>
          <button
            onClick={() => { setScaffoldSummary(null) }}
            className="text-slate-500 hover:text-slate-300"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">

      {/* === EDITOR AREA (expande quando sidebar fecha) === */}
      <div className={`flex-1 flex flex-col overflow-hidden transition-all duration-300 ${sidebarOpen ? 'mr-0' : ''}`}>
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 bg-dark border-b border-slate-800">
          <div className="flex items-center gap-3">
            <Code2 className="w-5 h-5 text-violet-400" />
            <div>
              <h1 className="text-sm font-semibold text-white">
                {selectedFile ? selectedFile.split('/').pop() : 'Code Generator'}
              </h1>
              <p className="text-xs text-slate-500">
                {selectedFile || 'Selecione um arquivo na árvore ou crie um novo'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* MVP 3: Gerar preview (dry_run) */}
            <button
              onClick={handleGenerateScaffold}
              disabled={scaffoldGenerating || scaffoldApplying}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
              title="Gerar preview do scaffold via IA (não commita — revise e clique em Aplicar)"
            >
              {scaffoldGenerating ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" />Gerando...</>
              ) : (
                <><Code2 className="w-3.5 h-3.5" />Gerar Preview</>
              )}
            </button>

            {/* MVP-F: Regenerar items inválidos (docstring missing) — aparece em
                 runs completed/applied com items done. Detecta + marca + regera. */}
            {(progressStore.snapshot?.status === 'completed'
              || progressStore.snapshot?.status === 'applied')
              && (progressStore.snapshot?.completed_items ?? 0) > 0 && (
              <button
                onClick={handleRegenerateInvalid}
                disabled={scaffoldRegenInvalid || scaffoldRetrying || scaffoldApplying || scaffoldGenerating}
                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-orange-600 hover:bg-orange-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
                title="Detecta arquivos com docstring missing e regera apenas esses, preservando os válidos."
              >
                {scaffoldRegenInvalid ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" />Validando...</>
                ) : (
                  <><RefreshCw className="w-3.5 h-3.5" />Regenerar Inválidos</>
                )}
              </button>
            )}

            {/* MVP-D: Re-tentar items failed — só aparece se a run completou com falhas */}
            {progressStore.snapshot?.status === 'completed'
              && (progressStore.snapshot?.failed_items ?? 0) > 0 && (
              <button
                onClick={handleRetryFailedScaffold}
                disabled={scaffoldRetrying || scaffoldApplying || scaffoldGenerating}
                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
                title={`Re-tentar os ${progressStore.snapshot.failed_items} arquivo(s) que falharam. Itens já gerados são preservados.`}
              >
                {scaffoldRetrying ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" />Re-tentando...</>
                ) : (
                  <><RefreshCw className="w-3.5 h-3.5" />Re-tentar Falhados ({progressStore.snapshot.failed_items})</>
                )}
              </button>
            )}

            {/* MVP 3: Aplicar no Git — só aparece com preview pendente */}
            {scaffoldPendingApply && (
              <button
                onClick={handleApplyScaffold}
                disabled={scaffoldApplying || scaffoldGenerating}
                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
                title="Commitar os arquivos do preview no repositório Git do projeto"
              >
                {scaffoldApplying ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" />Aplicando...</>
                ) : (
                  <><GitCommit className="w-3.5 h-3.5" />Aplicar no Git</>
                )}
              </button>
            )}

            {/* New file */}
            <button
              onClick={() => setShowNewFile(true)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
              title="Criar novo arquivo"
            >
              <Plus className="w-3.5 h-3.5" /> Novo
            </button>

            {/* Editar Código — alterna de visualização para edição */}
            {selectedFile && scaffoldFiles.has(selectedFile) && !hasChanges && (
              <button
                onClick={() => setHasChanges(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
                title="Alternar para modo de edição"
              >
                <FileCode className="w-3.5 h-3.5" /> Editar Código
              </button>
            )}

            {/* Run tests (qualquer membro) */}
            {isTestFile && (
              <button
                onClick={handleRunTests}
                disabled={runningTests}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-emerald-900/30 border border-emerald-700/40 text-emerald-400 rounded-lg hover:bg-emerald-900/50 transition-colors"
              >
                {runningTests ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Executar Teste
              </button>
            )}

            {/* Regenerate single file via LLM */}
            {canEdit && (selectedFile || newFilePath) && (
              <button
                onClick={openRegenerateModal}
                disabled={regenerating || saving || validating}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-amber-900/30 border border-amber-700/40 text-amber-300 rounded-lg hover:bg-amber-900/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Regenera apenas este arquivo via LLM (preserva os demais)"
              >
                {regenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <span>🔁</span>}
                Regenerar
              </button>
            )}

            {/* AI Review + Save */}
            {canEdit && (
              <>
                <button
                  onClick={handleReviewAndSave}
                  disabled={validating || saving || (!selectedFile && !newFilePath)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                >
                  {validating ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" />Validando...</>
                  ) : saving ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" />Salvando...</>
                  ) : saveSuccess ? (
                    <><CheckCircle2 className="w-3.5 h-3.5" />Salvo!</>
                  ) : (
                    <><Shield className="w-3.5 h-3.5" />Revisar e Salvar</>
                  )}
                </button>

                {hasChanges && (
                  <button
                    onClick={handleForceSave}
                    disabled={saving}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-slate-800 text-slate-400 rounded-lg hover:bg-slate-700 transition-colors"
                    title="Salvar sem revisão (registrado no audit)"
                  >
                    <Save className="w-3.5 h-3.5" /> Forçar
                  </button>
                )}
              </>
            )}

            {/* Toggle sidebar */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1.5 text-slate-500 hover:text-slate-300 transition-colors"
              title={sidebarOpen ? 'Fechar árvore' : 'Abrir árvore'}
            >
              {sidebarOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* New file dialog */}
        {showNewFile && (
          <div className="px-4 py-3 bg-dark-100 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <FolderPlus className="w-4 h-4 text-amber-400" />
              <input
                type="text"
                value={newFilePath}
                onChange={e => setNewFilePath(e.target.value)}
                placeholder="Caminho do arquivo: src/modules/meu_modulo/service.py"
                className="flex-1 bg-dark-200 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600"
              />
              <button
                onClick={() => {
                  if (newFilePath.trim()) {
                    setSelectedFile(newFilePath)
                    setFileContent('')
                    setOriginalContent('')
                    setHasChanges(true)
                    setShowNewFile(false)
                  }
                }}
                className="px-3 py-1.5 text-xs bg-violet-600 text-white rounded-lg hover:bg-violet-500"
              >Criar</button>
              <button onClick={() => setShowNewFile(false)} className="px-2 py-1.5 text-xs text-slate-500 hover:text-slate-300">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* AI Review results */}
        {aiReview && (
          <div className="px-4 pt-3">
            <AIReviewPanel review={aiReview} onDismiss={() => setAiReview(null)} />
          </div>
        )}

        {/* Test results */}
        {testResult && (
          <div className="px-4 pt-2">
            <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 mb-2">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-emerald-400 font-medium flex items-center gap-1">
                  <TestTube2 className="w-3.5 h-3.5" /> Resultado dos Testes
                </span>
                <button onClick={() => setTestResult(null)} className="text-slate-500 hover:text-slate-300">
                  <X className="w-3 h-3" />
                </button>
              </div>
              <pre className="text-xs text-slate-300 font-mono overflow-x-auto">{testResult}</pre>
            </div>
          </div>
        )}

        {/* Editor */}
        <div className="flex-1 overflow-hidden">
          {fileLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
            </div>
          ) : selectedFile || showNewFile ? (
            <div className="h-full flex flex-col">
              {/* Status bar */}
              <div className="flex items-center justify-between px-4 py-1 bg-dark-100 border-b border-slate-800 text-xs text-slate-500">
                <span>{selectedFile}</span>
                <div className="flex items-center gap-3">
                  {hasChanges && <span className="text-amber-400">Modificado</span>}
                  {!canEdit && (
                    <span className="flex items-center gap-1 text-slate-600">
                      <Eye className="w-3 h-3" /> Somente leitura
                    </span>
                  )}
                </div>
              </div>

              {/* Editor com highlighting para NMI/TODO */}
              {scaffoldFiles.has(selectedFile) && !hasChanges ? (
                <div className="flex-1 overflow-auto bg-[#0d1117]">
                  <div className="font-mono text-sm leading-relaxed">
                    {fileContent.split('\n').map((line, idx) => {
                      const isNMI = line.includes('[NMI]')
                      const isTODO = !isNMI && (line.includes('TODO') || line.includes('todo:'))
                      return (
                        <div
                          key={idx}
                          className={`flex ${
                            isNMI ? 'bg-red-900/30 border-l-2 border-red-500' :
                            isTODO ? 'bg-amber-900/30 border-l-2 border-amber-500' :
                            'border-l-2 border-transparent'
                          }`}
                        >
                          <span className="text-slate-600 text-right w-10 flex-shrink-0 pr-3 select-none py-0.5">{idx + 1}</span>
                          <pre className={`py-0.5 pr-4 whitespace-pre-wrap break-all ${
                            isNMI ? 'text-red-300' :
                            isTODO ? 'text-amber-300' :
                            'text-slate-200'
                          }`}>{line || ' '}</pre>
                        </div>
                      )
                    })}
                  </div>
                  {/* Badges de status NMI/TODO */}
                  {(scaffoldFiles.get(selectedFile)?.status === 'nmi' || scaffoldFiles.get(selectedFile)?.status === 'todo') && (
                    <div className="sticky bottom-0 bg-dark-100 border-t border-slate-800 px-4 py-2 flex items-center gap-2">
                      {scaffoldFiles.get(selectedFile)?.status === 'nmi' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">Necessita mais informacoes (NMI)</span>
                      )}
                      {scaffoldFiles.get(selectedFile)?.status === 'todo' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">Contem TODOs para implementar</span>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex-1 w-full">
                  <Editor
                    height="60vh"
                    language={detectLanguageForMonaco(selectedFile || newFilePath)}
                    value={fileContent}
                    theme="vs-dark"
                    onChange={(v) => {
                      if (!canEdit) return
                      const next = v ?? ''
                      setFileContent(next)
                      setHasChanges(next !== originalContent)
                      // Limpar estado de bloqueio e markers ao editar — evita ruído visual
                      if (validationBlocked) {
                        setValidationBlocked(false)
                        setValidationErrors([])
                        applyMarkers([])
                      }
                    }}
                    onMount={(editor, monaco) => {
                      editorRef.current = editor
                      monacoRef.current = monaco
                    }}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 13,
                      wordWrap: 'on',
                      readOnly: !canEdit,
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                    }}
                  />
                  {validationBlocked && (
                    <div className="px-4 py-2 bg-red-900/20 border-t border-red-800/40 text-red-300 text-xs">
                      {validationErrors.length} problema(s) de sintaxe — corrija os sublinhados em vermelho antes de salvar.
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Code2 className="w-10 h-10 text-slate-700 mx-auto mb-3" />
                <p className="text-slate-500 text-sm font-medium">Nenhum arquivo selecionado</p>
                <p className="text-slate-600 text-xs mt-1">
                  {scaffoldFiles.size > 0
                    ? 'Selecione um arquivo na árvore à direita para visualizar o código gerado'
                    : <>Clique em <strong className="text-emerald-400">"Gerar Preview"</strong> para criar o scaffold do projeto<br />ou selecione um arquivo na árvore do repositório</>
                  }
                </p>
                {scaffoldFiles.size === 0 && (
                  <button
                    onClick={handleGenerateScaffold}
                    disabled={scaffoldGenerating}
                    className="mt-4 px-4 py-2 text-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg transition-colors inline-flex items-center gap-2"
                  >
                    {scaffoldGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Code2 className="w-4 h-4" />}
                    Gerar Preview do Scaffold
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* === SIDEBAR DIREITA — Árvore Git === */}
      <div className={`border-l border-slate-800 bg-dark overflow-hidden transition-all duration-300 ${
        sidebarOpen ? 'w-72' : 'w-0'
      }`}>
        <div className="h-full flex flex-col w-72">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold text-slate-200">Repositório</span>
            </div>
            <button
              onClick={loadTree}
              disabled={treeLoading}
              className="p-1 text-slate-500 hover:text-slate-300 transition-colors"
              title="Atualizar árvore"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${treeLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Tree */}
          <div className="flex-1 overflow-y-auto py-1">
            {treeLoading ? (
              <div className="flex items-center justify-center h-20">
                <Loader2 className="w-4 h-4 text-slate-500 animate-spin" />
              </div>
            ) : fileTree.length > 0 ? (
              fileTree.map(node => (
                <TreeNode
                  key={node.path}
                  node={node}
                  depth={0}
                  onSelect={handleSelectFile}
                  selectedPath={selectedFile}
                  itemStatus={scaffoldItemStatus}
                />
              ))
            ) : (
              <p className="px-3 py-4 text-xs text-slate-600 text-center">
                Repositório não conectado.<br />
                Configure em Configurações.
              </p>
            )}
          </div>

          {/* Footer */}
          <div className="px-3 py-2 border-t border-slate-800">
            <p className="text-[10px] text-slate-600 text-center">
              Arquivos são commitados ao salvar
            </p>
          </div>
        </div>
      </div>
      </div>

      {/* Modal de regeneração com instruções */}
      {regenModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setRegenModalOpen(false)}>
          <div
            onClick={e => e.stopPropagation()}
            className="w-full max-w-xl bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 space-y-4"
          >
            <div>
              <h3 className="text-slate-100 text-sm font-semibold flex items-center gap-2">
                <span>🔁</span> Regenerar arquivo
              </h3>
              <p className="text-slate-400 text-xs mt-1 font-mono truncate">{selectedFile || newFilePath}</p>
            </div>

            <div>
              <label className="text-slate-300 text-xs font-medium block mb-1.5">
                Instruções para o LLM <span className="text-slate-500">(opcional)</span>
              </label>
              <textarea
                value={regenInstructions}
                onChange={e => setRegenInstructions(e.target.value)}
                placeholder="Ex: adicione logging estruturado em cada função; corrija o bug de null check; use async/await em vez de callbacks..."
                className="w-full h-28 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600 resize-none"
                autoFocus
              />
              <p className="text-slate-500 text-[11px] mt-1.5">
                Se deixar em branco, o LLM regera o arquivo do zero com base no OCG e no path.
                O conteúdo atual é enviado como referência.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setRegenModalOpen(false)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
              >
                Cancelar
              </button>
              <button
                onClick={handleRegenerateFile}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
              >
                <span>🔁</span> Regenerar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Helpers
// ============================================================================

function buildTree(paths: string[]): GitFile[] {
  const root: GitFile[] = []

  for (const path of paths) {
    const parts = path.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const name = parts[i]
      const isLast = i === parts.length - 1
      const fullPath = parts.slice(0, i + 1).join('/')

      let existing = current.find(n => n.name === name)
      if (!existing) {
        existing = {
          name,
          path: fullPath,
          type: isLast ? 'file' : 'dir',
          children: isLast ? undefined : [],
        }
        current.push(existing)
      }
      if (!isLast && existing.children) {
        current = existing.children
      }
    }
  }

  // Ordenar: dirs primeiro, depois files
  const sort = (nodes: GitFile[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    nodes.forEach(n => n.children && sort(n.children))
  }
  sort(root)
  return root
}

function getDefaultTree(): GitFile[] {
  return buildTree([
    'README.md',
    'docs/functional/overview.md',
    'docs/functional/user_stories.md',
    'docs/functional/business_rules.md',
    'docs/technical/architecture.md',
    'docs/technical/stack.md',
    'docs/technical/api_endpoints.md',
    'docs/technical/data_model.md',
    'docs/security/compliance.md',
    'docs/modules/.gitkeep',
    'docs/tests/test_plan.md',
    'docs/tests/unit_coverage.md',
    'docs/ocg_current.md',
    'docs/CHANGELOG.md',
    'src/modules/.gitkeep',
    'tests/unit/.gitkeep',
    'tests/integration/.gitkeep',
    'tests/uat/.gitkeep',
  ])
}

/**
 * Constrói árvore de arquivos com status (complete/todo/nmi) propagado
 */
function buildTreeWithStatus(files: { path: string; content: string; status: string }[]): GitFile[] {
  const root: GitFile[] = []
  const statusMap = new Map<string, string>()

  for (const f of files) {
    statusMap.set(f.path, f.status)
  }

  for (const file of files) {
    const parts = file.path.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const name = parts[i]
      const isLast = i === parts.length - 1
      const fullPath = parts.slice(0, i + 1).join('/')

      let existing = current.find(n => n.name === name)
      if (!existing) {
        existing = {
          name,
          path: fullPath,
          type: isLast ? 'file' : 'dir',
          children: isLast ? undefined : [],
          status: isLast ? (file.status as GitFile['status']) : undefined,
        }
        current.push(existing)
      }
      if (!isLast && existing.children) {
        current = existing.children
      }
    }
  }

  // Ordenar: dirs primeiro, depois files
  const sort = (nodes: GitFile[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    nodes.forEach(n => n.children && sort(n.children))
  }
  sort(root)
  return root
}

export default CodeGeneratorPage
