# Skill: gca-ocg-engine

## Quando usar
Use esta skill ao implementar, analisar ou tomar decisões relacionadas ao contexto do projeto.

## Objetivo
Tratar o OCG (Objeto de Contexto Global) como fonte única de verdade do projeto, iniciado pelo questionário externo e mantido como estado evolutivo.

---

## Definição

O OCG é um objeto de contexto global vivo.

Ele:
- começa no questionário externo
- é versionado e auditável
- evolui por eventos do sistema

Ele não é estático.

---

## Comportamento do OCG

### Expansão
O OCG deve expandir quando:
- a ingestão de dados for consistente
- houver novas evidências relevantes
- código ou testes aumentarem entendimento do sistema

### Contração
O OCG deve contrair quando:
- a ingestão for ruim ou incompleta
- houver conflito de informações
- validações falharem

Contração não remove histórico — reduz confiança e bloqueia propagação.

---

## Eventos que alteram o OCG

- QUESTIONNAIRE_APPROVED
- DOCUMENT_INGESTED
- MASTER_DOCUMENT_UPDATED
- GATEKEEPER_EVALUATED
- ARGUIDER_RESPONSE_REGISTERED
- CODE_GENERATED
- QA_EXECUTED
- LIVEDOCS_UPDATED

---

## Regras obrigatórias

- Nenhum módulo pode operar sem ler o OCG
- Toda ação relevante deve avaliar mutação do OCG
- O OCG deve ser sempre versionado após mudança
- O OCG deve refletir a qualidade da ingestão

---

## Uso pelo sistema

### Antes de qualquer ação
- carregar o OCG atual

### Durante decisões
- usar OCG como contexto principal
- não assumir dados inexistentes

### Após qualquer ação relevante
- atualizar OCG
- versionar OCG
- emitir evento
- recalcular backlog se necessário

---

## Backlog

O backlog é derivado do OCG.

Sempre que o OCG mudar:
- backlog deve ser reavaliado
- módulos devem ser atualizados

---

## Regra final

O OCG não é uma IA autônoma.

Ele é uma inteligência derivada do estado do projeto,
calculada a partir de eventos e evidências.
