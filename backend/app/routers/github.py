"""
GitHub Router
REST endpoints para integração com GitHub
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.services.github_service import GitHubIntegration, GitHubWorkflow

router = APIRouter(prefix="/api/v1/github", tags=["github"])


# ============================================================================
# Pydantic Models
# ============================================================================

class GitHubTokenRequest(BaseModel):
    """GitHub access token"""
    access_token: str = Field(..., description="GitHub personal access token")


class GitHubUserResponse(BaseModel):
    """GitHub user information"""
    login: str
    name: Optional[str]
    email: Optional[str]
    id: int
    avatar_url: Optional[str]


class Repository(BaseModel):
    """Repository information"""
    name: str
    full_name: str
    url: str
    description: Optional[str]
    language: Optional[str]
    stars: int
    is_fork: bool


class CreateBranchRequest(BaseModel):
    """Request to create branch"""
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    branch_name: str = Field(..., description="New branch name")
    source_branch: str = Field(default="main", description="Source branch")


class BranchResponse(BaseModel):
    """Branch response"""
    name: str
    sha: str
    ref: str


class CreateCommitRequest(BaseModel):
    """Request to create commit"""
    owner: str
    repo: str
    branch: str
    file_path: str
    content: str
    commit_message: str
    author_name: str = Field(default="GCA Bot")
    author_email: str = Field(default="gca@bot.local")


class CommitResponse(BaseModel):
    """Commit response"""
    sha: str
    message: str
    url: str
    file: str


class CreatePullRequestRequest(BaseModel):
    """Request to create pull request"""
    owner: str
    repo: str
    title: str
    body: str
    head: str
    base: str = Field(default="main")


class PullRequestResponse(BaseModel):
    """Pull request response"""
    id: int
    number: int
    title: str
    url: str
    state: str
    created_at: str
    user: str


class DeployCodeRequest(BaseModel):
    """Request to deploy generated code"""
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    project_name: str = Field(..., description="Project name")
    generated_code: str = Field(..., description="Generated code content")
    file_path: str = Field(default="generated/code.py", description="Target file path")


class DeployCodeResponse(BaseModel):
    """Deployment response"""
    success: bool
    project: str
    branch: Dict[str, Any]
    commit: Dict[str, Any]
    pull_request: Dict[str, Any]
    workflow_completed_at: str


class AddCommentRequest(BaseModel):
    """Request to add comment to PR"""
    owner: str
    repo: str
    pr_number: int
    comment: str


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/validate",
    summary="Validate GitHub token",
    description="Validate GitHub personal access token"
)
async def validate_github_token(request: GitHubTokenRequest):
    """
    Validate GitHub access token

    Returns whether token is valid and can be used for API calls
    """

    try:
        github = GitHubIntegration(request.access_token)
        valid = await github.validate_token()

        if valid:
            return {
                "valid": True,
                "message": "GitHub token is valid"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub token is invalid or expired"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token validation failed: {str(e)}"
        )


@router.post(
    "/user",
    response_model=GitHubUserResponse,
    summary="Get authenticated user",
    description="Get information about authenticated GitHub user"
)
async def get_github_user(request: GitHubTokenRequest):
    """
    Get authenticated GitHub user information
    """

    try:
        github = GitHubIntegration(request.access_token)
        user_info = await github.get_user_info()
        return GitHubUserResponse(**user_info)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user info: {str(e)}"
        )


@router.post(
    "/repositories",
    summary="List user repositories",
    description="Get list of user repositories"
)
async def list_repositories(
    request: GitHubTokenRequest,
    per_page: int = 30
):
    """
    List user repositories

    Args:
        access_token: GitHub personal access token
        per_page: Number of repos per page (default: 30)
    """

    try:
        github = GitHubIntegration(request.access_token)
        repos = await github.get_repositories(per_page=per_page)

        return {
            "count": len(repos),
            "repositories": [Repository(**repo) for repo in repos]
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list repositories: {str(e)}"
        )


@router.post(
    "/branches/create",
    response_model=BranchResponse,
    summary="Create new branch",
    description="Create new branch in repository"
)
async def create_branch(
    request: CreateBranchRequest,
    token: str = None
):
    """
    Create new branch

    Args:
        owner: Repository owner
        repo: Repository name
        branch_name: Name for new branch
        source_branch: Branch to create from (default: main)
        token: GitHub access token (from header or query param)
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token required"
        )

    try:
        github = GitHubIntegration(token)
        branch = await github.create_branch(
            owner=request.owner,
            repo=request.repo,
            branch_name=request.branch_name,
            source_branch=request.source_branch
        )

        return BranchResponse(**branch)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create branch: {str(e)}"
        )


