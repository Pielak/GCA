# Generated Files Sidebar

O painel de **Arquivos Gerados** exibe todos os componentes, páginas e módulos gerados pelo GPD no projeto atual, com suporte para:

## Funcionalidades

✅ **Listagem de Arquivos Gerados**
- Exibe todos os componentes, páginas, layout components, etc.
- Mostra contador de TODOs para cada arquivo
- Ordenação por data de criação

✅ **Visualização de TODOs**
- Lista automática de TODO/FIXME/BUG comentários no código
- Priorização: Alta (🔴), Média (🟡), Baixa (🔵)
- Número da linha para fácil navegação

✅ **Editor Inline**
- Edição de código gerado diretamente no IDE
- Suporte a copiar/baixar código
- Reversão de alterações
- Salvamento com confirmação

✅ **Opções de Arquivo**
- Copiar código para clipboard
- Baixar arquivo
- Editar inline
- Visualizar caminho completo

## Uso em Páginas

### Option 1: Usar PageWithRightSidebar (Recomendado)

```tsx
import { PageWithRightSidebar } from "@/components/layouts/PageWithRightSidebar";

export function MyPage() {
  const { projectId } = useParams();
  
  return (
    <PageWithRightSidebar projectId={projectId}>
      <div className="p-6">
        {/* Seu conteúdo aqui */}
      </div>
    </PageWithRightSidebar>
  );
}
```

### Option 2: Usar ProjectPageLayout (Com header)

```tsx
import { ProjectPageLayout } from "@/components/layouts/ProjectPageLayout";

export function MyPage() {
  const { projectId } = useParams();
  
  return (
    <ProjectPageLayout
      projectId={projectId}
      title="Minha Página"
      subtitle="Descrição da página"
    >
      <div className="p-6">
        {/* Seu conteúdo aqui */}
      </div>
    </ProjectPageLayout>
  );
}
```

### Option 3: Uso Manual do RightSidebar

```tsx
import { RightSidebar } from "@/components/layouts/RightSidebar";

export function MyPage() {
  const { projectId } = useParams();
  
  return (
    <div className="flex h-full">
      <div className="flex-1">
        {/* Seu conteúdo principal */}
      </div>
      <RightSidebar projectId={projectId} width="w-80" show={true} />
    </div>
  );
}
```

## API

### GeneratedFilesApi

Acesso programático aos arquivos gerados:

```tsx
import { generatedFilesApi } from "@/services/generatedFilesApi";

// Listar componentes gerados
const { data } = await generatedFilesApi.listComponents(projectId);

// Obter componente específico
const component = await generatedFilesApi.getComponent(projectId, componentId);

// Obter TODOs de um componente
const todos = await generatedFilesApi.getComponentTodos(projectId, componentId);

// Atualizar código gerado
await generatedFilesApi.updateComponent(projectId, componentId, newCode);

// Baixar código como arquivo
await generatedFilesApi.downloadComponentCode(projectId, componentId);
```

## Integração com Testes

O painel facilita a geração de testes unitários:

1. **Visualize o código gerado** na sidebar
2. **Identifique os TODOs** marcados no código
3. **Use o editor inline** para adicionar casos de teste
4. **Salve as alterações** no banco de dados
5. **Gere testes unitários/integrados** com base no código e TODOs

Exemplo de fluxo:

```
1. Developer seleciona componente na sidebar
2. Visualiza: código + TODO comments (linhas específicas)
3. Clica "Editar" → Editor abre
4. Modifica código se necessário
5. Salva alterações
6. Navega para QA/Teste module
7. Clica "Gerar Testes" → usa código + TODOs como contexto
8. Gera casos de teste automáticos
```

## Estrutura de Componentes

- `GeneratedFilesPanel.tsx` - Painel principal com lista de arquivos e TODOs
- `CodeEditor.tsx` - Editor inline para edição de código
- `RightSidebar.tsx` - Wrapper que gerencia abas (lista vs editor)
- `PageWithRightSidebar.tsx` - HOC para adicionar sidebar a qualquer página
- `ProjectPageLayout.tsx` - Layout completo com sidebar e header

## Próximas Melhorias

- [ ] Busca/filtro de arquivos
- [ ] Ordenação customizável
- [ ] Preview de componentes (render visual)
- [ ] Análise de complexidade ciclomática
- [ ] Sugestões de refatoração baseadas em TODOs
- [ ] Integração com Git (diff, commit history)
- [ ] Syntax highlighting aprimorado
- [ ] Multi-linguagem (JavaScript, Python, Go, etc.)
