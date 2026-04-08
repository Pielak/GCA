import { useState } from "react";
import { Palette, ChevronDown, ChevronUp, Download, Trash2, Eye } from "lucide-react";

interface DesignSystemData {
  accessibility_score: number;
  responsiveness_score: number;
  completeness_score: number;
  components_count: number;
  tokens_count: number;
}

interface WireframeArtifactCardProps {
  artifactId: string;
  designName: string;
  designSystem: DesignSystemData;
  createdAt: string;
  onView?: () => void;
  onExport?: () => void;
  onDelete?: () => void;
}

export function WireframeArtifactCard({
  artifactId,
  designName,
  designSystem,
  createdAt,
  onView,
  onExport,
  onDelete,
}: WireframeArtifactCardProps) {
  const [expandedNotes, setExpandedNotes] = useState(false);

  const avgScore = Math.round(
    (designSystem.accessibility_score +
      designSystem.responsiveness_score +
      designSystem.completeness_score) /
      3
  );

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="card flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Palette size={20} className="text-emerald-400 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-medium text-gray-100 truncate">
              {designName}
            </div>
            <div className="text-xs text-gray-500">Design System</div>
          </div>
        </div>
        <span className="bg-emerald-500/20 border border-emerald-600/50 rounded-full px-2 py-0.5 text-emerald-300 text-xs font-medium">
          Exportado
        </span>
      </div>

      {/* Category + Meta */}
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
        <span className="bg-dark-200 border border-gray-700 rounded-full px-2 py-0.5 text-violet-300">
          P5 — Arquitetura
        </span>
        <span>
          {designSystem.components_count} componentes · {designSystem.tokens_count} tokens
        </span>
        <span>·</span>
        <span>{formatDate(createdAt)}</span>
      </div>

      {/* Design Quality Scores (3 bars) */}
      <div className="space-y-2">
        <div className="text-xs text-gray-500 font-medium">Qualidade do Design</div>

        {/* Accessibility */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-gray-400">Acessibilidade</label>
            <span className="text-xs font-medium text-gray-300">
              {designSystem.accessibility_score}%
            </span>
          </div>
          <div className="h-2 bg-dark-200 rounded-full overflow-hidden border border-gray-700/50">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all"
              style={{ width: `${designSystem.accessibility_score}%` }}
            />
          </div>
        </div>

        {/* Responsiveness */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-gray-400">Responsividade</label>
            <span className="text-xs font-medium text-gray-300">
              {designSystem.responsiveness_score}%
            </span>
          </div>
          <div className="h-2 bg-dark-200 rounded-full overflow-hidden border border-gray-700/50">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-cyan-400 transition-all"
              style={{ width: `${designSystem.responsiveness_score}%` }}
            />
          </div>
        </div>

        {/* Completeness */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-gray-400">Completude</label>
            <span className="text-xs font-medium text-gray-300">
              {designSystem.completeness_score}%
            </span>
          </div>
          <div className="h-2 bg-dark-200 rounded-full overflow-hidden border border-gray-700/50">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all"
              style={{ width: `${designSystem.completeness_score}%` }}
            />
          </div>
        </div>
      </div>

      {/* Design Summary Notes */}
      <div className="bg-dark-200/50 border border-gray-700/50 rounded-lg p-3">
        <div className="text-xs text-gray-300 leading-relaxed">
          <p>
            Sistema de design com {designSystem.components_count} componentes e{" "}
            {designSystem.tokens_count} tokens de design extraídos.
            {expandedNotes && (
              <>
                {" "}
                Score geral: {avgScore}%. Pronto para injetar em codegen e gerar testes
                automaticamente.
              </>
            )}
          </p>
          <button
            className="text-emerald-400 hover:text-emerald-300 flex items-center gap-0.5 mt-2 font-medium"
            onClick={() => setExpandedNotes((v) => !v)}
          >
            {expandedNotes ? (
              <>
                <ChevronUp size={12} /> Recolher
              </>
            ) : (
              <>
                <ChevronDown size={12} /> Ver mais
              </>
            )}
          </button>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-gray-700/50">
        {onView && (
          <button
            className="text-xs px-3 py-1.5 rounded-lg font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-700/50 transition-colors flex items-center gap-1"
            onClick={onView}
            title="Visualizar sistema de design"
          >
            <Eye size={13} />
            Ver Design
          </button>
        )}

        {onExport && (
          <button
            className="text-xs px-3 py-1.5 rounded-lg font-semibold bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-700/50 transition-colors flex items-center gap-1"
            onClick={onExport}
            title="Exportar tokens (CSS, Tailwind, SCSS)"
          >
            <Download size={13} />
            Exportar
          </button>
        )}

        {onDelete && (
          <button
            className="text-xs px-3 py-1.5 rounded-lg font-semibold bg-red-900/20 hover:bg-red-900/30 text-red-300 border border-red-700/50 transition-colors flex items-center gap-1 ml-auto"
            onClick={onDelete}
            title="Remover design"
          >
            <Trash2 size={13} />
            Remover
          </button>
        )}
      </div>
    </div>
  );
}
