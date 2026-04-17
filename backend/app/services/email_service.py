"""Email Service"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _is_test_environment() -> bool:
    """Detecta se o processo está rodando dentro de pytest.

    pytest injeta `PYTEST_CURRENT_TEST` no ambiente durante a execução de
    cada teste. Funciona sem configuração, sem fixture, sem monkeypatch —
    garante que `EmailService.send_email` nunca dispare SMTP real em CI
    ou dev local quando testes rodarem com `SMTP_ENABLED=True`.
    """
    return "PYTEST_CURRENT_TEST" in os.environ


# Domínios reservados/inválidos que nunca devem receber email real.
# Baseado em RFC 2606 (.test, .example, .invalid, .localhost, example.com/org/net)
# e nos domínios usados pelas factories do GCA (test.com, test.org, localhost).
# Complementa `_is_test_environment`: mesmo fora do pytest, se algum admin/usuário
# fake sobreviveu no DB (lixo de teste persistido), o SMTP não tenta entregar
# — evita bounces chegando no admin real. Camada de defesa independente da
# DT-016 (SMTP compartimentalizado por projeto, MVP 5).
_BLOCKED_TLDS = (".test", ".example", ".invalid", ".localhost")
_BLOCKED_DOMAINS = (
    "example.com", "example.org", "example.net",
    "test.com", "test.org", "localhost",
)


def _is_non_deliverable_email(to_email: Optional[str]) -> bool:
    """True se o destinatário usa domínio reservado/fake que jamais resolveria."""
    if not to_email or "@" not in to_email:
        return False
    domain = to_email.strip().lower().rsplit("@", 1)[-1]
    if any(domain.endswith(tld) for tld in _BLOCKED_TLDS):
        return True
    if any(domain == d or domain.endswith("." + d) for d in _BLOCKED_DOMAINS):
        return True
    return False


class EmailService:
    """Service for sending emails via SMTP"""

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        from_name_override: Optional[str] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[tuple]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Send email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body content
            text_content: Plain text body (fallback)
            cc: List of CC email addresses
            bcc: List of BCC email addresses
            from_name_override: Override sender name (default: settings.SMTP_FROM_NAME)
            reply_to: Reply-To email address

        Returns:
            (success, error_message)
        """
        # Curto-circuito em ambiente de teste: nunca dispara SMTP real
        # quando rodando via pytest, mesmo com SMTP_ENABLED=True. Evita
        # que testes criem usuários fake com email `@test.com` e o admin
        # receba bounce do SMTP tentando entregar nesses destinatários.
        if _is_test_environment():
            logger.info(
                "email.skipped_test_environment",
                to=to_email,
                subject=subject,
            )
            return True, None

        # Segunda camada: mesmo fora de pytest, recusa domínios reservados
        # (RFC 2606 + test.com/test.org usados pelas factories). Protege o
        # admin real quando há lixo de teste persistido no DB.
        if _is_non_deliverable_email(to_email):
            logger.warning(
                "email.skipped_non_deliverable",
                to=to_email,
                subject=subject,
                reason="domain_in_blocklist",
            )
            return True, None

        if not settings.SMTP_ENABLED:
            logger.warning("email.smtp_disabled")
            return False, "SMTP is disabled"

        try:
            # Create message — use "mixed" when attachments are present
            msg = MIMEMultipart("mixed" if attachments else "alternative")
            msg["Subject"] = subject
            from_name = from_name_override or settings.SMTP_FROM_NAME
            msg["From"] = f"{from_name} <{settings.SMTP_FROM_EMAIL}>"
            if reply_to:
                msg["Reply-To"] = reply_to
            msg["To"] = to_email

            if cc:
                msg["Cc"] = ", ".join(cc)
            if bcc:
                msg["Bcc"] = ", ".join(bcc)

            # Attach text and HTML versions
            if attachments:
                body_part = MIMEMultipart("alternative")
                if text_content:
                    body_part.attach(MIMEText(text_content, "plain"))
                body_part.attach(MIMEText(html_content, "html"))
                msg.attach(body_part)
                for filename, data, mime_type in attachments:
                    from email.mime.application import MIMEApplication
                    part = MIMEApplication(data, Name=filename)
                    part["Content-Disposition"] = f'attachment; filename="{filename}"'
                    msg.attach(part)
            else:
                if text_content:
                    msg.attach(MIMEText(text_content, "plain"))
                msg.attach(MIMEText(html_content, "html"))

            # Send email
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                # TLS for Gmail (port 587)
                if settings.SMTP_PORT == 587:
                    server.starttls()

                # Login
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

                # Send message
                recipients = [to_email]
                if cc:
                    recipients.extend(cc)
                if bcc:
                    recipients.extend(bcc)

                server.sendmail(
                    settings.SMTP_FROM_EMAIL,
                    recipients,
                    msg.as_string(),
                )

            logger.info(
                "email.sent_success",
                to=to_email,
                subject=subject,
            )
            return True, None

        except smtplib.SMTPAuthenticationError as e:
            error_msg = "SMTP authentication failed. Check credentials."
            logger.error("email.auth_failed", error=str(e))
            return False, error_msg

        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            logger.error("email.smtp_error", error=str(e))
            return False, error_msg

        except Exception as e:
            error_msg = f"Email sending failed: {str(e)}"
            logger.error("email.send_failed", error=str(e))
            return False, error_msg

    @staticmethod
    def send_welcome_email(user_email: str, user_name: str) -> tuple[bool, Optional[str]]:
        """Send welcome email to new user"""
        subject = "Bem-vindo ao GCA!"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Bem-vindo ao GCA! 🎉</h2>
                <p>Olá <strong>{user_name}</strong>,</p>
                <p>Sua conta foi criada com sucesso no <strong>GCA — Gerenciador Central de Arquiteturas</strong>.</p>
                <p>Você pode acessar a plataforma em: <a href="http://localhost:8000">http://localhost:8000</a></p>
                <hr>
                <p>Atenciosamente,<br>Equipe GCA</p>
            </body>
        </html>
        """

        text_content = f"""
