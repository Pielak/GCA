/**
 * PilaresVivosPage — Página principal de Pilares Vivos
 */

import React from 'react'
import { useParams } from 'react-router-dom'
import { PilaresVivosView } from '@/components/analysis/PilaresVivosView'

export function PilaresVivosPage() {
  const { id: projectId } = useParams<{ id: string }>()

  if (!projectId) {
    return <div className="text-red-600">Projeto não encontrado</div>
  }

  return (
    <div className="space-y-6 py-6">
      <PilaresVivosView projectId={projectId} />
    </div>
  )
}
