"""Instruções específicas por persona para emitir SEÇÕES ESTRUTURADAS no OCG.

Cada persona contribui com chaves canônicas dentro de
`ocg_contributions.global_delta` no PersonaOutput-v2. O consolidador n8n agrega
essas chaves (Object.entries no merge) e o backend `_update_ocg_record` propaga
pra `ocg_data` JSON top-level — alimentando "Stack Recomendada", "Visão
Arquitetural", "Compliance Checklist", "Testing Requirements" na UI do OCG.

Anexada ao SYSTEM_PROMPT canônico via `get_persona_prompt` (prompts_registry).
"""
from __future__ import annotations

# Trecho comum a todas as personas — explica a estrutura geral.
_HEADER = """

---

## SEÇÕES ESTRUTURADAS DO OCG (obrigatório se aplicável)

Inclua em `ocg_contributions.global_delta` (parte do PersonaOutput-v2) as chaves
canônicas listadas abaixo PARA SUA PERSONA quando o documento contiver evidência.
Se não houver evidência sólida, OMITA a chave (não invente). Cada chave é um
objeto JSON estruturado, NÃO texto livre.

Exemplo de saída válida (extrato):
```json
{
  "ocg_contributions": {
    "individual": { "...": "seus scores granulares" },
    "global_delta": {
      "<CHAVE_CANONICA>": { "subchave1": "valor1", "subchave2": ["v2a","v2b"] }
    }
  }
}
```
"""

_INSTRUCTIONS: dict[str, str] = {
    "ARQ": _HEADER + """
**Suas chaves**:

- `STACK_RECOMMENDATION` (objeto): tecnologias adequadas ao escopo
  - `linguagem`: linguagem(s) sugeridas
  - `framework_backend`: framework backend
  - `framework_frontend`: framework frontend
  - `mensageria`: fila/broker (RabbitMQ, Kafka, Redis Streams etc)
  - `cache`: estratégia de cache
  - `observabilidade`: stack de logs/metrics/traces

- `ARCHITECTURE_OVERVIEW` (objeto): visão arquitetural de alto nível
  - `padrao`: monolito | microservicos | event_driven | serverless
  - `integracoes`: lista de sistemas externos integrados
  - `deployment`: on-prem | cloud_publica | hibrido + plataforma
  - `escalabilidade`: estratégia (horizontal, vertical, sharding)
  - `acoplamento`: avaliação textual breve
""",
    "DBA": _HEADER + """
**Suas chaves**:

- `DATA_PROFILE` (objeto): perfil de dados e persistência
  - `banco_principal`: SGBD principal e versão
  - `modelo_dados`: relacional | documento | grafo | time-series | misto
  - `volumetria`: estimativa de volume (linhas/mês ou TB)
  - `retencao`: políticas de retenção por tipo de dado
  - `backup`: estratégia (RPO, RTO, periodicidade)
  - `classificacao`: nível de criticidade (público | interno | sensível | secreto)

- Contribuição em `ARCHITECTURE_OVERVIEW.persistencia` (objeto):
  - `cache_strategy`, `read_replicas`, `migrations_tool`
""",
    "DEV": _HEADER + """
**Suas chaves**:

- Contribuição em `STACK_RECOMMENDATION.ferramentas_dev` (objeto):
  - `ci_cd`: ferramenta(s) de pipeline
  - `controle_versao`: SCM
  - `testes_unit`: framework
  - `lint`: ferramentas de qualidade

- Contribuição em `ARCHITECTURE_OVERVIEW.implementacao` (objeto):
  - `dependencias_externas`: bibliotecas críticas + versões
  - `padroes_codigo`: convenções aplicáveis
  - `viabilidade`: avaliação textual breve
""",
    "QA": _HEADER + """
**Suas chaves**:

- `TESTING_REQUIREMENTS` (objeto): estratégia de testes
  - `cobertura_minima`: percentual alvo
  - `unitarios`: framework + critérios
  - `integracao`: escopo + ferramentas
  - `e2e`: cenários críticos identificados
  - `bdd`: uso de Gherkin/Cucumber
  - `regressao`: estratégia automatizada
  - `performance`: ferramentas de carga (jmeter, locust, k6)
""",
    "SEG": _HEADER + """
**Suas chaves**:

- `SECURITY_PROFILE` (objeto): controles técnicos de segurança (base OWASP)
  - `autenticacao`: mecanismo (OAuth2, OIDC, SAML, mTLS)
  - `autorizacao`: modelo (RBAC, ABAC, ACL)
  - `criptografia_transito`: TLS versão + cipher suites
  - `criptografia_repouso`: algoritmo + escopo (DB, storage, backups)
  - `secrets`: vault/KMS adotado
  - `ameacas`: lista de ameaças mapeadas (STRIDE/DREAD)
  - `mitigacoes`: contramedidas por ameaça
  - `auditoria`: trilhas de auditoria + retenção
""",
    "CONF": _HEADER + """
**Suas chaves**:

- `COMPLIANCE_CHECKLIST` (objeto): aderência a frameworks de governança
  - `iso27001`: cláusulas relevantes (A.5..A.18) + status
  - `governanca`: ISMS scope + responsabilidades
  - `gestao_risco`: framework (ISO 31000) + apetite ao risco
  - `auditoria_interna`: periodicidade + escopo
  - `politicas`: lista de políticas aplicáveis
  - `bloqueante`: lista de não-conformidades que travam aprovação (score < 60)
""",
    "LGPD": _HEADER + """
**Suas chaves**:

- Contribuição em `COMPLIANCE_CHECKLIST.lgpd` (objeto):
  - `base_legal`: bases legais aplicáveis (consentimento, contrato, legítimo interesse etc)
  - `dados_pessoais`: categorias coletadas + sensíveis (Art. 5º II)
  - `consentimento`: mecanismo de coleta + revogação
  - `retencao`: prazos por categoria
  - `dpo`: indicação de DPO + canais de contato (Art. 41)
  - `direitos_titular`: workflows para acesso/correção/exclusão (Art. 18)
  - `transferencia_internacional`: aplicável + salvaguardas
  - `incidentes`: plano de resposta + comunicação ANPD (Art. 48)
""",
}


