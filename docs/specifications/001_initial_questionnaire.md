# Questionário Inicial — Essencial para Personas

**Objetivo:** Fornecer visão 360° do projeto para as 5 personas gerarem questões dinâmicas inteligentes.

**Não é** um questionário exaustivo. É um mapa de entrada que dispara análise profunda.

---

## **SEÇÃO A: CONTEXTO DO PROJETO (4 perguntas)**

### **Q1. Nome e Objetivo Principal**
- **Tipo:** Texto (nome) + Textarea (objetivo)
- **Objetivo:** GP + Arquiteto entendem o "why"
- **Exemplo de resposta:**
  ```
  Nome: "Plataforma de Agendamentos para Clínicas"
  Objetivo: "Sistema web que permite pacientes agendar consultas, 
  clínicas gerenciar agenda, e enviar lembretes automáticos."
  ```
- **Por quê:** Contexto mínimo para todas as personas

---

### **Q2. Novo vs Refactor vs Feature**
- **Tipo:** Radio Button (múltipla escolha exclusiva)
- **Opções:**
  - "Novo sistema (do zero)"
  - "Refactor de existente"
  - "Feature nova em sistema existente"
  - "Manutenção/bugfix"
- **Objetivo:** GP decide roadmap. Dev Sr sabe se há legacy code.
- **Por quê:** Impacto massivo em timeline, riscos, abordagem técnica

---

### **Q3. Usuários Finais e Volume**
- **Tipo:** Textarea + número
- **Campos:**
  ```
  Quem usa? (pacientes, médicos, gerentes, etc)
  Quantos usuários simultâneos esperados? (10, 100, 1000, 10k, 100k+)
  ```
- **Objetivo:** Arquiteto sabe escalabilidade. QA sabe scope de testes.
- **Por quê:** Define se precisa microservices, load balancing, etc.

---

### **Q4. Prazo Esperado**
- **Tipo:** Número + Datepicker
- **Campos:**
  ```
  Quantos meses até primeira release?
  Data desejada (opcional)
  ```
- **Objetivo:** GP monta roadmap. Dev Sr sabe se é agressivo.
- **Por quê:** Define número de fases, velocidade sprint, risco de qualidade

---

## **SEÇÃO B: REQUISITOS FUNCIONAIS (5 perguntas)**

### **Q5. Fluxos Principais (3-5 funcionalidades core)**
- **Tipo:** Textarea (um fluxo por linha)
- **Exemplo:**
  ```
  1. Paciente faz login → vê disponibilidades → agenda consulta
  2. Médico faz login → vê agenda → confirma/rejeita agendamentos
  3. Sistema envia SMS 24h antes da consulta
  4. Paciente cancela consulta com até 24h de antecedência
  5. Clínica gera relatório de ocupação mensal
  ```
- **Objetivo:** Arquiteto desenha módulos. Dev Sr quebra em tasks.
- **Por quê:** Define scope mínimo viável

---

### **Q6. Integrações Externas**
- **Tipo:** Checklist + Textarea (detalhes)
- **Opções (checklist):**
  - ☐ Nenhuma (sistema standalone)
  - ☐ API de pagamento (qual? Stripe, PagSeguro, etc)
  - ☐ SMS/WhatsApp (qual provider?)
  - ☐ Email (genérico ou integração específica?)
  - ☐ Google Calendar / Outlook
  - ☐ Sistema legado (descreva)
  - ☐ BI / Data Warehouse
  - ☐ Outra (especifique)
- **Objetivo:** Arquiteto planeja integrações. DBA planeja dados externos.
- **Por quê:** Impacto em stack, segurança, performance

---

### **Q7. Frequência de Transações**
- **Tipo:** Radio Button
- **Opções:**
  - "Centenas/dia (e-commerce pequeno, SaaS startup)"
  - "Milhares/dia (PME, plataforma regional)"
  - "Dezenas de milhares/dia (marketplace, rede social)"
  - "Centenas de milhares/hora (fintech, real-time trading)"
- **Objetivo:** Arquiteto sabe se precisa cache, message queues, etc.
- **Por quê:** Define infraestrutura (RDS simples vs multi-region)

