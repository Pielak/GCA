/**
 * VersionNotificationBanner — Banner de notificações de atualização de versão
 *
 * Exibe um banner quando há atualizações disponíveis para ferramentas do projeto.
 * Permite descartar/reconhecer atualizações.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, X, CheckCircle } from 'lucide-react';
import { languageStackApi } from '@/services/languageStackApi';

interface VersionNotificationBannerProps {
  projectId: string;
}

export function VersionNotificationBanner({ projectId }: VersionNotificationBannerProps) {
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  // ── Query para obter atualizações não lidas ────────────────────────────

  const { data: versionUpdates, isLoading } = useQuery({
    queryKey: ['version-updates', projectId],
    queryFn: () => languageStackApi.listVersionUpdates(projectId, false),
    refetchInterval: 5 * 60 * 1000, // Refetch a cada 5 minutos
    retry: 1,
    staleTime: 1000 * 60, // 1 minuto
  });

  // ── Mutation para marcar como lida ─────────────────────────────────────

  const acknowledgeMutation = useMutation({
    mutationFn: (updateId: string) =>
      languageStackApi.acknowledgeVersionUpdate(projectId, updateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['version-updates', projectId] });
    },
  });

  // ── Handlers ───────────────────────────────────────────────────────────

  const handleDismiss = (updateId: string) => {
    setDismissed(prev => new Set([...prev, updateId]));
  };

  const handleAcknowledge = (updateId: string) => {
    acknowledgeMutation.mutate(updateId);
  };

  // ── Render ─────────────────────────────────────────────────────────────

  if (isLoading || !versionUpdates || versionUpdates.unread_count === 0) {
    return null;
  }

  const visibleUpdates = versionUpdates.version_updates.filter(
    u => !dismissed.has(u.id)
  ).slice(0, 3); // Mostrar máximo 3 atualizações

  if (visibleUpdates.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2 mb-4">
      {visibleUpdates.map(update => (
        <div
          key={update.id}
          className="bg-amber-900/30 border border-amber-700/50 rounded-lg p-3 flex items-start justify-between gap-3"
        >
          <div className="flex items-start gap-3 flex-1">
            <AlertCircle size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-amber-300 font-medium">
                Atualização disponível: <strong>{update.tool_name}</strong>
              </p>
              <p className="text-xs text-amber-200/70 mt-0.5">
                {update.current_version} → {update.available_version}
                {update.is_breaking_change && (
                  <span className="ml-2 px-1.5 py-0.5 bg-red-900/50 text-red-300 rounded text-xs">
                    ⚠️ Breaking Change
                  </span>
                )}
              </p>
              {update.recommendation && (
                <p className="text-xs text-amber-200/60 mt-1 italic">
                  {update.recommendation}
                </p>
              )}
            </div>
          </div>

          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={() => handleAcknowledge(update.id)}
              disabled={acknowledgeMutation.isPending}
              className="px-2 py-1 text-xs bg-green-700/40 hover:bg-green-700/60 text-green-300 rounded transition-colors disabled:opacity-50 flex items-center gap-1"
            >
              <CheckCircle size={12} />
              Lido
            </button>
            <button
              onClick={() => handleDismiss(update.id)}
              className="px-2 py-1 text-xs bg-gray-700/40 hover:bg-gray-700/60 text-gray-300 rounded transition-colors"
              aria-label="Descartar"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ))}

      {versionUpdates.unread_count > 3 && (
        <p className="text-xs text-amber-400/60 px-3">
          +{versionUpdates.unread_count - 3} mais atualização(ões) disponível(is)
        </p>
      )}
    </div>
  );
}
