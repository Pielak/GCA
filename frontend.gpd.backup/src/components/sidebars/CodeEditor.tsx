import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  X,
  Save,
  RotateCcw,
  Copy,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import toast from "react-hot-toast";

interface CodeEditorProps {
  projectId: string;
  componentId: string;
  componentName: string;
  onClose: () => void;
}

export function CodeEditor({
  projectId,
  componentId,
  componentName,
  onClose,
}: CodeEditorProps) {
  const [code, setCode] = useState<string>("");
  const [isDirty, setIsDirty] = useState(false);
  const queryClient = useQueryClient();

  // Fetch component code
  const { data: codeData, isLoading } = useQuery({
    queryKey: ["component-code-edit", projectId, componentId],
    queryFn: async () => {
      const response = await api.get(
        `/projects/${projectId}/components/${componentId}`
      );
      setCode(response.data?.data?.code_content || "");
      return response.data;
    },
  });

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      // This would need a backend endpoint to update component code
      return api.put(
        `/projects/${projectId}/components/${componentId}`,
        { code_content: code }
      );
    },
    onSuccess: () => {
      setIsDirty(false);
      toast.success("Código salvo com sucesso!");
      queryClient.invalidateQueries({
        queryKey: ["component-code-edit", projectId, componentId],
      });
    },
    onError: () => {
      toast.error("Erro ao salvar código");
    },
  });

  const handleCodeChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setCode(e.target.value);
    setIsDirty(true);
  };

  const handleReset = () => {
    if (codeData?.data?.code_content) {
      setCode(codeData.data.code_content);
      setIsDirty(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    toast.success("Código copiado!");
  };

  const handleSave = () => {
    saveMutation.mutate();
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-900">
        <div className="text-slate-400">Carregando código...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-950 border-l border-slate-700">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between border-b border-slate-700 p-4 bg-slate-900">
        <div>
          <h3 className="text-sm font-semibold text-white">{componentName}</h3>
          <p className="text-xs text-slate-400 mt-1">
            {code.length} caracteres
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-slate-700 rounded transition-colors text-slate-400 hover:text-slate-200"
        >
          <X size={18} />
        </button>
      </div>

      {/* Editor Controls */}
      <div className="flex-shrink-0 flex gap-2 border-b border-slate-700 p-3 bg-slate-900">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-slate-700/50 hover:bg-slate-600 text-slate-300 transition-colors"
          title="Copiar código"
        >
          <Copy size={14} />
          Copiar
        </button>
        {isDirty && (
          <>
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-slate-700/50 hover:bg-slate-600 text-slate-300 transition-colors"
              title="Reverter alterações"
            >
              <RotateCcw size={14} />
              Reverter
            </button>
            <button
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-green-600/20 hover:bg-green-600/30 text-green-400 transition-colors disabled:opacity-50"
              title="Salvar alterações"
            >
              <Save size={14} />
              {saveMutation.isPending ? "Salvando..." : "Salvar"}
            </button>
          </>
        )}
      </div>

      {/* Code Editor */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <textarea
          value={code}
          onChange={handleCodeChange}
          className={clsx(
            "flex-1 w-full p-4 bg-slate-950 text-slate-100 font-mono text-sm resize-none border-0 focus:outline-none focus:ring-0",
            "placeholder-slate-600"
          )}
          placeholder="// Código gerado aparecerá aqui..."
          spellCheck="false"
          style={{
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
            lineHeight: "1.5",
            tabSize: 2,
          }}
        />
      </div>

      {/* Footer Info */}
      <div className="flex-shrink-0 border-t border-slate-700 p-3 bg-slate-900 text-xs text-slate-500">
        <div>
          {isDirty && (
            <span className="text-orange-400 font-semibold">● Não salvo</span>
          )}
        </div>
      </div>
    </div>
  );
}
