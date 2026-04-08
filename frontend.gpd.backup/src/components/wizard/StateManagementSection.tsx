/**
 * StateManagementSection — Phase 4 Sprint 3 — State Management Setup UI
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { Database, Loader, RefreshCw, Copy } from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';
import { api } from '@/services/api';

interface StateManagementSectionProps {
  projectId: string;
  pageState: string[];
  isLocked?: boolean;
}

interface StateLibrary {
  name: string;
  description: string;
  pros: string[];
  cons: string[];
  best_for: string[];
  bundle_size: string;
}

export function StateManagementSection({
  projectId,
  pageState = [],
  isLocked = false,
}: StateManagementSectionProps) {
  const [selectedLib, setSelectedLib] = useState<'redux' | 'zustand' | 'context'>('redux');
  const [includeHooks, setIncludeHooks] = useState(true);
  const [copiedText, setCopiedText] = useState<string | null>(null);

  // Fetch available libraries
  const { data: librariesData } = useQuery({
    queryKey: ['state-management-libraries', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/state-management/libraries`);
      return res.data;
    },
    enabled: !isLocked,
  });

  // Generate state management
  const { data: generationData, isPending, mutate: generateStateManagement } = useMutation({
    mutationFn: async (lib: string) => {
      const res = await api.post(`/projects/${projectId}/state-management/generate`, {
        page_state: pageState,
        framework: 'react',
        state_lib: lib,
        include_hooks: includeHooks,
      });
      return res.data;
    },
  });

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 2000);
  };

  if (isLocked) {
    return (
      <div className="text-xs text-gray-500">
        State management estará disponível quando o Gatekeeper estiver aprovado.
      </div>
    );
  }

  if (!pageState || pageState.length === 0) {
    return (
      <div className="text-xs text-gray-500">
        Defina o page state em Pages & Routes antes de gerar state management.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold">
        <Database size={15} className="text-purple-400" />
        <span>State Management Setup (Phase 4 Sprint 3)</span>
      </div>

      {/* Library Selection */}
      <div className="space-y-2">
        <p className="text-xs text-gray-400">Escolha a biblioteca de state management:</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {(['redux', 'zustand', 'context'] as const).map((lib) => (
            <button
              key={lib}
              onClick={() => setSelectedLib(lib)}
              className={clsx(
                'p-3 rounded-lg border text-xs transition-all text-left',
                selectedLib === lib
                  ? 'bg-purple-600/30 border-purple-600 text-purple-300'
                  : 'bg-gray-800/30 border-gray-700 text-gray-400 hover:border-gray-600'
              )}
            >
              <p className="font-medium mb-1">
                {lib === 'redux'
                  ? 'Redux Toolkit'
                  : lib === 'zustand'
                    ? 'Zustand'
                    : 'Context API'}
              </p>
              <p className="text-gray-500 text-xs">
                {lib === 'redux'
                  ? '~20kb • Complex apps'
                  : lib === 'zustand'
                    ? '~2.5kb • Medium apps'
                    : '0kb • Small apps'}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Include Hooks Toggle */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="includeHooks"
          checked={includeHooks}
          onChange={(e) => setIncludeHooks(e.target.checked)}
          className="rounded border-gray-700"
        />
        <label htmlFor="includeHooks" className="text-xs text-gray-400">
          Incluir custom hooks para estado
        </label>
      </div>

      {/* Generate Button */}
      <button
        onClick={() => generateStateManagement(selectedLib)}
        disabled={isPending}
        className={clsx(
          'w-full px-4 py-3 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-colors',
          isPending
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-purple-600 hover:bg-purple-700 text-white'
        )}
      >
        {isPending ? (
          <>
            <Loader size={14} className="animate-spin" />
            Gerando scaffolding...
          </>
        ) : (
          <>
            <RefreshCw size={14} />
            Gerar State Management
          </>
        )}
      </button>

      {/* Results */}
      {generationData && (
        <div className="space-y-4 border-t border-gray-700 pt-4">
          {/* Summary */}
          <div className="bg-dark-200/50 border border-purple-700/30 rounded-lg p-3">
            <p className="text-xs text-purple-300 mb-2">
              ✅ <strong>{generationData.state_lib.toUpperCase()}</strong> scaffolding gerado
            </p>
            <div className="text-xs text-gray-500">
              {generationData.page_state.length} state variables
            </div>
          </div>

          {/* Generated Files */}
          <div>
            <p className="text-xs text-gray-400 mb-2 font-semibold">Arquivos Gerados</p>
            <div className="space-y-2">
              {/* Main State File */}
              <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                <p className="text-sm font-medium text-gray-300 mb-1">
                  {generationData.state_management.file}
                </p>
                <p className="text-xs text-gray-500 mb-2">
                  {generationData.state_lib === 'redux'
                    ? 'Redux slice com actions, reducers e selectors'
                    : generationData.state_lib === 'zustand'
                      ? 'Zustand store com estado e actions'
                      : 'React Context com Provider e custom hooks'}
                </p>
                <button
                  onClick={() => handleCopy(generationData.state_management.file)}
                  className="text-xs text-purple-400 hover:text-purple-300 transition-colors flex items-center gap-1"
                >
                  <Copy size={12} />
                  {copiedText === generationData.state_management.file
                    ? 'Copiado!'
                    : 'Copiar caminho'}
                </button>
              </div>

              {/* Custom Hooks */}
              {generationData.custom_hooks && generationData.custom_hooks.length > 0 && (
                <div>
                  <p className="text-xs text-gray-400 mb-2">Custom Hooks</p>
                  {generationData.custom_hooks.map((hook: any, idx: number) => (
                    <div key={idx} className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                      <p className="text-sm font-medium text-gray-300">{hook.name}</p>
                      <p className="text-xs text-gray-500 mt-1">{hook.file}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Setup Instructions */}
              {generationData.setup && (
                <div className="bg-dark-200/30 border border-blue-700/30 rounded-lg p-3">
                  <p className="text-xs text-blue-300 font-semibold mb-2">Setup Instructions</p>
                  <pre className="text-xs text-blue-200 overflow-x-auto max-h-32">
                    {generationData.setup.store_configuration?.substring(0, 200)}...
                  </pre>
                </div>
              )}
            </div>
          </div>

          {/* Libraries Info */}
          {librariesData && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">Informações da Biblioteca</p>
              {librariesData[selectedLib] && (
                <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3 space-y-2">
                  <div>
                    <p className="text-xs text-gray-400">Vantagens:</p>
                    <ul className="text-xs text-gray-500 ml-4 list-disc">
                      {librariesData[selectedLib].pros?.slice(0, 3).map((pro: string, i: number) => (
                        <li key={i}>{pro}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400">Bundle Size:</p>
                    <p className="text-xs text-gray-500">{librariesData[selectedLib].bundle_size}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
