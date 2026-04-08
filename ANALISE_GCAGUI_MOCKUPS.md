# Análise GCA GUI — Mocks do Figma

**Data**: 05/04/2026  
**Repositório**: https://github.com/Pielak/Gcagui.git  
**Status**: ✅ Bem estruturado, com 1 gap crítico na aba Usuários

---

## 📊 Estrutura dos Mocks

### Páginas Admin (4)
```
src/app/pages/admin/
├── AdminDashboardPage.tsx  (métricas executivas)
├── AdminUsersPage.tsx      (⚠️ REVISAR)
├── AdminProjectsPage.tsx   (aprovação/rejeição de projetos)
└── AdminAuditPage.tsx      (logs operacionais)
```

### Páginas de Projeto (11)
```
src/app/pages/projects/
├── ProjectListPage.tsx         (lista de projetos por usuário)
├── ProjectDetailLayout.tsx     (wrapper do projeto)
├── ProjectDashPage.tsx         (overview)
├── IngestionPage.tsx           (coleta de artefatos)
├── GatekeeperPage.tsx          (avaliação de critérios)
├── QAReadinessPage.tsx         (plano de testes)
├── CodeGeneratorPage.tsx       (assistência de geração)
├── LegacyPage.tsx              (integração com sistemas legados)
├── ArguiderPage.tsx            (argumentação de decisões)
├── LiveDocsPage.tsx            (documentação ao vivo)
├── MergeEnginePage.tsx         (integração com GitHub)
├── OCGPage.tsx                 (gerador automático)
├── RoadmapPage.tsx             (timeline do projeto)
```

### Stack Técnico do Figma
- **React 18** + TypeScript
- **Radix UI** (completo: accordion, dialog, tabs, select, etc.)
- **Material UI** + Emotion
- **Tailwind CSS** + tw-animate-css
- **Recharts** (gráficos)
- **React Router** v7.13
- **React Hook Form** + Zod
- **Zustand** (estado global)
- **Lucide React** (ícones)
- **Sonner** (toasts)
- **Vite** 6.3.5

---

## 🎯 Gap Crítico: Aba Usuários

### ❌ Situação Atual
A página **AdminUsersPage.tsx** exibe **TODOS os usuários** do sistema com papéis globais:
- Admin
- GP (Gestor de Projeto)
- Tech Lead
- Dev Sênior
- Dev Pleno
- QA
- Compliance
- Stakeholder

### ✅ O Que Deveria Ser
**Apenas GPs de projetos** devem aparecer na aba, porque:

| Operação | Responsável | Motivo |
|----------|-------------|--------|
| **Convidar integrante** | GP (projeto) | Não é atribuição admin |
| **Recuperar senha** | Usuário (self-service) | Não envolve admin |
| **Gerenciar credenciais** | GP + Compliance | Admin só faz auditoria |
| **Remover usuário de projeto** | GP | Não é escopo admin |

### 🔑 Admin Só Precisa De:
1. **Listar GPs** dos projetos ativos
2. **Ver histórico de projetos** que cada GP já gerenciou
3. **Auditar ações críticas** (override Gatekeeper, aprovação de quarentena LGPD)
4. **Revogar permissão de GP** (apenas em caso de incidente)

### 📋 Mudanças Necessárias

**AdminUsersPage.tsx**:
```tsx
// ANTES (❌)
const filtered = USERS.filter(u => {
  return u.role === 'gp';  // ← Mostra TODOS
});

// DEPOIS (✅)
const gps = USERS.filter(u => u.role === 'gp').map(gp => ({
  ...gp,
  projectsManaging: PROJECTS.filter(p => p.gpId === gp.id),
  projectsManaged: PROJECTS.filter(p => p.gpId === gp.id && p.status === 'archived')
}));
```

**Colunas na tabela**:
- Nome / Email
- Projetos Ativos (contagem)
- Histórico (contagem arquivado)
- Status (ativo / inativo)
- Ações: Bloquear | Ver Auditoria | Revogar GP

---

## 📋 Análise do Questionário Técnico

O arquivo `/home/luiz/GCA/gca_questionario_tecnico_tenant.html` é **excelente**, cobrindo:

### Seção 1: Identificação (9 campos)
- Nome, slug, criticidade, área, GP responsável
- Descrição, classificação (Pública/Interna/Confidencial/Restrita)
- Tipo de iniciativa (6 tipos)

