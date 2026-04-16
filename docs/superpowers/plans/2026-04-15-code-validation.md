# Code Validation (Tier 1) — Plano de Implementação

> **Para workers agênticos:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).

**Goal:** Validar o código que o usuário edita no CodeGeneratorPage ANTES de salvar no Git. Bloquear save se houver erro, mostrar marker vermelho no Monaco Editor.

**Architecture:** Módulo `app.core.validation` expõe `validate_code(code, language)` com roteamento por extensão/language. Python usa `pyflakes` (syntax + imports), JS usa `esprima` (parser puro Python), JSON/TOML usam stdlib, YAML usa PyYAML (já presente). TS é tratado como JS (esprima aceita boa parte da sintaxe). Linguagens não suportadas retornam `supported=false` com mensagem informativa — UI não bloqueia save neste caso. Frontend substitui `<textarea>` por `@monaco-editor/react`, dispara validate ao clicar "Revisar e Salvar", popula markers com `monaco.editor.setModelMarkers`.

**Tech Stack:** FastAPI + pyflakes + esprima-python, React 18 + @monaco-editor/react (Monaco carregado via CDN).

---

## File Structure

**Backend — criar:**
- `backend/app/core/validation.py` — lógica de validação multi-linguagem + dataclass `ValidationIssue`
- `backend/app/tests/test_code_validation.py` — 5 testes (1 por linguagem Tier 1 + supported=false)

**Backend — modificar:**
- `backend/requirements.txt` — adicionar `pyflakes` e `esprima`
- `backend/app/routers/code_generation.py` — adicionar endpoint `POST /validate`

**Frontend — modificar:**
- `frontend/package.json` — adicionar `@monaco-editor/react`
- `frontend/src/pages/projects/CodeGeneratorPage.tsx` — substituir textarea por Monaco; adicionar estado `validationErrors`; implementar `handleReviewAndSave`

---

### Task 1: Backend — módulo de validação + dependências

