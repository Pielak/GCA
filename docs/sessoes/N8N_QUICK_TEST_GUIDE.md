# n8n Pipeline — TESTE RÁPIDO (5 MINUTOS)

**Status**: 🟢 **PRONTO PARA TESTAR AGORA**  
**Data**: 2026-04-06  
**O que vai testar**: Análise completa + Notificação por email

---

## ✅ PRÉ-REQUISITOS

- [x] Backend rodando
- [x] SMTP Gmail configurado (pielak.ctba@gmail.com)
- [x] Análise inteligente implementada
- [x] Email templates prontos

**Tudo pronto!** Vamos ao teste.

---

## 🧪 TESTE 1: Análise com Aprovação (Score ≥85%)

### Passo 1: Chamar o Webhook

```bash
curl -X POST http://localhost:8000/api/v1/questionnaires \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "gp_email": "pielak.ctba@gmail.com",
    "responses": {
      "frontend_stack": ["React"],
      "backend_stack": ["FastAPI"],
      "database_stack": ["PostgreSQL"],
      "ai_automation": ["Anthropic"],
      "security_controls": ["Autenticação", "Autorização / RBAC"],
      "test_types": ["Unitários", "Integração"],
      "deliverables": ["Aplicação web"],
      "execution_mode": ["Cloud"],
      "architecture_target": ["Microserviços"],
      "infra_support": ["Kafka"]
    }
  }'
```

### Passo 2: Esperado

**Resposta Imediata**:
```json
{
  "questionnaire_id": "abc123def456",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "submission_date": "2026-04-06T12:30:45Z",
  "message": "Questionário submetido para análise. Você receberá um email com o resultado"
}
```

**Email em ~30 segundos**:
```
De: GCA - Gerenciador Central de Arquiteturas <pielak.ctba@gmail.com>
Para: pielak.ctba@gmail.com
Assunto: ✅ Questionário Aprovado! Próximos Passos

Seu stack foi APROVADO! 🎉
Score: 95%

Próximos passos:
1. Convidar equipe para o projeto
2. Obter credenciais de deployment
3. Iniciar ingestão de documentação
...
```

**No console do backend**:
```
INFO questionnaire.submitted project_id=550e8400-e29b-41d4-a716-446655440000
INFO questionnaire.analysis_triggered adherence_score=95 approved=true
INFO questionnaire.sending_approval_email email=pielak.ctba@gmail.com
INFO questionnaire.email_sent notification_type=approved
```

---

## 🧪 TESTE 2: Análise com Revisão Necessária (Score <85%)

### Passo 1: Chamar o Webhook (com problemas intencionais)

```bash
curl -X POST http://localhost:8000/api/v1/questionnaires \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "gp_email": "pielak.ctba@gmail.com",
    "responses": {
      "frontend_stack": ["React", "Flutter"],
      "backend_stack": ["FastAPI"],
      "database_stack": [],
      "ai_automation": [],
      "security_controls": ["Autenticação"],
      "test_types": [],
      "deliverables": ["Aplicação web"],
      "execution_mode": ["Cloud"],
      "architecture_target": ["Monólito"],
      "infra_support": []
    }
  }'
```

### Passo 2: Esperado

**Resposta Imediata**:
```json
{
  "questionnaire_id": "xyz789uvw012",
  "project_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "pending",
  "submission_date": "2026-04-06T12:35:00Z",
  "message": "Questionário submetido para análise. Você receberá um email com o resultado"
}
```

**Email em ~30 segundos**:
```
De: GCA - Gerenciador Central de Arquiteturas <pielak.ctba@gmail.com>
Para: pielak.ctba@gmail.com
Assunto: ⚠️ Questionário Precisa de Revisão

Seu questionário foi analisado, mas precisa de revisão. 📋

Score: 65% (Limiar: 85%)

❌ CONFLITOS DETECTADOS:
1. React + Flutter são incompatíveis (linguagens diferentes)
   → Escolha UM framework: React para web, Flutter para mobile

2. Sem banco de dados em aplicação persistente
   → Selecione: PostgreSQL, MySQL, MongoDB ou similar

3. IA é obrigatória em TODOS os projetos GCA
   → Selecione pelo menos um provedor: Anthropic, OpenAI, etc

4. RBAC (Role-Based Access Control) é obrigatório
   → Selecione: Autorização / RBAC

Próximos passos:
1. Revisar os pontos acima
2. Atualizar seu questionário
3. Re-enviar para análise
```

**No console do backend**:
```
INFO questionnaire.submitted project_id=550e8400-e29b-41d4-a716-446655440001
INFO questionnaire.analysis_triggered adherence_score=65 approved=false
INFO questionnaire.sending_revision_email email=pielak.ctba@gmail.com
INFO questionnaire.email_sent notification_type=revision_needed
```

---

## 🧪 TESTE 3: Testar Webhook de Análise Direta

