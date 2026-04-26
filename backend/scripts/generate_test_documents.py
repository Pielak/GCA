#!/usr/bin/env python3
"""
Gerador de Documentos de Teste para GCA v0.1

Cria 3 variações de documentos AJA para testar:
  1. Simples (500 chars) — teste rápido
  2. Médio (2000 chars) — teste normal
  3. Complexo (5000 chars) — teste de edge case / performance

Uso:
  python generate_test_documents.py --output-dir ./test_docs
  python generate_test_documents.py --simple
  python generate_test_documents.py --all
"""

import argparse
from pathlib import Path
from typing import List


class TestDocumentGenerator:
    """Gera documentos de teste com diferentes complexidades"""

    @staticmethod
    def generate_simple() -> str:
        """
        Documento SIMPLES (~500 chars)
        Mínimo necessário, falta detalhes
        """
        return """SISTEMA DE AUTOMAÇÃO JURÍDICA ASSISTIDA (AJA) v3.0

Objetivo:
Gerar documentos jurídicos com IA.

Requisitos:
1. Login seguro
2. Geração de contratos
3. Exportação PDF

Stack:
- Backend: Python FastAPI
- Frontend: React
- Database: PostgreSQL

Timeline: 6 meses
Orçamento: R$ 500k
"""

    @staticmethod
    def generate_medium() -> str:
        """
        Documento MÉDIO (~2000 chars)
        Nível normal de detalhe, requisitos claros
        """
        return """SISTEMA DE AUTOMAÇÃO JURÍDICA ASSISTIDA (AJA) v3.0

Objetivo Principal:
Plataforma web para auxiliar advogados a gerar documentos jurídicos com IA,
começando com direito civil (contratos, testamentos, petições iniciais).

Requisitos Funcionais Principais:
1. Login seguro com email + 2FA via TOTP
2. Geração automática de contrato civil baseado em template + IA
3. Integração com DataJud API para consulta de processos
4. Versioning e histórico de documentos
5. Compartilhamento de documentos com outras partes (permissionado)
6. Auditoria completa de alterações (quem fez, quando, o quê)
7. Exportação para PDF/Word assinado digitalmente
8. Sugestões de cláusulas baseadas em jurisprudência

Requisitos Não-Funcionais:
- Performance: respostas < 2 segundos (99 percentil)
- Disponibilidade: 99.5% uptime (< 3.6 horas/mês de downtime)
- Escalabilidade: até 10.000 usuários simultâneos no MVP
- LGPD compliance: criptografia E2E de documentos, direito ao esquecimento
- Conformidade: assinatura digital (padrão ICP-Brasil)
- Backup: daily incremental, retenção 90 dias
- Disaster recovery: RTO 2h, RPO 15 min

Stack Técnico:
- Backend: Python FastAPI
- Frontend: React 18 + TypeScript + Tailwind
- Database: PostgreSQL 16 (ACID compliance crítico)
- Cache: Redis (sessões, drafts)
- Queue: Celery/RabbitMQ (async tasks)
- Storage: S3-compatible (MinIO local)
- IA: Claude (análise de cláusulas) + Ollama local
- Infrastructure: Docker + K8s

Timeline MVP: 6 meses
Fase 2: 4 meses
Fase 3: 3 meses

Casos de Uso Principais:
1. Advogado cria novo contrato: template → IA preenche → revisa → assina
2. Consulta jurisprudência: cláusula → IA busca precedentes → sugere
3. Cliente recebe contrato: acessa link seguro → revisa → assina digitalmente
4. Audit trail: órgão regulador acessa histórico completo

Riscos:
- Responsabilidade legal: disclaimer claro obrigatório
- Vazamento: cliente sensível precisa Ollama (não cloud)
- LGPD: dados de clientes = direito exclusão crítico
- DataJud: API pode cair → fallback manual necessário

Orçamento: R$ 500k
Cliente Piloto: 5 advogados em família
"""

    @staticmethod
    def generate_complex() -> str:
        """
        Documento COMPLEXO (~5000 chars)
        Alto detalhe, múltiplas seções, edge cases, performance concerns
        """
        return """SISTEMA DE AUTOMAÇÃO JURÍDICA ASSISTIDA (AJA) v3.0

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 1: VISÃO GERAL E OBJETIVOS
═══════════════════════════════════════════════════════════════════════════════

Objetivo Principal:
Plataforma web de código aberto (open-source) para auxiliar advogados e
paralegais a gerar documentos jurídicos de forma assistida por IA, com
foco inicial em direito civil (contratos, testamentos, petições iniciais).

Diferencial de Mercado:
- Privacy-first: IA local (Ollama) como opção em vez de cloud (Westlaw/LexisNexis)
- Customizável: clientes podem treinar modelos com sua jurisprudência local
- Transparente: todas as modificações IA rastreáveis via audit log
- Compliance-friendly: LGPD-nativo, sem armazenamento de dados em cloud

Target Users:
- Advogados independentes (foco)
- Pequenos escritórios (2-10 advogados)
- Firmas de médio porte em expansão
- Clientes B2B (Cartórios, Oab, Sindicatos)

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 2: REQUISITOS FUNCIONAIS (RF)
═══════════════════════════════════════════════════════════════════════════════

RF-001: Autenticação e Autorização
  - Login com email + TOTP (Google Authenticator, Authy)
  - OAuth 2.0 (Google, GitHub como opção futura)
  - RBAC: Admin, Attorney (criador), Client, Reviewer
  - Session management com Redis (TTL 24h)
  - 2FA obrigatório para usuários com permissão de assinar

RF-002: Geração de Documentos
  - Template library: 50+ templates iniciais (contratos, testamentos, etc)
  - IA-assisted filling: Claude 4.6 analisa contexto + preenche campos
  - Human-in-the-loop: antes de salvar, user revisa + aprova/rejeita cada IA suggestion
  - Versionamento automático: cada save cria nova versão com delta
  - Undo/Redo: até 50 versões por documento, recuperação rápida

RF-003: Integração com DataJud
  - Consulta processual: advogado busca por número → retorna status
  - Fallback: se DataJud offline, avisa user + permite continuar sem dados
  - Rate limiting: máx 100 req/hora por usuário (limite DataJud)
  - Cache: resultados em Redis por 12h

RF-004: Compartilhamento Seguro
  - Link compartilhável com expiração (1 dia, 7 dias, custom)
  - Permissions: view, comment, edit (configurável)
  - Cliente pode assinar digitalmente sem conta (one-time link)
  - Notificações via email para cada compartilhamento

RF-005: Assinatura Digital
  - Integração com ICP-Brasil (padrão legal)
  - Suporte para: A1 (cartório), A3 (smartcard)
  - Fallback: hash-based signature para testes (não legal, apenas audit)
  - Timestamp: cada assinatura incluir NTP timestamp (A4 compliance)

RF-006: Auditoria Completa
  - Quem: user_id + IP
  - Quando: timestamp UTC com ms precision
  - O quê: antes/depois JSON diff
  - Por quê: trigger source (manual_edit, template_generation, IA_suggestion)
  - Imutável: nenhum audit log pode ser deletado (compliance)

RF-007: Integração com Jurisprudência
  - Busca de precedentes: cláusula → busca em base pública (STJ/STF)
  - IA suggestions: "Cláusula X similiar a precedente Y. Risco: Z%"
  - Parametrizável: cliente pode desabilitar para reduzir latência

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 3: REQUISITOS NÃO-FUNCIONAIS (RNF)
═══════════════════════════════════════════════════════════════════════════════

RNF-001: Performance
  - Geração de documento (IA): < 5s (P99)
  - Load page (lista documentos): < 1s (P99)
  - Busca DataJud: < 2s (P99, com timeout)
  - Assinatura: < 3s (ICP-Brasil + timestamp)

RNF-002: Disponibilidade
  - 99.5% uptime (< 3.6h/mês downtime)
  - Graceful degradation: se IA offline, user pode editar manual
  - Healthcheck: /health endpoint responde sempre (< 100ms)
  - Replica database: standby automático em caso de failure

RNF-003: Escalabilidade
  - MVP target: 10.000 usuários simultâneos
  - Horizontal scaling: via Kubernetes (ou simples Docker Compose)
  - Async tasks: Celery workers para IA generation + async email
  - CDN: assets servidos via Cloudflare (ou nginx local)

RNF-004: LGPD Compliance
  - Direito ao esquecimento: delete user → cascade delete todos docs
  - Encryption at rest: dados de cliente em AES-256
  - Encryption in transit: TLS 1.3 obrigatório
  - Data minimization: nunca armazenar cópia no cloud de IA (se usando Ollama)
  - Consent forms: user deve aceitar ToS explicitamente

RNF-005: Conformidade Jurídica
  - ICP-Brasil: assinatura digital com timestamp
  - CNJ: integração com DataJud (Conselho Nacional de Justiça)
  - OAB: auditoria disponível para Conselho (via API autenticada)
  - Disclaimer: "Documento gerado por IA. Advogado responsável final."

RNF-006: Backup e Disaster Recovery
  - Backup: diário às 00:00 BRT (incremental após dia 1)
  - Retenção: 90 dias (compliance mínimo)
  - RTO: 2 horas (máximo tempo para recovery)
  - RPO: 15 minutos (máximo dado perdido)
  - Test restore: weekly test de backup (não automático)

RNF-007: Segurança
  - OWASP Top 10: todos mitigados (SQLi, XSS, CSRF, etc)
  - Rate limiting: 100 req/min por IP (preventivo a brute force)
  - WAF: Cloudflare (ou nginx mod_security local)
  - Secrets management: Vault (HashiCorp) ou .env com restricted perms
  - SSL/TLS: letsencrypt (auto-renewal)

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 4: STACK TÉCNICO
═══════════════════════════════════════════════════════════════════════════════

Backend:
  - Python 3.11+ (FastAPI, async/await)
  - Framework: FastAPI (minimal, fast, ASGI)
  - Database: PostgreSQL 15+ (ACID, JSON, full-text search)
  - Cache: Redis 7+ (sessões, locks, temp data)
  - Task Queue: Celery 5.3+ com Redis broker
  - ORM: SQLAlchemy 2.0+
  - Authentication: python-jose + passlib
  - Logging: structlog (structured, JSON output)

Frontend:
  - React 18+ (TypeScript)
  - Build: Vite (rápido, HMR)
  - Styling: Tailwind CSS v3+
  - State: Zustand (minimal Redux alternative)
  - API client: SWR (data fetching)
  - Editor: Monaco (VS Code editor component)

Storage:
  - Local: S3-compatible (MinIO para dev/self-hosted)
  - Cloud: AWS S3 (production, com replicação cross-region)
  - CDN: Cloudflare (static assets)

IA:
  - Cloud: Claude 4.6 (Anthropic API, primary)
  - Local: Ollama (alternative privacy, fallback)
  - Embedding: OpenAI embeddings (ou local Ollama embeddings)

DevOps:
  - Container: Docker + docker-compose (dev), Kubernetes (prod)
  - CI/CD: GitHub Actions (build + test + deploy)
  - Monitoring: Prometheus + Grafana (optional)
  - Logs: ELK stack (optional) ou Loki (simpler)

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 5: TIMELINE E FASES
═══════════════════════════════════════════════════════════════════════════════

Fase 1 - MVP (6 meses):
  Sprint 1-2: Scaffold (auth, DB, basic UI)
  Sprint 3-4: Geração básica (template + IA + human review)
  Sprint 5-6: Assinatura digital + auditoria
  Sprint 7-8: Integração DataJud (básica)
  Sprint 9-10: Polish + testes + deploy

Fase 2 - Expansão (4 meses):
  - Templates adicionais (testamentos, petições)
  - Versioning avançado (merge, 3-way diff)
  - Jurisprudência (busca + IA suggestions)
  - Integração Oab/Cartórios

Fase 3 - Escala (3 meses):
  - Multi-language (PT, EN, ES)
  - Mobile app (React Native)
  - Customização por cliente (branding)
  - Open-source release

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 6: RISCOS E MITIGAÇÕES
═══════════════════════════════════════════════════════════════════════════════

Risco 1: Responsabilidade Legal
  Impacto: Processo por má geração (documento viciado)
  Mitigação:
    - Disclaimer em todos os documentos
    - Human review obrigatória antes de download
    - Seguro de responsabilidade civil

Risco 2: Vazamento de Confidencialidade
  Impacto: Cliente sensível (confidencial) vai para Claude cloud
  Mitigação:
    - Opção Ollama (IA local) para dados sensíveis
    - Flag "confidential" → não enviar para IA cloud
    - Termos de serviço explícito

Risco 3: LGPD Violations
  Impacto: Multa (até 2% receita anual)
  Mitigação:
    - Direito ao esquecimento implementado desde v1
    - Audit log permanente
    - Data processing agreement (DPA) com Anthropic
    - Legal review antes de launch

Risco 4: DataJud API Indisponibilidade
  Impacto: Feature crítica quebrada
  Mitigação:
    - Cache de 12h dos dados
    - Fallback: permitir manual entry
    - Alert: notificar user quando offline

Risco 5: UX Complexa para Advogado Sênior
  Impacto: Baixa adoção
  Mitigação:
    - Onboarding guiado (tutorial interativo)
    - FAQ + video tutorials
    - Support hotline (fase 2)

═══════════════════════════════════════════════════════════════════════════════
SEÇÃO 7: ORÇAMENTO E RECURSOS
═══════════════════════════════════════════════════════════════════════════════

Orçamento: R$ 500.000 (MVP 6 meses)

Recursos:
  - 1 Product Manager (full-time)
  - 2 Backend Engineers (full-time)
  - 1 Frontend Engineer (full-time)
  - 1 QA Engineer (full-time)
  - 1 DevOps / SRE (50% part-time)

Cliente Piloto: 5 advogados em família (civil, trabalhista, contratos)

Expectativa: Após MVP, modelo SaaS R$ 500/mês por usuário (+ premium R$ 1500)
TAM (Total Addressable Market): ~500k advogados no Brasil = R$ 250M/ano
"""

    @staticmethod
    def save_documents(output_dir: Path):
        """Salva os 3 documentos em arquivos"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        docs = {
            "simple": TestDocumentGenerator.generate_simple(),
            "medium": TestDocumentGenerator.generate_medium(),
            "complex": TestDocumentGenerator.generate_complex(),
        }

        paths = {}
        for name, content in docs.items():
            path = output_dir / f"AJA_v3.0_{name}.txt"
            path.write_text(content)
            paths[name] = path
            print(f"✅ {name:10} → {path} ({len(content)} chars)")

        return paths


def main():
    parser = argparse.ArgumentParser(description="Gerador de Documentos de Teste AJA")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./test_docs",
        help="Diretório de output (default: ./test_docs)"
    )
    parser.add_argument("--simple", action="store_true", help="Gerar apenas documento simples")
    parser.add_argument("--medium", action="store_true", help="Gerar apenas documento médio")
    parser.add_argument("--complex", action="store_true", help="Gerar apenas documento complexo")
    parser.add_argument("--all", action="store_true", help="Gerar todos (default)")

    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Se nenhuma opção especificada, gerar todos
    if not any([args.simple, args.medium, args.complex]):
        args.all = True

    print("\n" + "=" * 80)
    print("GERADOR DE DOCUMENTOS DE TESTE — AJA v3.0")
    print("=" * 80 + "\n")

    paths = TestDocumentGenerator.save_documents(output_dir)

    print("\n" + "=" * 80)
    print("Documentos criados com sucesso!")
    print("=" * 80)
    print(f"\nPróximos passos:")
    print(f"1. Use esses documentos para testar o endpoint M01:")
    print(f"   curl -X POST http://localhost:8000/api/v1/projects/{{id}}/ingestion \\")
    print(f"     -F 'file=@{paths['simple']}'")
    print(f"\n2. Teste com diferentes documentos para validar:")
    print(f"   - Documento simples: teste rápido ({len(TestDocumentGenerator.generate_simple())} chars)")
    print(f"   - Documento médio: caso normal ({len(TestDocumentGenerator.generate_medium())} chars)")
    print(f"   - Documento complexo: edge case ({len(TestDocumentGenerator.generate_complex())} chars)")
    print("\n")


if __name__ == "__main__":
    main()
