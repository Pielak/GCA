"""
GitHub Service
Integração com GitHub para gestão de repositórios, PRs e commits
"""
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
import json
import base64

logger = structlog.get_logger(__name__)


class GitHubIntegration:
    """Integração com GitHub API v3"""

    def __init__(self, access_token: str):
        """
        Initialize GitHub service

        Args:
            access_token: GitHub personal access token
        """
        self.access_token = access_token
        self.api_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }

    async def validate_token(self) -> bool:
        """Validate GitHub access token"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.api_url}/user",
                    headers=self.headers
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning("github.token_validation_failed", error=str(e))
            return False

    async def get_user_info(self) -> Dict[str, Any]:
        """Get authenticated user information"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.api_url}/user",
                    headers=self.headers
                )

                if response.status_code == 200:
                    user_data = response.json()
                    return {
                        "login": user_data.get("login"),
                        "name": user_data.get("name"),
                        "email": user_data.get("email"),
                        "id": user_data.get("id"),
                        "avatar_url": user_data.get("avatar_url")
                    }
                else:
                    raise ValueError(f"GitHub API error: {response.status_code}")

        except Exception as e:
            logger.error("github.get_user_failed", error=str(e))
            raise

    async def get_repositories(self, per_page: int = 30) -> List[Dict[str, Any]]:
        """Get user repositories"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.api_url}/user/repos",
                    headers=self.headers,
                    params={"per_page": per_page, "sort": "updated"}
                )

                if response.status_code == 200:
                    repos = response.json()
                    return [
                        {
                            "name": r.get("name"),
                            "full_name": r.get("full_name"),
                            "url": r.get("html_url"),
                            "description": r.get("description"),
                            "language": r.get("language"),
                            "stars": r.get("stargazers_count"),
                            "is_fork": r.get("fork")
                        }
                        for r in repos
                    ]
                else:
                    raise ValueError(f"GitHub API error: {response.status_code}")

        except Exception as e:
            logger.error("github.get_repos_failed", error=str(e))
            raise

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main"
    ) -> Dict[str, Any]:
        """
        Create a pull request

        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            body: PR description
            head: Branch with changes
            base: Target branch (default: main)
        """
        try:
            import httpx

            pr_data = {
                "title": title,
                "body": body,
                "head": head,
                "base": base
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.api_url}/repos/{owner}/{repo}/pulls",
                    headers=self.headers,
                    json=pr_data
                )

                if response.status_code == 201:
                    pr = response.json()
                    return {
                        "id": pr.get("id"),
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "url": pr.get("html_url"),
                        "state": pr.get("state"),
                        "created_at": pr.get("created_at"),
                        "user": pr.get("user", {}).get("login")
                    }
                else:
                    error_detail = response.json().get("message", "Unknown error")
                    raise ValueError(f"Failed to create PR: {error_detail}")

        except Exception as e:
            logger.error("github.create_pr_failed",
                        owner=owner,
                        repo=repo,
                        error=str(e))
            raise

    async def create_commit(
        self,
        owner: str,
        repo: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
        author_name: str = "GCA Bot",
        author_email: str = "gca@bot.local"
    ) -> Dict[str, Any]:
        """
        Create or update a file via commit

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Target branch
            file_path: Path to file in repo
            content: File content
            commit_message: Commit message
            author_name: Author name
            author_email: Author email
        """
        try:
            import httpx

            # Encode content to base64
            content_b64 = base64.b64encode(content.encode()).decode()

            # Get current file SHA if it exists (for update)
            get_response = await self._get_file_sha(
                httpx.AsyncClient(timeout=10),
                owner,
                repo,
                file_path,
                branch
            )

            file_data = {
                "message": commit_message,
                "content": content_b64,
                "branch": branch,
                "committer": {
                    "name": author_name,
                    "email": author_email
                }
            }

            # Add SHA if file exists (update operation)
            if get_response and get_response.get("sha"):
                file_data["sha"] = get_response["sha"]

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.put(
                    f"{self.api_url}/repos/{owner}/{repo}/contents/{file_path}",
                    headers=self.headers,
                    json=file_data
                )

                if response.status_code in [201, 200]:
                    commit = response.json()
                    return {
                        "sha": commit.get("commit", {}).get("sha"),
                        "message": commit.get("commit", {}).get("message"),
                        "url": commit.get("html_url"),
                        "file": commit.get("content", {}).get("name")
                    }
                else:
                    error_detail = response.json().get("message", "Unknown error")
                    raise ValueError(f"Failed to create commit: {error_detail}")

        except Exception as e:
            logger.error("github.create_commit_failed",
                        owner=owner,
                        repo=repo,
                        file_path=file_path,
                        error=str(e))
            raise

    async def _get_file_sha(
        self,
        client,
        owner: str,
        repo: str,
        file_path: str,
        branch: str
    ) -> Optional[Dict[str, Any]]:
        """Get file SHA for update operations"""
        try:
            response = await client.get(
                f"{self.api_url}/repos/{owner}/{repo}/contents/{file_path}",
                headers=self.headers,
                params={"ref": branch}
            )

            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        source_branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Create a new branch

        Args:
            owner: Repository owner
            repo: Repository name
            branch_name: New branch name
            source_branch: Branch to branch from
        """
        try:
            import httpx

            # First, get the SHA of the source branch
            async with httpx.AsyncClient(timeout=10) as client:
                ref_response = await client.get(
                    f"{self.api_url}/repos/{owner}/{repo}/git/refs/heads/{source_branch}",
                    headers=self.headers
                )

                if ref_response.status_code != 200:
                    raise ValueError(f"Source branch '{source_branch}' not found")

                source_sha = ref_response.json().get("object", {}).get("sha")

                # Create new branch
                branch_data = {
                    "ref": f"refs/heads/{branch_name}",
                    "sha": source_sha
                }

                create_response = await client.post(
                    f"{self.api_url}/repos/{owner}/{repo}/git/refs",
                    headers=self.headers,
                    json=branch_data
                )

                if create_response.status_code == 201:
                    branch = create_response.json()
                    return {
                        "name": branch_name,
                        "sha": branch.get("object", {}).get("sha"),
                        "ref": branch.get("ref")
                    }
                else:
                    error = create_response.json().get("message", "Unknown error")
                    raise ValueError(f"Failed to create branch: {error}")

        except Exception as e:
            logger.error("github.create_branch_failed",
                        owner=owner,
                        repo=repo,
                        branch_name=branch_name,
                        error=str(e))
            raise

    async def get_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        per_page: int = 10
    ) -> List[Dict[str, Any]]:
        """Get pull requests for repository"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.api_url}/repos/{owner}/{repo}/pulls",
                    headers=self.headers,
                    params={"state": state, "per_page": per_page, "sort": "updated"}
                )

                if response.status_code == 200:
                    prs = response.json()
                    return [
                        {
                            "number": pr.get("number"),
                            "title": pr.get("title"),
                            "state": pr.get("state"),
                            "url": pr.get("html_url"),
                            "created_at": pr.get("created_at"),
                            "updated_at": pr.get("updated_at"),
                            "user": pr.get("user", {}).get("login"),
                            "head_branch": pr.get("head", {}).get("ref"),
                            "base_branch": pr.get("base", {}).get("ref")
                        }
                        for pr in prs
                    ]
                else:
                    raise ValueError(f"GitHub API error: {response.status_code}")

        except Exception as e:
            logger.error("github.get_prs_failed",
                        owner=owner,
                        repo=repo,
                        error=str(e))
            raise

    async def add_comment_to_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comment: str
    ) -> Dict[str, Any]:
        """Add comment to pull request"""
        try:
            import httpx

            comment_data = {"body": comment}

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.api_url}/repos/{owner}/{repo}/issues/{pr_number}/comments",
                    headers=self.headers,
                    json=comment_data
                )

                if response.status_code == 201:
                    comment_obj = response.json()
                    return {
                        "id": comment_obj.get("id"),
                        "body": comment_obj.get("body"),
                        "user": comment_obj.get("user", {}).get("login"),
                        "created_at": comment_obj.get("created_at")
                    }
                else:
                    raise ValueError(f"GitHub API error: {response.status_code}")

        except Exception as e:
            logger.error("github.add_comment_failed",
                        owner=owner,
                        repo=repo,
                        pr_number=pr_number,
                        error=str(e))
            raise


class GitHubWorkflow:
    """High-level GitHub workflow orchestration"""

    def __init__(self, access_token: str):
        self.github = GitHubIntegration(access_token)

    async def deploy_generated_code(
        self,
        owner: str,
        repo: str,
        project_name: str,
        generated_code: str,
        file_path: str = "generated/code.py"
    ) -> Dict[str, Any]:
        """
        Complete workflow: Create branch → Commit code → Create PR
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            branch_name = f"gca/generated-{project_name}-{timestamp}"

            # 1. Create branch
            logger.info("github.workflow_create_branch",
                       project=project_name,
                       branch=branch_name)

            branch = await self.github.create_branch(
                owner=owner,
                repo=repo,
                branch_name=branch_name,
                source_branch="main"
            )

            # 2. Create commit
            logger.info("github.workflow_create_commit",
                       project=project_name,
                       file=file_path)

            commit = await self.github.create_commit(
                owner=owner,
                repo=repo,
                branch=branch_name,
                file_path=file_path,
                content=generated_code,
                commit_message=f"GCA: Generated code for {project_name}"
            )

            # 3. Create PR
            logger.info("github.workflow_create_pr",
                       project=project_name)

            pr = await self.github.create_pull_request(
                owner=owner,
                repo=repo,
                title=f"GCA: Generated code for {project_name}",
                body=f"""# Generated Code: {project_name}

Generated by GCA (Gestão de Codificação Assistida)

## Changes
- Generated code file: `{file_path}`
- Branch: `{branch_name}`

## Ready for review
Please review the generated code and merge if approved.""",
                head=branch_name,
                base="main"
            )

            return {
                "success": True,
                "project": project_name,
                "branch": branch,
                "commit": commit,
                "pull_request": pr,
                "workflow_completed_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error("github.workflow_failed",
                        project=project_name,
                        owner=owner,
                        repo=repo,
                        error=str(e))
            raise
