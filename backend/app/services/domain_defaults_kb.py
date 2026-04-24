"""M02 — base de conhecimento canônico de defaults de domínio público.

Estrutura cada entrada como:
  {
    "key": str,                  # decision_key canônico
    "category": str,             # legal|security|technical|compliance|architecture
    "matches_any_of": list[str], # substrings/padrões que identificam o gap aplicável
    "value": str,                # valor default canônico (pode ter múltiplas linhas)
    "source": str,               # citação verificável da fonte
    "rationale": str,            # explicação curta
    "applies_when": list[str],   # contexto necessário do projeto (domain, stack, etc)
  }

Os defaults são consultados por `domain_defaults_resolver.resolve_gap`
que recebe o texto do gap + contexto do projeto e procura matches.
"""
from __future__ import annotations

from typing import Any

# Conjunto inicial canônico pra direito-BR + LGPD + segurança básica.
# Cada entry deve ter citação verificável (não inventar fonte).
LEGAL_DEFAULTS_BR: list[dict[str, Any]] = [
    {
        "key": "retention.civil_cases",
        "category": "legal",
        "matches_any_of": [
            "retenção de processos cíveis",
            "retenção cível",
            "prazo de guarda processo cível",
            "civil case retention",
        ],
        "value": "5 anos após o trânsito em julgado (prescrição executória — Código Civil art. 206 §5º I).",
        "source": "Código Civil Brasileiro, art. 206 §5º I (prescrição executória de títulos líquidos).",
        "rationale": "Após 5 anos do trânsito em julgado, prescreve a pretensão executória. Manter dados além disso é desnecessário e contraria princípio da minimização LGPD Art. 6º III.",
        "applies_when": ["domain:juridico", "project_type:processo_civil"],
    },
    {
        "key": "retention.labor_cases",
        "category": "legal",
        "matches_any_of": [
            "retenção de processos trabalhistas",
            "retenção trabalhista",
            "labor case retention",
        ],
        "value": "2 anos após encerramento do processo (CLT art. 11 — prescrição bienal pós-contrato).",
        "source": "CLT art. 11 — prescrição bienal após extinção do contrato de trabalho.",
        "rationale": "Passados 2 anos, não há pretensão trabalhista executável sobre o contrato extinto.",
        "applies_when": ["domain:juridico", "project_type:processo_trabalhista"],
    },
    {
        "key": "retention.access_logs",
        "category": "security",
        "matches_any_of": [
            "retenção de logs de acesso",
            "log retention",
            "access log retention",
        ],
        "value": "6 meses rolling (janela deslizante). Logs mais antigos são apagados automaticamente.",
        "source": "ISO/IEC 27001:2022 A.8.15 (Logging); Marco Civil Internet Lei 12.965/2014 art. 15 (6 meses mínimo).",
        "rationale": "6 meses atende Marco Civil como mínimo legal e é suficiente pra forense. Mais tempo agrava risco LGPD.",
        "applies_when": [],
    },
    {
        "key": "retention.deactivated_user_data",
        "category": "legal",
        "matches_any_of": [
            "retenção de dados de usuário inativo",
            "retenção advogado desativado",
            "user data retention",
        ],
        "value": "2 anos após desativação da conta. Após esse prazo, dados pessoais são anonimizados ou apagados.",
        "source": "LGPD Art. 16 (eliminação após tratamento); boa prática OAB (guarda de registro profissional).",
        "rationale": "LGPD exige eliminação quando a finalidade do tratamento cessa. 2 anos cobre eventuais auditorias de conformidade pós-desativação.",
        "applies_when": [],
    },
]

COMPLIANCE_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "compliance.ripd_structure",
        "category": "compliance",
        "matches_any_of": [
            "RIPD",
            "relatório de impacto",
            "privacy impact assessment",
            "LGPD art 38",
        ],
        "value": (
            "Estrutura canônica LGPD Art. 38:\n"
            "  1. Finalidade específica do tratamento\n"
            "  2. Base legal aplicada (Art. 7º / 11º)\n"
            "  3. Categorias de dados tratados\n"
            "  4. Categorias de titulares\n"
            "  5. Período de retenção (por categoria)\n"
            "  6. Medidas de segurança técnicas e administrativas\n"
            "  7. Transferência internacional (se houver) e salvaguardas\n"
            "  8. Avaliação de riscos e medidas mitigatórias\n"
            "  9. Contato do DPO/encarregado"
        ),
        "source": "LGPD (Lei 13.709/2018) Art. 38 e Resoluções ANPD.",
        "rationale": "Estrutura mínima do RIPD segundo a lei. Campos específicos do projeto (finalidade real, DPO) são parâmetros do cliente, mas a estrutura é pública.",
        "applies_when": ["compliance:lgpd"],
    },
    {
        "key": "compliance.pii_masking",
        "category": "compliance",
        "matches_any_of": [
            "mascaramento de dados pessoais",
            "PII masking",
            "CPF masking",
            "mascarar CPF",
        ],
        "value": (
            "CPF mascarado como ***.XXX.XXX-** (CGU padrão). "
            "Email mascarado como u***@dominio.com. "
            "Telefone mascarado como (**) XXXXX-XX**. "
            "Aplicado em: telas públicas, relatórios compartilhados, logs de aplicação, exports."
        ),
        "source": "Resolução CGU 01/2021; Resolução CNJ 121/2010; LGPD Art. 12.",
        "rationale": "Padrão público de mascaramento no setor jurídico e administrativo brasileiro.",
        "applies_when": ["compliance:lgpd"],
    },
]

