/**
 * DiscrepanciesPage — Página dedicada para resolução de conflitos entre personas
 *
 * Acessada após personas analisarem documento ingerido.
 * Permite visualizar e resolver conflitos detectados.
 */

import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader, ArrowLeft } from 'lucide-react'
import { DiscrepanciesBoard } from '@/components/ingestion/DiscrepanciesBoard'
import { useToast } from '@/hooks/useToast'

interface DocumentInfo {
  id: string
  original_filename: string
  file_type: string
  uploaded_at: string
}

export function DiscrepanciesPage() {
  const { id: projectId, documentId } = useParams<{
    id: string
    documentId: string
  }>()
  const navigate = useNavigate()
  const toast = useToast()

  const [document, setDocument] = useState<DocumentInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [consolidating, setConsolidating] = useState(false)

  useEffect(() => {
    if (projectId && documentId) {
      fetchDocumentInfo()
    }
  }, [projectId, documentId])

  const fetchDocumentInfo = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        }
      )
      if (response.ok) {
        const data = await response.json()
        setDocument(data)
      }
    } catch (error) {
      console.error('Erro ao carregar documento:', error)
      toast.error('Erro ao carregar informações do documento')
    } finally {
      setLoading(false)
    }
  }

  const handleConsolidate = async () => {
    if (!projectId || !documentId) return

    try {
      setConsolidating(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/consolidate-ocg`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        }
      )

      if (response.ok) {
        const data = await response.json()
        toast.success(`Consolidação completa: ${data.conflicts_count} conflitos detectados`)
      } else {
        toast.error('Erro ao consolidar análises')
      }
    } catch (error) {
      console.error('Erro ao consolidar:', error)
      toast.error('Erro ao consolidar análises')
    } finally {
      setConsolidating(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader className="h-8 w-8 animate-spin text-emerald-600" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header com volta */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate(`/projects/${projectId}/ingestion`)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-white hover:shadow transition-all"
          >
            <ArrowLeft className="h-5 w-5" />
            <span className="text-sm font-medium">Voltar para Ingestão</span>
          </button>
        </div>

        {/* Card principal */}
        <div className="bg-white rounded-xl shadow-lg overflow-hidden">
          {/* Header do card */}
          <div className="bg-gradient-to-r from-emerald-600 to-emerald-700 px-6 py-8">
            <h1 className="text-3xl font-bold text-white">Resolução de Conflitos</h1>
            {document && (
              <p className="text-emerald-100 mt-2">
                Documento: <span className="font-semibold">{document.original_filename}</span>
              </p>
            )}
          </div>

          {/* Conteúdo principal */}
          <div className="p-6">
            {/* Painel de ações */}
            <div className="mb-6 flex gap-3">
              <button
                onClick={handleConsolidate}
                disabled={consolidating}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {consolidating && <Loader className="h-4 w-4 animate-spin" />}
                Consolidar Análises
              </button>
              <p className="text-sm text-gray-600 flex items-center">
                Clique para disparar consolidação de personas
              </p>
            </div>

            {/* Board de discrepâncias */}
            {projectId && documentId && (
              <DiscrepanciesBoard projectId={projectId} documentId={documentId} />
            )}
          </div>

          {/* Footer informativo */}
          <div className="bg-gray-50 px-6 py-4 border-t border-gray-200">
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Como funciona:</h3>
            <ul className="text-xs text-gray-600 space-y-1">
              <li>• <strong>Conflito detectado:</strong> Personas divergem sobre um campo específico</li>
              <li>• <strong>Severidade:</strong> Varia de baixa (informativa) a crítica (decisão necessária)</li>
              <li>• <strong>Resolver:</strong> Escolha um valor ou aceite o consolidado (votação)</li>
              <li>• <strong>Override:</strong> Sua decisão sobrescreve o consenso das personas</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
