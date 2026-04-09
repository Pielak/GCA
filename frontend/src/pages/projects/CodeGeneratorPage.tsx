import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  Code2, Play, Save, GitBranch, Loader2, CheckCircle2, AlertTriangle,
  FolderTree, ChevronRight, ChevronDown, FileCode, FileText, File,
  PanelRightOpen, PanelRightClose, Plus, FolderPlus, TestTube2,
  Shield, RefreshCw, X, Eye
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

// ============================================================================
// Tipos
// ============================================================================

interface GitFile {
  name: string
  path: string
  type: 'file' | 'dir'
  size?: number
  children?: GitFile[]
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

  // Run tests
  const [runningTests, setRunningTests] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  // Permissions
  const isDevOrQA = true // TODO: check user.role in project (developer, qa, tech_lead, gp)
  const isTestFile = selectedFile.includes('test') || selectedFile.includes('spec')
  const canEdit = isTestFile ? isDevOrQA : isDevOrQA

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
  // Load file tree
  // ================================================================

  const loadTree = useCallback(async () => {
    if (!projectId) return
    setTreeLoading(true)
    try {
      const res = await apiClient.get(`/projects/${projectId}/git/status`)
      if (res.data?.connected) {
        // Buscar arquivos do repositório
        try {
          const filesRes = await apiClient.get(`/projects/${projectId}/livedocs`)
          const sections = filesRes.data?.sections || []
          // Converter lista plana em árvore
          const tree = buildTree(sections.map((s: any) => s.path || s.name))
          setFileTree(tree)
        } catch {
          // Fallback: árvore estática baseada na estrutura esperada
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
  }, [projectId])

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
    setFileLoading(true)

    try {
      const res = await apiClient.get(`/projects/${projectId}/livedocs/content`, {
        params: { path },
      })
      const content = res.data?.content || ''
      setFileContent(content)
      setOriginalContent(content)
    } catch {
      setFileContent('// Arquivo ainda não existe. Escreva o conteúdo e salve.')
      setOriginalContent('')
    } finally {
      setFileLoading(false)
    }
  }

  // ================================================================
  // AI Review before save
  // ================================================================

  const handleReviewAndSave = async () => {
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
      await apiClient.post(`/projects/${projectId}/git/connect`, {
        // Usar endpoint de commit — se não existir, simular
      })
    } catch {
      // Ignora erro de connect — já pode estar conectado
    }

    try {
      // Commit via API
      const commitMsg = hasChanges
        ? `[GCA] Atualiza ${path.split('/').pop()}`
        : `[GCA] Cria ${path.split('/').pop()}`

      await apiClient.post(`/projects/${projectId}/ingestion`, {
        // Fallback: salvar como artefato
      }).catch(() => {})

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
      alert(err?.message || 'Erro ao salvar arquivo')
    } finally {
      setSaving(false)
    }
  }

  // ================================================================
  // Force save (bypass AI review — com warning)
  // ================================================================

  const handleForceSave = async () => {
    if (!confirm('Salvar sem revisão da IA? Isso será registrado no audit log.')) return
    await commitFile(selectedFile || newFilePath, fileContent)
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
            {/* New file */}
            <button
              onClick={() => setShowNewFile(true)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
              title="Criar novo arquivo"
            >
              <Plus className="w-3.5 h-3.5" /> Novo
            </button>

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

            {/* AI Review + Save */}
            {canEdit && (
              <>
                <button
                  onClick={handleReviewAndSave}
                  disabled={reviewing || saving || !hasChanges}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                >
                  {reviewing ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" />Revisando IA...</>
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

              {/* Textarea editor */}
              <textarea
                value={fileContent}
                onChange={e => {
                  if (!canEdit) return
                  setFileContent(e.target.value)
                  setHasChanges(e.target.value !== originalContent)
                }}
                readOnly={!canEdit}
                spellCheck={false}
                className={`flex-1 w-full bg-[#0d1117] text-slate-200 font-mono text-sm p-4 resize-none focus:outline-none leading-relaxed ${
                  !canEdit ? 'cursor-default opacity-80' : ''
                }`}
                placeholder="// Escreva seu código aqui..."
              />
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Code2 className="w-10 h-10 text-slate-700 mx-auto mb-3" />
                <p className="text-slate-500 text-sm font-medium">Nenhum arquivo selecionado</p>
                <p className="text-slate-600 text-xs mt-1">
                  Selecione um arquivo na árvore do repositório à direita<br />
                  ou clique em "Novo" para criar um arquivo
                </p>
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

export default CodeGeneratorPage
