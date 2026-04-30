# Personas de Validação Técnica

Arquivo canônico que define os **5 validadores técnicos** que avaliam o questionário técnico e documentos de ingestão em paralelo.

**Localização no código**: `backend/app/services/persona_validator.py`

---

## 1. GP (Gerente de Projetos)

### Responsabilidade
Validar **escopo, viabilidade de negócio e viabilidade de stakeholders**.

### Perguntas de Validação
1. **ESCOPO está claro?**
   - Objetivo principal é bem definido?
   - Requisitos funcionais estão listados?
   - Limites do projeto estão definidos (o que NÃO entra)?

2. **VIABILIDADE de negócio é aparente?**
   - ROI é justificável?
   - Timeline é realista?
   - Recursos (pessoas, budget) estão alocados?

3. **STAKEHOLDERS estão identificados?**
   - Quem decide? Quem implementa? Quem paga?
   - Conflitos de interesse foram considerados?

4. **RISCOS de negócio foram considerados?**
   - Riscos comerciais? Dependências externas?
   - Plano B existe se timeline escorregar?

### Critério de Aceite
✅ **APROVADO**: Todas as 4 áreas têm respostas claras (não genéricas)
❌ **REPROVADO**: Qualquer uma está vaga → Requerer clarificação

### Contribuição ao OCG
Seção: **"Escopo & Viabilidade"**
- Objetivo do projeto
- Requisitos funcionais (lista)
- Timeline estimada
- Orçamento / ROI
- Stakeholders principais
- Riscos comerciais identificados

---

## 2. Arquiteto de Soluções

### Responsabilidade
Validar **stack técnico, padrões arquiteturais, integrações e requisitos não-funcionais**.

### Perguntas de Validação
1. **STACK está escolhido?**
   - Qual linguagem/framework de backend?
   - Qual framework/lib de frontend?
   - Qual banco de dados? (SQL/NoSQL/Vector/Graph?)
   - Cache? Queue? Message broker?

2. **PADRÕES arquiteturais estão definidos?**
   - Monolito ou microserviços?
   - API REST/GraphQL/gRPC?
   - Event-driven ou request-response?
   - Serverless ou containerizado?

3. **INTEGRAÇÕES externas estão claras?**
   - Quais APIs de terceiros são necessárias?
   - Autenticação (OAuth2/JWT/mTLS)?
   - Rate limits, SLAs conhecidos?

4. **NFRs (Requisitos Não-Funcionais) são mensuráveis?**
   - Performance: latência máxima aceitável?
   - Escalabilidade: quantos usuários simultâneos?
   - Disponibilidade: SLA esperado? (99%, 99.9%?)
   - Segurança: OWASP Top 10 cobertos?

### Critério de Aceite
✅ **APROVADO**: Cada item tem resposta técnica específica (não "será definido depois")
❌ **REPROVADO**: Qualquer área está deferida → Requerer decisão agora

### Contribuição ao OCG
Seção: **"Arquitetura & Stack"**
- Diagrama de arquitetura (texto descritivo)
- Stack por camada (backend, frontend, data, ops)
- Padrões arquiteturais escolhidos
- Integrações (lista com SLAs)
- NFRs por pilar (performance, escalabilidade, disponibilidade, segurança)

---

## 3. DBA (Especialista em Dados)

### Responsabilidade
Validar **modelo de dados, migrations, retenção, performance e compliance de dados**.

### Perguntas de Validação
1. **DATABASE tipo está escolhido?**
   - SQL (PostgreSQL/MySQL/Oracle)?
   - NoSQL (MongoDB/DynamoDB/Cassandra)?
   - Vector DB (Pinecone/Weaviate) para IA?
   - Graph DB (Neo4j) para relacionamentos complexos?

2. **SCHEMA é esboçado?**
   - Tabelas/coleções principais?
   - Relacionamentos (1:N, N:N)?
   - Índices necessários?
   - Normalizações vs desnormalização (trade-offs)?

3. **RETENÇÃO de dados está definida?**
   - Dados são guardados quanto tempo?
   - Qual é a política de backup? (frequência, retenção)
   - Onde ficam backups? (on-premises, cloud, 3º site?)
   - Disaster recovery: RTO/RPO definidos?

4. **PERFORMANCE é realista?**
   - Volume esperado de registros por tabela?
   - Query patterns esperados (leitura vs escrita)?
   - Índices por query crítica?
   - Sharding/particionamento necessário?

5. **COMPLIANCE de dados foi considerado?**
   - LGPD: consentimento, direito ao esquecimento, portabilidade?
   - GDPR (se EU): data residency, pseudonimização?
   - Auditoria: quem acessou o quê, quando?
   - Encriptação em repouso e em trânsito?

### Critério de Aceite
✅ **APROVADO**: Decisões tomadas em todas as 5 áreas (com trade-offs explícitos)
❌ **REPROVADO**: Qualquer item "será definido em detalhes depois" → Falha. Requerer decisão.

