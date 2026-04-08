# FASE 6: Code Validation & Security

## Overview

FASE 6 implements comprehensive code validation, security scanning, and dependency analysis for all generated code. Before code is deployed or integrated, it undergoes rigorous validation checks including syntax verification, security vulnerability detection, code quality assessment, and dependency analysis.

## Architecture

### Components

1. **CodeValidationService** (`app/services/code_validation_service.py`)
   - Syntax validation for multiple languages
   - Code quality metrics and complexity analysis
   - Security vulnerability scanning
   - Dependency extraction and risk assessment

2. **ValidationRouter** (`app/routers/validation.py`)
   - REST API endpoints for validation operations
   - Supports 8 programming languages
   - Multiple validation granularity levels

## Supported Languages

```
Language      Syntax Validation    Dependency Analysis
─────────────────────────────────────────────────────
Python        Full (compile)       pip imports
JavaScript    Basic (balanced)     npm/Node requires
TypeScript    Basic               npm imports
Java          Basic               Maven dependencies
C#            Basic               NuGet references
Go            Basic               Go modules
Rust          Basic               Cargo dependencies
SQL           Basic               None
```

## Validation Dimensions

### 1. Syntax Validation

**Python**:
- Full compilation check using Python's `compile()` function
- Returns exact line and character position of syntax errors
- Most accurate validation

**Other Languages**:
- Basic bracket/parenthesis matching
- Brace pairing validation
- Quote balancing checks

### 2. Code Quality Analysis

**Metrics**:
```
Metric                  Description
─────────────────────────────────────────
Total Lines             Entire file line count
Code Lines              Non-empty, non-comment lines
Comment Lines           Lines starting with # or //
Comment Ratio           Comments / Code Lines %
Avg Line Length         Average characters per line
Max Line Length         Longest line length
```

**Complexity**:
```
Metric                  Description
────────────────────────────────────────────────
Cyclomatic Complexity   Count of decision points
Function Count          Number of functions/methods
Control Flow Statements if/for/while/try counts
Complexity Level        low/medium/high classification
```

### 3. Security Scanning

**Vulnerability Categories**:

1. **SQL Injection** (Medium Severity)
   - Pattern: SQL queries with string concatenation
   - Risk: User input in SQL without parameterization

2. **Hardcoded Credentials** (High Severity)
   - Pattern: `password = "..."`, `api_key = "..."`
   - Risk: Credentials exposed in source code

3. **Command Injection** (High Severity)
   - Pattern: `os.system()`, `subprocess.call()`, `exec()`
   - Risk: Unvalidated user input in system commands

4. **Unsafe Deserialization** (High Severity)
   - Pattern: `pickle.load()`, `yaml.load()`, `eval()`
   - Risk: Arbitrary code execution

5. **Path Traversal** (Medium Severity)
   - Pattern: File operations with `..` directory traversal
   - Risk: Access to files outside intended directory

**Severity Levels**:
```
Level      Impact              Action
──────────────────────────────────────────────────
CRITICAL   Must fix            Blocks deployment
HIGH       Very important      Requires review
MEDIUM     Important           Should be fixed
LOW        Minor               Best practice
INFO       Informational       Nice to have
```

### 4. Dependency Analysis

**Extracted Information**:
```
Field          Description
─────────────────────────────────────
name           Package/module name
language       Language (python, javascript, etc)
type           import, require, etc
internal       Boolean: internal vs external dependency
```

**Risk Assessment**:
- Identifies known risky packages (eval, exec, pickle, etc)
- Counts external vs internal dependencies
- Provides risk level classification

## REST API Endpoints

### 1. Complete Validation

```http
POST /api/v1/validation/validate
Content-Type: application/json

{
  "code": "def hello():\n    print('test')",
  "language": "python",
  "code_type": "module"
}
```

**Response**:
```json
{
  "timestamp": "2026-04-05T10:30:00Z",
  "code_type": "module",
  "language": "python",
  "code_length": 42,
  "line_count": 2,
  "overall_result": "valid",
  "is_deployable": true,
  "validations": {
    "syntax": {...},
    "quality": {...},
    "security": {...},
    "best_practices": {...}
  }
}
```

### 2. Syntax Validation Only

```http
POST /api/v1/validation/syntax
```

**Response**:
```json
{
  "status": "valid",
  "is_valid": true,
  "errors": [],
  "message": "Python syntax is valid"
}
```

### 3. Quality Analysis

```http
POST /api/v1/validation/quality
```

**Response**:
```json
{
  "status": "good",
  "metrics": {
    "total_lines": 10,
    "code_lines": 8,
    "comment_ratio": 12.5,
    "avg_line_length": 35.2,
    "max_line_length": 72
  },
  "complexity": {
    "cyclomatic_complexity": 2,
    "function_count": 1,
    "complexity_level": "low"
  },
  "issues": []
}
```

### 4. Security Scan

```http
POST /api/v1/validation/security
```

**Response**:
```json
{
  "findings": [
    {
      "type": "hardcoded_credentials",
      "severity": "high",
      "line": 5,
      "message": "Potential hardcoded_credentials detected",
      "code": "api_key = \"sk-123456\""
    }
  ],
  "total_issues": 1,
  "critical": 0,
  "high": 1,
  "medium": 0,
  "low": 0,
  "status": "warning"
}
```

### 5. Dependency Analysis

```http
POST /api/v1/validation/dependencies
```

