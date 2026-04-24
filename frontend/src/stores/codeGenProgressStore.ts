import { create } from 'zustand'
import { apiClient } from '@/lib/api'

export type ItemStatus = 'pending' | 'generating' | 'complete' | 'error'

export interface PlanItem {
  path: string
  file_type: string
  purpose: string
  est_lines: number
}

export interface GeneratedFile {
  content: string
  status: string
}

interface CodeGenProgressState {
  active: boolean
  projectId: string | null
  projectName: string | null
  planSummary: string | null
  planItems: PlanItem[]
  itemStatus: Map<string, ItemStatus>
  filesByPath: Map<string, GeneratedFile>
  errorMessage: string | null
  startedAt: number | null
  finishedAt: number | null

  startScaffold: (projectId: string, projectName: string) => Promise<void>
  reset: () => void
  dismiss: () => void
}

const initialState = {
  active: false,
  projectId: null,
  projectName: null,
  planSummary: null,
  planItems: [],
  itemStatus: new Map<string, ItemStatus>(),
  filesByPath: new Map<string, GeneratedFile>(),
  errorMessage: null,
  startedAt: null,
  finishedAt: null,
}

/**
 * MVP 30 — store global pra progresso de geração de scaffold.
 *
 * O for-loop que chama `/scaffold/item` sequencialmente vive AQUI, fora
 * do ciclo de vida do componente CodeGeneratorPage. Isso garante que
 * navegar pra outra página NÃO interrompe a geração — o loop continua
 * rodando no store e o overlay global (ver CodeGenProgressOverlay)
 * exibe o progresso em qualquer tela do projeto.
 *
 * DT-091 futura: persistir no servidor pra sobreviver a refresh/F5.
 */
export const useCodeGenProgressStore = create<CodeGenProgressState>((set, get) => ({
  ...initialState,

  reset: () => set({ ...initialState, itemStatus: new Map(), filesByPath: new Map() }),

  dismiss: () => {
    if (get().active) return
    set({ ...initialState, itemStatus: new Map(), filesByPath: new Map() })
  },

  startScaffold: async (projectId: string, projectName: string) => {
    if (get().active) return

    set({
      ...initialState,
      active: true,
      projectId,
      projectName,
      startedAt: Date.now(),
      itemStatus: new Map(),
      filesByPath: new Map(),
    })

    try {
      const planRes = await apiClient.post('/code-generation/scaffold/plan', { project_id: projectId })
      const planItems: PlanItem[] = planRes.data.items || []
      const planSummary: string = planRes.data.summary || ''

      if (planItems.length === 0) {
        set({
          active: false,
          errorMessage: 'O LLM não retornou itens no plano. Ajuste o OCG e tente novamente.',
          finishedAt: Date.now(),
        })
        return
      }

      const initialStatus = new Map<string, ItemStatus>()
      for (const it of planItems) initialStatus.set(it.path, 'pending')

      set({
        planItems,
        planSummary,
        itemStatus: initialStatus,
      })

      const peerPathsCsv = planItems.map(it => it.path).join(',')
      const accumulated = new Map<string, GeneratedFile>()

      for (const item of planItems) {
        set((s) => {
          const next = new Map(s.itemStatus)
          next.set(item.path, 'generating')
          return { itemStatus: next }
        })

        try {
          const itemRes = await apiClient.post(
            `/code-generation/scaffold/item?peer_paths_csv=${encodeURIComponent(peerPathsCsv)}`,
            {
              project_id: projectId,
              path: item.path,
              file_type: item.file_type,
              purpose: item.purpose,
            },
          )
          const data = itemRes.data
          if (data.status === 'error') {
            set((s) => {
              const next = new Map(s.itemStatus)
              next.set(item.path, 'error')
              return { itemStatus: next }
            })
          } else {
            accumulated.set(item.path, { content: data.content || '', status: data.status || 'todo' })
            set((s) => {
              const nextStatus = new Map(s.itemStatus)
              nextStatus.set(item.path, 'complete')
              return {
                itemStatus: nextStatus,
                filesByPath: new Map(accumulated),
              }
            })
          }
        } catch {
          set((s) => {
            const next = new Map(s.itemStatus)
            next.set(item.path, 'error')
            return { itemStatus: next }
          })
        }
      }

      set({ active: false, finishedAt: Date.now() })
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err
        ? String((err as { message: unknown }).message)
        : 'Erro inesperado ao gerar scaffold'
      set({ active: false, errorMessage: msg, finishedAt: Date.now() })
    }
  },
}))