**Files:**
- Create: `backend/app/core/validation.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Adicionar dependências**

Abra `/home/luiz/GCA/backend/requirements.txt` e adicione ao final (antes de qualquer linha em branco final):

```
pyflakes==3.2.0
esprima==4.0.1
```

- [ ] **Step 2: Criar módulo de validação**

Conteúdo exato de `/home/luiz/GCA/backend/app/core/validation.py`:

```python
"""Validação de código multi-linguagem (Tier 1).

Expõe `validate_code(code, language)` que retorna uma lista de `ValidationIssue`.
Cada issue tem linha (1-based), coluna, mensagem e severidade (error|warning).
Linguagens não suportadas retornam `supported=False` no resultado.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import io
import json
import tomllib
from typing import List, Optional


@dataclass
class ValidationIssue:
    """Uma ocorrência de problema encontrada no código."""

    line: int
    column: int
    message: str
    severity: str  # "error" | "warning"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationResult:
    """Resultado da validação de um bloco de código."""

    supported: bool
    language: str
    issues: List[ValidationIssue]

    @property
    def valid(self) -> bool:
        return self.supported and not any(i.severity == "error" for i in self.issues)

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "language": self.language,
            "valid": self.valid,
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Python — pyflakes
# ---------------------------------------------------------------------------

def _validate_python(code: str) -> List[ValidationIssue]:
    """Executa pyflakes no código e traduz reporter para ValidationIssue."""
    from pyflakes.api import check
    from pyflakes.reporter import Reporter

    warn_buf = io.StringIO()
    err_buf = io.StringIO()
    reporter = Reporter(warn_buf, err_buf)
    check(code, filename="<input>", reporter=reporter)

    issues: List[ValidationIssue] = []
    for raw in err_buf.getvalue().splitlines():
        # formato: "<input>:LINE:COL: mensagem"
        parts = raw.split(":", 3)
        if len(parts) >= 4:
            try:
                line = int(parts[1])
                col = int(parts[2])
                message = parts[3].strip()
            except ValueError:
                continue
            issues.append(ValidationIssue(line=line, column=col, message=message, severity="error"))
    for raw in warn_buf.getvalue().splitlines():
        parts = raw.split(":", 3)
        if len(parts) >= 3:
            try:
                line = int(parts[1])
                message_tail = parts[-1].strip()
            except ValueError:
                continue
            issues.append(ValidationIssue(line=line, column=1, message=message_tail, severity="warning"))
    return issues


# ---------------------------------------------------------------------------
# JavaScript / TypeScript — esprima
# ---------------------------------------------------------------------------

def _validate_js_like(code: str) -> List[ValidationIssue]:
    """Parse JS/TS com esprima. TS com sintaxe só-de-tipos pode não parsear."""
    import esprima

    try:
        esprima.parseScript(code, tolerant=False, loc=True)
        return []
    except esprima.Error as exc:
        line = getattr(exc, "lineNumber", 1) or 1
        col = getattr(exc, "column", 1) or 1
        msg = str(exc)
        return [ValidationIssue(line=line, column=col, message=msg, severity="error")]


# ---------------------------------------------------------------------------
# JSON / YAML / TOML
# ---------------------------------------------------------------------------

def _validate_json(code: str) -> List[ValidationIssue]:
    try:
        json.loads(code)
        return []
    except json.JSONDecodeError as exc:
        return [ValidationIssue(line=exc.lineno, column=exc.colno, message=exc.msg, severity="error")]


def _validate_yaml(code: str) -> List[ValidationIssue]:
    import yaml

    try:
        yaml.safe_load(code)
        return []
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (mark.line + 1) if mark else 1
        col = (mark.column + 1) if mark else 1
        return [ValidationIssue(line=line, column=col, message=str(exc), severity="error")]


def _validate_toml(code: str) -> List[ValidationIssue]:
    try:
        tomllib.loads(code)
        return []
    except tomllib.TOMLDecodeError as exc:
        # tomllib não expõe line/col em todas versões — defaults seguros
        return [ValidationIssue(line=1, column=1, message=str(exc), severity="error")]


# ---------------------------------------------------------------------------
# Roteamento
# ---------------------------------------------------------------------------

_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


def detect_language(path: Optional[str], explicit: Optional[str] = None) -> Optional[str]:
    """Retorna 'python'|'javascript'|'typescript'|'json'|'yaml'|'toml' ou None."""
    if explicit:
        return explicit.lower()
    if not path:
        return None
    for ext, lang in _LANGUAGE_BY_EXT.items():
        if path.lower().endswith(ext):
            return lang
    return None


def validate_code(code: str, language: Optional[str], path: Optional[str] = None) -> ValidationResult:
    """Valida `code`. `language` explícito sobrepõe inferência por `path`."""
    lang = detect_language(path, language)
    if not lang:
        return ValidationResult(supported=False, language="unknown", issues=[])

    if lang == "python":
        return ValidationResult(supported=True, language=lang, issues=_validate_python(code))
    if lang in ("javascript", "typescript"):
        return ValidationResult(supported=True, language=lang, issues=_validate_js_like(code))
    if lang == "json":
        return ValidationResult(supported=True, language=lang, issues=_validate_json(code))
    if lang == "yaml":
        return ValidationResult(supported=True, language=lang, issues=_validate_yaml(code))
    if lang == "toml":
        return ValidationResult(supported=True, language=lang, issues=_validate_toml(code))

    return ValidationResult(supported=False, language=lang, issues=[])
```

- [ ] **Step 3: Rebuild backend com as novas dependências**

```bash
cd /home/luiz/GCA && docker compose build backend && docker compose up -d backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done
docker compose logs backend --tail 20 2>&1 | grep -iE "error|traceback" | head -5 || echo "OK"
docker compose exec -T backend python -c "from app.core.validation import validate_code; r=validate_code('x = 1\nundef_var','python'); print('issues:', [i.message for i in r.issues])"
```

Esperado: `issues: ["undefined name 'undef_var'"]` ou mensagem similar do pyflakes.

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add backend/requirements.txt backend/app/core/validation.py
git commit -m "feat(validation): módulo Tier 1 — Python/JS/TS/JSON/YAML/TOML via pyflakes+esprima+stdlib

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Endpoint REST `/code-generation/validate`

**Files:**
- Modify: `backend/app/routers/code_generation.py`

- [ ] **Step 1: Adicionar pydantic models e endpoint**

No topo do arquivo, perto dos outros modelos (ex: logo depois da definição de `ScaffoldResponse`), adicione:

```python
class ValidateCodeRequest(BaseModel):
    code: str = Field(..., description="Conteúdo do arquivo a validar")
    path: Optional[str] = Field(None, description="Caminho do arquivo (para inferir linguagem)")
    language: Optional[str] = Field(None, description="Sobrescrita explícita da linguagem")


class ValidateCodeIssue(BaseModel):
    line: int
    column: int
    message: str
    severity: str


class ValidateCodeResponse(BaseModel):
    supported: bool
    language: str
    valid: bool
    issues: List[ValidateCodeIssue]
```

No final do arquivo, adicione o endpoint:

```python
@router.post("/validate", response_model=ValidateCodeResponse, summary="Validar código antes de salvar")
async def validate_code_endpoint(request: ValidateCodeRequest) -> ValidateCodeResponse:
    """Valida sintaxe/lint do código. Retorna lista de issues com linha/coluna para markers."""
    from app.core.validation import validate_code

    result = validate_code(request.code, request.language, request.path)
    return ValidateCodeResponse(
        supported=result.supported,
        language=result.language,
        valid=result.valid,
        issues=[ValidateCodeIssue(**i.to_dict()) for i in result.issues],
    )
```

Se `List` não estiver importado ainda no topo do arquivo, adicionar `List` ao `from typing import ...`.

- [ ] **Step 2: Smoke test**

```bash
cd /home/luiz/GCA && docker compose restart backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://localhost:8000/api/v1/code-generation/validate \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"code":"def f(:\n  pass","language":"python"}' | python3 -m json.tool
```

Esperado: JSON com `valid: false` e pelo menos 1 issue com `line: 1`.

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/routers/code_generation.py
git commit -m "feat(validation): endpoint POST /code-generation/validate

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Testes de validação

**Files:**
- Create: `backend/app/tests/test_code_validation.py`

- [ ] **Step 1: Escrever testes**

Conteúdo exato de `/home/luiz/GCA/backend/app/tests/test_code_validation.py`:

```python
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
```

- [ ] **Step 2: Rodar**

```bash
cd /home/luiz/GCA && docker compose exec -T backend python -m pytest app/tests/test_code_validation.py -v 2>&1 | tail -15
```

Esperado: 8 testes passando. Se algum falhar, ajuste a mensagem esperada conforme a versão exata do linter.

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/tests/test_code_validation.py
git commit -m "test(validation): cobertura Tier 1 (python/js/json/yaml/toml/unsupported)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Frontend — Monaco Editor + dependência

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Instalar @monaco-editor/react**

```bash
cd /home/luiz/GCA/frontend && npm install @monaco-editor/react --save
cat package.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('monaco:', d['dependencies'].get('@monaco-editor/react'))"
```

Esperado: versão impressa (ex: `4.x.x`).

- [ ] **Step 2: Rebuild container frontend**

```bash
cd /home/luiz/GCA && docker compose restart frontend
until docker compose logs frontend --tail 5 2>&1 | grep -q "Local:  "; do sleep 3; done
docker compose logs frontend --tail 10 2>&1 | grep -iE "error|failed" | head -3 || echo "BUILD OK"
```

Esperado: "BUILD OK" (ou nenhum erro). Se houver erro de tipos durante o build, resolver antes de prosseguir.

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): instalar @monaco-editor/react para editor com lint markers

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Frontend — substituir textarea por Monaco + Revisar e Salvar

**Files:**
- Modify: `frontend/src/pages/projects/CodeGeneratorPage.tsx`

- [ ] **Step 1: Identificar o trecho do editor atual**

Rode:

```bash
grep -nE "textarea|Editor com highlighting|fileContent|setFileContent" /home/luiz/GCA/frontend/src/pages/projects/CodeGeneratorPage.tsx | head -10
```

Anote a linha do `<textarea>` e do botão "Salvar" existente (há uma função `handleSave` ou similar).

- [ ] **Step 2: Adicionar import e estado**

No topo do arquivo, nos imports React existentes, adicione:

```tsx
import Editor, { type OnMount } from '@monaco-editor/react'
```

E na zona de useState do componente (perto de `const [fileContent, setFileContent] = useState`), adicione:

```tsx
  const [validationErrors, setValidationErrors] = useState<Array<{ line: number; column: number; message: string; severity: string }>>([])
  const [validationBlocked, setValidationBlocked] = useState(false)
  const [validating, setValidating] = useState(false)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null)
```

Garanta que `useRef` está importado de `react` no topo.

- [ ] **Step 3: Função de detecção de linguagem**

Acima do JSX do componente, adicione helper:

```tsx
  const detectLanguageForMonaco = (path: string | null): string => {
    if (!path) return 'plaintext'
    const lower = path.toLowerCase()
    if (lower.endsWith('.py')) return 'python'
    if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return 'typescript'
    if (lower.endsWith('.js') || lower.endsWith('.jsx') || lower.endsWith('.mjs')) return 'javascript'
    if (lower.endsWith('.json')) return 'json'
    if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml'
    if (lower.endsWith('.toml')) return 'ini' // Monaco não tem TOML nativo; ini é próximo
    if (lower.endsWith('.md')) return 'markdown'
    if (lower.endsWith('.go')) return 'go'
    if (lower.endsWith('.java')) return 'java'
    return 'plaintext'
  }
```

- [ ] **Step 4: Função `handleReviewAndSave`**

Adicione logo antes do return do JSX:

```tsx
  const applyMarkers = (errors: Array<{ line: number; column: number; message: string; severity: string }>) => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    if (!editor || !monaco) return
    const model = editor.getModel()
    if (!model) return
    const markers = errors.map(e => ({
      startLineNumber: e.line,
      startColumn: e.column,
      endLineNumber: e.line,
      endColumn: e.column + 1,
      message: e.message,
      severity: e.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
    }))
    monaco.editor.setModelMarkers(model, 'gca-validator', markers)
  }

  const handleReviewAndSave = async () => {
    if (!selectedFile) return
    setValidating(true)
    setValidationBlocked(false)
    try {
      const res = await apiClient.post('/code-generation/validate', {
        code: fileContent,
        path: selectedFile,
      })
      const issues = (res.data?.issues || []) as Array<{ line: number; column: number; message: string; severity: string }>
      setValidationErrors(issues)
      applyMarkers(issues)
      const hasError = issues.some(i => i.severity === 'error')
      if (hasError) {
        setValidationBlocked(true)
        alert(`Código com ${issues.length} problema(s). Corrija os erros em vermelho antes de salvar.`)
        return
      }
      // Linguagem não suportada: não bloqueia, segue com save
      // Sem erros: salva chamando a função de save existente (handleSave ou similar)
      await handleSave()
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Falha ao validar código')
    } finally {
      setValidating(false)
    }
  }
```

**Importante:** a chamada `await handleSave()` assume que existe uma função `handleSave` no componente que salva o arquivo (commit ao Git). Procure por ela antes de integrar: `grep -n "const handleSave\|async function handleSave" /home/luiz/GCA/frontend/src/pages/projects/CodeGeneratorPage.tsx`. Se o nome for outro (ex: `saveFile`, `commitFile`), ajuste.

- [ ] **Step 5: Substituir textarea por Editor**

Localize o `<textarea>` e substitua pelo Monaco. Exemplo de substituição:

```tsx
              <Editor
                height="60vh"
                language={detectLanguageForMonaco(selectedFile)}
                value={fileContent}
                theme="vs-dark"
                onChange={(v) => {
                  setFileContent(v ?? '')
                  setHasChanges(true)
                }}
                onMount={(editor, monaco) => {
                  editorRef.current = editor
                  monacoRef.current = monaco
                }}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  wordWrap: 'on',
                  readOnly: false,
                }}
              />
```

Mantenha as classes/wrappers do container do editor para não quebrar layout.

- [ ] **Step 6: Adicionar botão "Revisar e Salvar"**

Perto do botão "Salvar" existente, adicione:

```tsx
              <button
                onClick={handleReviewAndSave}
                disabled={!hasChanges || validating}
                className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm"
              >
                {validating ? 'Revisando…' : 'Revisar e Salvar'}
              </button>
              {validationBlocked && (
                <span className="text-red-400 text-xs">
                  {validationErrors.length} problema(s) — corrija os marcados em vermelho.
                </span>
              )}
```

Se o botão "Salvar" antigo continuar, deixe-o: ele não valida, é save direto (útil para arquivos sem linguagem suportada).

- [ ] **Step 7: Rebuild e validar visualmente**

```bash
cd /home/luiz/GCA && docker compose restart frontend
until docker compose logs frontend --tail 5 2>&1 | grep -q "Local:  "; do sleep 3; done
docker compose logs frontend --tail 15 2>&1 | grep -iE "error|failed" | head -5 || echo "OK"
```

Abra no browser: vá em CodeGeneratorPage, selecione um arquivo `.py`, introduza erro (ex: `def f(:`), clique "Revisar e Salvar". Esperado:
- Sublinhado vermelho na linha 1
- Hover mostra mensagem do pyflakes
- Alert "Código com N problema(s)"
- Save bloqueado

Corrija o erro, clique de novo: commita no Git normalmente.

- [ ] **Step 8: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/CodeGeneratorPage.tsx
git commit -m "feat(codegen): Monaco Editor + validação bloqueante via Revisar e Salvar

- Substitui textarea por @monaco-editor/react com linguagem detectada por extensão
- Novo botão \"Revisar e Salvar\" chama POST /code-generation/validate
- Markers vermelhos sublinham linha/coluna com erro
- Save bloqueado se houver error; warning não bloqueia
- Linguagens não suportadas (Go, Rust, etc.) passam direto sem validar

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- ✅ Validação Tier 1 de múltiplas linguagens → Task 1 (module) + Task 2 (endpoint)
- ✅ Marker vermelho no Monaco → Task 5 (applyMarkers + setModelMarkers)
- ✅ Save bloqueado em erro → Task 5 (handleReviewAndSave early return)
- ✅ Linguagem detectada por extensão → Task 1 (detect_language) + Task 5 (detectLanguageForMonaco)
- ✅ Revisar e Salvar dispara validação → Task 5 (Step 6 botão)

**Placeholder scan:** nenhum TBD/TODO. Único ponto flexível é o nome de `handleSave` existente — instrução explícita de verificar antes de editar.

**Type consistency:** `ValidationIssue.line/column` é int 1-based em Python e 1-based em Monaco (`startLineNumber`/`startColumn`) — compatível direto, sem conversão.

---

## Execução

Plano salvo em `docs/superpowers/plans/2026-04-15-code-validation.md`. Executo inline (tokens baratos, rate-limit do subagent queimou mais cedo hoje).
