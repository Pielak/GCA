/**
 * ApiIntegrationSection — Phase 4 Sprint 4 — API Client & Data Fetching UI
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { Zap, Loader, Upload, Copy } from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';
import { api } from '@/services/api';

interface ApiIntegrationSectionProps {
  projectId: string;
  baseUrl?: string;
  isLocked?: boolean;
}

interface ApiSchema {
  type: 'openapi' | 'graphql' | 'custom';
  resources: string[];
}

export function ApiIntegrationSection({
  projectId,
  baseUrl = 'http://localhost:8000/api/v1',
  isLocked = false,
}: ApiIntegrationSectionProps) {
  const [clientLib, setClientLib] = useState<'axios' | 'fetch'>('axios');
  const [includeReactQuery, setIncludeReactQuery] = useState(true);
  const [apiUrl, setApiUrl] = useState(baseUrl);
  const [resources, setResources] = useState<string[]>(['products', 'users']);
  const [newResource, setNewResource] = useState('');
  const [copiedText, setCopiedText] = useState<string | null>(null);

  // Fetch HTTP client libraries info
  const { data: librariesData } = useQuery({
    queryKey: ['http-libraries', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/api-integration/client-libraries`);
      return res.data;
    },
    enabled: !isLocked,
  });

  // Fetch data fetching options
  const { data: dataFetchingData } = useQuery({
    queryKey: ['data-fetching-options', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/api-integration/data-fetching-options`);
      return res.data;
    },
    enabled: !isLocked && includeReactQuery,
  });

  // Generate API client
  const { data: generationData, isPending, mutate: generateApiClient } = useMutation({
    mutationFn: async () => {
      const res = await api.post(`/projects/${projectId}/api-integration/generate-client`, {
        base_url: apiUrl,
        client_lib: clientLib,
        include_react_query: includeReactQuery,
        api_schema: {
          type: 'custom',
          resources,
          base_url: apiUrl,
        },
      });
      return res.data;
    },
  });

  const handleAddResource = () => {
    if (newResource && !resources.includes(newResource)) {
      setResources([...resources, newResource]);
      setNewResource('');
    }
  };

  const handleRemoveResource = (idx: number) => {
    setResources(resources.filter((_, i) => i !== idx));
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 2000);
  };

  if (isLocked) {
    return (
      <div className="text-xs text-gray-500">
        API client estará disponível quando o Gatekeeper estiver aprovado.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold">
        <Zap size={15} className="text-yellow-400" />
        <span>API Client & Data Fetching (Phase 4 Sprint 4)</span>
      </div>

      {/* Base URL */}
      <div>
        <label className="text-xs text-gray-400 mb-1 block">API Base URL:</label>
        <input
          type="text"
          value={apiUrl}
          onChange={(e) => setApiUrl(e.target.value)}
          placeholder="http://localhost:8000/api/v1"
          className="w-full px-3 py-2 bg-dark-200 border border-gray-700 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-yellow-500"
        />
      </div>

      {/* HTTP Client Library */}
      <div className="space-y-2">
        <p className="text-xs text-gray-400">HTTP Client:</p>
        <div className="grid grid-cols-2 gap-2">
          {(['axios', 'fetch'] as const).map((lib) => (
            <button
              key={lib}
              onClick={() => setClientLib(lib)}
              className={clsx(
                'p-3 rounded-lg border text-xs transition-all text-left',
                clientLib === lib
                  ? 'bg-yellow-600/30 border-yellow-600 text-yellow-300'
                  : 'bg-gray-800/30 border-gray-700 text-gray-400 hover:border-gray-600'
              )}
            >
              <p className="font-medium">{lib === 'axios' ? 'Axios' : 'Fetch API'}</p>
              <p className="text-gray-500 text-xs mt-1">
                {lib === 'axios' ? '~14kb • Interceptors' : '0kb • Native'}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* React Query Toggle */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="includeReactQuery"
          checked={includeReactQuery}
          onChange={(e) => setIncludeReactQuery(e.target.checked)}
          className="rounded border-gray-700"
        />
        <label htmlFor="includeReactQuery" className="text-xs text-gray-400">
          Incluir React Query hooks para data fetching
        </label>
      </div>

      {/* Resources */}
      <div className="space-y-2">
        <p className="text-xs text-gray-400">API Resources (para geração de hooks):</p>
        <div className="flex gap-2">
          <input
            type="text"
            value={newResource}
            onChange={(e) => setNewResource(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') handleAddResource();
            }}
            placeholder="products, users, orders..."
            className="flex-1 px-3 py-2 bg-dark-200 border border-gray-700 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-yellow-500"
          />
          <button
            onClick={handleAddResource}
            className="px-3 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded text-sm transition-colors"
          >
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {resources.map((resource, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 px-3 py-1 bg-yellow-900/30 border border-yellow-700/50 rounded-full text-yellow-300 text-xs"
            >
              {resource}
              <button
                onClick={() => handleRemoveResource(idx)}
                className="text-yellow-400 hover:text-yellow-200"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Generate Button */}
      <button
        onClick={() => generateApiClient()}
        disabled={isPending || resources.length === 0}
        className={clsx(
          'w-full px-4 py-3 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-colors',
          isPending || resources.length === 0
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-yellow-600 hover:bg-yellow-700 text-white'
        )}
      >
        {isPending ? (
          <>
            <Loader size={14} className="animate-spin" />
            Gerando API client...
          </>
        ) : (
          <>
            <Zap size={14} />
            Gerar API Client & Hooks
          </>
        )}
      </button>

      {/* Results */}
      {generationData && (
        <div className="space-y-4 border-t border-gray-700 pt-4">
          {/* Summary */}
          <div className="bg-dark-200/50 border border-yellow-700/30 rounded-lg p-3">
            <p className="text-xs text-yellow-300">
              ✅ <strong>{clientLib === 'axios' ? 'Axios' : 'Fetch'}</strong> client gerado
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {generationData.hooks?.length || 0} hooks gerados • {resources.length} resources
            </p>
          </div>

          {/* API Client File */}
          {generationData.api_client && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">API Client</p>
              <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                <p className="text-sm font-medium text-gray-300 mb-1">
                  {generationData.api_client.file}
                </p>
                <p className="text-xs text-gray-500 mb-2">
                  {clientLib === 'axios'
                    ? 'Axios client com interceptors, auto-token injection e error handling'
                    : 'Fetch API wrapper com interceptors manuais'}
                </p>
                <button
                  onClick={() => handleCopy(generationData.api_client.file)}
                  className="text-xs text-yellow-400 hover:text-yellow-300 flex items-center gap-1"
                >
                  <Copy size={12} />
                  {copiedText === generationData.api_client.file ? 'Copiado!' : 'Copiar'}
                </button>
              </div>
            </div>
          )}

          {/* Hooks */}
          {generationData.hooks && generationData.hooks.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">
                React Query Hooks ({generationData.hooks.length})
              </p>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {generationData.hooks.map((hook: any, idx: number) => (
                  <div key={idx} className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                    <p className="text-sm font-medium text-gray-300">{hook.name}</p>
                    <p className="text-xs text-gray-500 mt-1">{hook.file}</p>
                    <p className="text-xs text-gray-600 mt-1">
                      ├─ use{hook.resource.charAt(0).toUpperCase() + hook.resource.slice(1)}List (GET)
                      <br />
                      ├─ use{hook.resource.charAt(0).toUpperCase() + hook.resource.slice(1)} (GET by ID)
                      <br />
                      ├─ useCreate{hook.resource.charAt(0).toUpperCase() + hook.resource.slice(1)} (POST)
                      <br />
                      ├─ useUpdate{hook.resource.charAt(0).toUpperCase() + hook.resource.slice(1)} (PUT)
                      <br />
                      └─ useDelete{hook.resource.charAt(0).toUpperCase() + hook.resource.slice(1)} (DELETE)
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Types File */}
          {generationData.types && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">Types</p>
              <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                <p className="text-sm font-medium text-gray-300">{generationData.types.file}</p>
                <p className="text-xs text-gray-500 mt-1">
                  Auto-generated TypeScript interfaces para todos os resources
                </p>
              </div>
            </div>
          )}

          {/* Data Fetching Info */}
          {includeReactQuery && dataFetchingData && (
            <div className="bg-dark-200/30 border border-green-700/30 rounded-lg p-3">
              <p className="text-xs text-green-300 font-semibold mb-2">React Query Features</p>
              <ul className="text-xs text-gray-500 space-y-1">
                <li>✓ Automatic caching & deduplication</li>
                <li>✓ Refetch on window focus</li>
                <li>✓ Query invalidation on mutations</li>
                <li>✓ Optimistic updates</li>
                <li>✓ DevTools integration</li>
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