### Seção 2: Legado (condicional)
- Se "Sim" → Sistema existente + repo URL
- Objetivo da alteração (6 categorias)
- Acesso ao repositório (Read-only / R+metadata / R+PR)
- Ações que n8n pode executar (7 ações)

### Seção 3: Entrega, Arquitetura e Stack
- **Entregáveis** (10 tipos: web, desktop, API, mobile, dashboard, docs, testes, CI/CD)
- **Arquitetura** (7 padrões: monólito, microserviços, event-driven, serverless, etc.)
- **Modo de execução** (6 modos: stand-alone, on-prem, cloud, híbrido, containerizado, offline)
- **Frontend stack** (11 opções: React, Vue, Angular, Next.js, Electron, Flutter, Tailwind, Material, etc.)
- **Backend stack** (8 opções: FastAPI, Django, Flask, NestJS, Express, Spring Boot, ASP.NET, Python)

### Status do Questionário
Inclui barra de progresso visual:
- % respondido
- Perguntas obrigatórias
- Gaps / incoerências detectadas
- Condição geral (Incompleto / Parcial / Completo)

**Ações principais**:
- Analisar consistência (via n8n)
- Imprimir / PDF
- Exportar JSON

---

## 🔗 Fluxo Integrado: Questionário → GCA

1. **GP responde questionário** (externo, HTML)
2. **n8n valida** respostas (gaps, incoerências)
3. **Resultado enviado** ao GP via email com parecer técnico
4. **GP submete para GCA** (durante Ingestão)
5. **GCA ingere dados** → alimenta Gatekeeper, CodeGen, Arguidor

---

## 📋 Checklist de Alinhamento

| Item | Status | Nota |
|------|--------|------|
| Mocks de UI completos | ✅ | 15 páginas implementadas |
| Estrutura de dados (mockData) | ✅ | User, Project, Artifact, etc. |
| Stack técnico definido | ✅ | React + Radix UI + Tailwind |
| Questionário técnico | ✅ | 3 seções, 50+ campos, validação n8n |
| **Filtro de usuários (apenas GPs)** | ❌ | **CRÍTICO — Deve revisar AdminUsersPage** |
| Integrações (GitHub, n8n) | ✅ | Pages criadas (MergeEngine, Ingestion) |
| Auditoria | ✅ | AuditPage + AuditEvent model |
| Credenciais seguras | ⚠️ | Modelo existe, implementação (Backend) pendente |

---

## 🚀 Próximos Passos Recomendados

### Curto Prazo
1. **Revisar AdminUsersPage** → Filtrar apenas GPs
2. **Atualizar tipo Project** → Adicionar `gpHistorical: string[]` para histórico
3. **Adicionar filtros** na aba Usuários (status, projetos ativos/arquivados)

### Médio Prazo
1. **Validação de resposta do questionário** → Implementar no backend (FastAPI)
2. **Integração n8n** → Fluxo de análise de gaps e parecer técnico
3. **Webhook para questões respondidas** → Ingestão automática no GCA

### Longo Prazo
1. **Live questionnaire** → Atualizar respostas dentro do GCA (pós-ingestão)
2. **Histórico de iterações** → Auditar mudanças em questões sensíveis
3. **Templates por tipo de projeto** → Pré-preenchimento baseado em OutputProfile

---

## 📁 Arquivos Analisados

| Arquivo | Linhas | Tipo |
|---------|--------|------|
| `package.json` | 91 | Config NPM |
| `AdminUsersPage.tsx` | 208+ | Component |
| `mockData.ts` | 407 | Mock database |
| `gca_questionario_tecnico_tenant.html` | 15.8K | Form |
| **Estrutura total** | 6 dirs | src/ bem organizado |

---

## 💬 Resumo Executivo

✅ **O que está ótimo**:
- UI/UX bem planejado em Figma
- Stack técnico moderno e pronto
- Questionário técnico abrangente
- Mocks de dados realistas

⚠️ **O que precisa revisar**:
- **AdminUsersPage deve mostrar APENAS GPs**, não todos os usuários
- Documentação técnica (DOCX) não foi analisada (formato binário)

🎯 **Viabilidade de implementação**:
- **Alto**: A estrutura Figma + HTML + mockData são sólidas
- **Integração com backend (Session 09+)**: Pronta para receber dados do GCA
