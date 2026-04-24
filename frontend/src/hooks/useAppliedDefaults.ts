import { useEffect, useState, useCallback } from 'react'
import { apiClient } from '@/lib/api'

export interface AppliedDefaultItem {
  id: string
  gap_id: string
  category: string
  decision_key: string
  decision_value: string
  source_citation: string
  rationale: string | null
  applied_at: string
  contested_at: string | null
  contested_value: string | null
  effective_value: string
}

export interface AppliedDefaultsResponse {
  items: AppliedDefaultItem[]
  count_by_category: Record<string, number>
  contested_count: number
}

/**
 * M02 — lista de decisões automáticas do projeto. Polling 30s
 * (padrão das páginas reativas do GCA). `refetch` pra atualização
 * imediata após contest.
 */
export function useAppliedDefaults(projectId: string | undefined) {
  const [data, setData] = useState<AppliedDefaultsResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/applied-defaults`)
      setData(res.data)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [projectId, load])

  return { data, loading, refetch: load }
}
