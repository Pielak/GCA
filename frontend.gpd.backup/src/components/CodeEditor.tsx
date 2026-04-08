/**
 * Componente CodeEditor com CodeMirror 6
 * Suporta múltiplas linguagens de programação
 * Features: syntax highlighting, line numbers, indentation guides, bracket matching
 */

import { useEffect, useRef } from "react";
import {
  EditorView,
  basicSetup,
} from "codemirror";
import { EditorState } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { rust } from "@codemirror/lang-rust";
import { go } from "@codemirror/lang-go";
import { sql } from "@codemirror/lang-sql";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { xml } from "@codemirror/lang-xml";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";

interface CodeEditorProps {
  value: string;
  language?: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  height?: string;
  className?: string;
}

/**
 * Mapeia linguagem para extension do CodeMirror
 */
function getLanguageExtension(language?: string) {
  const normalizedLang = (language || "").toLowerCase();

  switch (normalizedLang) {
    case "python":
    case "py":
      return python();
    case "javascript":
    case "js":
    case "jsx":
      return javascript({ jsx: true });
    case "typescript":
    case "ts":
    case "tsx":
      // TypeScript uses JavaScript extension with jsx support
      return javascript({ jsx: true });
    case "java":
      return java();
    case "cpp":
    case "c++":
    case "cc":
    case "cxx":
    case "c":
    case "h":
      // C/C++ not available, fallback to plain text
      return javascript();
    case "rust":
    case "rs":
      return rust();
    case "go":
    case "golang":
      return go();
    case "sql":
      return sql();
    case "html":
    case "htm":
      return html();
    case "css":
      return css();
    case "xml":
      return xml();
    case "json":
      return json();
    case "markdown":
    case "md":
      return markdown();
    default:
      return javascript(); // Fallback para JavaScript
  }
}

export function CodeEditor({
  value,
  language,
  readOnly = false,
  onChange,
  height = "400px",
  className = "",
}: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Se já existe um editor, atualiza o valor
    if (editorRef.current) {
      const currentValue = editorRef.current.state.doc.toString();
      if (currentValue !== value) {
        editorRef.current.dispatch({
          changes: {
            from: 0,
            to: currentValue.length,
            insert: value,
          },
        });
      }
      return;
    }

    // Cria novo editor
    const updateHandler = EditorView.updateListener.of((update) => {
      if (update.docChanged && onChange) {
        const newValue = update.state.doc.toString();
        onChange(newValue);
      }
    });

    const state = EditorState.create({
      doc: value,
      extensions: [
        basicSetup,
        getLanguageExtension(language),
        updateHandler,
        EditorState.readOnly.of(readOnly),
        oneDark,
        EditorView.theme({
          ".cm-content": {
            minHeight: height,
            fontSize: "14px",
            fontFamily: '"JetBrains Mono", "Courier New", monospace',
          },
          ".cm-gutters": {
            borderRight: "1px solid #3f3f3f",
            backgroundColor: "#1e1e1e",
          },
          ".cm-activeLineGutter": {
            backgroundColor: "#2e2e2e",
          },
        }),
      ],
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
      dispatch: (tr) => {
        view.update([tr]);
      },
    });

    editorRef.current = view;

    return () => {
      if (editorRef.current) {
        editorRef.current.destroy();
        editorRef.current = null;
      }
    };
  }, [language, readOnly, value, onChange]);

  return (
    <div
      ref={containerRef}
      className={`border border-gray-700 rounded-lg overflow-hidden bg-gray-900 ${className}`}
      style={{ height }}
    />
  );
}
