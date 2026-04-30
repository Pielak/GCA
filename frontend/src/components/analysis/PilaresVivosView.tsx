/**
 * PilaresVivosView — Visualização do documento vivo com análise de 7 personas
 *
 * Mostra resultado da consolidação com 7 seções (uma por persona).
 * Cada seção contém análise, DTs, status e recomendações.
 */

import React, { useEffect } from 'react'
import { Loader, AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react'
import { usePilaresVivos } from '@/hooks/usePilaresVivos'

interface Props {
  projectId: string
}

export function PilaresVivosView({ projectId }: Props) {
  const { data, loading, error, inicializar, regenerar } = usePilaresVivos(projectId)
  const [regenerando, setRegenerando] = React.useState(false)

  useEffect(() => {
    inicializar()
  }, [projectId, inicializar])

  const handleRegenerar = async () => {
    try {
      setRegenerando(true)
      await regenerar()
    } finally {
      setRegenerando(false)
    }
  }

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader className="h-6 w-6 animate-spin text-emerald-600" />
        <span className="ml-3 text-gray-700">Carregando Pilares Vivos...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-red-900">Erro ao carregar Pilares Vivos</h3>
            <p className="text-sm text-red-800 mt-1">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-amber-900">Pilares Vivos não gerado</h3>
            <p className="text-sm text-amber-800 mt-1">
              Clique no botão abaixo para iniciar a análise das 7 personas.
            </p>
            <button
              onClick={handleRegenerar}
              disabled={regenerando}
              className="mt-3 inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-sm font-medium"
            >
              {regenerando ? (
                <>
                  <Loader className="h-4 w-4 animate-spin" />
                  Gerando...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Gerar Pilares Vivos
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    )
  }

  const personas = ['P4_Arquiteto', 'P1_DBA', 'P2_Compliance', 'P3_Seguranca', 'P5_Dev', 'P6_Tester', 'P7_QA']

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6 flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Pilares Vivos</h2>
          <p className="text-sm text-gray-600 mt-2">
            Análise consolidada de 7 personas sobre o projeto
          </p>
          {data.gerado_em && (
            <p className="text-xs text-gray-500 mt-1">
              Gerado em {new Date(data.gerado_em).toLocaleString('pt-BR')}
            </p>
          )}
        </div>
        <button
          onClick={handleRegenerar}
          disabled={regenerando}
          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-sm font-medium"
        >
          {regenerando ? (
            <>
              <Loader className="h-4 w-4 animate-spin" />
              Regenerando...
            </>
          ) : (
            <>
              <RefreshCw className="h-4 w-4" />
              Regenerar
            </>
          )}
        </button>
      </div>

      {/* Seções por Persona */}
      <div className="space-y-4">
        {personas.map((persona) => {
          const parecer = data.documento[persona]

          if (!parecer) {
            return (
              <div
                key={persona}
                className="bg-gray-50 rounded-lg border border-gray-200 p-4"
              >
                <p className="text-sm text-gray-600">
                  {persona}: análise não disponível
                </p>
              </div>
            )
          }

          const status = parecer.status || 'desconhecido'
          const statusColor = {
            completo: 'bg-emerald-50 border-emerald-200',
            erro: 'bg-red-50 border-red-200',
            parseado_como_texto: 'bg-blue-50 border-blue-200',
          }[status] || 'bg-gray-50 border-gray-200'

          return (
            <div key={persona} className={`rounded-lg border p-4 ${statusColor}`}>
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-semibold text-gray-900">{persona}</h3>
                {status === 'completo' && (
                  <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                )}
              </div>

              {/* Resumo simples do parecer */}
              <div className="text-sm text-gray-700 space-y-2">
                {parecer.analise_texto && (
                  <p className="whitespace-pre-wrap line-clamp-3">{parecer.analise_texto}</p>
                )}

                {parecer.parecer && (
                  <pre className="bg-white rounded p-2 overflow-auto max-h-48 text-xs">
                    {JSON.stringify(parecer.parecer, null, 2)}
                  </pre>
                )}

                {parecer.dts && parecer.dts.length > 0 && (
                  <div>
                    <p className="font-medium text-gray-900">Discovery Tasks:</p>
                    <ul className="list-disc list-inside text-xs mt-1 space-y-1">
                      {parecer.dts.slice(0, 3).map((dt: any, idx: number) => (
                        <li key={idx}>
                          {typeof dt === 'string' ? dt : JSON.stringify(dt)}
                        </li>
                      ))}
                      {parecer.dts.length > 3 && (
                        <li className="text-gray-500">
                          ... e mais {parecer.dts.length - 3}
                        </li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