---

### **Q8. Relatórios e Analytics**
- **Tipo:** Textarea
- **Exemplo:**
  ```
  - Dashboard de ocupação (semanal/mensal)
  - Relatório de pacientes por especialidade
  - Revenue por médico
  ```
- **Objetivo:** DBA sabe índices para analytics. Dev Sr planeja batch jobs.
- **Por quê:** Define if precisa OLAP, data warehouse, etc.

---

### **Q9. Regras de Negócio Complexas**
- **Tipo:** Textarea
- **Exemplo:**
  ```
  - Médico A só atende terça/quinta, slots de 30min
  - Paciente novo requer consulta de 60min
  - Médicos de especialidades diferentes não podem ter slots simultâneos
  - Cancelamento com <24h tem taxa
  - Preço varia por especialidade e se é retorno
  ```
- **Objetivo:** Dev Sr sabe complexidade de implementação.
- **Por quê:** Define lógica de negócio crítica (validações, workflows)

---

## **SEÇÃO C: REQUISITOS NÃO-FUNCIONAIS (6 perguntas)**

### **Q10. Performance — Latência Aceitável**
- **Tipo:** Radio Button + Textarea (justificativa)
- **Opções:**
  - "Não crítica (segundos são OK)"
  - "Importante (100-500ms)"
  - "Crítica (<100ms)"
  - "Ultra-crítica (<50ms, real-time)"
- **Objetivo:** Arquiteto escolhe stack (Node vs Python, Redis, etc).
- **Por quê:** Define se precisa CDN, edge computing, otimizações caras

---

### **Q11. Disponibilidade — Uptime Crítico**
- **Tipo:** Radio Button
- **Opções:**
  - "Não crítica (99%, downtime aceitável)"
  - "Importante (99.5%)"
  - "Alta (99.9%, ~44min downtime/mês)"
  - "Crítica (99.99%, ~4min downtime/mês)"
  - "Ultra-crítica (99.999%, ~26seg downtime/mês)"
- **Objetivo:** Arquiteto sabe se precisa multi-region, failover, etc.
- **Por quê:** Define custo de infraestrutura, complexidade ops

---

### **Q12. Segurança — Dados Sensíveis?**
- **Tipo:** Checklist
- **Opções:**
  - ☐ Dados pessoais (nome, email, telefone)
  - ☐ Dados financeiros (cartão, transações)
  - ☐ Dados de saúde (HIPAA, prontuário)
  - ☐ Dados de governo (CNPJ, CPF)
  - ☐ Trade secrets / propriedade intelectual
  - ☐ Biometria
  - ☐ Outro (especifique)
- **Objetivo:** Arquiteto planeja encryption. DBA planeja compliance.
- **Por quê:** Define se precisa LGPD, GDPR, HIPAA, etc.

---

### **Q13. Escalabilidade — Crescimento Esperado**
- **Tipo:** Radio Button
- **Opções:**
  - "Estável (mesma escala por anos)"
  - "Modesto (crescimento de 2-3x em 2 anos)"
  - "Agressivo (crescimento de 10x em 6-12 meses)"
  - "Exponencial (pode viralizar, 100x+ em meses)"
- **Objetivo:** Arquiteto sabe se design precisa ser modular, stateless, etc.
- **Por quê:** Define arquitetura desde o início (microservices vs monolith)

---

### **Q14. Compliance e Auditoria**
- **Tipo:** Checklist
- **Opções:**
  - ☐ Nenhum (sem requirements específicos)
  - ☐ LGPD (Lei Geral de Proteção de Dados — Brasil)
  - ☐ GDPR (General Data Protection Regulation — EU)
  - ☐ HIPAA (Health Insurance Portability — Healthcare USA)
  - ☐ PCI DSS (cartões de crédito)
  - ☐ SOC 2 (auditoria de segurança)
  - ☐ ISO 27001 (segurança da informação)
  - ☐ Regulação específica (qual?)
- **Objetivo:** DBA + Arquiteto planejam retenção, encriptação, logs.
- **Por quê:** Define features não-funcionais críticas (direito ao esquecimento, auditoria)

---

