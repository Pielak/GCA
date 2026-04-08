"""
Code Validation Router
REST endpoints para validação de código gerado
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

from app.services.code_validation_service import (
    CodeValidationService,
    CodeLanguage,
    SeverityLevel,
    ValidationResult
)

router = APIRouter(prefix="/api/v1/validation", tags=["validation"])


# ============================================================================
# Pydantic Models
# ============================================================================

class CodeLanguageEnum(str, Enum):
    """Code language options"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    SQL = "sql"


class ValidateCodeRequest(BaseModel):
    """Request to validate code"""
    code: str = Field(..., description="Code to validate", min_length=1)
    language: CodeLanguageEnum = Field(..., description="Programming language")
    code_type: str = Field(default="module", description="Type: module, component, function, class")


class SyntaxError(BaseModel):
    """Syntax error details"""
    message: str
    line: int
    offset: Optional[int] = None


class SyntaxValidationResponse(BaseModel):
    """Syntax validation result"""
    status: str
    is_valid: bool
    errors: List[SyntaxError]
    message: Optional[str] = None


class CodeMetrics(BaseModel):
    """Code quality metrics"""
    total_lines: int
    code_lines: int
    comment_lines: int
    comment_ratio: float
    avg_line_length: float
    max_line_length: int


class ComplexityMetrics(BaseModel):
    """Code complexity metrics"""
    cyclomatic_complexity: int
    function_count: int
    control_flow_statements: int
    complexity_level: str


class QualityResult(BaseModel):
    """Code quality analysis result"""
    status: str
    metrics: CodeMetrics
    complexity: ComplexityMetrics
    issues: List[str]


class SecurityFinding(BaseModel):
    """Security finding in code"""
    type: str
    severity: str
    line: int
    message: str
    code: str


class SecurityScanResult(BaseModel):
    """Security scan result"""
    findings: List[SecurityFinding]
    total_issues: int
    critical: int
    high: int
    medium: int
    low: int
    status: str


class BestPracticesResult(BaseModel):
    """Best practices check result"""
    violations: List[str]
    total_violations: int
    compliance_score: float


class CodeValidationResponse(BaseModel):
    """Complete code validation response"""
    timestamp: str
    code_type: str
    language: str
    code_length: int
    line_count: int
    overall_result: str
    is_deployable: bool
    validations: Dict[str, Any]


class DependencyInfo(BaseModel):
    """Dependency information"""
    name: str
    language: str
    type: str
    internal: bool


class DependencyRisk(BaseModel):
    """Dependency risk assessment"""
    package: str
    risk: str
    reason: str


class DependencyAnalysisResponse(BaseModel):
    """Dependency analysis result"""
    timestamp: str
    language: str
    dependencies: List[DependencyInfo]
    total_count: int
    external_count: int
    risk_assessment: Dict[str, Any]


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/validate",
    response_model=CodeValidationResponse,
    summary="Validate generated code",
    description="Comprehensive validation including syntax, quality, and security checks"
)
async def validate_code(request: ValidateCodeRequest):
    """
    Validate code comprehensively

    Performs:
    - Syntax validation
    - Code quality analysis
    - Security scanning
    - Best practice compliance check

    Returns overall result and detailed findings
    """

    try:
        service = CodeValidationService()
        language = CodeLanguage(request.language.value)

        result = await service.validate_code(
            code=request.code,
            language=language,
            code_type=request.code_type
        )

        return CodeValidationResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language or parameters: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code validation failed: {str(e)}"
        )


@router.post(
    "/syntax",
    response_model=SyntaxValidationResponse,
    summary="Validate code syntax",
    description="Check if code has valid syntax"
)
async def validate_syntax(request: ValidateCodeRequest):
    """
    Validate code syntax only

    Returns syntax errors with line numbers if found
    """

    try:
        service = CodeValidationService()
        language = CodeLanguage(request.language.value)

        result = service._validate_syntax(request.code, language)
        return SyntaxValidationResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Syntax validation failed: {str(e)}"
        )


