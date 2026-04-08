"""
Code Validation Service
Valida sintaxe, qualidade e segurança do código gerado
"""
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from enum import Enum
import re

logger = structlog.get_logger(__name__)


class CodeLanguage(str, Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    SQL = "sql"


class SeverityLevel(str, Enum):
    """Security finding severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ValidationResult(str, Enum):
    """Code validation result"""
    VALID = "valid"
    WARNINGS = "warnings"
    ERRORS = "errors"


class CodeValidationService:
    """Service for validating generated code"""

    def __init__(self):
        self.security_patterns = self._init_security_patterns()
        self.quality_rules = self._init_quality_rules()

    async def validate_code(
        self,
        code: str,
        language: CodeLanguage,
        code_type: str = "module"  # module, component, function, class
    ) -> Dict[str, Any]:
        """
        Comprehensive code validation

        Checks:
        1. Syntax validation
        2. Code quality metrics
        3. Security scanning
        4. Best practice compliance
        """

        try:
            results = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "code_type": code_type,
                "language": language.value,
                "code_length": len(code),
                "line_count": len(code.split('\n')),
                "validations": {}
            }

            # 1. Syntax validation
            syntax_result = self._validate_syntax(code, language)
            results["validations"]["syntax"] = syntax_result

            # 2. Quality metrics
            quality_result = self._analyze_code_quality(code, language)
            results["validations"]["quality"] = quality_result

            # 3. Security scanning
            security_result = await self._security_scan(code, language)
            results["validations"]["security"] = security_result

            # 4. Best practices
            best_practices = self._check_best_practices(code, language)
            results["validations"]["best_practices"] = best_practices

            # Overall result
            results["overall_result"] = self._determine_overall_result(results)
            results["is_deployable"] = self._is_deployable(results)

            logger.info("code.validation_complete",
                       language=language.value,
                       code_type=code_type,
                       result=results["overall_result"],
                       security_issues=len(security_result.get("findings", [])))

            return results

        except Exception as e:
            logger.error("code.validation_failed",
                        language=language.value,
                        error=str(e))
            raise

    async def validate_dependencies(
        self,
        code: str,
        language: CodeLanguage
    ) -> Dict[str, Any]:
        """
        Extract and validate dependencies from code
        """

        try:
            dependencies = self._extract_dependencies(code, language)

            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "language": language.value,
                "dependencies": dependencies,
                "total_count": len(dependencies),
                "external_count": sum(1 for d in dependencies if not d.get("internal", False)),
                "risk_assessment": self._assess_dependency_risk(dependencies)
            }

            logger.info("dependencies.analyzed",
                       language=language.value,
                       count=len(dependencies))

            return result

        except Exception as e:
            logger.error("dependencies.analysis_failed",
                        language=language.value,
                        error=str(e))
            raise

    async def security_scan(
        self,
        code: str,
        language: CodeLanguage
    ) -> Dict[str, Any]:
        """
        Focused security scanning
        """

        return await self._security_scan(code, language)

    def _validate_syntax(self, code: str, language: CodeLanguage) -> Dict[str, Any]:
        """Validate code syntax"""

        try:
            if language == CodeLanguage.PYTHON:
                return self._validate_python_syntax(code)
            elif language == CodeLanguage.JAVASCRIPT:
                return self._validate_javascript_syntax(code)
            elif language == CodeLanguage.JSON:
                return self._validate_json_syntax(code)
            else:
                # For unsupported languages, do basic checks
                return self._basic_syntax_check(code, language)

        except Exception as e:
            return {
                "status": "error",
                "errors": [{"message": str(e), "line": 0}],
                "is_valid": False
            }

    def _validate_python_syntax(self, code: str) -> Dict[str, Any]:
        """Validate Python syntax"""

        try:
            compile(code, '<string>', 'exec')
            return {
                "status": "valid",
                "errors": [],
                "is_valid": True,
                "message": "Python syntax is valid"
            }
        except SyntaxError as e:
            return {
                "status": "invalid",
                "errors": [
                    {
                        "message": str(e.msg),
                        "line": e.lineno,
                        "offset": e.offset
                    }
                ],
                "is_valid": False
            }

    def _validate_javascript_syntax(self, code: str) -> Dict[str, Any]:
        """Basic JavaScript syntax validation"""

        errors = []

        # Check for common syntax issues
        if code.count('{') != code.count('}'):
            errors.append({"message": "Mismatched braces", "line": 0})

        if code.count('(') != code.count(')'):
            errors.append({"message": "Mismatched parentheses", "line": 0})

        if code.count('[') != code.count(']'):
            errors.append({"message": "Mismatched brackets", "line": 0})

        return {
            "status": "valid" if not errors else "invalid",
            "errors": errors,
            "is_valid": len(errors) == 0,
            "message": "Basic JavaScript syntax check completed"
        }

    def _validate_json_syntax(self, code: str) -> Dict[str, Any]:
        """Validate JSON syntax"""

        try:
            import json
            json.loads(code)
            return {
                "status": "valid",
                "errors": [],
                "is_valid": True,
                "message": "JSON syntax is valid"
            }
        except json.JSONDecodeError as e:
            return {
                "status": "invalid",
                "errors": [{"message": str(e), "line": e.lineno}],
                "is_valid": False
            }

    def _basic_syntax_check(self, code: str, language: CodeLanguage) -> Dict[str, Any]:
        """Basic syntax checks for any language"""

        errors = []

        # Check for unmatched braces
        if code.count('{') != code.count('}'):
            errors.append({"message": "Unmatched braces { }", "line": 0})

        # Check for unmatched quotes (basic)
        if code.count('"') % 2 != 0 or code.count("'") % 2 != 0:
            errors.append({"message": "Unmatched quotes", "line": 0})

        return {
            "status": "valid" if not errors else "invalid",
            "errors": errors,
            "is_valid": len(errors) == 0,
            "message": f"Basic syntax check for {language.value}"
        }

    def _analyze_code_quality(self, code: str, language: CodeLanguage) -> Dict[str, Any]:
        """Analyze code quality metrics"""

        lines = code.split('\n')
        non_empty_lines = [l for l in lines if l.strip()]
        comments = [l for l in lines if l.strip().startswith('#') or l.strip().startswith('//')]

        metrics = {
            "total_lines": len(lines),
            "code_lines": len(non_empty_lines),
            "comment_lines": len(comments),
            "comment_ratio": round(len(comments) / len(non_empty_lines) * 100, 1) if non_empty_lines else 0,
            "avg_line_length": round(sum(len(l) for l in non_empty_lines) / len(non_empty_lines), 1) if non_empty_lines else 0,
            "max_line_length": max((len(l) for l in lines), default=0)
        }

        # Complexity assessment
        complexity = self._assess_complexity(code, language)

        issues = []
        if metrics["avg_line_length"] > 120:
            issues.append("Some lines exceed recommended 120 character limit")
        if metrics["comment_ratio"] < 5:
            issues.append("Low comment ratio - consider adding more documentation")
        if complexity["cyclomatic_complexity"] > 15:
            issues.append("High cyclomatic complexity - consider refactoring")

        return {
            "status": "good" if not issues else "warning",
            "metrics": metrics,
            "complexity": complexity,
            "issues": issues
        }

    async def _security_scan(self, code: str, language: CodeLanguage) -> Dict[str, Any]:
        """Scan code for security vulnerabilities"""

        findings = []

        # Check for common security issues
        for pattern_name, patterns in self.security_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, code)
                for match in matches:
                    line_num = code[:match.start()].count('\n') + 1
                    findings.append({
                        "type": pattern_name,
                        "severity": "medium",
                        "line": line_num,
                        "message": f"Potential {pattern_name} detected",
                        "code": code.split('\n')[line_num - 1].strip()
                    })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "language": language.value,
            "findings": findings,
            "total_issues": len(findings),
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "medium": sum(1 for f in findings if f["severity"] == "medium"),
            "low": sum(1 for f in findings if f["severity"] == "low"),
            "status": "secure" if len(findings) == 0 else "warning"
        }

    def _check_best_practices(self, code: str, language: CodeLanguage) -> Dict[str, Any]:
        """Check code against best practice rules"""

        violations = []

        for rule_name, rule_check in self.quality_rules.items():
            if rule_check(code):
                violations.append(rule_name)

        return {
            "violations": violations,
            "total_violations": len(violations),
            "compliance_score": round((len(self.quality_rules) - len(violations)) / len(self.quality_rules) * 100, 1)
        }

    def _extract_dependencies(self, code: str, language: CodeLanguage) -> List[Dict[str, Any]]:
        """Extract dependencies from code"""

        dependencies = []

        if language == CodeLanguage.PYTHON:
            # Extract Python imports
            import_patterns = [
                r'^\s*import\s+(\w+)',
                r'^\s*from\s+(\w+)\s+import'
            ]
            for pattern in import_patterns:
                matches = re.finditer(pattern, code, re.MULTILINE)
                for match in matches:
                    pkg_name = match.group(1)
                    dependencies.append({
                        "name": pkg_name,
                        "language": language.value,
                        "type": "import",
                        "internal": pkg_name.startswith('.')
                    })

        elif language == CodeLanguage.JAVASCRIPT:
            # Extract JavaScript/Node imports
            import_patterns = [
                r'require\(["\']([^"\']+)["\']\)',
                r'from\s+["\']([^"\']+)["\']'
            ]
            for pattern in import_patterns:
                matches = re.finditer(pattern, code)
                for match in matches:
                    pkg_name = match.group(1)
                    dependencies.append({
                        "name": pkg_name,
                        "language": language.value,
                        "type": "require/import",
                        "internal": pkg_name.startswith('.')
                    })

        # Remove duplicates
        seen = set()
        unique_deps = []
        for dep in dependencies:
            key = dep["name"]
            if key not in seen:
                seen.add(key)
                unique_deps.append(dep)

        return unique_deps

    def _assess_complexity(self, code: str, language: CodeLanguage) -> Dict[str, Any]:
        """Assess code complexity"""

        # Count control flow statements
        control_keywords = ['if', 'else', 'for', 'while', 'try', 'except', 'case', 'switch']
        keyword_count = sum(len(re.findall(rf'\b{kw}\b', code, re.IGNORECASE)) for kw in control_keywords)

        # Simple cyclomatic complexity estimate
        cyclomatic = keyword_count + 1

        # Count functions/methods
        func_pattern = r'def\s+\w+|function\s+\w+|\w+\s*\(\s*\)\s*\{'
        function_count = len(re.findall(func_pattern, code))

        return {
            "cyclomatic_complexity": cyclomatic,
            "function_count": function_count,
            "control_flow_statements": keyword_count,
            "complexity_level": "low" if cyclomatic < 10 else "medium" if cyclomatic < 20 else "high"
        }

    def _assess_dependency_risk(self, dependencies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess risk from dependencies"""

        external_deps = [d for d in dependencies if not d.get("internal", False)]
        internal_deps = [d for d in dependencies if d.get("internal", False)]

        # Known risky packages (example list)
        risky_packages = {
            "eval": "high",
            "exec": "critical",
            "pickle": "medium",
            "subprocess": "medium"
        }

        risks = []
        for dep in external_deps:
            if dep["name"] in risky_packages:
                risks.append({
                    "package": dep["name"],
                    "risk": risky_packages[dep["name"]],
                    "reason": f"{dep['name']} can execute arbitrary code"
                })

        return {
            "total_dependencies": len(dependencies),
            "external_dependencies": len(external_deps),
            "internal_dependencies": len(internal_deps),
            "risky_packages": risks,
            "risk_level": "critical" if risks else "low"
        }

    def _determine_overall_result(self, results: Dict[str, Any]) -> str:
        """Determine overall validation result"""

        validations = results["validations"]

        if not validations["syntax"]["is_valid"]:
            return "invalid"
        if validations["security"]["total_issues"] > 5:
            return "warning"
        if validations["quality"]["status"] == "warning":
            return "warning"

        return "valid"

    def _is_deployable(self, results: Dict[str, Any]) -> bool:
        """Determine if code is deployable"""

        validations = results["validations"]

        # Must have valid syntax
        if not validations["syntax"]["is_valid"]:
            return False

        # Critical security issues block deployment
        if validations["security"]["critical"] > 0:
            return False

        # More than 5 high severity issues block deployment
        if validations["security"]["high"] > 5:
            return False

        return True

    def _init_security_patterns(self) -> Dict[str, List[str]]:
        """Initialize security pattern checks"""

        return {
            "sql_injection": [
                r'execute\s*\(\s*["\'].*\{',
                r'query\s*=\s*["\'].*\+.*["\']'
            ],
            "hardcoded_credentials": [
                r'password\s*=\s*["\'][^"\']*["\']',
                r'api_key\s*=\s*["\'][^"\']*["\']',
                r'secret\s*=\s*["\'][^"\']*["\']'
            ],
            "unsafe_deserialization": [
                r'pickle\.load',
                r'yaml\.load',
                r'json\.loads.*eval'
            ],
            "command_injection": [
                r'os\.system\s*\(',
                r'subprocess\.call\s*\(',
                r'exec\s*\('
            ],
            "path_traversal": [
                r'open\s*\(\s*["\'].*\.\.',
                r'readFile\s*\(\s*.*\.\.'
            ]
        }

    def _init_quality_rules(self) -> Dict[str, callable]:
        """Initialize code quality rules"""

        return {
            "imports_at_top": lambda code: not code.startswith('import') and 'import' in code,
            "no_trailing_whitespace": lambda code: any(l.endswith(' ') or l.endswith('\t') for l in code.split('\n')),
            "proper_indentation": lambda code: True  # Simplified
        }
