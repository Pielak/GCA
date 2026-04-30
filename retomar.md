# retomar.md — Ações Tomadas (2026-04-30)

Documento de retomada para recobrar contexto rapidamente em caso de perda de sessão.

---

## O que aconteceu

### Simplificação do Pipeline (Fase 2)
10 arquivos deletados, 4 modelos ORM removidos, 8 arquivos editados.
- Removido: `persona_tasks.py`, `ocg_consolidation_service.py`, `follow_up_service.py`, `analysis_dashboard_router.py`, `ocg_override_router.py`
- Removido: modelos `OCGIndividual`, `OCGIndividualRefined`, `PersonaFollowUpQuestion`, `OCGGlobal`
- Pipeline único: Questionário → 5 Personas → OCG (legacy) → Gatekeeper → Backlog → CodeGen
- Docs atualizados: `PIPELINE_FLOW.md` v3.0, `AUDITORIA_PIPELINE_2026_04_30.md`

### Código fonte mais recente
**Importante**: O código que está rodando nos containers NÃO é o mesmo do disco. As edições foram salvas, mas os containers rodam com o código do momento em que foram construídos/iniciados.

Arquivos com alterações não refletidas nos containers:
- `backend/app/services/pilares_vivos_service.py` — alterado no disco (code review fixes), containers NÃO recriados
- `frontend/vite.config.ts` — alterado no disco (VITE_API_URL), containers NÃO recriados
- `docker-compose.yml` — alterado no disco (VITE_API_URL), containers NÃO recriados

#### Para sincronizar containers com disco:
```bash
# Backend e celery-worker montam ./backend como volume → restart já pega alterações
docker restart gca-celery-worker
docker restart gca-backend

# Frontend precisa rebuild completo (Vite embeds env vars em build time)
docker compose up -d --build frontend
```

### Pilares Vivos — Status Atual
- **Provider**: DeepSeek (chave: `sk-58091d09c6ea42fe819eab28a4b02657` em `backend/.env`)
- **Performance**: 7 personas em paralelo, ~33-43s total
- **Todas as 7 personas rodam em paralelo** (sem dependência do Arquiteto)
- **Timeout**: 120s por chamada LLM (`asyncio.wait_for`)
- **max_tokens**: 5000 (era 3000, estava truncando respostas)
- **Último resultado**: 7/7 personas completas, salvas no DB com `regenerado_em` atualizado

### Correções aplicadas no código (disco)
1. `celery_app.py` — adicionado `"app.tasks.pilares_vivos_task"` ao `include`
2. `pilares_vivos_task.py` — imports movidos para topo (asyncio, engine, ProjectMember, InAppNotificationService)
3. `pilares_vivos_service.py` — imports limpos, `PERSONAS_TODAS` → `PERSONAS_ORDER`, timeout 120s, max_tokens 5000
4. `pilares_vivos_service.py` — kwargs `items_p1`–`p6` mantidos (prompts referenciam, mesmo com valor vazio)
5. `backend/.env` — DEEPSEEK_API_KEY atualizada
6. `docker-compose.yml` — `VITE_API_URL=http://gca-backend:8000` adicionado

### Problema conhecido: frontend mostrava "Carregando" infinito
**Causa raiz**: `VITE_API_URL` default `http://127.0.0.1:8000` inalcançável dentro do container Docker.
**Fix**: Adicionar `VITE_API_URL=http://gca-backend:8000` em `docker-compose.yml` + rebuild do frontend.
**Teste**: Fazer hard refresh (Ctrl+F5). Se ainda não funcionar, rebuildar frontend.

---

## Próximos passos sugeridos

1. **Rebuild frontend** para aplicar VITE_API_URL:
   ```bash
   docker compose up -d --build frontend
   ```
2. **Hard refresh** no navegador na página Pilares Vivos
3. **Reprocessar questionário** de projeto real para validar pipeline E2E
4. **Remover tabelas órfãs** do banco via migration (ocg_individual, ocg_individual_refined, persona_follow_up_questions, ocg_global)
5. **Regenerar Pilares Vivos** via API se necessário:
   ```bash
   docker compose exec celery-worker python -c "
   from app.tasks.pilares_vivos_task import regenerar_pilares_apos_analise
   regenerar_pilares_apos_analise.delay(
       project_id='24bf72c3-2ee8-45fd-b879-d3a00b347c39',
       user_id='adad2c84-6142-4eeb-aefb-db60e9a3dae8',
       trigger='manual',
   )
   "
   ```

---

## Memórias salvas
- `memory/gca_session_33_simplificacao_pipeline.md` — sessão completa
- Feedback: "monitorar processos longos com tail é preferível a esperar sem retorno"
