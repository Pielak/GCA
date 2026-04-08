/**
 * Componente ConflictModal
 * Modal mostrando conflito de sincronização com opções de resolução
 */

import { X, AlertTriangle } from "lucide-react";
import { useState } from "react";

export type ConflictType = "sync_conflict" | "pull_conflict";

interface ConflictModalProps {
  isOpen: boolean;
  type?: ConflictType;
  fileName?: string;
  message?: string;
  onDiscard: () => void;           // Descartar edições locais / usar remoto
  onKeep: () => void;              // Manter edições locais / sobrescrever remoto
  onCancel: () => void;
  discardLoading?: boolean;
  keepLoading?: boolean;
}

export function ConflictModal({
  isOpen,
  type = "sync_conflict",
  fileName,
  message,
  onDiscard,
  onKeep,
  onCancel,
  discardLoading = false,
  keepLoading = false,
}: ConflictModalProps) {
  if (!isOpen) return null;

  const isSyncConflict = type === "sync_conflict";

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center">
      <div className="bg-gray-900 rounded-lg max-w-md w-full border border-red-700/50 overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 p-4 border-b border-red-700/50 bg-red-900/20">
          <AlertTriangle className="text-red-500 shrink-0" size={24} />
          <div>
            <h2 className="text-lg font-semibold text-red-400">⚠️ Conflito Detectado!</h2>
            {fileName && (
              <p className="text-xs text-gray-400 mt-1">{fileName}</p>
            )}
          </div>
          <button
            onClick={onCancel}
            className="ml-auto text-gray-400 hover:text-gray-300 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-3">
          <div className="text-sm text-gray-300 space-y-2">
            {isSyncConflict ? (
              <>
                <p>
                  💥 <strong>Arquivo foi modificado no GitHub</strong> enquanto você editava localmente.
                </p>
                <p className="text-xs text-gray-500">
                  {message || "Outro usuário ou outro commit alterou este arquivo. Escolha como proceder."}
                </p>
              </>
            ) : (
              <>
                <p>
                  🔄 <strong>Arquivo mudou no repositório remoto</strong>
                </p>
                <p className="text-xs text-gray-500">
                  {message || "Sincronize sua cópia local com o GitHub."}
                </p>
              </>
            )}
          </div>

          {/* Options */}
          <div className="bg-gray-800/50 rounded p-3 text-xs space-y-2">
            <div className="text-gray-400">
              <strong>O que você quer fazer?</strong>
            </div>
            {isSyncConflict ? (
              <>
                <p className="text-gray-500">
                  ✓ <strong>Manter edições locais:</strong> Sobrescreve o arquivo no GitHub com suas alterações
                </p>
                <p className="text-gray-500">
                  ✓ <strong>Sincronizar com remoto:</strong> Descarta edições e usa a versão do GitHub
                </p>
              </>
            ) : (
              <>
                <p className="text-gray-500">
                  ✓ <strong>Manter edições locais:</strong> Continua editando, fará merge depois
                </p>
                <p className="text-gray-500">
                  ✓ <strong>Sincronizar com remoto:</strong> Carrega versão mais recente do GitHub
                </p>
              </>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 p-4 border-t border-gray-700 bg-gray-800/50">
          <button
            onClick={onCancel}
            className="flex-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded text-sm font-medium transition-colors"
          >
            Cancelar
          </button>

          <button
            onClick={onDiscard}
            disabled={discardLoading}
            className="flex-1 px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
          >
            {discardLoading ? "Sincronizando..." : "Sincronizar com Remoto"}
          </button>

          <button
            onClick={onKeep}
            disabled={keepLoading}
            className="flex-1 px-3 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
          >
            {keepLoading ? "Salvando..." : "Manter Edições"}
          </button>
        </div>
      </div>
    </div>
  );
}
