"""Testes do módulo de validação Tier 1."""
from app.core.validation import detect_language, validate_code


def test_python_undefined_name_is_reported():
    result = validate_code("x = 1\nundef", "python")
    assert result.supported is True
    assert result.valid is False
    assert any("undef" in i.message for i in result.issues)


def test_python_valid_code_has_no_issues():
    result = validate_code("x = 1\nprint(x)\n", "python")
    assert result.valid is True


def test_python_unused_import_is_warning_not_error():
    result = validate_code("import os\nx = 1\n", "python")
    assert result.supported is True
    assert result.valid is True  # só warning, não bloqueia
    assert any(i.severity == "warning" for i in result.issues)


def test_javascript_syntax_error_is_reported():
    result = validate_code("function ( { return 1 }", "javascript")
    assert result.valid is False
    assert result.issues[0].line >= 1


def test_json_invalid_returns_line_column():
    result = validate_code('{"a": 1,}', "json")
    assert result.valid is False
    assert result.issues[0].line >= 1
    assert result.issues[0].column >= 1


def test_yaml_invalid_is_reported():
    result = validate_code("a: b\n  c: d", "yaml")
    assert result.valid is False


def test_toml_valid_passes():
    result = validate_code('[section]\nkey = "value"', "toml")
    assert result.valid is True


def test_unsupported_language_returns_supported_false():
    result = validate_code("package main\nfunc main() {}", "go")
    assert result.supported is False
    assert result.issues == []


def test_detect_language_by_path():
    assert detect_language("app/main.py", None) == "python"
    assert detect_language("src/App.tsx", None) == "typescript"
    assert detect_language("package.json", None) == "json"
    assert detect_language("unknown", None) is None
