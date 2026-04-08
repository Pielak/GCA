/**
 * Generated Files Showcase
 *
 * Página de exemplo mostrando como usar a sidebar de arquivos gerados
 * com opções de edição, visualização de TODOs e testes integrados
 */

import { useParams } from "react-router-dom";
import { FileCode, BookOpen, Zap } from "lucide-react";
import { ProjectPageLayout } from "@/components/layouts/ProjectPageLayout";

export function GeneratedFilesPage() {
  const { projectId } = useParams<{ projectId: string }>();

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-400">Projeto não encontrado</div>
      </div>
    );
  }

  return (
    <ProjectPageLayout
      projectId={projectId}
      title="📁 Arquivos Gerados"
      subtitle="Visualize, edite e gere testes para seus componentes"
      showRightSidebar={true}
    >
      <div className="h-full overflow-auto bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
        <div className="max-w-4xl mx-auto px-6 py-8">
          {/* Hero Section */}
          <div className="text-center mb-12">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600/20 mb-4">
              <FileCode size={32} className="text-blue-400" />
            </div>
            <h1 className="text-4xl font-bold text-white mb-2">
              Seus Arquivos Gerados
            </h1>
            <p className="text-slate-400 text-lg">
              Visualize todos os componentes, páginas e módulos gerados pelo GPD
            </p>
          </div>

          {/* Features Grid */}
          <div className="grid md:grid-cols-3 gap-6 mb-12">
            {/* Feature 1: Visualização */}
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-6 hover:border-slate-600/50 transition-colors">
              <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-blue-600/20 mb-4">
                <FileCode size={20} className="text-blue-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Visualização de Código
              </h3>
              <p className="text-slate-400 text-sm mb-4">
                Veja todo o código gerado na sidebar direita com suporte a cópia
                e download
              </p>
              <ul className="text-xs text-slate-500 space-y-1">
                <li>✓ Syntax highlighting</li>
                <li>✓ Copiar para clipboard</li>
                <li>✓ Baixar arquivo</li>
              </ul>
            </div>

            {/* Feature 2: Edição */}
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-6 hover:border-slate-600/50 transition-colors">
              <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-green-600/20 mb-4">
                <Zap size={20} className="text-green-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Editor Inline
              </h3>
              <p className="text-slate-400 text-sm mb-4">
                Edite código gerado diretamente no IDE e salve as alterações
              </p>
              <ul className="text-xs text-slate-500 space-y-1">
                <li>✓ Editor com tema dark</li>
                <li>✓ Reversão de alterações</li>
                <li>✓ Salvamento automático</li>
              </ul>
            </div>

            {/* Feature 3: TODOs */}
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-6 hover:border-slate-600/50 transition-colors">
              <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-orange-600/20 mb-4">
                <BookOpen size={20} className="text-orange-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Extração de TODOs
              </h3>
              <p className="text-slate-400 text-sm mb-4">
                Visualize todos os TODOs/FIXME do código com priorização
              </p>
              <ul className="text-xs text-slate-500 space-y-1">
                <li>✓ Prioridade: 🔴 Alta 🟡 Média 🔵 Baixa</li>
                <li>✓ Número da linha</li>
                <li>✓ Filtragem por prioridade</li>
              </ul>
            </div>
          </div>

          {/* Usage Guide */}
          <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-8 mb-12">
            <h2 className="text-2xl font-bold text-white mb-6">
              Como Usar
            </h2>

            <div className="space-y-6">
              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white font-bold">
                  1
                </div>
                <div>
                  <h3 className="font-semibold text-white mb-1">
                    Abra a Sidebar Direita
                  </h3>
                  <p className="text-slate-400 text-sm">
                    Veja a lista de arquivos gerados na sidebar direita. Cada
                    arquivo mostra o nome, framework e contador de TODOs.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-green-600 text-white font-bold">
                  2
                </div>
                <div>
                  <h3 className="font-semibold text-white mb-1">
                    Selecione um Arquivo
                  </h3>
                  <p className="text-slate-400 text-sm">
                    Clique em qualquer arquivo para ver seu conteúdo completo,
                    caminho no repositório e TODOs extraídos.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-orange-600 text-white font-bold">
                  3
                </div>
                <div>
                  <h3 className="font-semibold text-white mb-1">
                    Visualize TODOs
                  </h3>
                  <p className="text-slate-400 text-sm">
                    TODOs aparecem logo abaixo do arquivo selecionado, ordenados
                    por prioridade. Cada TODO mostra a linha exata no código.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-purple-600 text-white font-bold">
                  4
                </div>
                <div>
                  <h3 className="font-semibold text-white mb-1">
                    Edite o Código (Opcional)
                  </h3>
                  <p className="text-slate-400 text-sm">
                    Clique "Editar" para abrir o editor inline. Modifique o
                    código, revise TODOs atualizados e salve.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-cyan-600 text-white font-bold">
                  5
                </div>
                <div>
                  <h3 className="font-semibold text-white mb-1">
                    Gere Testes
                  </h3>
                  <p className="text-slate-400 text-sm">
                    Use o código e TODOs como contexto para gerar testes
                    unitários/integrados. Navegue para QA Readiness page.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Integration Example */}
          <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-8 mb-12">
            <h2 className="text-2xl font-bold text-white mb-4">
              Integração em Suas Páginas
            </h2>

            <div className="bg-slate-950 rounded-lg p-4 font-mono text-sm text-slate-300 overflow-x-auto mb-4">
              <pre>{`import { PageWithRightSidebar } from "@/components/layouts/PageWithRightSidebar";

export function MyPage() {
  const { projectId } = useParams();

  return (
    <PageWithRightSidebar projectId={projectId}>
      <div className="p-6">
        {/* Seu conteúdo aqui */}
      </div>
    </PageWithRightSidebar>
  );
}`}</pre>
            </div>

            <p className="text-slate-400 text-sm">
              💡 Veja <code className="bg-slate-800 px-2 py-1 rounded">GENERATED_FILES_SIDEBAR.md</code> para mais exemplos e documentação completa.
            </p>
          </div>

          {/* Stats */}
          <div className="grid md:grid-cols-4 gap-4">
            <div className="bg-gradient-to-br from-blue-600/20 to-blue-600/10 border border-blue-600/30 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-blue-400 mb-1">
                Sidebar
              </div>
              <p className="text-sm text-slate-400">
                Painel lateral direito
              </p>
            </div>

            <div className="bg-gradient-to-br from-green-600/20 to-green-600/10 border border-green-600/30 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-green-400 mb-1">
                Editor
              </div>
              <p className="text-sm text-slate-400">
                Edição inline
              </p>
            </div>

            <div className="bg-gradient-to-br from-orange-600/20 to-orange-600/10 border border-orange-600/30 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-orange-400 mb-1">
                TODOs
              </div>
              <p className="text-sm text-slate-400">
                Extração automática
              </p>
            </div>

            <div className="bg-gradient-to-br from-purple-600/20 to-purple-600/10 border border-purple-600/30 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-purple-400 mb-1">
                API
              </div>
              <p className="text-sm text-slate-400">
                Acesso programático
              </p>
            </div>
          </div>
        </div>
      </div>
    </ProjectPageLayout>
  );
}
