import { useState, useEffect, useCallback, useRef } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  Code2, Play, Save, GitBranch, Loader2, CheckCircle2, AlertTriangle,
  FolderTree, ChevronRight, ChevronDown, FileCode, FileText, File,
  PanelRightOpen, PanelRightClose, Plus, FolderPlus, TestTube2,
  Shield, RefreshCw, X, Eye
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { OperationBar, PulseIndicator } from '@/components/ui/PipelineProgress'

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
  node, depth, onSelect, selectedPath
}: {
  node: GitFile; depth: number; onSelect: (path: string) => void; selectedPath: string
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
          <TreeNode key={child.path} node={child} depth={depth + 1} onSelect={onSelect} selectedPath={selectedPath} />
        ))}
      </div>
    )
  }

  const isSelected = node.path === selectedPath
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
  const isDevOrQA = true // TODO: check user.role in project (developer, qa, tech_lead, gp)
  const isTestFile = selectedFile.includes('test') || selectedFile.includes('spec')
  const canEdit = isTestFile ? isDevOrQA : isDevOrQA

  // Backlog item auto-generation
  const [searchParams] = useSearchParams()
  const backlogItemId = searchParams.get('backlog_item')
  const [generating, setGenerating] = useState(false)
  const [generatedFromBacklog, setGeneratedFromBacklog] = useState(false)

  // Scaffold state
  const [scaffoldFiles, setScaffoldFiles] = useState<Map<string, { content: string; status: string }>>(new Map())
  const [scaffoldGenerating, setScaffoldGenerating] = useState(false)
  const [scaffoldSummary, setScaffoldSummary] = useState<string | null>(null)

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

  // ================================================================
  // Gerar Scaffold do Projeto
  // ================================================================

  const handleGenerateScaffold = async () => {
    if (!projectId) return
    if (scaffoldFiles.size > 0 && !confirm('Isso substituirá o scaffold atual. Continuar?')) return

    setScaffoldGenerating(true)
    setScaffoldSummary(null)
    try {
      const res = await apiClient.post('/code-generation/scaffold', { project_id: projectId })
      const data = res.data
      const files: { path: string; content: string; status: string }[] = data.files || []

      // Armazenar conteúdos no map
      const newMap = new Map<string, { content: string; status: string }>()
      const paths: string[] = []
      for (const f of files) {
        newMap.set(f.path, { content: f.content, status: f.status })
        paths.push(f.path)
      }
      setScaffoldFiles(newMap)

      // Sumário combinando geração e commits
      const cs = data.commit_summary as { committed?: number; failed?: number } | undefined
      const baseSummary = data.summary || `Gerados ${files.length} arquivos`
      const commitPart = cs
        ? ` — Commitados ${cs.committed || 0} no repositório${cs.failed ? `, ${cs.failed} falharam` : ''}`
        : ''
      setScaffoldSummary(baseSummary + commitPart)

      // Construir árvore a partir dos caminhos gerados, propagando status
      const tree = buildTreeWithStatus(files)
      setFileTree(tree)

      // Refetch árvore do Git (caso haja arquivos já commitados do scaffold inicial)
      loadTree()

      // Selecionar o primeiro arquivo
      if (paths.length > 0) {
        const firstFile = paths[0]
        setSelectedFile(firstFile)
        setFileContent(newMap.get(firstFile)?.content || '')
        setOriginalContent(newMap.get(firstFile)?.content || '')
        setHasChanges(false)
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Erro ao gerar scaffold'
      alert(`Falha na geração: ${detail}`)
    } finally {
      setScaffoldGenerating(false)
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
      } catch (err: any) {
        console.error('Erro ao gerar codigo:', err)
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

    // Se já temos scaffold gerado, usar ele
    if (scaffoldFiles.size > 0) return

    setTreeLoading(true)
    try {
      const res = await apiClient.get(`/projects/${projectId}/git/status`)
      if (res.data?.connected) {
        // Buscar árvore completa do repositório (arquivos + diretórios, recursivo)
        try {
          const treeRes = await apiClient.get(`/projects/${projectId}/git/tree`)
          const entries = (treeRes.data?.tree || []) as Array<{ path: string; type: string }>
          const filePaths = entries.filter(e => e.type === 'file').map(e => e.path)
          if (filePaths.length > 0) {
            setFileTree(buildTree(filePaths))
          } else {
            setFileTree(getDefaultTree())
          }
        } catch {
          setFileTree(getDefaultTree())
        }
      } else {
        setFileTree(getDefaultTree())
      }
    } catch {
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

    // Verificar se o arquivo está no scaffold gerado
    const scaffoldFile = scaffoldFiles.get(path)
    if (scaffoldFile) {
      setFileContent(scaffoldFile.content)
      setOriginalContent(scaffoldFile.content)
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
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Erro ao salvar arquivo')
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
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Falha ao validar código')
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
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Falha ao regenerar arquivo')
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
            <span className="text-slate-400">Backend: <span className="text-blue-400">{ocgContext.stack.backend.language || ''} {ocgContext.stack.backend.framework || ''}</span></span>
          )}
          {ocgContext.stack?.frontend && (
            <span className="text-slate-400">Frontend: <span className="text-emerald-400">{ocgContext.stack.frontend.framework || ''} {ocgContext.stack.frontend.language || ''}</span></span>
          )}
          {ocgContext.stack?.database && (
            <span className="text-slate-400">DB: <span className="text-amber-400">{ocgContext.stack.database.primary || ''}</span></span>
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
      {scaffoldGenerating && (
        <div className="px-4 py-3 border-b border-emerald-700/40">
          <OperationBar
            message="Gerando scaffold do projeto"
            detail="Analisando OCG, documentos e regras de negocio para gerar codigo real..."
            status="running"
          />
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
            {/* Gerar Scaffold */}
            <button
              onClick={handleGenerateScaffold}
              disabled={scaffoldGenerating}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
              title="Gerar scaffold completo do projeto via IA"
            >
              {scaffoldGenerating ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" />Gerando...</>
              ) : (
                <><Code2 className="w-3.5 h-3.5" />Gerar Codigo</>
              )}
            </button>

            {/* New file */}
            <button
              onClick={() => setShowNewFile(true)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
              title="Criar novo arquivo"
            >
              <Plus className="w-3.5 h-3.5" /> Novo
            </button>

            {/* Editar Codigo — alterna de visualizacao para edicao */}
            {selectedFile && scaffoldFiles.has(selectedFile) && !hasChanges && (
              <button
                onClick={() => setHasChanges(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
                title="Alternar para modo de edicao"
              >
                <FileCode className="w-3.5 h-3.5" /> Editar Codigo
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
                    ? 'Selecione um arquivo na arvore a direita para visualizar o codigo gerado'
                    : <>Clique em <strong className="text-emerald-400">"Gerar Codigo"</strong> para criar o scaffold do projeto<br />ou selecione um arquivo na arvore do repositorio</>
                  }
                </p>
                {scaffoldFiles.size === 0 && (
                  <button
                    onClick={handleGenerateScaffold}
                    disabled={scaffoldGenerating}
                    className="mt-4 px-4 py-2 text-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg transition-colors inline-flex items-center gap-2"
                  >
                    {scaffoldGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Code2 className="w-4 h-4" />}
                    Gerar Codigo do Projeto
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
 * Constroi arvore de arquivos com status (complete/todo/nmi) propagado
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