# B4 (Decisão GP 2026-05-05): instrução anti-retrabalho HITL.
# Aplicada a TODAS as 12 personas (não só as com seções estruturadas).
# Persona deve consultar OCG atual em shared_context.ocg_summary (quando
# fornecido) ou inferir do próprio normalized_text + analyses anteriores
# disponíveis ANTES de gerar question. Se o tema já tem resposta canônica
# no OCG, NÃO repetir. Filtro determinístico no backend webhook complementa
# (commit 142fc53), mas atacar na origem reduz tokens desperdiçados +
# evita ruído na UI.
_ANTI_RETRABALHO_HITL = """

---

## ANTES DE GERAR question[] — VERIFIQUE O OCG

Você está numa cadeia de análise. O documento que você analisa NÃO é o
único insumo: o OCG (Objeto de Contexto Global) consolidado pode já
conter respostas para perguntas que você cogitou fazer.

**REGRA OBRIGATÓRIA**: antes de incluir um item em `questions[]`, conferir:

1. **shared_context.ocg_summary** (se fornecido no payload): tem a chave/
   campo correspondente preenchido? Se sim → NÃO pergunte de novo. Em vez
   disso, use a info como contexto para análise mais profunda.

2. **shared_context.questionnaire_responses** (respostas do GP no
   Questionário Técnico): cobre o tema? Se sim → NÃO pergunte.

3. **Conteúdo do próprio documento atual**: mesmo que conciso, talvez
   responda implicitamente. Releia antes de perguntar.

**Pergunte SOMENTE quando**:
- O tema pertence ao seu escopo de persona,
- Não há resposta no OCG, no questionário, nem no documento atual,
- A informação faltante bloqueia análise determinística do seu pilar.

**Exemplo de retrabalho proibido**:
- Persona ARQ pergunta "Qual a stack tecnológica?" — mas
  `ocg_data.STACK_RECOMMENDATION` já lista frontend/backend/banco. ❌
- Persona LGPD pergunta "Há DPO designado?" — mas
  `ocg_data.LGPD_COMPLIANCE.dpo` está preenchido. ❌

Em texto livre da pergunta, prefira formulações específicas que indicam
que você JÁ leu o OCG e identificou a lacuna pontual:
- "O OCG menciona stack <X> mas não detalha <Y>. Pode esclarecer?" ✅
- "O documento define <A> mas o pilar P3 exige também <B> — qual o
  posicionamento?" ✅

A filosofia "Assistida" do GCA permite à persona NÃO saber. Mas exige
que perguntar seja a ÚLTIMA opção, não a primeira.
"""


def append_ocg_sections(tag: str, base_prompt: str) -> str:
    """Anexa a instrução de seções estruturadas ao prompt da persona.

    Personas sem instrução específica (AUD/GP/UX/UI/NEG) recebem o prompt sem
    alteração — não contribuem com seções estruturadas do OCG.

    B4: TODAS as personas recebem o addendum anti-retrabalho HITL.
    """
    out = base_prompt
    structured = _INSTRUCTIONS.get(tag.upper())
    if structured:
        out += structured
    out += _ANTI_RETRABALHO_HITL
    return out
