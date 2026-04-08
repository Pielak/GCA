/**
 * Componente RepositoryFileTree
 * Exibe arquivos do repositório em árvore hierárquica com expand/collapse
 */

import { useState, useMemo } from "react";
import { ChevronRight, ChevronDown, FileCode, Folder, FolderOpen } from "lucide-react";
import clsx from "clsx";
import { RepositoryFile } from "@/services/repositoryFilesApi";

interface FileTreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  language?: string;
  children?: Record<string, FileTreeNode> | FileTreeNode[];
}

interface RepositoryFileTreeProps {
  files: RepositoryFile[];
  selectedFile?: string;
  onSelectFile: (filePath: string) => void;
  loading?: boolean;
}

/**
 * Constrói árvore hierárquica a partir de lista flat de arquivos
 */
function buildFileTree(files: RepositoryFile[]): FileTreeNode[] {
  const root: Record<string, any> = {};

  for (const file of files) {
    const parts = file.path.split("/");
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const path = parts.slice(0, i + 1).join("/");
      const isFile = i === parts.length - 1 && file.type === "file";

      if (!current[part]) {
        current[part] = {
          name: part,
          path,
          type: isFile ? "file" : "dir",
          language: isFile ? file.language : undefined,
          children: isFile ? undefined : {},
        };
      }

      if (!isFile && typeof current[part].children === "object") {
        current = current[part].children;
      }
    }
  }

  return Object.values(root).sort((a, b) => {
    // Diretórios primeiro, depois arquivos
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

/**
 * Converte object de filhos em array ordenado
 */
function sortChildren(children: any): FileTreeNode[] {
  if (!children) return [];
  const arr = Array.isArray(children) ? children : Object.values(children);
  return arr.sort((a: any, b: any) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

interface TreeItemProps {
  node: FileTreeNode;
  expanded: Set<string>;
  onToggleExpand: (path: string) => void;
  onSelectFile: (path: string) => void;
  selectedFile?: string;
  level: number;
}

function TreeItem({
  node,
  expanded,
  onToggleExpand,
  onSelectFile,
  selectedFile,
  level,
}: TreeItemProps) {
  const isExpanded = expanded.has(node.path);
  const isSelected = selectedFile === node.path;
  const children = sortChildren(node.children as any);

  return (
    <div>
      <div
        className={clsx(
          "flex items-center gap-1 px-2 py-1 cursor-pointer hover:bg-gray-700 rounded",
          "text-sm transition-colors",
          isSelected && "bg-violet-900/50 text-violet-200"
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => {
          if (node.type === "dir") {
            onToggleExpand(node.path);
          } else {
            onSelectFile(node.path);
          }
        }}
      >
        {node.type === "dir" ? (
          <>
            {children.length > 0 ? (
              isExpanded ? (
                <ChevronDown size={16} className="text-gray-400 shrink-0" />
              ) : (
                <ChevronRight size={16} className="text-gray-400 shrink-0" />
              )
            ) : (
              <div className="w-4" />
            )}
            {isExpanded ? (
              <FolderOpen size={16} className="text-yellow-500 shrink-0" />
            ) : (
              <Folder size={16} className="text-yellow-500 shrink-0" />
            )}
          </>
        ) : (
          <>
            <div className="w-4" />
            <FileCode size={16} className="text-blue-400 shrink-0" />
          </>
        )}
        <span className="truncate">{node.name}</span>
      </div>

      {node.type === "dir" && isExpanded && children.length > 0 && (
        <div>
          {children.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              expanded={expanded}
              onToggleExpand={onToggleExpand}
              onSelectFile={onSelectFile}
              selectedFile={selectedFile}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function RepositoryFileTree({
  files,
  selectedFile,
  onSelectFile,
  loading = false,
}: RepositoryFileTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const tree = useMemo(() => buildFileTree(files), [files]);

  const handleToggleExpand = (path: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setExpanded(newExpanded);
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-gray-400">
        <div className="animate-spin inline-block">⟳</div>
        <p className="mt-2">Carregando arquivos...</p>
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="p-4 text-center text-gray-400 text-sm">
        Nenhum arquivo encontrado
      </div>
    );
  }

  return (
    <div className="text-gray-300 text-sm font-mono overflow-y-auto">
      {tree.map((node) => (
        <TreeItem
          key={node.path}
          node={node}
          expanded={expanded}
          onToggleExpand={handleToggleExpand}
          onSelectFile={onSelectFile}
          selectedFile={selectedFile}
          level={0}
        />
      ))}
    </div>
  );
}