@router.post(
    "/commits/create",
    response_model=CommitResponse,
    summary="Create commit",
    description="Create or update file via commit"
)
async def create_commit(
    request: CreateCommitRequest,
    token: str = None
):
    """
    Create commit in repository

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Target branch
        file_path: Path to file
        content: File content
        commit_message: Commit message
        token: GitHub access token
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token required"
        )

    try:
        github = GitHubIntegration(token)
        commit = await github.create_commit(
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            file_path=request.file_path,
            content=request.content,
            commit_message=request.commit_message,
            author_name=request.author_name,
            author_email=request.author_email
        )

        return CommitResponse(**commit)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create commit: {str(e)}"
        )


@router.post(
    "/pulls/create",
    response_model=PullRequestResponse,
    summary="Create pull request",
    description="Create pull request in repository"
)
async def create_pull_request(
    request: CreatePullRequestRequest,
    token: str = None
):
    """
    Create pull request

    Args:
        owner: Repository owner
        repo: Repository name
        title: PR title
        body: PR description
        head: Branch with changes
        base: Target branch (default: main)
        token: GitHub access token
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token required"
        )

    try:
        github = GitHubIntegration(token)
        pr = await github.create_pull_request(
            owner=request.owner,
            repo=request.repo,
            title=request.title,
            body=request.body,
            head=request.head,
            base=request.base
        )

        return PullRequestResponse(**pr)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create pull request: {str(e)}"
        )


@router.post(
    "/deploy",
    response_model=DeployCodeResponse,
    summary="Deploy generated code",
    description="Complete workflow: create branch → commit code → create PR"
)
async def deploy_generated_code(
    request: DeployCodeRequest,
    token: str = None
):
    """
    Deploy generated code to GitHub

    Complete workflow:
    1. Creates new branch
    2. Commits generated code
    3. Creates pull request

    Args:
        owner: Repository owner
        repo: Repository name
        project_name: Project name
        generated_code: Generated code content
        file_path: Target file path
        token: GitHub access token
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token required"
        )

    try:
        workflow = GitHubWorkflow(token)
        result = await workflow.deploy_generated_code(
            owner=request.owner,
            repo=request.repo,
            project_name=request.project_name,
            generated_code=request.generated_code,
            file_path=request.file_path
        )

        return DeployCodeResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deployment failed: {str(e)}"
        )


@router.get(
    "/pulls/{owner}/{repo}",
    summary="List pull requests",
    description="List pull requests for repository"
)
async def get_pull_requests(
    owner: str,
    repo: str,
    state: str = "all",
    per_page: int = 10,
    token: str = None
):
    """
    Get pull requests for repository

    Args:
        owner: Repository owner
        repo: Repository name
        state: PR state (all/open/closed)
        per_page: Number per page
        token: GitHub access token
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token required"
        )

    try:
        github = GitHubIntegration(token)
        prs = await github.get_pull_requests(
            owner=owner,
            repo=repo,
            state=state,
            per_page=per_page
        )

        return {
            "count": len(prs),
            "pull_requests": prs
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pull requests: {str(e)}"
        )


@router.post(
    "/pulls/{owner}/{repo}/{pr_number}/comments",
    summary="Add comment to PR",
    description="Add comment to pull request"
)
async def add_comment_to_pr(
    owner: str,
    repo: str,
    pr_number: int,
    request: AddCommentRequest,
    token: str = None
):
    """
    Add comment to pull request

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number
        comment: Comment text
        token: GitHub access token
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token required"
        )

    try:
        github = GitHubIntegration(token)
        comment = await github.add_comment_to_pr(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            comment=request.comment
        )

        return comment

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add comment: {str(e)}"
        )
