import { create } from 'zustand'
import { apiClient } from '@/lib/api'

/**
 * Camada A — scaffold server-side persistido (2026-04-25).
 *
 * Antes este store chamava `/scaffold/plan` síncrono (LLM ~180s) e estourava
 * Cloudflare timeout (~100s) → Network Error e perda de progresso. Agora:
 *
 *   1. POST /scaffold/start  → retorna run_id em milissegundos (Celery enfileirado)
 *   2. Poll GET /scaffold/runs/{run_id} com backoff exponencial em erro de rede
 *   3. run_id persistido em localStorage por projeto — sobrevive a refresh/F5,
 *      queda de rede, queda de eletricidade. Ao montar, hidrata e retoma poll.
 *   4. Status canônicos do servidor:
 *        run.status: pending → planning → generating → completed | failed | applied
 *        item.status: pending → generating → done | failed | skipped
 *   5. Apply pelo próprio store (POST /scaffold/runs/{id}/apply).
 *   6. Dismiss limpa localStorage e estado.
 */

export type RunStatus = 'pending' | 'planning' | 'generating' | 'completed' | 'failed' | 'applied' | 'applying'
export type ItemStatus = 'pending' | 'generating' | 'done' | 'failed' | 'skipped'

export interface RunItem {
  id: string
  ordinal: number
  path: string
  file_type: string | null
  purpose: string | null
  status: ItemStatus
  tokens_used: number | null
  error: string | null
  notes: string | null
  has_content: boolean
}

export interface RunSnapshot {
  id: string
  project_id: string
  status: RunStatus
  plan_summary: string | null
  total_items: number
  completed_items: number
  failed_items: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  applied_at: string | null
  apply_committed: number | null
  apply_failed: number | null
  items: RunItem[]
}

interface CodeGenProgressState {
  runId: string | null
  projectId: string | null
  projectName: string | null
  snapshot: RunSnapshot | null
  active: boolean
  errorMessage: string | null
  pollErrorCount: number
  startedAt: number | null
  finishedAt: number | null

  startScaffold: (projectId: string, projectName: string) => Promise<void>
  hydrateForProject: (projectId: string, projectName: string) => Promise<void>
  refresh: () => Promise<void>
  apply: () => Promise<{ enqueued: true } | null>
  retryFailed: () => Promise<{ items_reset: number; items_done_preserved: number } | null>
  regenerateInvalid: () => Promise<{ items_marked_invalid: number; items_done_preserved: number } | null>
  fixBuildErrors: (errorsText: string) => Promise<{ items_marked: number; items_done_preserved: number; affected_paths: string[] } | null>
  fetchItemContent: (itemId: string) => Promise<string | null>
  dismiss: () => void
  reset: () => void
}

const LS_KEY = (projectId: string) => `gca:scaffold:active:${projectId}`

const POLL_INTERVAL_MS = 3500
const POLL_MAX_BACKOFF_MS = 30000
// MVP-E: 'applying' NÃO é terminal — é fase em curso entre completed → applied.
// Polling deve continuar ativo durante 'applying' pra UI ver apply_committed
// e apply_failed subindo conforme cada commit termina.
const TERMINAL_STATUSES: RunStatus[] = ['completed', 'failed', 'applied']

const initialState = {
  runId: null,
  projectId: null,
  projectName: null,
  snapshot: null,
  active: false,
  errorMessage: null,
  pollErrorCount: 0,
  startedAt: null,
  finishedAt: null,
}

let pollTimer: ReturnType<typeof setTimeout> | null = null

function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function persistRunId(projectId: string, runId: string) {
  try {
    localStorage.setItem(LS_KEY(projectId), runId)
  } catch { /* ignora */ }
}

function readRunId(projectId: string): string | null {
  try {
    return localStorage.getItem(LS_KEY(projectId))
  } catch {
    return null
  }
}

function clearRunId(projectId: string) {
  try {
    localStorage.removeItem(LS_KEY(projectId))
  } catch { /* ignora */ }
}

