"""
Git Service — Conexão e operações com repositórios Git por projeto.
Suporta GitHub (prioritário), GitLab, Bitbucket, Azure DevOps.
"""
import base64
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import ProjectGitConfig, Project
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Timeout para chamadas HTTP aos providers
GIT_API_TIMEOUT = 30


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extrai owner/repo de uma URL GitHub."""
    patterns = [
        r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$",
        r"github\.com[/:]([^/]+)/([^/.]+?)/?$",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1), m.group(2)
    return None


def _parse_gitlab_url(url: str) -> tuple[str, str] | None:
    """Extrai namespace/project de uma URL GitLab."""
    m = re.search(r"gitlab\.com[/:](.+?)/([^/.]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _parse_bitbucket_url(url: str) -> tuple[str, str] | None:
    """Extrai workspace/repo de uma URL Bitbucket."""
    m = re.search(r"bitbucket\.org[/:]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    return None


class GitService:
    """Serviço de integração Git por projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # CONNECT / VERIFY / DISCONNECT
    # ================================================================

    async def connect_repository(
        self,
        project_id: UUID,
        provider: str,
        repository_url: str,
        pat: str,
        default_branch: str = "main",
    ) -> dict:
        """
        Valida o PAT fazendo chamada de teste ao provider.
        Se válido, salva em project_git_configs.
        """
        valid_providers = ("github", "gitlab", "bitbucket", "azure_devops", "other")
        if provider not in valid_providers:
            return {"success": False, "message": f"Provider inválido. Aceitos: {', '.join(valid_providers)}"}

        # Verificar se projeto existe
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return {"success": False, "message": "Projeto não encontrado"}

        # Testar conexão com o provider
        test_result = await self._test_connection(provider, repository_url, pat)
        if not test_result["connected"]:
            return {"success": False, "message": test_result.get("error", "Falha na conexão")}

        # Salvar ou atualizar configuração
        existing = await self.db.execute(
            select(ProjectGitConfig).where(ProjectGitConfig.project_id == project_id)
        )
        config = existing.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if config:
            config.provider = provider
            config.repository_url = repository_url
            config.default_branch = default_branch
            config.pat_encrypted = pat  # Fase 0.2 criptografará
            config.connection_verified = True
            config.connection_verified_at = now
            config.updated_at = now
        else:
            config = ProjectGitConfig(
                project_id=project_id,
                provider=provider,
                repository_url=repository_url,
                default_branch=default_branch,
                pat_encrypted=pat,  # Fase 0.2 criptografará
                connection_verified=True,
                connection_verified_at=now,
            )
            self.db.add(config)

        await self.db.commit()

        logger.info(
            "git.repository_connected",
            project_id=str(project_id),
            provider=provider,
            branch=default_branch,
        )

        return {
            "success": True,
            "message": f"Repositório {provider} conectado com sucesso.",
            "provider": provider,
            "branch": default_branch,
        }

    async def verify_connection(self, project_id: UUID) -> dict:
        """Testa a conexão atual do projeto com o repositório."""
        config = await self._get_config(project_id)
        if not config:
            return {"connected": False}

        test_result = await self._test_connection(
            config.provider, config.repository_url, config.pat_encrypted
        )

        if test_result["connected"]:
            config.connection_verified = True
            config.connection_verified_at = datetime.now(timezone.utc)
            await self.db.commit()

        return {
            "connected": test_result["connected"],
            "provider": config.provider,
            "repository_url": config.repository_url,
            "branch": config.default_branch,
            "last_verified": config.connection_verified_at.isoformat() if config.connection_verified_at else None,
            "last_commit_at": config.last_commit_at.isoformat() if config.last_commit_at else None,
        }

    async def disconnect(self, project_id: UUID) -> bool:
        """Remove configuração Git do projeto."""
        config = await self._get_config(project_id)
        if not config:
            return False
        await self.db.delete(config)
        await self.db.commit()
        logger.info("git.repository_disconnected", project_id=str(project_id))
        return True

    # ================================================================
    # FILE OPERATIONS
    # ================================================================

    async def commit_file(
        self,
        project_id: UUID,
        file_path: str,
        content: str,
        commit_message: str,
    ) -> dict:
        """Cria ou atualiza arquivo no repositório do projeto."""
        config = await self._get_config(project_id)
        if not config:
            return {"success": False, "message": "Repositório Git não configurado para este projeto"}

        if config.provider == "github":
            return await self._github_commit_file(config, file_path, content.encode("utf-8"), commit_message)
        elif config.provider == "gitlab":
            return await self._gitlab_commit_file(config, file_path, content.encode("utf-8"), commit_message)
        else:
            return {"success": False, "message": f"Commit automático não suportado para provider '{config.provider}'"}

    async def commit_binary_file(
        self,
        project_id: UUID,
        file_path: str,
        content_bytes: bytes,
        commit_message: str,
    ) -> dict:
        """Commit de arquivo binário (imagens, PDFs)."""
        config = await self._get_config(project_id)
        if not config:
            return {"success": False, "message": "Repositório Git não configurado"}

        if config.provider == "github":
            return await self._github_commit_file(config, file_path, content_bytes, commit_message)
        else:
            return {"success": False, "message": f"Commit binário não suportado para '{config.provider}'"}

    async def get_file_content(self, project_id: UUID, file_path: str) -> str | None:
        """Lê conteúdo de um arquivo do repositório."""
        config = await self._get_config(project_id)
        if not config:
            return None

        if config.provider == "github":
            return await self._github_get_file(config, file_path)
        elif config.provider == "gitlab":
            return await self._gitlab_get_file(config, file_path)
        return None

    async def list_files(self, project_id: UUID, path: str = "") -> list[dict]:
        """Lista arquivos em um diretório do repositório."""
        config = await self._get_config(project_id)
        if not config:
            return []

        if config.provider == "github":
            return await self._github_list_files(config, path)
        return []

    async def list_tree(self, project_id: UUID) -> list[dict]:
        """Retorna a árvore completa recursiva do repositório (paths planos)."""
        config = await self._get_config(project_id)
        if not config:
            return []
        if config.provider == "github":
            return await self._github_list_tree(config)
        return []

    async def _github_list_tree(self, config: ProjectGitConfig) -> list[dict]:
        """Git Trees API recursiva."""
        parsed = _parse_github_url(config.repository_url)
        if not parsed:
            return []
        owner, repo = parsed
        try:
            async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/git/trees/{config.default_branch}",
                    headers={
                        "Authorization": f"Bearer {config.pat_encrypted}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={"recursive": "1"},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return [
                    {
                        "path": node["path"],
                        "type": "dir" if node["type"] == "tree" else "file",
                        "size": node.get("size", 0),
                    }
                    for node in data.get("tree", [])
                ]
        except Exception as e:
            logger.error("git.github_tree_error", error=str(e))
            return []

    async def initialize_repository_structure(self, project_id: UUID) -> bool:
        """
        Cria estrutura inicial de diretórios no repositório via commits.
        Chamado quando projeto é aprovado pelo Admin.
        """
        config = await self._get_config(project_id)
        if not config:
            logger.warning("git.init_structure_no_config", project_id=str(project_id))
            return False

        # Buscar dados do projeto
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return False

        project_name = project.name or "Projeto GCA"
        project_desc = project.description or "Projeto gerenciado pelo GCA"

        # Estrutura de arquivos iniciais
        files = {
            "README.md": f"# {project_name}\n\n{project_desc}\n\n> Projeto gerenciado pelo GCA — Gestão de Codificação Assistida\n",
            "docs/functional/overview.md": f"# Visão Funcional — {project_name}\n\n*Gerado automaticamente pelo GCA. Será atualizado conforme o OCG evolui.*\n",
            "docs/technical/architecture.md": f"# Arquitetura — {project_name}\n\n*Gerado automaticamente pelo GCA.*\n",
            "docs/technical/stack.md": f"# Stack Tecnológico — {project_name}\n\n*Será preenchido após geração do OCG.*\n",
            "docs/business_rules/rules.md": f"# Regras de Negócio — {project_name}\n\n*Será preenchido após geração do OCG.*\n",
            "docs/modules/.gitkeep": "",
            "docs/tests/test_plan.md": f"# Plano de Testes — {project_name}\n\n*Será preenchido após geração do OCG.*\n",
            "docs/ingested/.gitkeep": "",
            "docs/ocg_current.md": f"# OCG Atual — {project_name}\n\n*Aguardando geração do OCG.*\n",
            "docs/CHANGELOG.md": f"# Changelog — {project_name}\n\n## [{datetime.now().strftime('%Y-%m-%d')}] — Inicialização\n- Estrutura do repositório criada pelo GCA\n",
            "src/modules/.gitkeep": "",
            "tests/unit/.gitkeep": "",
            "tests/integration/.gitkeep": "",
            "tests/uat/.gitkeep": "",
        }

        success_count = 0
        for fpath, content in files.items():
            result = await self.commit_file(
                project_id=project_id,
                file_path=fpath,
                content=content,
                commit_message=f"[GCA] init: {fpath}",
            )
            if result.get("success"):
                success_count += 1

        logger.info(
            "git.structure_initialized",
            project_id=str(project_id),
            files_created=success_count,
            total_files=len(files),
        )
        return success_count > 0

    # ================================================================
    # INTERNAL HELPERS
    # ================================================================

    async def _get_config(self, project_id: UUID) -> ProjectGitConfig | None:
        result = await self.db.execute(
            select(ProjectGitConfig).where(ProjectGitConfig.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def _test_connection(self, provider: str, url: str, pat: str) -> dict:
        """Testa conexão com o provider."""
        try:
            if provider == "github":
                parsed = _parse_github_url(url)
                if not parsed:
                    return {"connected": False, "error": "URL do GitHub inválida. Formato: https://github.com/owner/repo"}
                owner, repo = parsed
                async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                    resp = await client.get(
                        f"https://api.github.com/repos/{owner}/{repo}",
                        headers={"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github.v3+json"},
                    )
                if resp.status_code == 200:
                    return {"connected": True}
                elif resp.status_code == 401:
                    return {"connected": False, "error": "PAT inválido ou expirado"}
                elif resp.status_code == 404:
                    return {"connected": False, "error": "Repositório não encontrado. Verifique a URL e permissões do PAT"}
                return {"connected": False, "error": f"GitHub retornou status {resp.status_code}"}

            elif provider == "gitlab":
                parsed = _parse_gitlab_url(url)
                if not parsed:
                    return {"connected": False, "error": "URL do GitLab inválida"}
                namespace, project = parsed
                project_path = f"{namespace}/{project}"
                async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                    resp = await client.get(
                        f"https://gitlab.com/api/v4/projects/{httpx.URL(project_path).raw_path.decode() if hasattr(httpx.URL(project_path).raw_path, 'decode') else project_path.replace('/', '%2F')}",
                        headers={"PRIVATE-TOKEN": pat},
                    )
                if resp.status_code == 200:
                    return {"connected": True}
                elif resp.status_code == 401:
                    return {"connected": False, "error": "Token GitLab inválido"}
                return {"connected": False, "error": f"GitLab retornou status {resp.status_code}"}

            elif provider == "bitbucket":
                parsed = _parse_bitbucket_url(url)
                if not parsed:
                    return {"connected": False, "error": "URL do Bitbucket inválida"}
                workspace, repo = parsed
                async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                    resp = await client.get(
                        f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}",
                        headers={"Authorization": f"Bearer {pat}"},
                    )
                if resp.status_code == 200:
                    return {"connected": True}
                return {"connected": False, "error": f"Bitbucket retornou status {resp.status_code}"}

            elif provider == "azure_devops":
                return {"connected": False, "error": "Azure DevOps: verificação automática ainda não implementada. Configuração salva para uso manual."}

            elif provider == "other":
                return {"connected": False, "error": "Provider 'other': verificação automática não suportada. Configuração salva para uso manual."}

            return {"connected": False, "error": f"Provider '{provider}' não suportado"}

        except httpx.TimeoutException:
            return {"connected": False, "error": "Timeout ao conectar com o provider"}
        except Exception as e:
            logger.error("git.connection_test_error", provider=provider, error=str(e))
            return {"connected": False, "error": f"Erro ao testar conexão: {str(e)}"}

    # ================================================================
    # GITHUB API
    # ================================================================

    async def _github_commit_file(
        self, config: ProjectGitConfig, file_path: str, content: bytes, message: str
    ) -> dict:
        """Commit de arquivo via GitHub API."""
        parsed = _parse_github_url(config.repository_url)
        if not parsed:
            return {"success": False, "message": "URL GitHub inválida"}
        owner, repo = parsed

        try:
            async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                headers = {
                    "Authorization": f"Bearer {config.pat_encrypted}",
                    "Accept": "application/vnd.github.v3+json",
                }

                # Verificar se arquivo já existe (para obter SHA)
                existing = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                    headers=headers,
                    params={"ref": config.default_branch},
                )
                sha = None
                if existing.status_code == 200:
                    sha = existing.json().get("sha")

                # Criar/atualizar arquivo
                body = {
                    "message": message,
                    "content": base64.b64encode(content).decode("ascii"),
                    "branch": config.default_branch,
                }
                if sha:
                    body["sha"] = sha

                resp = await client.put(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                    headers=headers,
                    json=body,
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    commit_sha = data.get("commit", {}).get("sha", "")
                    file_url = data.get("content", {}).get("html_url", "")

                    # Atualizar last_commit_at
                    config.last_commit_at = datetime.now(timezone.utc)
                    await self.db.commit()

                    return {"success": True, "commit_sha": commit_sha, "file_url": file_url}
                else:
                    return {"success": False, "message": f"GitHub API retornou {resp.status_code}: {resp.text[:200]}"}

        except Exception as e:
            logger.error("git.github_commit_error", error=str(e))
            return {"success": False, "message": str(e)}

    async def _github_get_file(self, config: ProjectGitConfig, file_path: str) -> str | None:
        """Lê conteúdo de arquivo do GitHub."""
        parsed = _parse_github_url(config.repository_url)
        if not parsed:
            return None
        owner, repo = parsed

        try:
            async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                    headers={
                        "Authorization": f"Bearer {config.pat_encrypted}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={"ref": config.default_branch},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content_b64 = data.get("content", "")
                    return base64.b64decode(content_b64).decode("utf-8")
                return None
        except Exception as e:
            logger.error("git.github_get_file_error", error=str(e))
            return None

    async def _github_list_files(self, config: ProjectGitConfig, path: str) -> list[dict]:
        """Lista arquivos de um diretório no GitHub."""
        parsed = _parse_github_url(config.repository_url)
        if not parsed:
            return []
        owner, repo = parsed

        try:
            async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                    headers={
                        "Authorization": f"Bearer {config.pat_encrypted}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={"ref": config.default_branch},
                )
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list):
                        return [
                            {
                                "name": item["name"],
                                "path": item["path"],
                                "type": "dir" if item["type"] == "dir" else "file",
                                "size": item.get("size", 0),
                            }
                            for item in items
                        ]
                return []
        except Exception as e:
            logger.error("git.github_list_error", error=str(e))
            return []

    # ================================================================
    # GITLAB API
    # ================================================================

    async def _gitlab_commit_file(
        self, config: ProjectGitConfig, file_path: str, content: bytes, message: str
    ) -> dict:
        """Commit via GitLab API."""
        parsed = _parse_gitlab_url(config.repository_url)
        if not parsed:
            return {"success": False, "message": "URL GitLab inválida"}
        namespace, project = parsed
        project_encoded = f"{namespace}/{project}".replace("/", "%2F")

        try:
            async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                headers = {"PRIVATE-TOKEN": config.pat_encrypted}

                # Verificar se arquivo existe
                existing = await client.get(
                    f"https://gitlab.com/api/v4/projects/{project_encoded}/repository/files/{file_path.replace('/', '%2F')}",
                    headers=headers,
                    params={"ref": config.default_branch},
                )

                action = "update" if existing.status_code == 200 else "create"

                resp = await client.post(
                    f"https://gitlab.com/api/v4/projects/{project_encoded}/repository/commits",
                    headers=headers,
                    json={
                        "branch": config.default_branch,
                        "commit_message": message,
                        "actions": [
                            {
                                "action": action,
                                "file_path": file_path,
                                "content": base64.b64encode(content).decode("ascii"),
                                "encoding": "base64",
                            }
                        ],
                    },
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    config.last_commit_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    return {"success": True, "commit_sha": data.get("id", ""), "file_url": ""}
                return {"success": False, "message": f"GitLab retornou {resp.status_code}"}

        except Exception as e:
            logger.error("git.gitlab_commit_error", error=str(e))
            return {"success": False, "message": str(e)}

    async def _gitlab_get_file(self, config: ProjectGitConfig, file_path: str) -> str | None:
        """Lê conteúdo de arquivo do GitLab."""
        parsed = _parse_gitlab_url(config.repository_url)
        if not parsed:
            return None
        namespace, project = parsed
        project_encoded = f"{namespace}/{project}".replace("/", "%2F")

        try:
            async with httpx.AsyncClient(timeout=GIT_API_TIMEOUT) as client:
                resp = await client.get(
                    f"https://gitlab.com/api/v4/projects/{project_encoded}/repository/files/{file_path.replace('/', '%2F')}/raw",
                    headers={"PRIVATE-TOKEN": config.pat_encrypted},
                    params={"ref": config.default_branch},
                )
                if resp.status_code == 200:
                    return resp.text
                return None
        except Exception as e:
            logger.error("git.gitlab_get_file_error", error=str(e))
            return None
