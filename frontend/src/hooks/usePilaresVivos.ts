/**
 * Hook: usePilaresVivos
 * Gerencia estado e operações de Pilares Vivos com polling de jobs assíncronos
 */
import { useState, useCallback, useRef } from 'react'
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

export interface JobStatus {
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  criado_em: string | null
  iniciado_em: string | null
  concluido_em: string | null
  tempo_total_segundos: number | null
  resultado_json?: Record<string, any>
  erro_mensagem?: string
}

export function usePilaresVivos(projectId: string) {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<PilaresVivosData | null>(null)
  const [historia, setHistoria] = useState<PilaresVivosHistoryItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const pollTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const pollAttemptsRef = useRef(0)
  const MAX_POLL_ATTEMPTS = 120  // 120 × 2s = 4 minutos máximo
  const toast = useToast()

  const obterStatusJob = useCallback(
    async (jobId: string): Promise<JobStatus> => {
      const response = await fetch(
        `/api/v1/projects/${projectId}/pilares/jobs/${jobId}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        }
      )

      if (!response.ok) {
        throw new Error('Erro ao obter status do job')
      }

      return response.json()
    },
    [projectId]
  )

  const atualizarComResultado = useCallback(
    async (resultado: Record<string, any>) => {
      try {
        const response = await fetch(`/api/v1/projects/${projectId}/pilares`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        })

        if (response.ok) {
          const pilares = await response.json()
          setData(pilares)
        }
      } catch (err) {
        console.error('Erro ao atualizar Pilares com resultado:', err)
      }
    },
    [projectId]
  )

  const limparPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
    pollAttemptsRef.current = 0
  }, [])

  const sondagemJob = useCallback(
    async (jobId: string) => {
      try {
        pollAttemptsRef.current += 1

        // Timeout: após 4 minutos ou 120 tentativas, parar
        if (pollAttemptsRef.current > MAX_POLL_ATTEMPTS) {
          limparPolling()
          const msg = 'Tempo limite excedido (4 min). Verifique o status do job no backend.'
          setError(msg)
          toast.error(msg)
          setLoading(false)
          return
        }

        const status = await obterStatusJob(jobId)
        setJobStatus(status)

        if (status.status === 'completed') {
          limparPolling()
          await atualizarComResultado(status.resultado_json || {})
          const tempo = status.tempo_total_segundos?.toFixed(1) || '?'
          toast.success(`Pilares Vivos regenerados em ${tempo}s`)
          setLoading(false)
        } else if (status.status === 'failed') {
          limparPolling()
          const msg = status.erro_mensagem || 'Erro desconhecido'
          setError(msg)
          toast.error(`Falha ao regenerar: ${msg}`)
          setLoading(false)
        }
        // Se 'queued' ou 'processing', continua polando (será chamado novamente em 2s)
      } catch (err) {
        pollAttemptsRef.current += 1

        // Para na 10ª tentativa falhada (20 segundos)
        if (pollAttemptsRef.current > 10) {
          limparPolling()
          const message = err instanceof Error ? err.message : 'Erro ao sondar job'
          setError(`${message} (após 10 tentativas)`)
          toast.error(`Erro persistente: ${message}`)
          setLoading(false)
          return
        }

        // Continua tentando se falhar no meio
        console.warn(`Tentativa ${pollAttemptsRef.current}: ${err}`)
      }
    },
    [obterStatusJob, atualizarComResultado, toast, limparPolling]
  )

  const regenerar = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      setJobStatus(null)

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
        throw new Error(errorData.detail?.erro || 'Erro ao iniciar regeneração')
      }

      const result = await response.json()
      const jobId = result.job_id

      setJobStatus({
        job_id: jobId,
        status: 'queued',
        criado_em: new Date().toISOString(),
        iniciado_em: null,
        concluido_em: null,
        tempo_total_segundos: null,
      })

      toast.info('Regeneração iniciada... aguardando conclusão')

      limparPolling()
      pollAttemptsRef.current = 0

      pollIntervalRef.current = setInterval(() => {
        sondagemJob(jobId)
      }, 2000)

      return result
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido'
      setError(message)
      toast.error(message)
      setLoading(false)
      throw err
    }
  }, [projectId, toast, sondagemJob, limparPolling])

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
        console.warn('Histórico não disponível:', response.status)
        setHistoria([])
        return []
      }

      const items = await response.json()
      setHistoria(items)
      return items
    } catch (err) {
      console.warn('Erro ao obter histórico:', err)
      setHistoria([])
      return []
    }
  }, [projectId])

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
    jobStatus,

    // Operações
    regenerar,
    obter,
    obterHistoria,
    inicializar,
  }
}