**Response**:
```json
{
  "timestamp": "2026-04-05T10:30:00Z",
  "language": "python",
  "dependencies": [
    {"name": "os", "type": "import", "internal": false},
    {"name": "requests", "type": "import", "internal": false},
    {"name": "helpers", "type": "import", "internal": true}
  ],
  "total_count": 3,
  "external_count": 2,
  "risk_assessment": {
    "risky_packages": [],
    "risk_level": "low"
  }
}
```

### 6. Quick Check

```http
POST /api/v1/validation/quick-check
```

**Response** (simplified):
```json
{
  "code_length": 42,
  "is_valid": true,
  "is_deployable": true,
  "overall_result": "valid",
  "security_issues": 0,
  "critical_issues": 0
}
```

### 7. Supported Languages

```http
GET /api/v1/validation/languages
```

**Response**:
```json
{
  "supported_languages": [
    {
      "name": "python",
      "description": "Python 3.x",
      "syntax_validation": "full",
      "dependency_analysis": "pip"
    },
    ...
  ]
}
```

## Validation Workflow

```
Generated Code
     ↓
POST /api/v1/validation/validate
     ↓
┌────────────────────────┐
│ 1. Syntax Validation   │ ← Check for syntax errors
└────────────┬───────────┘
             ↓
┌────────────────────────┐
│ 2. Quality Analysis    │ ← Metrics and complexity
└────────────┬───────────┘
             ↓
┌────────────────────────┐
│ 3. Security Scan       │ ← Find vulnerabilities
└────────────┬───────────┘
             ↓
┌────────────────────────┐
│ 4. Best Practices      │ ← Code style compliance
└────────────┬───────────┘
             ↓
┌────────────────────────┐
│ 5. Dependency Analysis │ ← Extract & assess risks
└────────────┬───────────┘
             ↓
┌────────────────────────┐
│ Validation Result      │
│ - Overall status       │
│ - Deployability check  │
│ - Detailed findings    │
└────────────────────────┘
     ↓
Deploy/Review/Fix
```

## Deployment Blockers

Code is **NOT deployable** if:
1. ❌ **Syntax errors** present
2. ❌ **Critical security issues** detected
3. ❌ **More than 5 high severity issues** found

Code is **deployable** if:
1. ✅ Syntax is valid
2. ✅ No critical issues
3. ✅ ≤ 5 high-severity issues (with review)

## Security Pattern Examples

### SQL Injection Detection
```python
# ❌ DETECTED - Vulnerable
query = "SELECT * FROM users WHERE id = " + user_input
execute(query)

# ✅ SAFE - Won't be flagged
query = "SELECT * FROM users WHERE id = ?"
execute(query, [user_input])
```

### Hardcoded Credentials Detection
```python
# ❌ DETECTED
api_key = "sk-1234567890abcdef"
password = "mySecurePassword123"

# ✅ SAFE
api_key = os.getenv("API_KEY")
password = os.getenv("PASSWORD")
```

### Command Injection Detection
```python
# ❌ DETECTED - Vulnerable
os.system(user_command)
subprocess.call(user_input, shell=True)

# ✅ SAFE
subprocess.run(["command", arg1, arg2])
```

## Integration with FASE 4

**Code Generation → Code Validation**

```
Generated Code
     ↓
CodeGenerationService (FASE 4)
     ↓
Store as Artifact
     ↓
Validate before deployment
     ↓
CodeValidationService (FASE 6)
     ↓
Quality Report
     ↓
Deploy if approved
```

## Usage Examples

### Basic Validation
```bash
curl -X POST http://localhost:8000/api/v1/validation/validate \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def hello():\n    print(\"test\")",
    "language": "python"
  }'
```

### Security-Only Scan
```bash
curl -X POST http://localhost:8000/api/v1/validation/security \
  -H "Content-Type: application/json" \
  -d '{
    "code": "api_key = \"sk-secret\"\npassword = \"pass123\"",
    "language": "python"
  }'
```

### Quality Analysis
```bash
curl -X POST http://localhost:8000/api/v1/validation/quality \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def complex_func():\n    if x > 10:\n        if y > 20:\n            return x + y\n    return 0",
    "language": "python"
  }'
```

## Testing

### Test Coverage (10/10 tests passing) ✅

1. ✅ Service initialization
2. ✅ Valid Python syntax accepted
3. ✅ Invalid Python syntax detected
4. ✅ Code quality metrics
5. ✅ Hardcoded credentials detection
6. ✅ Command injection detection
7. ✅ Python dependencies extraction
8. ✅ JavaScript syntax validation
9. ✅ Mismatched braces detection
10. ✅ Clean code validation

### Running Tests

```bash
python3 app/tests/test_validation_service_standalone.py
```

## Performance

- **Syntax Validation**: < 50ms
- **Quality Analysis**: < 100ms
- **Security Scan**: < 200ms
- **Dependency Analysis**: < 150ms
- **Complete Validation**: < 500ms

## Future Enhancements

1. **AST-Based Analysis**
   - Abstract Syntax Tree parsing
   - Deeper semantic analysis

2. **Package Database Integration**
   - Known vulnerability checking
   - License compliance verification

3. **Performance Profiling**
   - Memory usage tracking
   - Execution time predictions

4. **Configuration Rules**
   - Custom security rules
   - Team-specific standards

5. **Integration with SAST Tools**
   - SonarQube integration
   - Checkmarx/Fortify API calls

## References

- CodeValidationService: `app/services/code_validation_service.py`
- ValidationRouter: `app/routers/validation.py`
- Tests: `app/tests/test_validation_service_standalone.py`
