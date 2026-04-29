import React, { useEffect, useState } from 'react';
import { CheckCircle2, Clock, AlertCircle, Zap, Loader } from 'lucide-react';

interface PersonaResponse {
  id: string;
  persona_name: string;
  status: 'pending' | 'evaluating' | 'completed' | 'error';
  decision?: string;
  ocg_delta: Record<string, any>;
  followup_questions?: Array<any>;
  severity: 'info' | 'warning' | 'critical';
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  ai_provider_used?: string;
  ai_model_used?: string;
}

interface PersonasBoardProps {
  projectId: string;
  questionnaireId: string;
  onBoardUpdate?: (allCompleted: boolean) => void;
  pollInterval?: number; // ms, default 2000
}

const PERSONA_LABELS = {
  gp: 'Gerente de Projetos',
  arquiteto: 'Arquiteto',
  dba: 'DBA',
  dev_sr: 'Dev Senior',
  qa: 'QA',
};

const PERSONA_COLORS = {
  gp: 'bg-blue-50 border-blue-200',
  arquiteto: 'bg-purple-50 border-purple-200',
  dba: 'bg-green-50 border-green-200',
  dev_sr: 'bg-orange-50 border-orange-200',
  qa: 'bg-red-50 border-red-200',
};

const StatusIcon: React.FC<{ status: string; severity?: string }> = ({ status, severity }) => {
  switch (status) {
    case 'pending':
      return <Clock className="w-5 h-5 text-gray-400" />;
    case 'evaluating':
      return <Loader className="w-5 h-5 text-blue-500 animate-spin" />;
    case 'completed':
      if (severity === 'critical') {
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      }
      return <CheckCircle2 className="w-5 h-5 text-green-500" />;
    case 'error':
      return <AlertCircle className="w-5 h-5 text-red-500" />;
    default:
      return null;
  }
};

export const PersonaBoard: React.FC<PersonasBoardProps> = ({
  projectId,
  questionnaireId,
  onBoardUpdate,
  pollInterval = 2000,
}) => {
  const [personas, setPersonas] = useState<PersonaResponse[]>([]);
  const [allCompleted, setAllCompleted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch persona board data
  const fetchBoard = async () => {
    try {
      const response = await fetch(
        `/api/projects/${projectId}/technical-questionnaire/${questionnaireId}/personas-board`,
        {
          credentials: 'include',
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch persona board');
      }

      const data = await response.json();
      setPersonas(data.personas);
      setAllCompleted(data.all_completed);
      setError(null);

      if (onBoardUpdate) {
        onBoardUpdate(data.all_completed);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBoard();

    // Poll for updates
    const interval = setInterval(() => {
      if (!allCompleted) {
        fetchBoard();
      }
    }, pollInterval);

    return () => clearInterval(interval);
  }, [projectId, questionnaireId, pollInterval, allCompleted]);

  if (loading && personas.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700">Erro ao carregar board: {error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">Avaliação das Personas</h3>
        <div className="flex items-center gap-2">
          {allCompleted && (
            <span className="inline-flex items-center gap-1 bg-green-100 text-green-700 px-3 py-1 rounded-full text-sm font-medium">
              <CheckCircle2 className="w-4 h-4" />
              Avaliação Completa
            </span>
          )}
        </div>
      </div>

      {/* Persona Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {personas.map((persona) => (
          <div
            key={persona.id}
            className={`border rounded-lg p-4 transition-all ${PERSONA_COLORS[persona.persona_name as keyof typeof PERSONA_COLORS] || 'bg-gray-50 border-gray-200'}`}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div>
                <h4 className="font-semibold text-gray-900">
                  {PERSONA_LABELS[persona.persona_name as keyof typeof PERSONA_LABELS] || persona.persona_name}
                </h4>
                <p className="text-xs text-gray-500 mt-1">
                  {persona.ai_provider_used && persona.ai_model_used
                    ? `${persona.ai_provider_used} • ${persona.ai_model_used}`
                    : 'Configurando...'}
                </p>
              </div>
              <StatusIcon status={persona.status} severity={persona.severity} />
            </div>

            {/* Status */}
            <div className="mb-3">
              <span className="inline-block bg-white px-2 py-1 rounded text-xs font-medium">
                {persona.status === 'pending' && 'Aguardando'}
                {persona.status === 'evaluating' && 'Avaliando...'}
                {persona.status === 'completed' && 'Concluído'}
                {persona.status === 'error' && 'Erro'}
              </span>
            </div>

            {/* Decision */}
            {persona.decision && (
              <div className="mb-3">
                <p className="text-sm text-gray-700 line-clamp-2">{persona.decision}</p>
              </div>
            )}

            {/* Severity Badge */}
            {persona.severity !== 'info' && (
              <div className="mb-3">
                {persona.severity === 'critical' && (
                  <span className="inline-flex items-center gap-1 bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-medium">
                    <AlertCircle className="w-3 h-3" />
                    Crítico
                  </span>
                )}
                {persona.severity === 'warning' && (
                  <span className="inline-flex items-center gap-1 bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs font-medium">
                    <AlertCircle className="w-3 h-3" />
                    Aviso
                  </span>
                )}
              </div>
            )}

            {/* OCG Delta Preview */}
            {Object.keys(persona.ocg_delta).length > 0 && (
              <div className="mb-3 pt-3 border-t border-current border-opacity-20">
                <p className="text-xs text-gray-600 font-semibold mb-2">OCG Delta:</p>
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {Object.entries(persona.ocg_delta).map(([key, value]) => (
                    <div key={key} className="text-xs bg-white bg-opacity-50 p-1 rounded">
                      <span className="font-mono text-gray-700">
                        {key}: {typeof value === 'string' ? value.substring(0, 30) : JSON.stringify(value).substring(0, 30)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Error Message */}
            {persona.error_message && (
              <div className="text-xs bg-red-100 text-red-700 p-2 rounded mt-3">
                {persona.error_message}
              </div>
            )}

            {/* Timestamps */}
            <div className="text-xs text-gray-500 pt-3 border-t border-current border-opacity-20 space-y-1">
              {persona.started_at && (
                <p>Iniciado: {new Date(persona.started_at).toLocaleTimeString('pt-BR')}</p>
              )}
              {persona.completed_at && (
                <p>Concluído: {new Date(persona.completed_at).toLocaleTimeString('pt-BR')}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Empty State */}
      {personas.length === 0 && !loading && (
        <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
          <p className="text-gray-500">Nenhuma avaliação iniciada ainda</p>
        </div>
      )}

      {/* Progress Summary */}
      {personas.length > 0 && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="text-sm text-gray-600">
            <p>
              Progresso:{' '}
              <span className="font-semibold text-gray-900">
                {personas.filter((p) => p.status === 'completed').length} de {personas.length}
              </span>
            </p>
            <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full transition-all"
                style={{
                  width: `${(personas.filter((p) => p.status === 'completed').length / personas.length) * 100}%`,
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PersonaBoard;
