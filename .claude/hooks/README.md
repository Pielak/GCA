# Hooks do Claude Code — GCA

Hooks que enforçam regras do `CLAUDE.md` no nível de execução, não só de leitura.

## O que cada hook faz

| Hook | Quando dispara | Comportamento |
|---|---|---|
| `pre-edit.sh` | Antes de Edit/Write | **Bloqueia** (exit 2) se tentar criar símbolo canônico que já existe (AIKeyResolver, VaultService, is_active_integrated_member, generate_temporary_password). Cita onde o original mora. |
| `pre-edit-readcheck.sh` | Antes de Edit/Write | **Bloqueia** (exit 2) se o arquivo está em hot-path do GCA (`backend/app/services/personas/`, `backend/app/routers/`, `n8n/`) e não houve `Read` do mesmo arquivo nos últimos 3600s. Bypass: `GCA_SKIP_READCHECK=1`. |
| `post-edit.sh` | Depois de Edit/Write | Roda pytest **só** do `test_<nome>.py` correspondente. **Warning** (exit 1) se vermelho. Saída do pytest vai para o contexto do modelo. |
| `pre-bash.sh` | Antes de qualquer Bash | **Bloqueia** (exit 2) se tentar rodar pytest e `DATABASE_URL` efetivo apontar para `gca` (produção) em vez de `gca_test`. |
| `audit-logger.sh` | Depois de Read/Edit/Write/Bash | **Não bloqueia.** Append em `.claude/audit.log`: `[ts] tool=X file=Y` ou `cmd="..."`. Trilha forense para detectar padrões de tentativa-e-erro. Rotaciona em 10MB. |
| `on-stop.sh` | Ao encerrar sessão | **Warning** se houver mudanças não commitadas em arquivos críticos (CLAUDE.md, contrato, migrations). |

## Pré-requisitos

```bash
# jq é usado pelos hooks para parsear o input JSON
which jq || sudo apt install jq

# pytest deve estar disponível (venv do backend ou sistema)
which pytest || ls backend/.venv/bin/pytest
```

## Instalação

Já está. O `.claude/settings.json` no repo aponta para `$CLAUDE_PROJECT_DIR/.claude/hooks/*.sh`.
Toda nova sessão do Claude Code dentro de `/home/luiz/GCA/` vai carregar.

Para confirmar que estão registrados:
```bash
cd /home/luiz/GCA
claude
# dentro do Claude Code:
/hooks
```

Deve listar os 4 hooks.

## Testar manualmente

### Test 1 — pre-edit (bloqueio de duplicação)

```bash
cd /home/luiz/GCA
echo '{
  "tool_input": {
    "file_path": "/home/luiz/GCA/backend/app/services/test_dup.py",
    "content": "class AIKeyResolver:\n    pass\n"
  }
}' | bash .claude/hooks/pre-edit.sh

echo "Exit code: $?"
# Esperado: exit 2, mensagem citando onde AIKeyResolver já existe
```

### Test 2 — pre-bash (proteção do DB)

```bash
echo '{
  "tool_input": {
    "command": "DATABASE_URL=postgresql://gca:gca_secret@localhost/gca pytest"
  }
}' | bash .claude/hooks/pre-bash.sh

echo "Exit code: $?"
# Esperado: exit 2, mensagem dizendo que DB extraído é 'gca' e esperado é 'gca_test'
```

```bash
echo '{
  "tool_input": {
    "command": "DATABASE_URL=postgresql://gca:gca_secret@localhost/gca_test pytest"
  }
}' | bash .claude/hooks/pre-bash.sh

echo "Exit code: $?"
# Esperado: exit 0
```

### Test 3 — post-edit (pytest do arquivo)

```bash
echo '{
  "tool_input": {
    "file_path": "/home/luiz/GCA/backend/app/services/personas/auditor.py"
  }
}' | bash .claude/hooks/post-edit.sh

echo "Exit code: $?"
# Esperado: exit 0 se test_auditor.py passa, exit 1 se vermelho com saída do pytest
```

### Test 4 — on-stop (mudanças não commitadas)

```bash
echo '{}' | bash .claude/hooks/on-stop.sh
echo "Exit code: $?"
# Esperado: exit 1 + lista se há .md/migrations modificados sem commit; exit 0 caso contrário
```

### Test 5 — audit-logger (registro forense)

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"/home/luiz/GCA/foo.py"}}' | bash .claude/hooks/audit-logger.sh
tail -1 .claude/audit.log
# Esperado: linha "[ts] tool=Read file=foo.py", exit 0
```

### Test 6 — pre-edit-readcheck (leitura prévia em hot-path)

```bash
# (a) Cold path: passa
echo '{"tool_input":{"file_path":"/home/luiz/GCA/CHANGELOG.md"}}' | bash .claude/hooks/pre-edit-readcheck.sh
echo "Exit: $?"
# Esperado: 0

# (b) Hot path sem Read prévio: bloqueia
echo '{"tool_input":{"file_path":"/home/luiz/GCA/backend/app/routers/foo.py"}}' | bash .claude/hooks/pre-edit-readcheck.sh
echo "Exit: $?"
# Esperado: 2 + mensagem orientando Read antes de Edit

# (c) Bypass legítimo
echo '{"tool_input":{"file_path":"/home/luiz/GCA/n8n/workflow.json"}}' | GCA_SKIP_READCHECK=1 bash .claude/hooks/pre-edit-readcheck.sh
echo "Exit: $?"
# Esperado: 0 + warning no stderr + linha BYPASS no audit.log
```

## Manutenção

### Adicionar novo símbolo canônico ao pre-edit

Editar `pre-edit.sh`, no array associativo `CANONICAL`, adicionar:

```bash
["class NovoSimbolo"]="Mensagem orientando a usar o existente."
```

Padrão é regex de início de linha `^[[:space:]]*<padrão>\b`. Funciona para classes (`class X`), funções (`def x`), variáveis globais (`X = `).

### Desativar um hook temporariamente

Comentar a entrada correspondente em `.claude/settings.json` ou renomear o `.sh`. Em sessão pontual, dentro do Claude Code: `/hooks` permite desabilitar via UI.

### Logs e debugging

Hooks rodam em subshell sem TTY. Para debugar, redirecione stderr para arquivo:

```bash
# editar a linha do hook em settings.json para:
"command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/pre-edit.sh 2>>/tmp/gca-hooks.log"
```

E acompanhe:
```bash
tail -f /tmp/gca-hooks.log
```

## O que estes hooks NÃO fazem

- Não detectam duplicação semântica (helper criado com nome diferente).
- Não impedem o modelo de afirmar "tudo passa" se o hook tiver falha silenciosa — sempre verifique manualmente após sessões críticas.
- Não cobrem hot-paths não listados (ex: novos símbolos canônicos do Marco 4 ainda não existem).
- Não substituem revisão humana. São rede de segurança, não substituto de revisão.

## Versionamento

Estes arquivos são commitados no repo. Mudanças passam por revisão como qualquer outra mudança de código operacional. Atualizações de regra devem refletir mudanças correspondentes no `CLAUDE.md`.
