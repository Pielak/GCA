/**
 * PilaresBlockerAlert — Alerta visual quando há DTs bloqueantes pendentes
 *
 * Exibido em páginas críticas como CodeGen para avisar GP
 * de que há bloqueantes que precisam ser resolvidos antes de continuar.
 */

import React, { useEffect, useState } from 'react'
import { AlertTriangle, Loader, X } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'

interface Props {
  projectId: string
  show?: boolean
  onDismiss?: () => void
}

interface BlockerData {
  count: number
  personas: string[]
}

export function PilaresBlockerAlert({ projectId, show = true, onDismiss }: Props) {
  const [blockers, setBlockers] = useState<BlockerData | null>(null)
  const [loading, setLoading] = useState(true)
  const [dismissed, setDismissed] = useState(false)

  const { user } = useAuthStore()
  const isGP = user?.project_roles?.some((r) => r.role === 'gp')

  useEffect(() => {
    if (!show || !isGP) {
      setLoading(false)
      return
    }

    const fetchBlockers = async () => {
      try {
        const response = await fetch(`/api/v1/projects/${projectId}/pilares`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        })

        if (response.ok) {
          const data = await response.json()
          const documento = data.documento || {}

          // Verificar DTs bloqueantes
          let blockerCount = 0
          const personas = new Set<string>()

          for (const [persona, parecer] of Object.entries(documento)) {
            if (
              parecer &&
              typeof parecer === 'object' &&
              'dts' in parecer &&
              Array.isArray(parecer.dts)
            ) {
              for (const dt of parecer.dts) {
                const dtData = typeof dt === 'object' ? dt : {}
                if (dtData.impacto === 'BLOCKER') {
                  blockerCount++
                  personas.add(persona)
                }
              }
            }
          }

          if (blockerCount > 0) {
            setBlockers({
              count: blockerCount,
              personas: Array.from(personas),
            })
          }
        }
      } catch (error) {
        console.error('Erro ao verificar bloqueantes:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchBlockers()
  }, [projectId, show, isGP])

  if (!show || !isGP || dismissed || loading || !blockers) {
    return null
  }

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-900">
              ⚠️ Discovery Tasks Bloqueantes Detectadas
            </h3>
            <p className="text-sm text-red-800 mt-1">
              Há {blockers.count} DT(s) bloqueante(s) em {blockers.personas.join(', ')} que precisam ser
              resolvidas antes de prosseguir com a geração de código.
            </p>
          </div>
        </div>
        <button
          onClick={() => {
            setDismissed(true)
            onDismiss?.()
          }}
          className="text-red-500 hover:text-red-700 transition-colors"
          aria-label="Descartar aviso"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}
