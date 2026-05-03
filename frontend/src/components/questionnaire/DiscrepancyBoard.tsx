import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Clock, Zap } from 'lucide-react';

interface Discrepancy {
  id: string;
  field_path: string;
  conflicting_personas: string[];
  conflicting_values: Record<string, any>;
  severity: 'low' | 'medium' | 'high' | 'critical';
  category?: string;
  status: 'unresolved' | 'voted' | 'overridden' | 'resolved';
  context?: string;
  created_at: string;
  resolved_at?: string;
}

interface DiscrepancyBoardProps {
  projectId: string;
  questionnaireId: string;
  onDiscrepanciesUpdate?: (unresolvedCount: number) => void;
  pollInterval?: number; // ms, default 2000
}

const SEVERITY_COLOR = {
  low: 'bg-blue-50 border-blue-200',
  medium: 'bg-yellow-50 border-yellow-200',
  high: 'bg-orange-50 border-orange-200',
  critical: 'bg-red-50 border-red-200',
};

const SEVERITY_LABEL = {
  low: 'Baixa',
  medium: 'Média',
  high: 'Alta',
  critical: 'Crítica',
};

const PERSONA_LABELS = {
  gp: 'GP',
  arquiteto: 'Arquiteto',
  dba: 'DBA',
  dev_sr: 'Dev Sr',
  qa: 'QA',
};

export const DiscrepancyBoard: React.FC<DiscrepancyBoardProps> = ({
  projectId,
  questionnaireId,
  onDiscrepanciesUpdate,
  pollInterval = 2000,
}) => {
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [unresolvedCount, setUnresolvedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  // Fetch discrepancies board
  const fetchBoard = async () => {
    try {
      const response = await fetch(
        `/api/projects/${projectId}/technical-questionnaire/${questionnaireId}/discrepancies-board`,
        { credentials: 'include' }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch discrepancies board');
      }

      const data = await response.json();
      setDiscrepancies(data.discrepancies);
      setUnresolvedCount(data.unresolved_count);
      setError(null);

      if (onDiscrepanciesUpdate) {
        onDiscrepanciesUpdate(data.unresolved_count);
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
      if (unresolvedCount > 0) {
        fetchBoard();
      }
    }, pollInterval);

    return () => clearInterval(interval);
  }, [projectId, questionnaireId, pollInterval, unresolvedCount]);

  const handleResolveVote = async (discrepancyId: string, selectedValue: string) => {
    setResolvingId(discrepancyId);

    try {
      const response = await fetch(
        `/api/projects/${projectId}/technical-questionnaire/${questionnaireId}/discrepancies/${discrepancyId}/resolve`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            resolved_value: selectedValue,
            resolution_type: 'vote',
            justification: 'Resolvido pela equipe',
          }),
        }
      );

      if (response.ok) {
        // Refresh board
        await fetchBoard();
      } else {
        setError('Falha ao resolver discrepância');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setResolvingId(null);
    }
  };

  if (loading && discrepancies.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Clock className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    );
  }

  if (discrepancies.length === 0) {
    return (
      <div className="text-center py-12 bg-green-50 rounded-lg border border-green-200">
        <CheckCircle2 className="w-8 h-8 text-green-600 mx-auto mb-2" />
        <p className="text-green-700 font-semibold">Sem discrepâncias</p>
        <p className="text-green-600 text-sm mt-1">Todas as personas concordam!</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">Conflitos Detectados</h3>
        <span className="inline-flex items-center gap-2 bg-red-100 text-red-700 px-3 py-1 rounded-full text-sm font-medium">
          <AlertCircle className="w-4 h-4" />
          {unresolvedCount} não resolvido{unresolvedCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Discrepancy Cards */}
      <div className="space-y-3">
        {discrepancies.map((disc) => (
          <div
            key={disc.id}
            className={`border rounded-lg p-4 transition-all ${SEVERITY_COLOR[disc.severity]}`}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-gray-900">{disc.field_path}</h4>
                  <span className="text-xs bg-white px-2 py-1 rounded font-medium">
                    {SEVERITY_LABEL[disc.severity]}
                  </span>
                </div>
                {disc.category && (
                  <p className="text-xs text-gray-600 mt-1">Categoria: {disc.category}</p>
                )}
              </div>
              {disc.status === 'resolved' && (
                <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
              )}
            </div>

            {/* Personas em conflito */}
            <div className="mb-3">
              <p className="text-xs text-gray-600 mb-2">Personas em desacordo:</p>
              <div className="space-y-2">
                {disc.conflicting_personas.map((persona) => (
                  <div key={persona} className="text-sm bg-white bg-opacity-50 p-2 rounded flex items-center justify-between">
                    <span className="font-medium text-gray-700">
                      {PERSONA_LABELS[persona as keyof typeof PERSONA_LABELS] || persona}
                    </span>
                    <span className="text-gray-600">
                      {typeof disc.conflicting_values[persona] === 'string'
                        ? disc.conflicting_values[persona]
                        : JSON.stringify(disc.conflicting_values[persona]).substring(0, 30)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Resolução */}
            {disc.status === 'unresolved' && (
              <div className="mt-4 pt-4 border-t border-current border-opacity-20">
                <p className="text-xs text-gray-700 font-semibold mb-2">Qual valor aceitar?</p>
                <div className="space-y-2">
                  {disc.conflicting_personas.map((persona) => (
                    <button
                      key={persona}
                      onClick={() => handleResolveVote(disc.id, String(disc.conflicting_values[persona]))}
                      disabled={resolvingId === disc.id}
                      className="w-full text-left bg-white hover:bg-gray-100 disabled:opacity-50 p-2 rounded border border-gray-300 text-sm transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span>
                          {PERSONA_LABELS[persona as keyof typeof PERSONA_LABELS] || persona}:
                          {' '}
                          <span className="font-medium">
                            {typeof disc.conflicting_values[persona] === 'string'
                              ? disc.conflicting_values[persona]
                              : JSON.stringify(disc.conflicting_values[persona])}
                          </span>
                        </span>
                        {resolvingId === disc.id && (
                          <Zap className="w-4 h-4 animate-pulse text-blue-500" />
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {disc.status === 'resolved' && disc.resolved_at && (
              <div className="text-xs text-gray-600 pt-2">
                Resolvido em {new Date(disc.resolved_at).toLocaleString('pt-BR')}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Progress */}
      {discrepancies.length > 0 && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="text-sm text-gray-600">
            <p>
              Resolvidas:{' '}
              <span className="font-semibold text-gray-900">
                {discrepancies.filter((d) => d.status === 'resolved').length} de {discrepancies.length}
              </span>
            </p>
            <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full transition-all"
                style={{
                  width: `${(discrepancies.filter((d) => d.status === 'resolved').length / discrepancies.length) * 100}%`,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-sm text-red-700">Erro: {error}</p>
        </div>
      )}
    </div>
  );
};

export default DiscrepancyBoard;
