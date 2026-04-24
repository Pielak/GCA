import { useEffect, useState } from 'react'
import { apiClient } from '@/lib/api'

export interface IterativeQStatus {
  overall: number | null
  deficit_pillars: Record<string, number>
  eligible_for_iteration: boolean
  has_pending: boolean
  converged: boolean
  latest_iteration: {
    id: string
    iteration: number
    status: string
    created_at: string | null
    target_pillars: string[]
    question_count: number
    overall_before: number | null
    overall_after: number | null
  } | null
}

/**
 * M01 — status do questionário iterativo. Usado pelo sidebar pra decidir
 * badge (• pendente / ✓ convergido / nada) e pela página pra montar UI.
 * Polling a cada 30s (padrão canônico das páginas reativas do GCA).
 */
export function useIterativeQuestionnaireStatus(projectId: string | undefined) {
  const [data, setData] = useState<IterativeQStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    const load = async () => {
      try {
        const res = await apiClient.get(`/projects/${projectId}/iterative-questionnaire/status`)
        if (!cancelled) setData(res.data)
      } catch {
        if (!cancelled) setData(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 30_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [projectId])

  return { data, loading }
}
