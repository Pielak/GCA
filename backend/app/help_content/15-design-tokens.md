# Design Tokens — paleta e escalas governadas pelo OCG

**Design Tokens** formalizam paleta, tipografia, espaçamento, border-radius e sombras como **parte do contrato do OCG**. Em vez do CodeGen inventar cores a cada geração, o prompt recebe os tokens canônicos e o código sai consistente com o design declarado.

O fluxo é **determinístico, sem LLM no caminho crítico**: CSS/SCSS ingerido → extractor regex → `STACK_RECOMMENDATION.frontend.design_tokens` no OCG → prompt do CodeGen com hints por frontend stack.

## O que é extraído do CSS

O extractor (`app/services/css_token_extractor_service.py`) reconhece cinco dimensões:

| Dimensão | O que coleta | Convenções canônicas |
|---|---|---|
| **Paleta** | hex 3/6/8, `rgb()/rgba()`, `hsl()/hsla()`, nomes CSS básicos | Top 12 por frequência de uso; duplicatas normalizadas para `#rrggbb` minúsculo |
| **Paleta por role** | custom properties `--primary`, `--color-primary-500`, etc | Mapeia para 16 roles canônicos: `primary`, `secondary`, `accent`, `success`, `warning`, `danger`, `error`, `info`, `muted`, `background`, `foreground`, `text`, `surface`, `border`, `link`, `brand` |
| **Tipografia** | `font-family`, `font-size` (px/rem/em), `font-weight`, `line-height` | Conversão `1rem=16px`; pesos normalizados para múltiplos de 100 entre 100-1000 |
| **Escalas** | `padding`, `margin`, `gap`, `border-radius` | Valores únicos ordenados ascendente; spacing limitado a 256px, radii a 9999px |
| **Sombras** | `box-shadow` | Top 6 por frequência; preservadas como string CSS completa |

Comentários `/* ... */` são removidos antes da análise — cores em exemplos documentais não contaminam a paleta.

## Fluxo canônico

1. **Ingestão automática**: GP faz upload de `theme.css` ou `tokens.scss` na Ingestão padrão. O hook detecta `file_type=stylesheet`, roda o extractor, grava em `OCG.STACK_RECOMMENDATION.frontend.design_tokens` e bumpa a versão do OCG. **Não passa pelo pipeline LLM** — `document_category=design_stylesheet` e `arguider_status=completed` direto.
2. **Seed automático de gap**: se o GP ingere mock visual (PNG/PDF) mas o OCG ainda não tem tokens, o Arguidor ganha um `GatekeeperItem` com código canônico `DT-DSGN001` pedindo paleta/tipografia — idempotente (não duplica).
3. **Edição manual**: aba **"Design Tokens (editável)"** em `/projects/:id/ocg`. GP ajusta roles, adiciona cores fora do top, edita escalas. Só papéis com `project:manage_team` (GP/Admin) escrevem; demais só leem.
4. **Lifecycle do `source`**:
   - `css_ingested` — extrator rodou sobre CSS.
   - `manual` — GP preencheu direto pelo endpoint, sem CSS anterior.
   - `mixed` — extrator rodou **e depois** GP editou manualmente.
   - Badge colorido na UI identifica o estado atual.

## Como o CodeGen consome

`codegen_prompt_builder` injeta dois blocos no prompt quando `design_tokens` está presente:

### Bloco principal
```markdown
## Design System (derivado da Ingestão)

### Paleta
- **primary**: `#7c3aed`
- **secondary**: `#0ea5e9`
- Cores mais usadas: `#7c3aed`, `#ffffff`, ...

### Tipografia
- Famílias: `Inter`, `JetBrains Mono`
- Escala de tamanhos (px): [12, 14, 16, 24, 32]
- Pesos: [400, 600, 700]

### Spacing (px): [4, 8, 12, 16, 24]
### Border-radius (px): [4, 8, 9999]

### Shadows
- `0 1px 2px rgba(0,0,0,0.05)`

> O código gerado **deve** reutilizar estes tokens (CSS variables,
> theme.extend do Tailwind, ThemeProvider do styled-components, etc).
> Não inventar paleta nem criar variações sem justificativa.
```

### Hints por stack
O builder detecta o frontend stack via `STACK_RECOMMENDATION.frontend` e injeta instruções idiomáticas:

| Stack | Onde declarar | Exemplo canônico |
|---|---|---|
| Tailwind | `tailwind.config.ts` → `theme.extend` | `colors: { primary: '#...' }`, usa `bg-primary` |
| styled-components | `src/theme.ts` + `<ThemeProvider>` | `theme.colors.primary` via `props.theme.*` |
| Emotion | `@emotion/react` ThemeProvider | `useTheme()` ou `(theme) => ...` |
| MUI | `createTheme({ palette, typography })` | `palette: { primary: { main: '#...' } }` |
| vanilla-extract | `createGlobalTheme(':root', { colors })` | `vars.colors.primary` |
| CSS Modules / plain CSS | `src/styles/tokens.css` com `:root { --color-primary: #...; }` | `var(--color-primary)` |
| genérica | CSS custom properties em `:root` | `var(--token-name)` |

Regra dura: o CodeGen **deve** declarar tokens no local canônico da stack e consumir via referência simbólica — nunca `#hex` literal em componente ou classe utilitária ad-hoc.

## Auditoria

Eventos emitidos:

| Evento | Quando | Payload |
|---|---|---|
| `OCG_UPDATED` | Ingestão de CSS aplicou tokens | `source=design_tokens_ingestion`, `version_from/to`, `source_document_id`, `tokens_source` |
| `OCG_UPDATED` | PUT manual via endpoint | `source=design_tokens.put`, `version_from/to`, `tokens_source` |

Tudo com hash chain em `audit_log_global`.

## Regras duras

- **Extração é determinística** — regex sobre AcroForm AST, zero LLM. Mesmo CSS de entrada sempre produz mesmos tokens de saída.
- **Hex canônico** — toda cor normalizada para `#rrggbb` minúsculo. Hex 3 expande (`#abc` → `#aabbcc`); hex 8 remove alpha (`#aabbccdd` → `#aabbcc`).
- **Roles filtrados** — `--minha-cor-especial` é ignorado; só os 16 roles canônicos entram em `by_role`. Cores fora do canônico vão para `palette.top`.
- **Validação binária** — endpoint PUT retorna 422 com `errors[]` se algo for inválido (hex malformado, weight fora da escala, role desconhecido). Nunca aceita parcialmente.
- **Idempotência** — payload idêntico (ignorando `generated_at`) não bumpa versão. Evita inflar histórico com edições triviais.

## Ver também

- [OCG — Objeto de Contexto Global](?section=05-ocg) — onde os tokens vivem.
- [Contratos RNF](?section=13-contratos-rnf) — outro contrato canônico paralelo (performance, security, compliance).
- [Codegen e linguagens suportadas](?section=08-codegen) — consumidor principal dos tokens.
- [Pipeline canônico](?section=04-pipeline) — ordem das etapas.
