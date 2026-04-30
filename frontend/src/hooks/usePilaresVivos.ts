/**
 * Hook: usePilaresVivos
 * Gerencia estado e operações de Pilares Vivos
 */
import { useState, useCallback } from 'react'
import { useToast } from '@/hooks/useToast'

export interface PilaresVivosData {
  id: string
  projeto_id: string
  documento: Record<string, any>
  gerado_em: string | null
  regenerado_em: string | null
  gerado_por: string
}

export interface PilaresVivosHistoryItem {
  id: string
  gerado_em: string | null
  archived_em: string | null
  personas_modificadas: string[]
  resumo_mudancas: string | null
}

export function usePilaresVivos(projectId: string) {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<PilaresVivosData | null>(null)
  const [historia, setHistoria] = useState<PilaresVivosHistoryItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()

  const regenerar = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch(
        `/api/v1/projects/${projectId}/pilares/regenerar`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail?.erro || 'Erro ao regenerar Pilares Vivos')
      }

      const result = await response.json()
      toast.success(`Pilares Vivos regenerados em ${result.tempo_total?.toFixed(1)}s`)

      // Buscar dados atualizados
      await obter()

      return result
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido'
      setError(message)
      toast.error(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [projectId, toast])

  const obter = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch(`/api/v1/projects/${projectId}/pilares`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      })

      if (response.status === 404) {
        setData(null)
        return
      }

      if (!response.ok) {
        throw new Error('Erro ao obter Pilares Vivos')
      }

      const pilares = await response.json()
      setData(pilares)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [projectId, toast])

  const obterHistoria = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/projects/${projectId}/pilares/historia`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      })

      if (!response.ok) {
        throw new Error('Erro ao obter histórico')
      }

      const items = await response.json()
      setHistoria(items)
      return items
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido'
      toast.error(message)
      throw err
    }
  }, [projectId, toast])

  // Buscar dados ao montar o component
  const inicializar = useCallback(async () => {
    await obter()
    await obterHistoria()
  }, [obter, obterHistoria])

  return {
    // Estado
    data,
    historia,
    loading,
    error,

    // Operações
    regenerar,
    obter,
    obterHistoria,
    inicializar,
  }
}