Bem-vindo ao GCA!

Olá {user_name},

Sua conta foi criada com sucesso no GCA — Gerenciador Central de Arquiteturas.

Você pode acessar a plataforma em: http://localhost:8000

Atenciosamente,
Equipe GCA
        """

        return EmailService.send_email(
            to_email=user_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_password_reset_email(
        user_email: str,
        user_name: str,
        reset_link: str,
    ) -> tuple[bool, Optional[str]]:
        """Send password reset email"""
        subject = "Redefinir sua senha no GCA"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Redefinir Senha</h2>
                <p>Olá <strong>{user_name}</strong>,</p>
                <p>Recebemos uma solicitação para redefinir sua senha no GCA.</p>
                <p><a href="{reset_link}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Redefinir Senha</a></p>
                <p>Se você não solicitou isso, ignore este email.</p>
                <p><small>Este link expira em 24 horas.</small></p>
                <hr>
                <p>Atenciosamente,<br>Equipe GCA</p>
            </body>
        </html>
        """

        text_content = f"""
Redefinir Senha

Olá {user_name},

Recebemos uma solicitação para redefinir sua senha no GCA.

Clique no link abaixo para redefinir sua senha:
{reset_link}

Se você não solicitou isso, ignore este email.

Este link expira em 24 horas.

Atenciosamente,
Equipe GCA
        """

        return EmailService.send_email(
            to_email=user_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_project_invitation_email(
        to_email: str,
        inviter_name: str,
        project_name: str,
        invitation_link: str,
        role: str,
    ) -> tuple[bool, Optional[str]]:
        """Send project invitation email"""
        subject = f"Você foi convidado para o projeto '{project_name}' no GCA"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Convite de Projeto</h2>
                <p><strong>{inviter_name}</strong> convidou você para participar do projeto <strong>{project_name}</strong> no GCA.</p>
                <p><strong>Seu papel:</strong> {role}</p>
                <p><a href="{invitation_link}" style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Aceitar Convite</a></p>
                <hr>
                <p>Atenciosamente,<br>Equipe GCA</p>
            </body>
        </html>
        """

        text_content = f"""
Convite de Projeto

{inviter_name} convidou você para participar do projeto {project_name} no GCA.

Seu papel: {role}

Clique no link abaixo para aceitar o convite:
{invitation_link}

Atenciosamente,
Equipe GCA
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_admin_password_reset_email(
        to_email: str,
        user_name: str,
        temp_password: str,
    ) -> tuple[bool, Optional[str]]:
        """Send admin-initiated password reset email with temporary password"""
        subject = "Sua Senha foi Resetada no GCA"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Sua Senha foi Resetada</h2>
                <p>Olá <strong>{user_name}</strong>,</p>
                <p>Um administrador do GCA resetou sua senha de acesso.</p>
                <p><strong>Senha Temporária:</strong> <code style="background-color: #f5f5f5; padding: 8px; border-radius: 3px; font-family: monospace; font-weight: bold;">{temp_password}</code></p>
                <p style="color: #d9534f; font-weight: bold;">⚠️ IMPORTANTE:</p>
                <ul>
                    <li>Use esta senha para fazer login em: <a href="http://localhost:8000">http://localhost:8000</a></li>
                    <li>Você DEVE trocar esta senha imediatamente após o primeiro acesso</li>
                    <li>Não compartilhe esta senha com ninguém</li>
                </ul>
                <p>Se você não pediu este reset, entre em contato com seu administrador imediatamente.</p>
                <hr>
                <p>Atenciosamente,<br>Equipe GCA</p>
            </body>
        </html>
        """

        text_content = f"""
Sua Senha foi Resetada

Olá {user_name},

Um administrador do GCA resetou sua senha de acesso.

Senha Temporária: {temp_password}

IMPORTANTE:
- Use esta senha para fazer login em: http://localhost:8000
- Você DEVE trocar esta senha imediatamente após o primeiro acesso
- Não compartilhe esta senha com ninguém

Se você não pediu este reset, entre em contato com seu administrador imediatamente.

Atenciosamente,
Equipe GCA
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_gatekeeper_notification_email(
        to_email: str,
        user_name: str,
        project_name: str,
        blocking_status: str,
        overall_score: float,
        dashboard_link: str,
    ) -> tuple[bool, Optional[str]]:
        """Send Gatekeeper evaluation notification"""
        subject = f"Avaliação Gatekeeper concluída para {project_name}"

        status_badge = "🔴 BLOQUEADO" if blocking_status == "blocked_p7" else "🟢 APROVADO"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Avaliação Gatekeeper</h2>
                <p>Olá <strong>{user_name}</strong>,</p>
                <p>A avaliação Gatekeeper para o projeto <strong>{project_name}</strong> foi concluída.</p>
                <p><strong>Status:</strong> {status_badge}</p>
                <p><strong>Score Geral:</strong> {overall_score:.1f}/10</p>
                <p><a href="{dashboard_link}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Ver Detalhes</a></p>
                <hr>
                <p>Atenciosamente,<br>Equipe GCA</p>
            </body>
        </html>
        """

        text_content = f"""
Avaliação Gatekeeper

Olá {user_name},

A avaliação Gatekeeper para o projeto {project_name} foi concluída.

Status: {status_badge}
Score Geral: {overall_score:.1f}/10

Clique no link abaixo para ver os detalhes:
{dashboard_link}

Atenciosamente,
Equipe GCA
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_questionnaire_approved_email(
        to_email: str,
        gp_name: str,
        project_name: str,
        suggested_stack: str,
        observations: str,
        restrictions: str,
        project_link: str,
    ) -> tuple[bool, Optional[str]]:
        """Send questionnaire approval email to GP"""
        subject = f"✅ Projeto {project_name} — Aprovado para Ingestão"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>🎉 Seu Questionário foi Aprovado!</h2>
                <p>Olá <strong>{gp_name}</strong>,</p>
                <p>Seu questionário técnico foi analisado e <strong style="color: #16a34a;">APROVADO!</strong> ✅</p>

                <h3>📊 Resultado da Análise:</h3>
                <ul>
                    <li><strong>Status:</strong> OK</li>
                    <li><strong>Stack Recomendado:</strong> {suggested_stack}</li>
                    <li><strong>Próximo Passo:</strong> Inicie a ingestão de artefatos</li>
                </ul>

                {f'<h3>ℹ️ Observações Técnicas:</h3><p>{observations}</p>' if observations else ''}
                {f'<h3>⚠️ Restrições Técnicas:</h3><p>{restrictions}</p>' if restrictions else ''}

                <h3>🔗 Próximos Passos:</h3>
                <ol>
                    <li>Convide sua equipe: <a href="{project_link}/team">{project_link}/team</a></li>
                    <li>Configure credenciais: <a href="{project_link}/credentials">{project_link}/credentials</a></li>
                    <li>Inicie a ingestão: <a href="{project_link}/ingest">{project_link}/ingest</a></li>
                </ol>

                <p><a href="{project_link}" style="display: inline-block; background-color: #60a5fa; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">Acessar Projeto</a></p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    GCA — Gestão de Código Assistida<br>
                    <a href="https://gca.com/support">Suporte</a> | <a href="https://gca.com/docs">Documentação</a>
                </p>
            </body>
        </html>
        """

        observations_text = f"Observações Técnicas:\n{observations}\n" if observations else ""
        restrictions_text = f"Restrições Técnicas:\n{restrictions}\n" if restrictions else ""

        text_content = f"""
Seu Questionário foi Aprovado!

Olá {gp_name},

Seu questionário técnico foi analisado e APROVADO! ✅

Resultado da Análise:
- Status: OK
- Stack Recomendado: {suggested_stack}
- Próximo Passo: Inicie a ingestão de artefatos

{observations_text}{restrictions_text}
Próximos Passos:
1. Convide sua equipe: {project_link}/team
2. Configure credenciais: {project_link}/credentials
3. Inicie a ingestão: {project_link}/ingest

Acesse seu projeto: {project_link}

GCA — Gestão de Código Assistida
Suporte: https://gca.com/support
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_questionnaire_revision_needed_email(
        to_email: str,
        gp_name: str,
        project_name: str,
        conflicts: list,
        adherence_score: int,
        revision_link: str,
    ) -> tuple[bool, Optional[str]]:
        """Send questionnaire revision needed email to GP"""
        subject = f"⚠️ Projeto {project_name} — Revisão Necessária"

        conflicts_html = "\n".join([f"<li>{conflict}</li>" for conflict in conflicts])

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>⚠️ Seu Questionário Precisa de Revisão</h2>
                <p>Olá <strong>{gp_name}</strong>,</p>
                <p>Seu questionário técnico apresenta <strong>{len(conflicts)} conflito(s)</strong> que precisam ser resolvidos.</p>

                <h3>🚨 Conflitos Detectados:</h3>
                <ol>
                    {conflicts_html}
                </ol>

                <h3>📊 Análise Técnica:</h3>
                <ul>
                    <li><strong>Aderência Atual:</strong> {adherence_score}%</li>
                    <li><strong>Threshold para Aprovação:</strong> 85%</li>
                    <li><strong>Diferença:</strong> {max(0, 85 - adherence_score)}%</li>
                </ul>

                <p style="background-color: #fef3c7; padding: 12px; border-left: 4px solid #f59e0b; border-radius: 3px;">
                    <strong>ℹ️ Dica:</strong> Clique nos campos destacados em âmbar para ver sugestões de correção.
                </p>

                <p><a href="{revision_link}" style="display: inline-block; background-color: #f59e0b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">Revisar Questionário</a></p>

                <p>O sistema reavaluará seu questionário automaticamente após suas correções. Se tiver dúvidas, entre em contato com o suporte.</p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    GCA — Gestão de Código Assistida<br>
                    <a href="https://gca.com/support">Suporte</a> | <a href="https://gca.com/docs">Documentação</a>
                </p>
            </body>
        </html>
        """

        text_content = f"""
Seu Questionário Precisa de Revisão

Olá {gp_name},

Seu questionário técnico apresenta {len(conflicts)} conflito(s) que precisam ser resolvidos.

Conflitos Detectados:
{chr(10).join([f"- {conflict}" for conflict in conflicts])}

Análise Técnica:
- Aderência Atual: {adherence_score}%
- Threshold para Aprovação: 85%
- Diferença: {max(0, 85 - adherence_score)}%

Revisar Questionário: {revision_link}

O sistema reavaluará seu questionário automaticamente após suas correções.

GCA — Gestão de Código Assistida
Suporte: https://gca.com/support
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_team_invitation_email(
        to_email: str,
        user_name: str,
        project_name: str,
        gp_name: str,
        role_name: str,
        accept_link: str,
        project_url: str = "",
    ) -> tuple[bool, Optional[str]]:
        """Send team invitation email with project-specific URL"""
        subject = f"Convite para participar do projeto {project_name}"

        # Bloco opcional com URL do projeto
        project_url_html = ""
        project_url_text = ""
        if project_url:
            project_url_html = f"""
                <li><strong>URL do Projeto:</strong> <a href="{project_url}">{project_url}</a></li>"""
            project_url_text = f"\n- URL do Projeto: {project_url}"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Voce foi convidado para um projeto!</h2>
                <p>Ola <strong>{user_name}</strong>,</p>
                <p>Voce foi convidado para participar do projeto <strong>{project_name}</strong> como <strong>{role_name}</strong>.</p>

                <h3>Detalhes do Projeto:</h3>
                <ul>
                    <li><strong>Nome:</strong> {project_name}</li>
                    <li><strong>Seu Papel:</strong> {role_name}</li>
                    <li><strong>Gestor do Projeto:</strong> {gp_name}</li>{project_url_html}
                </ul>

                <p style="background-color: #d1fae5; padding: 12px; border-left: 4px solid #16a34a; border-radius: 3px;">
                    <strong>Proximo Passo:</strong> Clique no botao abaixo para aceitar o convite e configurar seu acesso.
                </p>

                <p><a href="{accept_link}" style="display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">Aceitar Convite</a></p>

                <p style="color: #666; font-size: 12px;">
                    <strong>Este convite expira em 7 dias.</strong><br>
                    Se voce nao conseguir clicar no botao, copie e cole este link no seu navegador:<br>
                    <code style="background-color: #f5f5f5; padding: 4px 8px; border-radius: 3px; font-family: monospace; word-break: break-all;">{accept_link}</code>
                </p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    GCA — Gestao de Codigo Assistida<br>
                    <a href="https://gca.com/support">Suporte</a> | <a href="https://gca.com/docs">Documentacao</a>
                </p>
            </body>
        </html>
        """

        text_content = f"""
Voce foi convidado para um projeto!

Ola {user_name},

Voce foi convidado para participar do projeto {project_name} como {role_name}.

Detalhes do Projeto:
- Nome: {project_name}
- Seu Papel: {role_name}
- Gestor do Projeto: {gp_name}{project_url_text}

Aceitar Convite: {accept_link}

Este convite expira em 7 dias.

GCA — Gestao de Codigo Assistida
Suporte: https://gca.com/support
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_first_access_password_change_email(
        to_email: str,
        user_name: str,
        project_name: str,
        first_access_link: str,
        temporary_password: str,
    ) -> tuple[bool, Optional[str]]:
        """Send first access email with mandatory password change requirement"""
        subject = f"🔐 Bem-vindo ao GCA - Configure sua Senha"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>🔐 Bem-vindo ao GCA!</h2>
                <p>Olá <strong>{user_name}</strong>,</p>
                <p>Você foi convidado para participar do projeto <strong>{project_name}</strong> no GCA.</p>

                <h3>📋 Seus Dados de Acesso:</h3>
                <ul>
                    <li><strong>Email:</strong> {to_email}</li>
                    <li><strong>Senha Temporária:</strong> <code style="background-color: #f5f5f5; padding: 8px; border-radius: 3px; font-family: monospace; font-weight: bold; letter-spacing: 1px;">{temporary_password}</code></li>
                    <li><strong>Projeto:</strong> {project_name}</li>
                </ul>

                <h3>🔒 Próximas Etapas:</h3>
                <ol>
                    <li><strong>Clique no link abaixo</strong> para primeiro acesso</li>
                    <li><strong>Faça login com a senha temporária</strong> acima</li>
                    <li><strong>Altere sua senha</strong> (obrigatório - você será forçado a fazer isso no primeiro login)</li>
                    <li><strong>Acesse seu projeto</strong></li>
                </ol>

                <p><a href="{first_access_link}" style="display: inline-block; background-color: #1d4ed8; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">Primeiro Acesso</a></p>

                <div style="background-color: #fef3c7; padding: 12px; border-left: 4px solid #dc2626; border-radius: 3px; margin: 16px 0;">
                    <p style="color: #dc2626; font-weight: bold; margin-top: 0;">⚠️ IMPORTANTE:</p>
                    <ul style="margin-bottom: 0;">
                        <li>A senha temporária <strong>expira em 24 horas</strong></li>
                        <li>Você <strong>será obrigado a alterar</strong> a senha no primeiro login</li>
                        <li>Use uma senha <strong>forte (mín. 12 caracteres)</strong></li>
                        <li>Não compartilhe esta senha com ninguém</li>
                    </ul>
                </div>

                <p style="color: #666; font-size: 12px;">
                    Se você não conseguir clicar no botão, copie e cole este link:<br>
                    <code style="background-color: #f5f5f5; padding: 4px 8px; border-radius: 3px; font-family: monospace; word-break: break-all;">{first_access_link}</code>
                </p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    GCA — Gestão de Código Assistida<br>
                    <a href="https://gca.com/support">Suporte</a> | <a href="https://gca.com/docs">Documentação</a>
                </p>
            </body>
        </html>
        """

        text_content = f"""
Bem-vindo ao GCA - Configure sua Senha

Olá {user_name},

Você foi convidado para participar do projeto {project_name} no GCA.

Seus Dados de Acesso:
- Email: {to_email}
- Senha Temporária: {temporary_password}
- Projeto: {project_name}

Próximas Etapas:
1. Clique no link abaixo para primeiro acesso
2. Faça login com a senha temporária acima
3. Altere sua senha (obrigatório - você será forçado a fazer isso no primeiro login)
4. Acesse seu projeto

Primeiro Acesso: {first_access_link}

IMPORTANTE:
- A senha temporária expira em 24 horas
- Você será obrigado a alterar a senha no primeiro login
- Use uma senha forte (mín. 12 caracteres)
- Não compartilhe esta senha com ninguém

GCA — Gestão de Código Assistida
Suporte: https://gca.com/support
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_admin_invitation_email(
        to_email: str,
        invited_by_name: str,
        temporary_password: str,
        activation_link: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Send admin invitation email with temporary password.

        Args:
            to_email: Recipient email address
            invited_by_name: Name of admin who invited this user
            temporary_password: Temporary password (10 chars, 1 upper, 1 number, 1 special)
            activation_link: Link to activate account

        Returns:
            (success, error_message)
        """
        subject = "🔐 Você foi convidado para o GCA - Gestão de Codificação Assistida"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f3ff; margin: 0; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; padding: 32px;">
                    <h1 style="color: #2e1065; text-align: center;">Bem-vindo ao GCA!</h1>
                    <p style="color: #333;">Você foi convidado por <strong>{invited_by_name}</strong> para ser administrador.</p>
                    <div style="background-color: #fef3c7; padding: 16px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; color: #92400e;"><strong>Sua Senha Temporária:</strong></p>
                        <p style="font-family: monospace; font-size: 18px; background: white; padding: 10px; text-align: center; margin: 10px 0;">{temporary_password}</p>
                        <p style="margin: 0; color: #92400e; font-size: 12px;">⚠️ Expira em 24 horas</p>
                    </div>
                    <p style="color: #333;">Requisitos para senha permanente:</p>
                    <ul style="color: #333;">
                        <li>Mínimo 10 caracteres</li>
                        <li>1 letra maiúscula</li>
                        <li>1 número</li>
                        <li>1 caractere especial (!@#$%^&*)</li>
                    </ul>
                    <div style="text-align: center; margin-top: 24px;">
                        <a href="{activation_link}" style="background-color: #7c3aed; color: white; padding: 12px 32px; text-decoration: none; border-radius: 8px; display: inline-block;">
                            Ativar Minha Conta
                        </a>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = f"""
Bem-vindo ao GCA!

{invited_by_name} o convidou para ser administrador.

Sua Senha Temporária: {temporary_password}
(Expira em 24 horas)

Requisitos para senha permanente:
- Mínimo 10 caracteres
- 1 letra maiúscula
- 1 número
- 1 caractere especial

Ative sua conta: {activation_link}

GCA — Gestão de Codificação Assistida
        """

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def send_questionnaire_link_email(
        to_email: str,
        full_name: str,
        questionnaire_link: str,
        expires_at,
    ) -> tuple:
        """Envia email com link único do questionário."""
        if _is_test_environment():
            logger.info("email.skipped_test_environment", to=to_email, kind="questionnaire_link")
            return True, None
        if _is_non_deliverable_email(to_email):
            logger.warning("email.skipped_non_deliverable", to=to_email, kind="questionnaire_link")
            return True, None
        try:
            from app.core.config import settings
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            expires_str = expires_at.strftime("%d/%m/%Y às %H:%M") if expires_at else "5 dias"

            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: #7c3aed; padding: 20px; border-radius: 12px 12px 0 0; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 24px;">GCA - Questionário Técnico</h1>
                </div>
                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 12px 12px;">
                    <p>Olá <strong>{full_name}</strong>,</p>
                    <p>Seu questionário para criação de projeto no GCA está pronto para ser preenchido.</p>
                    <p><strong>Prazo:</strong> Até {expires_str}</p>
                    <p>Você pode salvar como rascunho e continuar depois usando este mesmo link.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{questionnaire_link}" style="background: #7c3aed; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
                            Abrir Questionário
                        </a>
                    </div>
                    <p style="color: #666; font-size: 12px;">Este link é único e intransferível. Não compartilhe com terceiros.</p>
                    <p style="color: #666; font-size: 12px;">Após {expires_str}, o formulário será excluído automaticamente.</p>
                </div>
            </div>
            """

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "📋 GCA - Seu Questionário Técnico está disponível"
            msg["From"] = settings.SMTP_FROM_EMAIL
            msg["To"] = to_email
            msg.attach(MIMEText(f"Olá {full_name}, acesse seu questionário: {questionnaire_link}", "plain"))
            msg.attach(MIMEText(html, "html"))

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
            server.quit()

            structlog.get_logger().info("email.questionnaire_link_sent", to=to_email)
            return True, None
        except Exception as e:
            structlog.get_logger().error("email.questionnaire_link_failed", to=to_email, error=str(e))
            return False, str(e)

    @staticmethod
    def send_ocg_generated_email(
        to_email: str,
        project_name: str,
        ocg_data: dict,
        project_id: str,
    ) -> tuple:
        """Template 12: Notifica GP quando OCG é gerado com sucesso."""
        if _is_test_environment():
            logger.info("email.skipped_test_environment", to=to_email, kind="ocg_generated")
            return True, None
        if _is_non_deliverable_email(to_email):
            logger.warning("email.skipped_non_deliverable", to=to_email, kind="ocg_generated")
            return True, None
        try:
            from app.core.config import settings
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            overall = ocg_data.get("COMPOSITE_SCORE", {}).get("overall", 0)
            status_ocg = ocg_data.get("COMPOSITE_SCORE", {}).get("status", "UNKNOWN")
            is_blocking = ocg_data.get("COMPOSITE_SCORE", {}).get("is_blocking", False)

            pillar_scores = ocg_data.get("PILLAR_SCORES", {})
            p1 = pillar_scores.get("P1_Business", {}).get("score", 0)
            p2 = pillar_scores.get("P2_Rules", {}).get("score", 0)
            p3 = pillar_scores.get("P3_Features", {}).get("score", 0)
            p4 = pillar_scores.get("P4_NFR", {}).get("score", 0)
            p5 = pillar_scores.get("P5_Architecture", {}).get("score", 0)
            p6 = pillar_scores.get("P6_Data", {}).get("score", 0)
            p7 = pillar_scores.get("P7_Security", {}).get("score", 0)

            blocked_warning = ""
            if is_blocking or p7 < 70:
                blocked_warning = """
                <div style="background: #fef2f2; border: 1px solid #ef4444; border-radius: 8px; padding: 16px; margin: 16px 0;">
                    <p style="color: #dc2626; font-weight: bold; margin: 0 0 8px 0;">⚠️ PROJETO BLOQUEADO</p>
                    <p style="color: #991b1b; margin: 0; font-size: 14px;">
                        O score de Segurança (P7) está abaixo de 70. A geração de código não será permitida
                        até que as questões de segurança sejam resolvidas e o questionário reavaliado.
                    </p>
                </div>
                """

            status_color = "#10b981" if status_ocg == "READY" else "#f59e0b" if status_ocg in ("NEEDS_REVIEW", "AT_RISK") else "#ef4444"

            base_url = getattr(settings, "FRONTEND_URL", "https://gca.code-auditor.com.br")
            ocg_link = f"{base_url}/projects/{project_id}/ocg"

            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: #7c3aed; padding: 20px; border-radius: 12px 12px 0 0; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 24px;">GCA — OCG Gerado</h1>
                </div>
                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 12px 12px;">
                    <p>O <strong>Objeto Contexto Global (OCG)</strong> do seu projeto foi gerado com sucesso.</p>

                    <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                        <tr><td style="padding: 8px; font-weight: bold;">Projeto</td><td style="padding: 8px;">{project_name}</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">Score Geral</td><td style="padding: 8px; font-size: 24px; font-weight: bold;">{overall}/100</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">Status</td><td style="padding: 8px;"><span style="background: {status_color}; color: white; padding: 4px 12px; border-radius: 4px;">{status_ocg}</span></td></tr>
                    </table>

                    <h3 style="color: #5b21b6; margin: 20px 0 10px;">Scores por Pilar</h3>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tr style="background: #f3f4f6;"><td style="padding: 6px 8px;">P1 Contexto de Negócio</td><td style="padding: 6px 8px; text-align: right; font-weight: bold;">{p1}/100</td></tr>
                        <tr><td style="padding: 6px 8px;">P2 Regras e Conformidade</td><td style="padding: 6px 8px; text-align: right; font-weight: bold;">{p2}/100</td></tr>
                        <tr style="background: #f3f4f6;"><td style="padding: 6px 8px;">P3 Requisitos Funcionais</td><td style="padding: 6px 8px; text-align: right; font-weight: bold;">{p3}/100</td></tr>
                        <tr><td style="padding: 6px 8px;">P4 Requisitos Não Funcionais</td><td style="padding: 6px 8px; text-align: right; font-weight: bold;">{p4}/100</td></tr>
                        <tr style="background: #f3f4f6;"><td style="padding: 6px 8px;">P5 Arquitetura</td><td style="padding: 6px 8px; text-align: right; font-weight: bold;">{p5}/100</td></tr>
                        <tr><td style="padding: 6px 8px;">P6 Dados</td><td style="padding: 6px 8px; text-align: right; font-weight: bold;">{p6}/100</td></tr>
                        <tr style="background: {'#fef2f2' if p7 < 70 else '#f3f4f6'};"><td style="padding: 6px 8px; {'color: #dc2626;' if p7 < 70 else ''}">P7 Segurança</td><td style="padding: 6px 8px; text-align: right; font-weight: bold; {'color: #dc2626;' if p7 < 70 else ''}">{p7}/100</td></tr>
                    </table>

                    {blocked_warning}

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{ocg_link}" style="background: #7c3aed; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold;">
                            Ver OCG Completo
                        </a>
                    </div>
                </div>
            </div>
            """

            if not getattr(settings, "SMTP_ENABLED", False):
                structlog.get_logger().info("email.ocg_generated_skipped_smtp_disabled", to=to_email)
                return True, None

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"GCA — OCG Gerado: {project_name} ({status_ocg})"
            msg["From"] = settings.SMTP_FROM_EMAIL
            msg["To"] = to_email
            msg.attach(MIMEText(f"OCG do projeto {project_name} gerado. Score: {overall}/100. Status: {status_ocg}. Acesse: {ocg_link}", "plain"))
            msg.attach(MIMEText(html, "html"))

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
            server.quit()

            structlog.get_logger().info("email.ocg_generated_sent", to=to_email, status=status_ocg)
            return True, None

        except Exception as e:
            structlog.get_logger().error("email.ocg_generated_failed", to=to_email, error=str(e))
            return False, str(e)

    @staticmethod
    def send_project_email(
        to_email: str,
        subject: str,
        html_content: str,
        project_name: str,
        reply_to: Optional[str] = None,
        text_content: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Envia e-mail contextualizado com nome do projeto no subject.
        Subject format: [GCA - {project_name}] {subject}
        From: GCA - {project_name} <noreply@...>
        Reply-To: e-mail do GP ou membro responsavel.
        """
        full_subject = f"[GCA - {project_name}] {subject}"
        from_name = f"GCA - {project_name}"

        return EmailService.send_email(
            to_email=to_email,
            subject=full_subject,
            html_content=html_content,
            text_content=text_content,
            from_name_override=from_name,
            reply_to=reply_to,
        )
