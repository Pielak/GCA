/**
 * PagesAndRoutesSection — Phase 4 — Pages & Routes Generation
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { Layers, ExternalLink, Loader, RefreshCw, Copy } from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';
import { api } from '@/services/api';

interface PagesAndRoutesSectionProps {
  projectId: string;
  isLocked?: boolean;
}

interface PageConfig {
  id: string;
  path: string;
  name: string;
  file: string;
  layout: string;
  components: string[];
  state: string[];
  metadata: {
    appType: string;
    needsAuth: boolean;
    isPublic: boolean;
    requiresData: boolean;
  };
}

interface RouteConfig {
  id: string;
  path: string;
  name: string;
  component: string;
  lazy: boolean;
  icon?: string;
  label?: string;
}

interface LayoutConfig {
  name: string;
  file: string;
  template: string;
  components: string[];
  responsive: Record<string, string>;
  children_routes: string[];
}

interface ContextConfig {
  id: string;
  name: string;
  file: string;
  provides: string[];
  hooks: string[];
  description: string;
}

interface GenerationResult {
  pages: PageConfig[];
  routes: RouteConfig[];
  layouts: LayoutConfig[];
  contexts: ContextConfig[];
  file_structure: Array<{ path: string; type: string; description?: string }>;
  framework: string;
  codeSplitting: { enabled: boolean; strategy: string };
}

export function PagesAndRoutesSection({ projectId, isLocked = false }: PagesAndRoutesSectionProps) {
  const [selectedFramework, setSelectedFramework] = useState<'react' | 'vue' | 'svelte' | 'next'>('react');
  const [expandedPage, setExpandedPage] = useState<string | null>(null);
  const [copiedText, setCopiedText] = useState<string | null>(null);

  // Fetch layout templates
  const { data: templatesData } = useQuery({
    queryKey: ['layout-templates', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/pages/templates`);
      return res.data.data;
    },
    enabled: !isLocked,
  });

  // Fetch route patterns
  const { data: patternsData } = useQuery({
    queryKey: ['route-patterns', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/pages/route-patterns`);
      return res.data.data;
    },
    enabled: !isLocked,
  });

  // Generate pages and routes
  const { data: generationData, isPending, mutate: generatePagesAndRoutes } = useMutation({
    mutationFn: async (framework: string) => {
      const res = await api.post(`/projects/${projectId}/pages/generate`, {
        framework,
        include_nested_routes: true,
        auto_code_split: true,
      });
      return res.data.data as GenerationResult;
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
        Configuração de páginas estará disponível quando o Gatekeeper estiver aprovado.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold">
        <Layers size={15} className="text-cyan-400" />
        <span>Páginas & Rotas (Phase 4)</span>
      </div>

      {/* Framework Selection */}
      <div className="flex flex-wrap gap-2">
        {(['react', 'vue', 'svelte', 'next'] as const).map((fw) => (
          <button
            key={fw}
            onClick={() => setSelectedFramework(fw)}
            className={clsx(
              'px-3 py-2 text-xs font-medium rounded-lg border transition-colors',
              selectedFramework === fw
                ? 'bg-cyan-700/50 border-cyan-600 text-cyan-300'
                : 'bg-gray-800/30 border-gray-700 text-gray-400 hover:border-gray-600'
            )}
          >
            {fw.charAt(0).toUpperCase() + fw.slice(1)}
          </button>
        ))}
      </div>

      {/* Generate Button */}
      <button
        onClick={() => generatePagesAndRoutes(selectedFramework)}
        disabled={isPending}
        className={clsx(
          'w-full px-4 py-3 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-colors',
          isPending
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-cyan-600 hover:bg-cyan-700 text-white'
        )}
      >
        {isPending ? (
          <>
            <Loader size={14} className="animate-spin" />
            Gerando estrutura...
          </>
        ) : (
          <>
            <RefreshCw size={14} />
            Gerar Páginas & Rotas
          </>
        )}
      </button>

      {/* Results */}
      {generationData && (
        <div className="space-y-4 border-t border-gray-700 pt-4">
          {/* Summary Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-dark-200/50 border border-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-400 mb-1">Páginas</div>
              <div className="text-lg font-bold text-cyan-400">{generationData.pages.length}</div>
            </div>
            <div className="bg-dark-200/50 border border-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-400 mb-1">Rotas</div>
              <div className="text-lg font-bold text-cyan-400">{generationData.routes.length}</div>
            </div>
            <div className="bg-dark-200/50 border border-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-400 mb-1">Layouts</div>
              <div className="text-lg font-bold text-cyan-400">{generationData.layouts.length}</div>
            </div>
            <div className="bg-dark-200/50 border border-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-400 mb-1">Contextos</div>
              <div className="text-lg font-bold text-cyan-400">{generationData.contexts.length}</div>
            </div>
          </div>

          {/* Code Splitting Info */}
          <div className="bg-dark-200/30 border border-blue-700/30 rounded-lg p-3">
            <p className="text-xs text-blue-300">
              ✅ <strong>Code Splitting Automático:</strong> {generationData.codeSplitting.strategy}
            </p>
          </div>

          {/* Pages List */}
          <div>
            <p className="text-xs text-gray-400 mb-2 font-semibold">Páginas Geradas</p>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {generationData.pages.map((page) => (
                <div
                  key={page.id}
                  className="bg-dark-200/50 border border-gray-700/50 rounded-lg p-3 hover:border-cyan-700/50 transition-colors cursor-pointer"
                  onClick={() => setExpandedPage(expandedPage === page.id ? null : page.id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-300">{page.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{page.path || '/'}</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        <span className="text-xs bg-purple-900/40 text-purple-300 px-2 py-0.5 rounded">
                          {page.layout}
                        </span>
                        {page.metadata.needsAuth && (
                          <span className="text-xs bg-orange-900/40 text-orange-300 px-2 py-0.5 rounded">
                            🔐 Auth Required
                          </span>
                        )}
                        {page.metadata.requiresData && (
                          <span className="text-xs bg-green-900/40 text-green-300 px-2 py-0.5 rounded">
                            📊 Data Fetching
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {expandedPage === page.id && (
                    <div className="mt-3 pt-3 border-t border-gray-700/50 space-y-2 text-xs">
                      <div>
                        <p className="text-gray-400 mb-1">Componentes:</p>
                        <div className="flex flex-wrap gap-1">
                          {page.components.map((comp) => (
                            <span
                              key={comp}
                              className="bg-cyan-900/30 border border-cyan-700/50 text-cyan-300 px-2 py-0.5 rounded"
                            >
                              {comp}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-gray-400 mb-1">Estado Inicial:</p>
                        <div className="flex flex-wrap gap-1">
                          {page.state.map((state) => (
                            <span
                              key={state}
                              className="bg-indigo-900/30 border border-indigo-700/50 text-indigo-300 px-2 py-0.5 rounded"
                            >
                              {state}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="bg-gray-900/50 rounded p-2">
                        <p className="text-gray-400 mb-1">Caminho do Arquivo:</p>
                        <div className="flex items-center gap-2">
                          <code className="text-gray-300 text-xs break-all flex-1">{page.file}</code>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCopy(page.file);
                            }}
                            className="p-1 hover:bg-gray-700 rounded text-gray-500 hover:text-gray-300 transition-colors"
                            title="Copiar caminho"
                          >
                            <Copy size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Layouts Summary */}
          {generationData.layouts.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">Layouts Reutilizáveis</p>
              <div className="space-y-2">
                {generationData.layouts.map((layout) => (
                  <div key={layout.name} className="bg-dark-200/30 border border-purple-700/30 rounded-lg p-3">
                    <p className="text-sm font-medium text-purple-300">{layout.name}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      Usado em: {layout.children_routes.length} rota(s)
                    </p>
                    <div className="text-xs text-gray-400 mt-1">
                      {layout.components.length} componentes
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Contexts Summary */}
          {generationData.contexts.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">Contextos Globais</p>
              <div className="space-y-2">
                {generationData.contexts.map((ctx) => (
                  <div key={ctx.id} className="bg-dark-200/30 border border-green-700/30 rounded-lg p-3">
                    <p className="text-sm font-medium text-green-300">{ctx.name}</p>
                    <p className="text-xs text-gray-500 mt-1">{ctx.description}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {ctx.provides.slice(0, 3).map((item) => (
                        <span key={item} className="text-xs bg-green-900/40 text-green-300 px-2 py-0.5 rounded">
                          {item}
                        </span>
                      ))}
                      {ctx.provides.length > 3 && (
                        <span className="text-xs text-gray-500">
                          +{ctx.provides.length - 3} mais
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* File Structure */}
          {generationData.file_structure.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-2 font-semibold">Estrutura de Arquivos Recomendada</p>
              <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3 max-h-48 overflow-y-auto">
                <code className="text-xs text-gray-400 whitespace-pre-wrap break-words">
                  {generationData.file_structure
                    .map((f) => `${f.type === 'directory' ? '📁 ' : '📄 '}${f.path}`)
                    .join('\n')}
                </code>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!generationData && !isPending && (
        <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-4 text-center">
          <Layers size={24} className="text-gray-600 mx-auto mb-2" />
          <p className="text-xs text-gray-500">
            Clique acima para gerar estrutura de páginas baseada em seus artefatos
          </p>
        </div>
      )}
    </div>
  );
}