SECURITY_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "security.password_hashing",
        "category": "security",
        "matches_any_of": [
            "password hashing",
            "hash de senha",
            "armazenamento de senha",
        ],
        "value": "argon2id com parâmetros OWASP (memory=64MB, iterations=3, parallelism=4). Fallback: bcrypt cost≥12.",
        "source": "OWASP Password Storage Cheat Sheet (2024); NIST SP 800-63B.",
        "rationale": "argon2id é o algoritmo recomendado desde 2015 (Password Hashing Competition). bcrypt cost 12+ aceito como fallback.",
        "applies_when": [],
    },
    {
        "key": "security.jwt_secret",
        "category": "security",
        "matches_any_of": [
            "JWT secret",
            "segredo JWT",
            "JWT_SECRET",
        ],
        "value": "256-bit random (32 bytes via urandom), armazenado APENAS em env var/secret manager. Nunca no código, nunca no Git.",
        "source": "RFC 7519 §11 (JWT security); OWASP JWT Cheat Sheet.",
        "rationale": "Secret forte + armazenamento seguro é baseline. Qualquer comprometimento invalida todos os tokens ativos.",
        "applies_when": ["tech:jwt_auth"],
    },
    {
        "key": "security.icp_brasil_signing",
        "category": "security",
        "matches_any_of": [
            "ICP-Brasil",
            "assinatura digital",
            "certificado digital jurídico",
        ],
        "value": (
            "Assinatura via biblioteca pyhanko (Python) ou equivalente. "
            "Certificado A3 armazenado externamente ao app (token USB ou smartcard). "
            "Leitura via PKCS#11 (padrão ICP-Brasil). "
            "A1 (arquivo .pfx) aceito como alternativa para ambientes controlados, sempre com senha forte."
        ),
        "source": "ITI — Instituto Nacional de Tecnologia da Informação; MP 2.200-2/2001 (ICP-Brasil).",
        "rationale": "PKCS#11 é o padrão ICP-Brasil. Armazenamento externo (A3) é requisito pra cargos que exigem alta confiabilidade.",
        "applies_when": ["domain:juridico"],
    },
]

TECHNICAL_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "technical.datajud_rate_limit",
        "category": "technical",
        "matches_any_of": [
            "rate limit DataJud",
            "DataJud rate",
            "throttling DataJud",
        ],
        "value": "120 requisições/minuto (2 req/s). Por chave de API. Implementar com token bucket + retry exponencial em 429.",
        "source": "CNJ Termo de Uso da API DataJud, item 3.13.",
        "rationale": "Limite documentado pelo próprio CNJ. Excedê-lo bloqueia a chave temporariamente.",
        "applies_when": ["integration:datajud"],
    },
    {
        "key": "technical.datajud_endpoint_base",
        "category": "technical",
        "matches_any_of": [
            "endpoint DataJud",
            "URL DataJud",
        ],
        "value": (
            "DataJud (CNJ): https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search — "
            "onde {tribunal} segue o padrão tjXX (ex: tjsp, tjba, tjrj). "
            "Autenticação: API Key via header `X-DataJud-Key`."
        ),
        "source": "Portal DataJud CNJ — documentação pública da API.",
        "rationale": "Endpoint público padronizado. Cada tribunal tem seu próprio subdomínio/path.",
        "applies_when": ["integration:datajud"],
    },
]

ARCHITECTURE_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "architecture.sqlite_encryption",
        "category": "architecture",
        "matches_any_of": [
            "SQLite criptografado",
            "SQLCipher",
            "banco local criptografado",
        ],
        "value": "SQLCipher com AES-256-CBC + PBKDF2 100k iterações. Senha derivada da senha mestra do usuário (não armazenada em plaintext).",
        "source": "SQLCipher docs (Zetetic LLC); NIST SP 800-132 (PBKDF2).",
        "rationale": "Padrão da indústria para SQLite criptografado. 100k iterações é o mínimo NIST pra proteção offline.",
        "applies_when": ["stack:sqlite", "deployment:desktop"],
    },
]


def all_defaults() -> list[dict[str, Any]]:
    """Retorna a união de todas as categorias de defaults conhecidos."""
    return [
        *LEGAL_DEFAULTS_BR,
        *COMPLIANCE_DEFAULTS,
        *SECURITY_DEFAULTS,
        *TECHNICAL_DEFAULTS,
        *ARCHITECTURE_DEFAULTS,
    ]


def find_matches(gap_text: str, project_context_tags: list[str]) -> list[dict[str, Any]]:
    """Busca defaults cujas `matches_any_of` batem com o texto do gap E cujo
    `applies_when` é subset do contexto do projeto.

    Case-insensitive substring match em `matches_any_of`. Retorna lista —
    caller decide qual aplicar (geralmente o primeiro match com menor
    specificity; mas callers podem aplicar múltiplos se as decision_keys
    forem distintas).
    """
    gap_lower = gap_text.lower()
    ctx = set(project_context_tags or [])
    matches = []
    for entry in all_defaults():
        if not any(m.lower() in gap_lower for m in entry["matches_any_of"]):
            continue
        required = set(entry.get("applies_when") or [])
        if required and not required.issubset(ctx):
            continue
        matches.append(entry)
    return matches
