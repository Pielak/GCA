import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { HelpIcon } from "@/components/HelpIcon";
import {
  GitBranch, Clock, ChevronDown, ChevronUp,
  Sparkles, User, FolderOpen, Loader2,
} from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { api } from "@/services/api";
import { clsx } from "clsx";

interface RequirementHistory {
  id: string;
  req_ref: string;
  version: number;
  change_type: "created" | "updated" | "deprecated";
  title: string;
  description: string;
  justification: string;
  changed_by: string;
  created_at: string;
  source: "gatekeeper" | "manual";
  evaluation_id: string | null;
}

interface Project {
  id: string;
  name: string;
  description?: string;
}

const changeColors: Record<string, string> = {
  created:    "bg-emerald-900/40 text-emerald-300 border border-emerald-700/50",
  updated:    "bg-amber-900/40 text-amber-300 border border-amber-700/50",
  deprecated: "bg-red-900/40 text-red-300 border border-red-700/50",
};
const changeLabels: Record<string, string> = {
  created: "Criado", updated: "Atualizado", deprecated: "Depreciado",
};

const PILLAR_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"];
const PILLAR_FULL: Record<string, string> = {
  P1: "P1 — Requisitos Negociais",
  P2: "P2 — Regras de Negócio",
  P3: "P3 — Requisitos Funcionais",
  P4: "P4 — Requisitos Não Funcionais",
  P5: "P5 — Arquitetura da Solução",
  P6: "P6 — Dados, Integrações e Legado",
  P7: "P7 — Segurança, Compliance e QA",
};

export function RoadmapPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: projectData } = useQuery<{ success: boolean; data: Project }>({
    queryKey: ["project", projectId],
    queryFn: () => api.get(`/projects/${projectId}`).then((r) => r.data),
    enabled: !!projectId,
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["roadmap", projectId],
    queryFn: () => api.get(`/projects/${projectId}/roadmap`).then((r) => r.data),
    enabled: !!projectId,
  });

  const project = projectData?.data;
  const items: RequirementHistory[] = data?.data ?? [];

  const grouped = items.reduce<Record<string, RequirementHistory[]>>((acc, item) => {
    if (!acc[item.req_ref]) acc[item.req_ref] = [];
    acc[item.req_ref].push(item);
    return acc;
  }, {});

  const sortedRefs = Object.keys(grouped).sort((a, b) => {
    const ai = PILLAR_ORDER.indexOf(a);
    const bi = PILLAR_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <GitBranch size={22} className="text-violet-400" />
            Roadmap de Requisitos
            <HelpIcon text="Histórico imutável dos requisitos do projeto. Populado automaticamente pelo Gatekeeper a cada avaliação — cada pilar gera uma entrada versionada com score, lacunas e recomendações." />
          </h1>
          {project && (
            <div className="flex items-center gap-1.5 mt-1 text-sm text-gray-400">
              <FolderOpen size={13} className="text-violet-400" />
              <span className="text-violet-300 font-medium">{project.name}</span>
              {project.description && (
                <span className="text-gray-600 truncate max-w-xs">· {project.description}</span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 bg-dark-100 border border-gray-700 rounded-full px-3 py-1">
            Histórico imutável · append-only
          </span>
          {items.length > 0 && (
            <span className="text-xs text-violet-400 bg-violet-900/20 border border-violet-700/30 rounded-full px-3 py-1">
              {sortedRefs.length} pilar{sortedRefs.length !== 1 ? "es" : ""} · {items.length} entrad{items.length !== 1 ? "as" : "a"}
            </span>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-24 text-gray-500 gap-2">
          <Loader2 size={18} className="animate-spin" />
          Carregando roadmap…
        </div>
      )}

      {isError && (
        <div className="card border-red-700/50 text-red-400 text-center py-8">
          Erro ao carregar roadmap. Tente novamente.
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="card text-center py-20 space-y-3">
          <GitBranch size={40} className="text-gray-600 mx-auto" />
          <p className="text-gray-300 font-medium">Nenhuma entrada ainda</p>
          <p className="text-sm text-gray-500 max-w-sm mx-auto">
            Execute o <strong className="text-violet-400">Gatekeeper</strong> para gerar automaticamente
            o roadmap com o status de cada pilar documental do projeto.
          </p>
        </div>
      )}

      {!isLoading && !isError && sortedRefs.length > 0 && (
        <div className="space-y-2">
          {sortedRefs.map((reqRef) => {
            const history = [...grouped[reqRef]].sort((a, b) => b.version - a.version);
            const latest = history[0];
            const isOpen = expanded === reqRef;
            const fullLabel = PILLAR_FULL[reqRef] ?? reqRef;
            const isGatekeeper = latest.source === "gatekeeper";

            return (
              <div key={reqRef} className="card overflow-hidden">
                <button
                  className="w-full flex items-center justify-between gap-4 text-left"
                  onClick={() => setExpanded(isOpen ? null : reqRef)}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-wrap">
                    <span className="font-mono text-violet-400 font-bold text-sm shrink-0">{reqRef}</span>
                    <span className="text-white font-medium truncate">{fullLabel}</span>
                    <span className={clsx("text-xs px-2 py-0.5 rounded-full shrink-0", changeColors[latest.change_type])}>
                      {changeLabels[latest.change_type]}
                    </span>
                    <span className="text-xs text-gray-500 shrink-0">v{latest.version}</span>
                    {isGatekeeper ? (
                      <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-violet-900/30 text-violet-300 border border-violet-700/30 shrink-0">
                        <Sparkles size={10} />
                        Gatekeeper
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700 shrink-0">
                        <User size={10} />
                        Manual
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-gray-500 shrink-0">
                    <Clock size={12} />
                    <span className="text-xs">
                      {format(new Date(latest.created_at), "dd MMM yyyy", { locale: ptBR })}
                    </span>
                    {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </button>

                {isOpen && (
                  <div className="mt-4 pt-4 border-t border-gray-700/50 space-y-4">
                    {latest.description && (
                      <div className="bg-dark-200 rounded-lg p-3">
                        <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                          {latest.description}
                        </pre>
                      </div>
                    )}
                    {latest.justification && (
                      <p className="text-xs text-gray-500 italic">{latest.justification}</p>
                    )}
                    {history.length > 1 && (
                      <div className="space-y-1.5">
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Versões anteriores</p>
                        {history.slice(1).map((h) => (
                          <div key={h.id} className="flex items-center gap-3 text-xs text-gray-500 pl-4 border-l-2 border-gray-700">
                            <span className="font-mono text-gray-600">v{h.version}</span>
                            <span className={clsx("px-1.5 py-0.5 rounded-full text-xs", changeColors[h.change_type])}>
                              {changeLabels[h.change_type]}
                            </span>
                            <span className="truncate">{h.title}</span>
                            {h.source === "gatekeeper" && <Sparkles size={9} className="text-violet-400 shrink-0" />}
                            <span className="ml-auto shrink-0">{format(new Date(h.created_at), "dd/MM/yyyy HH:mm")}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