Se você quiser chamar o webhook de análise diretamente (testando análise pura):

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/questionnaire \
  -H "Content-Type: application/json" \
  -d '{
    "projectId": "proj-test-direct",
    "gp_email": "test@example.com",
    "responses": {
      "frontend_stack": ["React"],
      "backend_stack": ["FastAPI"],
      "database_stack": ["PostgreSQL"],
      "ai_automation": ["Anthropic"],
      "security_controls": ["Autenticação", "Autorização / RBAC"],
      "test_types": ["Unitários", "Integração"],
      "deliverables": ["Aplicação web"],
      "execution_mode": ["Cloud"],
      "architecture_target": ["Microserviços"],
      "infra_support": ["Kafka"]
    }
  }'
```

**Resposta esperada** (sem envio de email):
```json
{
  "projectId": "proj-test-direct",
  "questionnaireStatus": "OK",
  "adherenceScore": 95,
  "approved": true,
  "validations": {
    "logicConflicts": [],
    "gaps": [],
    "incompatibilities": []
  },
  "observations": "✅ Seu stack está bem alinhado com a arquitetura recomendada",
  "restrictions": "IA externa: Certifique-se de manter dados sensíveis em compliance com LGPD/GDPR",
  "highlightedFields": []
}
```

---

## 📊 MÉTRICAS DE SCORE

**Fórmula**: `100 - (conflitos × 5) - (gaps × 10) - (incompatibilities × 5)`

| Elementos | Score | Status |
|-----------|-------|--------|
| 0 conflitos, 0 gaps | 100 | ✅ Aprovado |
| 1 conflito, 0 gaps | 95 | ✅ Aprovado |
| 2 conflitos, 1 gap | 75 | 🟡 Revisão |
| 3 conflitos, 2 gaps | 65 | 🟡 Revisão |
| 5+ conflitos, 3+ gaps | <50 | ❌ Rejeitado |

**Threshold**: ≥85% para aprovação automática

---

## 📋 REGRAS DE CONFLITO (15+)

```
1. React + Flutter = incompatível
2. Monólito + Microserviços = incompatível
3. Offline (sem sincronização) = warning
4. Electron + Python = incompatível
5. ... (mais 11 regras)
```

## 📋 REGRAS DE GAPS (8+)

```
1. Web app sem frontend
2. API sem backend
3. App persistente sem DB
4. Microserviço sem messaging
5. Sem IA (obrigatória)
6. Kafka sem testes de resiliência
7. Sem autenticação
8. Sem RBAC
```

---

## 🔍 O QUE ESPERAR

### Na Submissão (Imediato)
- [x] Resposta 200 OK com questionnaire_id
- [x] Análise é feita em background
- [x] Email disparado via SMTP (Gmail)

### No Email (~30 segundos)
- [x] Se score ≥85%: Email de aprovação
- [x] Se score <85%: Email com conflitos/gaps encontrados
- [x] Links para próximas ações

### No Backend (Console)
- [x] Log de submissão
- [x] Log de análise com score
- [x] Log de email enviado
- [x] Sem erros ou exceções

---

## 🐛 TROUBLESHOOTING

### Email não chegou
**Causas**:
- [ ] SMTP desabilidado (check `.env`: SMTP_ENABLED=True)
- [ ] Senha Gmail errada (check `.env`: SMTP_PASSWORD)
- [ ] Firewall bloqueando porta 587

**Solução**:
```bash
# Verificar config
grep "SMTP" GCA/backend/.env

# Testar envio manual
python3 -c "
import sys
sys.path.insert(0, 'GCA/backend')
from app.services.email_service import EmailService
service = EmailService()
success, msg = service.send_email(
    to='seu-email@example.com',
    subject='Teste',
    html='<p>Teste SMTP</p>',
    text='Teste SMTP'
)
print(f'Enviado: {success}')
"
```

### Score diferente do esperado
**Causas**:
- [ ] Campo respondido incorretamente
- [ ] Campo vazio (conta como gap)
- [ ] Conflito não detectado

**Solução**: Verificar logs do backend

### Endpoint retorna 400 Bad Request
**Causas**:
- [ ] Projeto não existe no DB
- [ ] GP email não cadastrado
- [ ] JSON malformado

**Solução**: Verificar erro na resposta

---

## ✅ CHECKLIST DE TESTE

- [ ] Teste 1: Análise com Aprovação (score ≥85%)
- [ ] Teste 2: Análise com Revisão (score <85%)
- [ ] Teste 3: Webhook direto (analysis only)
- [ ] Email chegou na inbox
- [ ] Score calculado corretamente
- [ ] Console backend sem erros
- [ ] Todos os campos análise preenchidos

---

## 📊 RESULTADO ESPERADO

```
✅ Submissão: 200 OK (imediato)
✅ Análise: 15+ regras aplicadas (background)
✅ Email: Enviado via SMTP (30 segundos)
✅ Status: FUNCIONANDO 100%
```

---

## 🎯 PRÓXIMO PASSO

Quando quiser integrar com n8n (Opção B ou C):
1. Criar workflow no n8n
2. Configurar webhook trigger
3. Implementar chamada para n8n no submit_questionnaire
4. Testar fluxo completo

Documentação: **N8N_PIPELINE_STATUS.md** (seção "Próximos Passos")

---

**Tempo estimado de teste**: 5 minutos  
**Sucesso esperado**: 100%  
**Status**: 🟢 **PRONTO PARA TESTAR**

Avance! 🚀