@router.post(
    "/quality",
    response_model=QualityResult,
    summary="Analyze code quality",
    description="Analyze code quality metrics and best practices"
)
async def analyze_quality(request: ValidateCodeRequest):
    """
    Analyze code quality

    Measures:
    - Lines of code and comments
    - Average/max line length
    - Cyclomatic complexity
    - Compliance with quality rules
    """

    try:
        service = CodeValidationService()
        language = CodeLanguage(request.language.value)

        result = service._analyze_code_quality(request.code, language)
        return QualityResult(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quality analysis failed: {str(e)}"
        )


@router.post(
    "/security",
    response_model=SecurityScanResult,
    summary="Security scan code",
    description="Scan code for security vulnerabilities"
)
async def security_scan(request: ValidateCodeRequest):
    """
    Perform security scan

    Detects:
    - SQL injection vulnerabilities
    - Hardcoded credentials
    - Unsafe deserialization
    - Command injection risks
    - Path traversal vulnerabilities
    """

    try:
        service = CodeValidationService()
        language = CodeLanguage(request.language.value)

        result = await service.security_scan(request.code, language)
        return SecurityScanResult(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Security scan failed: {str(e)}"
        )


@router.post(
    "/dependencies",
    response_model=DependencyAnalysisResponse,
    summary="Analyze code dependencies",
    description="Extract and analyze dependencies from code"
)
async def analyze_dependencies(request: ValidateCodeRequest):
    """
    Analyze dependencies

    Extracts:
    - All imports and requires
    - External vs internal dependencies
    - Risky packages
    """

    try:
        service = CodeValidationService()
        language = CodeLanguage(request.language.value)

        result = await service.validate_dependencies(request.code, language)
        return DependencyAnalysisResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dependency analysis failed: {str(e)}"
        )


@router.get(
    "/languages",
    summary="Get supported languages",
    description="List all supported code languages for validation"
)
async def get_supported_languages():
    """
    Get list of supported programming languages
    """

    return {
        "supported_languages": [
            {
                "name": "python",
                "description": "Python 3.x",
                "syntax_validation": "full",
                "dependency_analysis": "pip"
            },
            {
                "name": "javascript",
                "description": "JavaScript (Node.js compatible)",
                "syntax_validation": "basic",
                "dependency_analysis": "npm"
            },
            {
                "name": "typescript",
                "description": "TypeScript",
                "syntax_validation": "basic",
                "dependency_analysis": "npm"
            },
            {
                "name": "java",
                "description": "Java",
                "syntax_validation": "basic",
                "dependency_analysis": "maven"
            },
            {
                "name": "csharp",
                "description": "C#/.NET",
                "syntax_validation": "basic",
                "dependency_analysis": "nuget"
            },
            {
                "name": "go",
                "description": "Go/Golang",
                "syntax_validation": "basic",
                "dependency_analysis": "go modules"
            },
            {
                "name": "rust",
                "description": "Rust",
                "syntax_validation": "basic",
                "dependency_analysis": "cargo"
            },
            {
                "name": "sql",
                "description": "SQL",
                "syntax_validation": "basic",
                "dependency_analysis": "none"
            }
        ]
    }


@router.post(
    "/quick-check",
    summary="Quick validation check",
    description="Quick validation for immediate feedback"
)
async def quick_check(request: ValidateCodeRequest):
    """
    Quick validation check

    Performs basic checks for fast feedback:
    - Syntax validation
    - Critical security issues
    - Deployability assessment
    """

    try:
        service = CodeValidationService()
        language = CodeLanguage(request.language.value)

        result = await service.validate_code(request.code, language)

        return {
            "code_length": result["code_length"],
            "is_valid": result["validations"]["syntax"]["is_valid"],
            "is_deployable": result["is_deployable"],
            "overall_result": result["overall_result"],
            "security_issues": result["validations"]["security"]["total_issues"],
            "critical_issues": result["validations"]["security"]["critical"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quick check failed: {str(e)}"
        )
