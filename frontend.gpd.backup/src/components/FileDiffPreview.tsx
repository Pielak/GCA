/**
 * Componente FileDiffPreview
 * Modal mostrando diff side-by-side do original vs editado
 */

import { X, Copy, Check } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { DiffPreview } from "@/services/repositoryFilesApi";

interface FileDiffPreviewProps {
  isOpen: boolean;
  diff: DiffPreview | null;
  fileName?: string;
  onClose: () => void;
}

/**
 * Renderiza linhas do diff com colorização
 */
function DiffLine({ line, type }: { line: string; type: "add" | "remove" | "context" | "header" }) {
  const colors = {
    add: "bg-green-900/30 text-green-300 border-l-4 border-green-500",
    remove: "bg-red-900/30 text-red-300 border-l-4 border-red-500",
    context: "bg-gray-800/30 text-gray-300",
    header: "bg-gray-700/50 text-gray-400 font-semibold",
  };

  return (
    <div className={`px-3 py-0.5 font-mono text-xs whitespace-pre-wrap word-break ${colors[type]}`}>
      {line}
    </div>
  );
}

/**
 * Processa diff raw em linhas tipadas
 */
function processDiffLines(diffText: string): Array<{ line: string; type: "add" | "remove" | "context" | "header" }> {
  if (!diffText) return [];

  return diffText.split("\n").map((line) => {
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
      return { line, type: "header" };
    } else if (line.startsWith("+")) {
      return { line: line.substring(1), type: "add" };
    } else if (line.startsWith("-")) {
      return { line: line.substring(1), type: "remove" };
    } else {
      return { line: line.substring(1), type: "context" };
    }
  });
}

export function FileDiffPreview({ isOpen, diff, fileName, onClose }: FileDiffPreviewProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !diff) return null;

  const diffLines = processDiffLines(diff.diff);
  const addedCount = diff.added_lines;

  const handleCopyDiff = () => {
    navigator.clipboard.writeText(diff.diff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center">
      <div className="bg-gray-900 rounded-lg max-w-4xl w-full max-h-[90vh] flex flex-col border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Preview do Diff</h2>
            {fileName && <p className="text-xs text-gray-400 mt-1">{fileName}</p>}
            <p className="text-xs text-gray-500 mt-1">
              {addedCount} linhas adicionadas
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-300 p-1 hover:bg-gray-800 rounded transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Resumo de mudanças */}
        {diff.change_summary && (
          <div className="px-4 py-2 bg-gray-800/50 text-sm text-gray-300">
            📊 {diff.change_summary}
          </div>
        )}

        {/* Diff Content */}
        <div className="flex-1 overflow-y-auto">
          {diffLines.length > 0 ? (
            <div>
              {diffLines.map((item, i) => (
                <DiffLine key={i} line={item.line} type={item.type} />
              ))}
            </div>
          ) : (
            <div className="p-4 text-center text-gray-400">
              Nenhuma mudança detectada
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-700 bg-gray-800/50">
          <button
            onClick={handleCopyDiff}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded text-sm transition-colors"
          >
            {copied ? (
              <>
                <Check size={16} />
                Copiado!
              </>
            ) : (
              <>
                <Copy size={16} />
                Copiar Diff
              </>
            )}
          </button>

          <button
            onClick={onClose}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded text-sm font-medium transition-colors"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
