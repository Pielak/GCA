# Pacote de tasks — Tratamento canônico de exceções no GCA

Conjunto de 6 arquivos `.md` para execução sequencial pelo Claude Code, mais um `setup.sh` que automatiza a instalação no repositório.

## Ordem de execução

| # | Arquivo | Escopo | Tempo estimado |
|---|---|---|---|
| 0 | `TASK_EH_00_SETUP.md` | Cria infraestrutura base (exceptions.py, handlers, ruff, doc, check AST) | 30–45 min |
| 1 | `TASK_EH_01_SERVICES.md` | Refatora `backend/app/services/` | 1–3h (depende do volume) |
| 2 | `TASK_EH_02_API.md` | Refatora `backend/app/api/` (esperar redução de código) | 1–2h |
| 3 | `TASK_EH_03_MODELS.md` | Refatora `backend/app/models/` + repositórios | 1–2h |
| 4 | `TASK_EH_04_INTEGRATIONS.md` | Refatora `backend/app/integrations/` (LLMs, HTTP, crypto) | 1–2h |
| 5 | `TASK_EH_05_CODEGEN.md` | Refatora CodeGen + propaga paradigma para código gerado | 2–4h |

## Instalação automatizada

Você baixou os arquivos em `/home/luiz/Downloads/gca_exception_tasks/` e seu repo está em `/home/luiz/GCA`. Execute:

```bash
bash /home/luiz/Downloads/gca_exception_tasks/setup.sh
```

O script faz, com checagens em cada passo:

1. Valida que o diretório de downloads contém os 7 arquivos esperados
2. Valida que `/home/luiz/GCA` é um repositório git
3. Verifica se a working tree está limpa (pergunta se quer continuar caso contrário)
4. Cria/checa a branch `feat/exception-handling-canonical`
5. Cria `/home/luiz/GCA/docs/tasks/exception-handling/`
6. Copia os 6 TASK_EH_*.md + README para esse diretório
7. Faz commit inicial das tasks

Cores no output: azul = passo, verde = ok, amarelo = warn, vermelho = erro.

## Execução das tasks

Após `setup.sh` terminar:

```bash
cd /home/luiz/GCA
claude
```

Dentro da sessão Claude Code:

```
Leia docs/tasks/exception-handling/TASK_EH_00_SETUP.md e execute exatamente
como descrito. Pare ao final, antes do commit, e me apresente o relatório.
```

Após cada task:

1. Revise o relatório apresentado pelo Claude Code
2. Inspecione `git diff`
3. Rode manualmente:
   ```bash
   cd /home/luiz/GCA/backend
   pytest -q
   ruff check .
   ```
4. Se OK: `git add -A && git commit -m "feat(exceptions): TASK_EH_0X — descrição"`
5. Avance para a próxima task

## Merge final

Após TASK_EH_05 commitada e tudo verde:

```bash
cd /home/luiz/GCA
git push origin feat/exception-handling-canonical
# abrir PR, revisar, mergear via GitHub
```

## Princípios que guiam o pacote

1. **Uma task por vez** — não tente paralelizar. Contexto longo degrada qualidade.
2. **Sem commit automático** — Claude Code para no final de cada task; você revisa e commita manualmente.
3. **Testes primeiro, refatoração depois** — quando teste quebra, ajuste o teste para a nova exceção, nunca reverta a refatoração.
4. **Linter como guarda permanente** — ruff em CI bloqueia regressão.
5. **Gatekeeper fecha o ciclo** — código gerado é verificado antes de chegar ao cliente.

## Após o pacote completo

- Adicione ao CI (`.github/workflows/ci.yml` ou equivalente) o step: `ruff check .`
- Adicione ao pre-commit (`.pre-commit-config.yaml`) hook do ruff com BLE/TRY/LOG
- Atualize `/home/luiz/GCA/CLAUDE.md` (memória do Claude Code do projeto) referenciando `docs/conventions/exception-handling.md` como leitura obrigatória
- Comunique a equipe: novos PRs devem seguir a convenção; reviews bloqueiam violações

## Em caso de problema

Se uma task estourar contexto (Claude Code começar a perder fio):

1. Encerre a sessão Claude Code (`/exit`)
2. Faça commit do progresso parcial: `git commit -m "wip: TASK_EH_0X parcial"`
3. Inicie nova sessão e diga: "Continue de onde paramos em TASK_EH_0X. Estado atual: <breve resumo>. Próximos arquivos a processar: <lista>."

Cada task foi escrita para ser **resumível** — todas têm inventário inicial, lista de arquivos, e critério de conclusão claro.

## Estrutura final no repo após setup

```
/home/luiz/GCA/
├── docs/
│   └── tasks/
│       └── exception-handling/
│           ├── README.md
│           ├── TASK_EH_00_SETUP.md
│           ├── TASK_EH_01_SERVICES.md
│           ├── TASK_EH_02_API.md
│           ├── TASK_EH_03_MODELS.md
│           ├── TASK_EH_04_INTEGRATIONS.md
│           └── TASK_EH_05_CODEGEN.md
└── ... (resto do repo)
```

E após TASK_EH_00 ser executada, também:

```
/home/luiz/GCA/
├── backend/
│   └── app/
│       ├── core/
│       │   ├── exceptions.py          ← NOVO
│       │   └── error_handlers.py      ← NOVO
│       ├── gatekeeper/
│       │   └── checks/
│       │       └── exception_handling.py  ← NOVO
│       └── main.py                    ← AJUSTADO
├── docs/
│   └── conventions/
│       ├── exception-handling.md      ← NOVO
│       └── baseline_violations.txt    ← NOVO
├── pyproject.toml                     ← AJUSTADO
└── ...
```