### **Q15. Longevidade — Quanto Tempo Este Sistema Vai Rodar?**
- **Tipo:** Radio Button
- **Opções:**
  - "MVP curto (3-6 meses, pode ser descartado)"
  - "Médio prazo (2-3 anos)"
  - "Longo prazo (5-10 anos)"
  - "Permanente (sistema crítico, suporte indefinido)"
- **Objetivo:** Dev Sr planeja dívida técnica. DBA planeja migrations.
- **Por quê:** Define se vale investir em cobertura de testes, documentação, etc.

---

## **SEÇÃO D: CONTEXTO TÉCNICO (3 perguntas)**

### **Q16. Preferência de Stack**
- **Tipo:** Textarea (ou Multi-select se temos lista predefinida)
- **Campos:**
  ```
  Backend: (Python/FastAPI, Node/Express, Go, Java, outro?)
  Frontend: (React, Vue, Angular, outro?)
  Database: (PostgreSQL, MySQL, MongoDB, outro?)
  Infraestrutura: (AWS, GCP, Azure, on-prem, outro?)
  ```
- **Objetivo:** Arquiteto respeita preferências. CodeGen sabe o que gerar.
- **Por quê:** Organização já tem expertise em X, reusa infra existente

---

### **Q17. Infraestrutura Existente**
- **Tipo:** Textarea
- **Exemplo:**
  ```
  Já temos:
  - AWS (RDS PostgreSQL, S3, Lambda)
  - Jenkins CI/CD
  - Docker Kubernetes
  - SonarQube
  ```
- **Objetivo:** Dev Sr não inventa infra nova. Reutiliza.
- **Por quê:** Economiza setup time, reutiliza conhecimento da equipe

---

### **Q18. Constraints Técnicos Conhecidos**
- **Tipo:** Textarea
- **Exemplo:**
  ```
  - Precisa falar com SAP ERP (legado, API SOAP, lenta)
  - Não pode usar GPL (client é proprietário)
  - Precisa rodar on-prem (air-gapped)
  - Tem limite de memória (IoT device)
  ```
- **Objetivo:** Arquiteto evita decisões incompatíveis.
- **Por quê:** Define blockers antes de começar

---

## **SEÇÃO E: VISÃO DO GCA (2 perguntas)**

### **Q19. O Que Você Espera que o GCA Faça?**
- **Tipo:** Textarea + Checklist
- **Checklist options:**
  - ☐ Gerar código completo (backend + frontend + DB)
  - ☐ Scaffold inicial (base estrutura, eu completo)
  - ☐ Arquitetura e design (blueprint, implementação manual)
  - ☐ Validação de requisitos (checagem de completude)
  - ☐ Documentação técnica (archi docs, diagrams)
  - ☐ Outro (especifique)
- **Objective:** GP sabe o que vai entregar. CodeGen sabe scope.
- **Por quê:** Define expectativas de automação vs manual work

---

### **Q20. Maiores Incertezas/Riscos**
- **Tipo:** Textarea
- **Exemplo:**
  ```
  - Não sabemos se a performance vai ser suficiente com volume esperado
  - Team tem pouca experiência com React
  - Integração com SAP é um ponto de risco
  - Não temos budget se custo crescer
  ```
- **Objetivo:** Personas sabem onde validar mais. GP sabe riscos a mitigar.
- **Por quê:** Permite personas focar em perguntas de alto risco

---

## **RESUMO: As 20 Perguntas**

