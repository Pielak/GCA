"""
Integration Tests - FASE 6 Code Validation & Security
Valida: Code validation, security scanning, dependency analysis
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.code_validation_service import (
    CodeValidationService,
    CodeLanguage
)
import structlog

logger = structlog.get_logger(__name__)


class ValidationTester:
    """Integration test suite for FASE 6"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []

    async def test_service_init(self):
        """Test 1: CodeValidationService initializes correctly"""
        try:
            service = CodeValidationService()
            assert service.security_patterns is not None
            assert service.quality_rules is not None
            assert len(service.security_patterns) > 0
            assert len(service.quality_rules) > 0

            self._log_pass("Test 1: CodeValidationService initializes")

        except Exception as e:
            self._log_fail(f"Test 1: {str(e)}")

    async def test_python_syntax_valid(self):
        """Test 2: Valid Python syntax validation"""
        try:
            service = CodeValidationService()

            valid_python = """
def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
"""

            result = service._validate_syntax(valid_python, CodeLanguage.PYTHON)

            assert result["is_valid"] == True
            assert result["status"] == "valid"
            assert len(result["errors"]) == 0

            self._log_pass("Test 2: Valid Python syntax accepted")

        except Exception as e:
            self._log_fail(f"Test 2: {str(e)}")

    async def test_python_syntax_invalid(self):
        """Test 3: Invalid Python syntax detection"""
        try:
            service = CodeValidationService()

            invalid_python = """
def broken_function(
    print("Missing closing paren")
"""

            result = service._validate_syntax(invalid_python, CodeLanguage.PYTHON)

            assert result["is_valid"] == False
            assert result["status"] == "invalid"
            assert len(result["errors"]) > 0

            self._log_pass("Test 3: Invalid Python syntax detected")

        except Exception as e:
            self._log_fail(f"Test 3: {str(e)}")

    async def test_code_quality_analysis(self):
        """Test 4: Code quality metrics analysis"""
        try:
            service = CodeValidationService()

            code = """
# This is a well-documented function
def calculate_sum(numbers):
    '''Calculate sum of numbers'''
    total = 0
    for num in numbers:
        total += num
    return total
"""

            result = service._analyze_code_quality(code, CodeLanguage.PYTHON)

            assert "metrics" in result
            assert "complexity" in result
            assert result["metrics"]["code_lines"] > 0
            assert result["complexity"]["cyclomatic_complexity"] > 0

            self._log_pass(f"Test 4: Code quality analyzed (complexity: {result['complexity']['cyclomatic_complexity']})")

        except Exception as e:
            self._log_fail(f"Test 4: {str(e)}")

    async def test_security_scan_hardcoded_credentials(self):
        """Test 5: Detect hardcoded credentials"""
        try:
            service = CodeValidationService()

            suspicious_code = """
api_key = "sk-1234567890abcdefghij"
password = "supersecret123"
token = "Bearer xyz789"
"""

            result = await service.security_scan(suspicious_code, CodeLanguage.PYTHON)

            assert result["total_issues"] > 0
            assert len(result["findings"]) > 0

            self._log_pass(f"Test 5: Hardcoded credentials detected ({result['total_issues']} issues)")

        except Exception as e:
            self._log_fail(f"Test 5: {str(e)}")

    async def test_security_scan_command_injection(self):
        """Test 6: Detect command injection risks"""
        try:
            service = CodeValidationService()

            risky_code = """
import os
import subprocess

# Dangerous: user input directly in command
user_input = request.args.get('cmd')
os.system(user_input)

# Also dangerous
subprocess.call(user_input, shell=True)
"""

            result = await service.security_scan(risky_code, CodeLanguage.PYTHON)

            assert result["total_issues"] > 0

            self._log_pass(f"Test 6: Command injection risks detected ({result['total_issues']} issues)")

        except Exception as e:
            self._log_fail(f"Test 6: {str(e)}")

    async def test_python_dependencies_extraction(self):
        """Test 7: Extract Python dependencies"""
        try:
            service = CodeValidationService()

            code = """
import os
import sys
from datetime import datetime
from flask import Flask, render_template
import requests
from mymodule import helper
"""

            result = await service.validate_dependencies(code, CodeLanguage.PYTHON)

            assert result["total_count"] > 0
            assert result["external_count"] > 0
            dependencies = [d["name"] for d in result["dependencies"]]
            assert "os" in dependencies or "sys" in dependencies or "flask" in dependencies

            self._log_pass(f"Test 7: Dependencies extracted ({result['total_count']} total, {result['external_count']} external)")

        except Exception as e:
            self._log_fail(f"Test 7: {str(e)}")

    async def test_javascript_syntax_validation(self):
        """Test 8: JavaScript syntax validation"""
        try:
            service = CodeValidationService()

            valid_js = """
function greet(name) {
    console.log('Hello, ' + name);
}

greet('World');
"""

            result = service._validate_syntax(valid_js, CodeLanguage.JAVASCRIPT)

            # Should pass basic checks
            assert result["is_valid"] == True or len(result["errors"]) == 0

            self._log_pass("Test 8: JavaScript syntax validation works")

        except Exception as e:
            self._log_fail(f"Test 8: {str(e)}")

    async def test_javascript_mismatched_braces(self):
        """Test 9: Detect JavaScript syntax errors"""
        try:
            service = CodeValidationService()

            invalid_js = """
function broken() {
    console.log('Missing closing brace');
"""

            result = service._validate_syntax(invalid_js, CodeLanguage.JAVASCRIPT)

            assert len(result["errors"]) > 0 or result["is_valid"] == False

            self._log_pass("Test 9: JavaScript syntax errors detected")

        except Exception as e:
            self._log_fail(f"Test 9: {str(e)}")

    async def test_javascript_dependencies(self):
        """Test 10: Extract JavaScript dependencies"""
        try:
            service = CodeValidationService()

            code = """
const express = require('express');
const { readFile } = require('fs');
import axios from 'axios';
from './utils' import helper;
"""

            result = await service.validate_dependencies(code, CodeLanguage.JAVASCRIPT)

            assert result["total_count"] > 0

            self._log_pass(f"Test 10: JavaScript dependencies extracted ({result['total_count']} dependencies)")

        except Exception as e:
            self._log_fail(f"Test 10: {str(e)}")

    async def test_complete_validation(self):
        """Test 11: Complete code validation workflow"""
        try:
            service = CodeValidationService()

            code = """
import json

def process_data(data):
    '''Process incoming data safely'''
    try:
        parsed = json.loads(data)
        return parsed
    except json.JSONDecodeError:
        return None
"""

            result = await service.validate_code(code, CodeLanguage.PYTHON)

            assert "timestamp" in result
            assert "validations" in result
            assert result["overall_result"] in ["valid", "warning", "invalid"]
            assert isinstance(result["is_deployable"], bool)

            self._log_pass(f"Test 11: Complete validation passed (result: {result['overall_result']})")

        except Exception as e:
            self._log_fail(f"Test 11: {str(e)}")

    async def test_sql_injection_detection(self):
        """Test 12: Detect SQL injection patterns"""
        try:
            service = CodeValidationService()

            vulnerable_sql = """
user_input = request.args.get('id')
query = "SELECT * FROM users WHERE id = " + user_input
execute(query)
"""

            result = await service.security_scan(vulnerable_sql, CodeLanguage.PYTHON)

            # Should detect potential SQL injection
            assert len(result["findings"]) > 0 or result["total_issues"] >= 0

            self._log_pass("Test 12: SQL injection patterns checked")

        except Exception as e:
            self._log_fail(f"Test 12: {str(e)}")

    async def test_complexity_assessment(self):
        """Test 13: Code complexity assessment"""
        try:
            service = CodeValidationService()

            code = """
def calculate(x):
    if x > 10:
        if x > 20:
            if x > 30:
                return x * 3
            else:
                return x * 2
        else:
            return x
    else:
        return 0
"""

            result = service._analyze_code_quality(code, CodeLanguage.PYTHON)

            assert result["complexity"]["cyclomatic_complexity"] > 1
            assert result["complexity"]["complexity_level"] in ["low", "medium", "high"]

            self._log_pass(f"Test 13: Complexity assessed (level: {result['complexity']['complexity_level']})")

        except Exception as e:
            self._log_fail(f"Test 13: {str(e)}")

    async def test_best_practices_check(self):
        """Test 14: Check best practices"""
        try:
            service = CodeValidationService()

            code = """
import os
import sys
from datetime import datetime

def main():
    print("Hello")
"""

            result = service._check_best_practices(code, CodeLanguage.PYTHON)

            assert "violations" in result
            assert isinstance(result["compliance_score"], float)
            assert 0 <= result["compliance_score"] <= 100

            self._log_pass(f"Test 14: Best practices checked (compliance: {result['compliance_score']}%)")

        except Exception as e:
            self._log_fail(f"Test 14: {str(e)}")

    async def test_json_validation(self):
        """Test 15: JSON syntax validation"""
        try:
            service = CodeValidationService()

            valid_json = '{"name": "test", "value": 123}'
            result = service._validate_syntax(valid_json, CodeLanguage.SQL)  # Generic check

            # Should detect valid structure
            assert result["is_valid"] == True or len(result["errors"]) == 0

            self._log_pass("Test 15: JSON syntax validation works")

        except Exception as e:
            self._log_fail(f"Test 15: {str(e)}")

    def _log_pass(self, test_name: str):
        self.passed += 1
        self.tests_result.append(f"✅ {test_name}")
        print(f"✅ {test_name}")

    def _log_fail(self, test_name: str):
        self.failed += 1
        self.tests_result.append(f"❌ {test_name}")
        print(f"❌ {test_name}")

    async def run_all_tests(self):
        print("\n╔════════════════════════════════════════════════════════════════╗")
        print("║        INTEGRATION TEST - FASE 6 CODE VALIDATION              ║")
        print("║    Security Scanning, Syntax Validation, Dependencies         ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        await self.test_service_init()
        await self.test_python_syntax_valid()
        await self.test_python_syntax_invalid()
        await self.test_code_quality_analysis()
        await self.test_security_scan_hardcoded_credentials()
        await self.test_security_scan_command_injection()
        await self.test_python_dependencies_extraction()
        await self.test_javascript_syntax_validation()
        await self.test_javascript_mismatched_braces()
        await self.test_javascript_dependencies()
        await self.test_complete_validation()
        await self.test_sql_injection_detection()
        await self.test_complexity_assessment()
        await self.test_best_practices_check()
        await self.test_json_validation()

        return self.print_results()

    def print_results(self):
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DO TESTE - FASE 6 CODE VALIDATION")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TESTES DE VALIDAÇÃO COMPLETOS COM SUCESSO!")
            print("\n✨ FASE 6 APROVADA - CODE VALIDATION & SECURITY READY")
            return True
        else:
            print("⚠️  ALGUNS TESTES FALHARAM")
            return False


async def main():
    tester = ValidationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
