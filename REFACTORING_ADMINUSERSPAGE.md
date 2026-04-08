# Refactoring: AdminUsersPage — Show Only GPs

**Commit**: `ecf0fc0`  
**Date**: 05/04/2026  
**Status**: ✅ COMPLETE

---

## 🎯 Objetivo

Alinhar a aba **Gestão de Usuários** com a especificação GCA Seção 5.2:

**Admin NÃO gerencia**:
- ❌ Convites (responsabilidade do GP)
- ❌ Membros de projeto (GP decide)
- ❌ Credenciais do projeto (GP + Tech Lead)
- ❌ Recuperação de senha (self-service)

**Admin APENAS audita**:
- ✅ Ações críticas (override Gatekeeper, quarentena LGPD)
- ✅ Revoga permissão de GP em incidentes
- ✅ Consolida logs operacionais

---

## 📝 Mudanças Implementadas

### 1. Filtro por Papéis
```typescript
// ANTES
const filtered = USERS.filter(u => 
  u.role === 'admin' || u.role === 'gp' || ...
);

// DEPOIS
const gpsWithContext: GPWithContext[] = USERS.filter(u => 
  u.role === 'gp'  // ← APENAS GPs
).map(gp => {...});
```

### 2. Novo Tipo: `GPWithContext`
```typescript
interface GPWithContext {
  id: string;
  name: string;
  email: string;
  active: boolean;
  createdAt: string;
  projectsActive: number;        // ← Novo
  projectsArchived: number;      // ← Novo
  projectsList: string[];        // ← Novo
  lastCriticalAction?: {         // ← Novo
    action: string;
    date: string;
  };
}
```

### 3. Colunas da Tabela

| Coluna | Conteúdo | Novo? |
|--------|----------|-------|
| **GERENTE** | Nome + E-mail | — |
| **PROJETOS** | Ativos + Arquivados (count) | ✅ |
| **STATUS** | Ativo / Bloqueado | ✅ (renomeado) |
| **ÚLTIMA AÇÃO** | Ação crítica + data | ✅ |
| **DESDE** | Data criação | — |
| **AÇÕES** | Block/Unlock, Audit, Revoke | ✅ |

### 4. Novas Ações

| Ação | Ícone | Descrição |
|------|-------|-----------|
| **Ver Auditoria** | 👁️ | Abre modal com histórico crítico |
| **Bloquear / Desbloquear** | 🔒 / 🔓 | Toggle acesso GP |
| **Revogar GP** | ⚡ | Remove papel (incidentes) |

### 5. Modal de Detalhe

Novo modal ao clicar em "Ver Auditoria":
- Mostra nome e email do GP
- Lista projetos gerenciados
- Placeholder para histórico de ações críticas (backend em Session 09+)

---

## 🔄 Fluxo de Dados

```
USERS (role === 'gp')
        ↓
        └─→ PROJECTS.filter(p => p.gpId === gp.id)
                ↓
                ├─→ activeProjects.length
                ├─→ archivedProjects.length
                ├─→ projectsList
                └─→ lastCriticalAction (from gatekeeper.status)
        ↓
GPWithContext[]
        ↓
filter(search, status)
        ↓
Display table + modal
```

---

## 🎨 UI/UX Melhorias

### Status Badges
- ✅ **Ativo** (verde): GP com acesso pleno
- ❌ **Bloqueado** (cinza): GP sem acesso

### Indicadores Visuais
- 🟢 Projetos ativos em **emerald-400**
- ⚪ Projetos arquivados em texto normal
- ⚠️ Ação crítica com **AlertTriangle** em âmbar

### Info Panel
Novo painel explicativo no rodapé documentando o escopo de Admin.

---

## 🔐 Dados Simulados (Mock)

No `AdminUsersPage.tsx`:
```typescript
// Simulado: em produção viria do audit log
lastCriticalAction: gpsProjects.some(p => p.gatekeeper.status === 'blocked')
  ? { action: 'Override Gatekeeper', date: '2026-03-28T15:30:00Z' }
  : undefined,
```

**Em Session 09**: Integrar com `AUDIT_EVENTS` real do backend.

---

## 📊 Exemplo: Dados Atuais

### GP: Carla Sousa (u2)
- Projetos Ativos: **2**
  - Portal de Clientes v2 (Gatekeeper: blocked)
  - App Mobile RH (provisioning)
- Projetos Arquivados: **0**
- Última Ação: Override Gatekeeper (28/03/2026)
- Status: ✅ Ativo

### GP: Pedro Nunes (u9)
- Projetos Ativos: **1**
  - API de Pagamentos (Gatekeeper: approved)
- Projetos Arquivados: **0**
- Última Ação: —
- Status: ✅ Ativo

---

## 🚀 Próximas Fases

### Session 09: Integração Backend
1. **Audit Events Real**
   - Query `AuditEvent` por `actor === gp.email`
   - Filtrar por `action IN ['OVERRIDE_GATEKEEPER', 'APPROVE_QUARANTINE']`
   - Display últimas 5 ações críticas no modal

2. **Block/Unblock Action**
   - POST `/api/v1/admin/users/{id}/lock`
   - POST `/api/v1/admin/users/{id}/unlock`
   - Refresh table após sucesso

3. **Revoke GP Role**
   - Modal de confirmação
   - POST `/api/v1/admin/users/{id}/revoke-gp`
   - Audit log da revogação

### Session 10+: Enhancements
- [ ] Exportar lista de GPs (CSV)
- [ ] Bulk actions (bloquear múltiplos GPs)
- [ ] Gráfico de projetos por GP
- [ ] Search avançado (por status de projeto, data)

---

## 🧪 Testing Checklist

### Manual
- [ ] Página carrega com apenas 2 GPs (Carla, Pedro)
- [ ] Search funciona (nome/email)
- [ ] Status filter funciona (all/active/inactive)
- [ ] Click em Eye abre modal com projetos
- [ ] Modal fecha ao clicar X
- [ ] Badges exibem corretamente

### Integração Backend (Session 09)
- [ ] Lock/unlock muta estado no backend
- [ ] Audit log registra bloqueios
- [ ] Modal popula com audit events real

---

## 📁 Arquivos Modificados

| Arquivo | Linhas | Mudança |
|---------|--------|---------|
| `src/app/pages/admin/AdminUsersPage.tsx` | 286 | +255 / -142 |

---

## 📝 Notas Técnicas

### Stack Utilizado
- React 18 + TypeScript
- Lucide React (ícones)
- Tailwind CSS (styling)
- Estado local (React.useState)

### Estrutura TypeScript
- `GPWithContext` interface para enriquecer dados
- Filtros tipados (`statusFilter: 'all' | 'active' | 'inactive'`)
- Modal com `selectedGp: GPWithContext | null`

### Performance
- Filter executado em memória (mockData) — O(n)
- Em produção: usar GraphQL com paginação + lazy load

---

## 🔗 Referência

- **GCA_Documento.pdf** — Seção 5.2 (Público-alvo e papéis)
- **ANALISE_COMPLETA_GCA.md** — Gap crítico: AdminUsersPage
- **GitHub Commit** — `ecf0fc0`
- **Branch** — `main`

---

## ✅ Checklist de Conclusão

- [x] Refactoring código ✅
- [x] Adicionar tipo TypeScript ✅
- [x] Implementar novo UI (tabela + modal) ✅
- [x] Adicionar ícones Lucide ✅
- [x] Criar info panel de contexto ✅
- [x] Git commit ✅
- [x] Documentação ✅
- [ ] Integração backend (Session 09)
- [ ] Testes E2E (Session 09+)