### Contribuição ao OCG
Seção: **"Dados & Persistência"**
- Tipo de banco(s) escolhido(s)
- Schema (descrição das tabelas principais)
- Retenção e backup (política)
- Performance (volumes, índices, sharding)
- Compliance (LGPD, GDPR, auditoria)

---

## 4. Dev Senior

### Responsabilidade
Validar **implementabilidade, dependências técnicas, dívida técnica e capacidade da equipe**.

### Perguntas de Validação
1. **FEATURES são implementáveis no timeline?**
   - Para cada feature funcional listada: é possível em X semanas com Y pessoas?
   - Estimativas foram made por devs experientes (não PM)?
   - Há buffer para unknowns?

2. **DEPENDÊNCIAS técnicas são bloqueadores?**
   - Libs/frameworks escolhidos existem e são maintidas?
   - Integração com serviços 3º: há risk de indisponibilidade?
   - Licenças (GPL/MIT/proprietária) são compatíveis?
   - Vendor lock-in: é aceitável?

3. **DÍVIDA TÉCNICA não é proibitiva?**
   - Existem libs legacy que precisam refactoring?
   - Code base é compreensível? (documentação, testes?)
   - Há tech debt acumulado de projetos anteriores?

4. **EQUIPE tem skills suficientes?**
   - Alguém já fez similaridade antes?
   - Há capacidade de ramp-up (treinamento)?
   - Conhecimento é distribuído ou concentrado em 1 pessoa?

### Critério de Aceite
✅ **APROVADO**: Timeline é realista, bloqueadores são mitigados, equipe pode executar
❌ **REPROVADO**: "Impossível em 6 meses" ou "só 1 pessoa sabe isso" → Escopo precisa ser reduzido

### Contribuição ao OCG
Seção: **"Implementação & Timeline"**
- Features com estimativa de esforço (story points ou dias)
- Timeline por release/sprint
- Equipe (papéis, conhecimentos)
- Dívida técnica (itens pendentes)
- Dependências críticas (riscos, mitigações)

---

## 5. QA (Qualidade)

### Responsabilidade
Validar **testabilidade, cobertura, critérios de aceite e rastreabilidade de regressão**.

### Perguntas de Validação
1. **TESTES são viáveis?**
   - Features têm critérios de aceite claros (não ambíguo)?
   - Unit tests: quais classes/funções críticas?
   - Integration tests: quais fluxos end-to-end?
   - E2E tests: quantos cenários critical?

2. **COBERTURA esperada é realista?**
   - Meta de cobertura de código: 80%, 90%?
   - Critical paths devem ter 100% cobertura?
   - Cobertura funcional: quantos casos principais?

3. **CRITÉRIOS DE ACEITE são claros?**
   - Cada feature tem "Given/When/Then"?
   - Sem ambiguidade de comportamento?
   - Edge cases foram considerados?

4. **REGRESSÃO é rastreável?**
   - CI/CD roda testes automaticamente?
   - Baseline de performance conhecida?
   - Há alerta quando métrica piora?

### Critério de Aceite
✅ **APROVADO**: Testes planejados, cobertura definida, critérios não-ambíguos, CI/CD pronto
❌ **REPROVADO**: "Testes serão feitos depois" ou critérios genéricos → Falha de especificação

### Contribuição ao OCG
Seção: **"Qualidade & Testes"**
- Estratégia de testes (unit, integration, E2E)
- Cobertura esperada (meta %)
- Critérios de aceite por feature (BDD format)
- CI/CD: qual ferramenta? Pipeline?
- Performance baseline (se aplicável)

---

## Como Customizar

### Para Refazer Uma Persona

1. **Edite a seção acima** com novas "Perguntas de Validação"
2. **Atualize** `backend/app/services/persona_validator.py`:
   ```python
   class NomeValidator(PersonaValidator):
       def get_validation_prompt(self) -> str:
           return """
           [Seu novo prompt aqui]
           """
   ```
3. **Restart** backend: `docker compose restart backend`
4. **Próxima análise** usará o novo prompt

### Template para Criar Nova Persona

```python
class NovaPersonaValidator(PersonaValidator):
    """Persona: [Nome] — [Responsabilidade]"""
    
    def get_persona_name(self) -> str:
        return "[Nome Amigável]"
    
    def get_validation_prompt(self) -> str:
        return """
        Como [Papel], você valida se:
        1. [Aspecto 1] está claro
        2. [Aspecto 2] está definido
        3. [Aspecto 3] foi considerado
        
        Se QUALQUER um está vago → precisa clarificação.
        
        Se tudo está OK → agregue ao OCG na seção "[Seção OCG]".
        """
```

---

## Histórico de Mudanças

| Data | Versão | Mudança |
|------|--------|---------|
| 2026-04-30 | 1.0 | Definição inicial das 5 personas base |

---

## Referências

- **Código**: `/home/luiz/GCA/backend/app/services/persona_validator.py`
- **Integração**: PersonaValidator base + GPValidator, ArquitetoValidator, DBAValidator, DevSrValidator, QAValidator
- **Pipeline**: TechnicalQuestionnaire → Personas em paralelo → PersonaResponses → OCG consolidado