function clearAllProjectData() {
  try {
    // Remove todos os keys gca:scaffold:active:* do localStorage
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith('gca:scaffold:active:')) {
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach(key => localStorage.removeItem(key))
  } catch { /* ignora */ }
}

export const useCodeGenProgressStore = create<CodeGenProgressState>((set, get) => {
  /**
   * Loop de poll. Backoff exponencial em erros de rede; reset ao 1º sucesso.
   * Para automaticamente quando run entra em status terminal.
   */
  const schedulePoll = (delayMs: number) => {
    clearPoll()
    pollTimer = setTimeout(() => {
      void pollOnce()
    }, delayMs)
  }

  const pollOnce = async () => {
    const { runId, projectId } = get()
    if (!runId || !projectId) return
    try {
      const res = await apiClient.get(`/code-generation/scaffold/runs/${runId}`)
      const snap = res.data as RunSnapshot
      const isTerminal = TERMINAL_STATUSES.includes(snap.status)
      set({
        snapshot: snap,
        active: !isTerminal,
        pollErrorCount: 0,
        finishedAt: isTerminal && !get().finishedAt ? Date.now() : get().finishedAt,
        errorMessage: snap.status === 'failed' ? snap.error : null,
      })
      if (isTerminal) {
        clearPoll()
        if (snap.status === 'applied' || snap.status === 'failed') {
          // applied: scope encerrado; failed: deixa run_id pra owner ver erro,
          // mas saímos do polling. Owner pode dar dismiss manual.
        }
      } else {
        schedulePoll(POLL_INTERVAL_MS)
      }
    } catch (err: any) {
      const errStatus = err?.response?.status
      // 404 → run sumiu (deletada externamente). Limpa.
      if (errStatus === 404) {
        const pid = get().projectId
        if (pid) clearRunId(pid)
        set({ ...initialState, errorMessage: 'Run não encontrada — pode ter sido removida.' })
        clearPoll()
        return
      }
      const next = get().pollErrorCount + 1
      // Backoff exponencial 3s, 6s, 12s, 24s, 30s (cap)
      const backoff = Math.min(POLL_INTERVAL_MS * Math.pow(2, next - 1), POLL_MAX_BACKOFF_MS)
      set({
        pollErrorCount: next,
        errorMessage: next >= 5
          ? 'Conexão instável — retomamos automaticamente quando voltar.'
          : null,
      })
      schedulePoll(backoff)
    }
  }

  return {
    ...initialState,

    reset: () => {
      clearPoll()
      const pid = get().projectId
      if (pid) clearRunId(pid)
      set({ ...initialState })
    },

    /**
     * Dispensa o overlay flutuante de progresso SEM apagar a run em si.
     * Antes esta função fazia `set({ ...initialState })` + `clearRunId`,
     * o que zerava snapshot/runId/projectId do store. Resultado colateral:
     * a CodeGeneratorPage perdia a fonte de verdade dos items e ficava
     * incapaz de carregar conteúdo dos arquivos (cai no placeholder).
     *
     * Agora dismiss só esconde o overlay (active=false + finishedAt=null
     * faz `shouldShow` no overlay virar false). Snapshot, runId e
     * projectId persistem em memória; localStorage também — assim refresh
     * de página ou navegação re-hidratam normalmente. Reset total fica
     * com `reset()` (caminho explícito do user).
     */
    dismiss: () => {
      if (get().active) return
      clearPoll()
      set({ active: false, finishedAt: null, errorMessage: null })
    },

    /**
     * Hidratação ao montar: se há run_id no localStorage do projeto, retoma.
     * Chamado pelo CodeGeneratorPage no useEffect inicial.
     */
    hydrateForProject: async (projectId: string, projectName: string) => {
      // Se já há run no store ativa pra este projeto, não hidrata de novo
      const cur = get()
      if (cur.runId && cur.projectId === projectId) return

      // Estratégia de hidratação:
      //   1. localStorage tem run_id → busca direta
      //   2. localStorage vazio → fallback API "última run do projeto"
      // Sem o fallback, runs concluídas em outra sessão do browser ficam
      // invisíveis (apply/retry/view dos arquivos somem do UI).
      const persistedId = readRunId(projectId)
      let snap: RunSnapshot | null = null
      let runIdLoaded: string | null = null

      if (persistedId) {
        try {
          const res = await apiClient.get(`/code-generation/scaffold/runs/${persistedId}`)
          snap = res.data as RunSnapshot
          runIdLoaded = persistedId
        } catch (err: any) {
          if (err?.response?.status === 404) {
            clearRunId(projectId)
          }
        }
      }

      if (snap === null) {
        try {
          const res = await apiClient.get(
            `/code-generation/scaffold/runs/latest?project_id=${projectId}`,
          )
          snap = res.data as RunSnapshot & { id?: string }
          runIdLoaded = (snap as any).id || null
          if (runIdLoaded) {
            persistRunId(projectId, runIdLoaded)
          }
        } catch {
          return
        }
      }

      if (!snap || !runIdLoaded) return

      const isTerminal = TERMINAL_STATUSES.includes(snap.status)
      clearPoll()
      set({
        ...initialState,
        runId: runIdLoaded,
        projectId,
        projectName,
        snapshot: snap,
        active: !isTerminal,
        startedAt: snap.started_at ? new Date(snap.started_at).getTime() : Date.now(),
        finishedAt: isTerminal && snap.finished_at ? new Date(snap.finished_at).getTime() : null,
        errorMessage: snap.status === 'failed' ? snap.error : null,
      })
      if (!isTerminal) {
        schedulePoll(POLL_INTERVAL_MS)
      }
    },

    startScaffold: async (projectId: string, projectName: string) => {
      if (get().active) return
      clearPoll()

      set({
        ...initialState,
        active: true,
        projectId,
        projectName,
        startedAt: Date.now(),
      })

      try {
        const res = await apiClient.post('/code-generation/scaffold/start', { project_id: projectId })
        const runId = res.data.run_id as string
        persistRunId(projectId, runId)
        set({ runId })
        // Primeiro poll já — backend pode estar em planning ainda
        schedulePoll(POLL_INTERVAL_MS)
      } catch (err: any) {
        const detail = err?.response?.data?.detail
        const msg = typeof detail === 'string' ? detail : 'Falha ao iniciar scaffold.'
        set({ active: false, errorMessage: msg, finishedAt: Date.now() })
      }
    },

    apply: async () => {
      const { runId, snapshot } = get()
      if (!runId || !snapshot) return null
      // Aceita 'completed' (caso normal) e 'failed' apenas quando o erro
      // veio do próprio executor de apply (run.error 'Apply falhou: ...'),
      // espelhando a regra do backend. Geração travada não reaproveita.
      const isApplyFailedRetriable =
        snapshot.status === 'failed'
        && (snapshot.error || '').startsWith('Apply falhou')
      if (snapshot.status !== 'completed' && !isApplyFailedRetriable) {
        set({ errorMessage: 'Scaffold ainda não terminou — aguarde o status completed.' })
        return null
      }
      try {
        // MVP-E: backend agora retorna 202 com { run_id, status: 'applying' }
        // sem esperar os 164 commits terminarem. Reativa polling pra ver
        // apply_committed/apply_failed subindo até status virar 'applied'.
        await apiClient.post(`/code-generation/scaffold/runs/${runId}/apply`)
        set({ active: true, finishedAt: null, errorMessage: null })
        await pollOnce()
        return { enqueued: true }
      } catch (err: any) {
        const detail = err?.response?.data?.detail
        const msg = typeof detail === 'string' ? detail : 'Falha ao enfileirar apply.'
        set({ errorMessage: msg })
        return null
      }
    },

    /**
     * Força um refetch do snapshot atual (sem early-return de hydrateForProject).
     * Usado quando uma view depende de snapshot fresco (ex: clicar em arquivo
     * cujo `has_content` no snapshot local pode estar stale).
     */
    refresh: async () => {
      await pollOnce()
    },

    /**
     * MVP-K (2026-04-26): owner cola erros de build (tsc/docker/npm).
     * Backend extrai paths via regex, marca items afetados como pending
     * + persiste erro em build_errors, reseta run pra generating.
     * Worker regera items afetados com prompt enriquecido pelo erro.
     */
    fixBuildErrors: async (errorsText: string) => {
      const { runId, snapshot } = get()
      if (!runId || !snapshot) return null
      try {
        const res = await apiClient.post(
          `/code-generation/scaffold/runs/${runId}/fix-build-errors`,
          { errors_text: errorsText },
        )
        const marked = res.data?.items_marked || 0
        if (marked > 0) {
          set({ active: true, finishedAt: null, errorMessage: null })
        }
        await pollOnce()
        return {
          items_marked: marked,
          items_done_preserved: res.data?.items_done_preserved || 0,
          affected_paths: res.data?.affected_paths || [],
        }
      } catch (err: any) {
        const detail = err?.response?.data?.detail
        const msg = typeof detail === 'string' ? detail : 'Falha ao processar erros de build.'
        set({ errorMessage: msg })
        return null
      }
    },

    /**
     * MVP-F (2026-04-25): regenera items 'done' que falham na validação
     * pré-commit (docstring missing). Marca afetados como failed + reseta
     * run pra generating + enfileira scaffold_run_executor.
     */
    regenerateInvalid: async () => {
      const { runId, snapshot } = get()
      if (!runId || !snapshot) return null
      if (snapshot.status !== 'completed' && snapshot.status !== 'applied') {
        set({ errorMessage: 'Operação requer status completed ou applied.' })
        return null
      }
      try {
        const res = await apiClient.post(`/code-generation/scaffold/runs/${runId}/regenerate-invalid`)
        const marked = res.data?.items_marked_invalid || 0
        if (marked > 0) {
          // Reativa polling — run volta pra 'generating'.
          set({ active: true, finishedAt: null, errorMessage: null })
        }
        await pollOnce()
        return {
          items_marked_invalid: marked,
          items_done_preserved: res.data?.items_done_preserved || 0,
        }
      } catch (err: any) {
        const detail = err?.response?.data?.detail
        const msg = typeof detail === 'string' ? detail : 'Falha ao regenerar items inválidos.'
        set({ errorMessage: msg })
        return null
      }
    },

    retryFailed: async () => {
      const { runId, snapshot } = get()
      if (!runId || !snapshot) return null
      if (snapshot.status !== 'completed') {
        set({ errorMessage: 'Retry só funciona em runs com status completed.' })
        return null
      }
      if (snapshot.failed_items === 0) {
        set({ errorMessage: 'Nenhum item failed pra re-tentar.' })
        return null
      }
      try {
        const res = await apiClient.post(`/code-generation/scaffold/runs/${runId}/retry-failed`)
        // Run volta pra generating; reativa polling.
        set({ active: true, finishedAt: null, errorMessage: null })
        await pollOnce()
        return {
          items_reset: res.data?.items_reset || 0,
          items_done_preserved: res.data?.items_done_preserved || 0,
        }
      } catch (err: any) {
        const detail = err?.response?.data?.detail
        const msg = typeof detail === 'string' ? detail : 'Falha ao re-tentar items.'
        set({ errorMessage: msg })
        return null
      }
    },

    fetchItemContent: async (itemId: string) => {
      const { runId } = get()
      if (!runId) return null
      try {
        const res = await apiClient.get(`/code-generation/scaffold/runs/${runId}/items/${itemId}/content`)
        return res.data?.content || ''
      } catch {
        return null
      }
    },
  }
})
