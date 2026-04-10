# Estratégia de Migração NVMe → SSD — Segurança & Otimização

## Estado Atual (2026-04-05)
- **NVMe** (`/dev/nvme0n1p2`): 234G total | 221G usado | **499MB LIVRE** ⚠️ CRÍTICO
- **SSD** (`/dev/sda1`): 440G total | 437G **LIVRE** ✅ Excelente
- **Diretórios Candidatos**: 157.1G identificados para migração

## Mapa de Prioridades

### FASE 1: Limpeza Segura (Sem symlinks) — ~7.7G RECUPERADOS
- **✓ .cache** (3.5G) → Limpar completamente
- **✓ .npm** (1.1G) → Limpar cache npm
- **✓ /var/log** (1.5G) → Rotacionar logs antigos
- **✓ .thunderbird** (475M) → Transferir para SSD com symlink

**Risco**: Nenhum | **Tempo**: ~10 minutos | **Espaço Recuperado**: ~7.7G

### FASE 2: Migrações com Symlinks (Grandes Repositórios) — ~48G RECUPERADOS
- **→ .git** (48G) → Mover para SSD `/mnt/dados/git-backup`
- **Symlink**: `~/.git → /mnt/dados/git-backup/.git`
- **Verificação**: `git status` deve funcionar normalmente

**Risco**: Baixo (reversível com backup) | **Tempo**: ~5 minutos
**Benefício**: Libera ~48G no NVMe

### FASE 3: Migração Seletiva .local (87G) — ~70G RECUPERADOS
Subdivisão segura:
- **→ .local/share/applications** (100MB)
- **→ .local/share/icons** (200MB)
- **→ .local/share/npm-packages** (300MB)
- **→ .local/share/docker** (1.2G) — SE não afetar Docker em execução
- **→ .cache/npm** (incluído em .npm acima)

Manter NO NVMe (para performance):
- `.local/bin` — Executáveis críticos
- `.local/lib` — Bibliotecas de sistema
- `.local/share/applications` → Link para SSD

**Risco**: Médio (Docker requer cuidado) | **Tempo**: ~15 minutos
**Benefício**: Libera ~70G adicionais

### FASE 4: Migração /var/lib (Docker) — ~10-14G RECUPERADOS
**CUIDADO**: Docker está rodando!
- Pausar containers: `docker-compose down`
- Mover `/var/lib/docker` para SSD
- Symlink: `/var/lib/docker → /mnt/dados/docker`
- Reiniciar: `docker-compose up -d`

**Risco**: Médio (Docker requer verificação) | **Tempo**: ~10 minutos
**Dependências**: Acesso root, docker-compose

## Resumo de Liberação de Espaço

```
FASE 1 (Limpeza):     +7.7G  →  507.7MB livres
FASE 2 (.git):       +48.0G  → 48.5GB livres
FASE 3 (.local):     +70.0G  → 118.5GB livres
FASE 4 (/var/lib):   +14.0G  → 132.5GB livres
─────────────────────────────
TOTAL POTENCIAL:    +139.7G  → **132GB+ LIVRES** ✅
```

## Verificações Pré-Migração

- [ ] SSD montada e acessível: `/mnt/dados`
- [ ] Docker em execução: `docker ps`
- [ ] Backend respondendo: `curl http://localhost:8000/health`
- [ ] Frontend dev running: `npm run dev` no `/home/luiz/GCA/frontend`
- [ ] Backup de .git: `cp -r ~/.git /mnt/dados/git-backup-original`

## Plano de Execução (Início em FASE 1)

Proceder fase por fase com verificações entre cada uma.
Reversibilidade garantida em cada etapa.
