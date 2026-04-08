/**
 * TechStackSection — Exibição de tech stack detectado + StackShare
 */

import { useQuery } from '@tanstack/react-query';
import { Cpu, ExternalLink, Loader } from 'lucide-react';
import clsx from 'clsx';
import { api } from '@/services/api';

interface TechStackSectionProps {
  projectId: string;
}

interface TechStackData {
  languages: string[];
  frameworks: string[];
  databases: string[];
  similar_companies?: Array<{
    name: string;
    similarity_score: number;
    shared_tools: string[];
    url: string;
  }>;
}

interface ApiResponse {
  success: boolean;
  data: TechStackData;
}

export function TechStackSection({ projectId }: TechStackSectionProps) {
  const { data: response, isLoading } = useQuery<ApiResponse>({
    queryKey: ['tech-stack', projectId],
    queryFn: async () => {
      try {
        const res = await api.get(`/projects/${projectId}/artifacts/tech-stack`);
        return res.data || { success: false, data: {} };
      } catch {
        return { success: false, data: { languages: [], frameworks: [], databases: [] } };
      }
    },
  });

  const stackData = response?.data;

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-500">
        <Loader size={14} className="animate-spin" />
        Detectando tech stack…
      </div>
    );
  }

  if (!stackData || (stackData.languages?.length === 0 && stackData.frameworks?.length === 0)) {
    return (
      <div className="text-xs text-gray-600">
        Tech stack será detectado quando você fizer upload de código ou artefatos.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold">
        <Cpu size={15} className="text-cyan-400" />
        <span>Tech Stack Detectado</span>
      </div>

      {/* Tech Stack Badges */}
      <div className="space-y-3">
        {stackData.languages && stackData.languages.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 mb-2">Linguagens</p>
            <div className="flex flex-wrap gap-2">
              {stackData.languages.map((lang, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 text-xs font-medium bg-blue-900/30 border border-blue-700/50 rounded-full text-blue-300"
                >
                  {lang}
                </span>
              ))}
            </div>
          </div>
        )}

        {stackData.frameworks && stackData.frameworks.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 mb-2">Frameworks</p>
            <div className="flex flex-wrap gap-2">
              {stackData.frameworks.map((fw, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 text-xs font-medium bg-green-900/30 border border-green-700/50 rounded-full text-green-300"
                >
                  {fw}
                </span>
              ))}
            </div>
          </div>
        )}

        {stackData.databases && stackData.databases.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 mb-2">Bancos de Dados</p>
            <div className="flex flex-wrap gap-2">
              {stackData.databases.map((db, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 text-xs font-medium bg-purple-900/30 border border-purple-700/50 rounded-full text-purple-300"
                >
                  {db}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Similar Companies (StackShare) */}
      {stackData.similar_companies && stackData.similar_companies.length > 0 && (
        <div className="border-t border-gray-700 pt-4 mt-4">
          <p className="text-xs text-gray-400 mb-3">Empresas com Stack Similar (StackShare)</p>
          <div className="space-y-2">
            {stackData.similar_companies.slice(0, 3).map((company, i) => (
              <a
                key={i}
                href={company.url}
                target="_blank"
                rel="noopener noreferrer"
                className={clsx(
                  'flex items-start justify-between p-2.5 rounded border transition-colors',
                  'bg-dark-200/50 border-gray-700/50 hover:border-cyan-700/50 hover:bg-dark-200'
                )}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-300">{company.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {(company.similarity_score * 100).toFixed(0)}% similar
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {company.shared_tools.slice(0, 2).map((tool, j) => (
                      <span key={j} className="text-xs text-cyan-400">
                        {tool}{j < company.shared_tools.length - 1 ? ', ' : ''}
                      </span>
                    ))}
                    {company.shared_tools.length > 2 && (
                      <span className="text-xs text-gray-500">
                        +{company.shared_tools.length - 2} mais
                      </span>
                    )}
                  </div>
                </div>
                <ExternalLink size={12} className="text-gray-400 shrink-0 mt-1 ml-2" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