| # | Seção | Pergunta | Objetivo | Persona Principal |
|---|-------|----------|----------|------------------|
| 1 | A | Nome e objetivo | Contexto mínimo | GP, Arquiteto |
| 2 | A | Novo vs refactor | Abordagem | GP, Dev Sr |
| 3 | A | Usuários e volume | Escala | Arquiteto, QA |
| 4 | A | Prazo | Timeline | GP |
| 5 | B | Fluxos principais | Escopo | Arquiteto, Dev Sr |
| 6 | B | Integrações | Stack | Arquiteto, DBA |
| 7 | B | Frequência de TX | Infraestrutura | Arquiteto |
| 8 | B | Relatórios | Analytics | DBA, Dev Sr |
| 9 | B | Regras de negócio | Complexidade | Dev Sr |
| 10 | C | Performance | Otimizações | Arquiteto |
| 11 | C | Uptime | HA/Failover | Arquiteto |
| 12 | C | Segurança | Encriptação | Arquiteto, DBA |
| 13 | C | Escalabilidade | Modularidade | Arquiteto |
| 14 | C | Compliance | Retenção | DBA |
| 15 | C | Longevidade | Tech Debt | Dev Sr |
| 16 | D | Stack preference | CodeGen target | Arquiteto |
| 17 | D | Infra existente | Reutilizar | Dev Sr |
| 18 | D | Constraints | Blockers | Arquiteto |
| 19 | E | Espectativas GCA | Scope de automação | GP |
| 20 | E | Riscos/incertezas | Focos de validação | Todas |

---

## **FLUXO: Como as Personas Usam Essas 20 Respostas**

```
User responde Q1-Q20
        ↓
Arguidor analisa docs
        ↓
┌──────────────────────────────────────────────┐
│ GP lê Q1-4, Q19-20                           │
│ → Gera "Questionário de Viabilidade"         │
│    "Isso é viável em X meses? Riscos?"       │
├──────────────────────────────────────────────┤
│ Arquiteto lê Q5-7, Q10-13, Q16, Q18          │
│ → Gera "Questionário de Arquitetura"         │
│    "Qual stack? Quais padrões? NFRs?"        │
├──────────────────────────────────────────────┤
│ DBA lê Q6-8, Q12, Q14, Q17                   │
│ → Gera "Questionário de Dados"               │
│    "Qual schema? Compliance? Backup?"        │
├──────────────────────────────────────────────┤
│ Dev Sr lê Q2, Q5, Q9, Q15, Q17               │
│ → Gera "Questionário de Implementação"       │
│    "Fases? Dependências? Tech debt?"         │
├──────────────────────────────────────────────┤
│ QA lê Q3, Q7, Q10-11, Q20                    │
│ → Gera "Questionário de Testes"              │
│    "Coverage? Automation? Perf testing?"     │
└──────────────────────────────────────────────┘
        ↓
User responde 5 questionários dinâmicos
        ↓
Personas consolidam OCG_FINAL
```

---

## **DADOS MOCK PARA TESTE (Session T1)**

Quando criarmos o formulário em T4, vamos pré-popular com esses dados pra testar:

```python
MOCK_INITIAL_QUESTIONNAIRE = {
    "q1_name": "Plataforma de Agendamentos para Clínicas",
    "q1_objective": "Sistema web que permite pacientes agendar consultas...",
    "q2_type": "novo_sistema",
    "q3_users": "Pacientes, médicos, recepcionistas",
    "q3_volume": 500,
    "q4_months": 6,
    "q4_target_date": "2026-10-27",
    "q5_flows": "1. Paciente agenda\n2. Médico confirma\n3. SMS enviado\n4. Paciente cancela",
    "q6_integrations": ["sms_provider", "google_calendar"],
    "q6_sms_provider": "Twilio",
    "q7_frequency": "milhares_dia",
    "q8_reports": "Dashboard ocupação, revenue por médico",
    "q9_rules": "Slot de 30min, preço varia por especialidade...",
    "q10_performance": "importante_100_500ms",
    "q11_uptime": "99.5",
    "q12_sensitive_data": ["dados_pessoais", "dados_saude"],
    "q13_scalability": "modesto_2_3x",
    "q14_compliance": ["lgpd"],
    "q15_longevity": "medio_prazo_2_3_anos",
    "q16_stack": "Backend: Python/FastAPI, Frontend: React, DB: PostgreSQL",
    "q17_existing_infra": "AWS, Docker, Jenkins",
    "q18_constraints": "Integração com SAP ERP",
    "q19_gca_expectations": ["codigo_completo", "documentacao"],
    "q20_risks": "Performance com volume, experiência de equipe com React"
}
```

---

**PRÓXIMA TAREFA:** T2 — Criar modelo de dados no SQLAlchemy (InitialQuestionnaire table + schema)

Você concorda com essas 20 perguntas? Algo a adicionar/remover/ajustar?
