"""DT-058 Sprint 3.1 — Scaffolder Go.

Gera estrutura inicial de um app Go modular com `chi` (router HTTP
leve, padrão idiomático Go). Não chama LLM.

Layout produzido:
    go.mod
    .gitignore
    README.md
    cmd/server/main.go
    internal/server/server.go
    internal/server/server_test.go

Decisões:
- Go 1.22 (LTS-current).
- chi/v5 — router minimalista, idiomático, suporta middleware. Mais
  leve que Gin/Echo, não esconde o net/http.
- Layout cmd/+internal/ — convenção oficial da comunidade Go pra
  separar entrypoint (cmd) de código não-importável (internal).
- Testes em pacote interno usando `testing` stdlib + httptest.
- Postgres via `pgx/v5` (driver moderno, sem ORM por default — Go
  prefere DAOs explícitos).
"""
from typing import List

from .types import ScaffoldFile, ScaffoldSpec


_GO_VERSION_DEFAULT = "1.22"
_CHI_VERSION = "v5.0.12"
_PGX_VERSION = "v5.5.5"
_REDIS_VERSION = "v9.6.1"


def _module_path(spec: ScaffoldSpec) -> str:
    """`com.gca.demo` → `github.com/gca/demo` (convenção Go)."""
    if "/" in spec.package:
        return spec.package  # já é path Go
    parts = spec.package.split(".")
    if not parts:
        return f"example.com/{spec.project_slug}"
    # Reverter convenção Java reverso: com.gca.x → github.com/gca/x
    if parts[0] == "com" and len(parts) >= 2:
        return f"github.com/{'/'.join(parts[1:])}"
    return f"example.com/{spec.project_slug}"


def _go_mod(spec: ScaffoldSpec) -> str:
    mod = _module_path(spec)
    deps = [f"\tgithub.com/go-chi/chi/v5 {_CHI_VERSION}"]
    if (spec.database or "").lower().startswith("postgres"):
        deps.append(f"\tgithub.com/jackc/pgx/v5 {_PGX_VERSION}")
    if spec.requires_redis:
        deps.append(f"\tgithub.com/redis/go-redis/v9 {_REDIS_VERSION}")
    deps_block = "\n".join(deps)

    return f"""// Auto-gerado pelo GCA. [gca:auto]
module {mod}

go {spec.java_version if spec.java_version != "21" else _GO_VERSION_DEFAULT}

require (
{deps_block}
)
"""


def _main_go(spec: ScaffoldSpec) -> str:
    mod = _module_path(spec)
    return f"""// Auto-gerado pelo GCA — entrypoint. [gca:auto]
package main

import (
\t"log"
\t"net/http"
\t"os"

\t"{mod}/internal/server"
)

func main() {{
\tport := os.Getenv("PORT")
\tif port == "" {{
\t\tport = "8080"
\t}}

\tsrv := server.New()
\tlog.Printf("starting %s on :%s", "{spec.project_slug}", port)
\tif err := http.ListenAndServe(":"+port, srv.Handler()); err != nil {{
\t\tlog.Fatal(err)
\t}}
}}
"""


def _server_go(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — router e handlers básicos. [gca:auto]
package server

import (
\t"encoding/json"
\t"net/http"

\t"github.com/go-chi/chi/v5"
\t"github.com/go-chi/chi/v5/middleware"
)

type Server struct {{
\trouter *chi.Mux
}}

func New() *Server {{
\tr := chi.NewRouter()
\tr.Use(middleware.RequestID)
\tr.Use(middleware.RealIP)
\tr.Use(middleware.Logger)
\tr.Use(middleware.Recoverer)

\ts := &Server{{router: r}}
\ts.routes()
\treturn s
}}

func (s *Server) Handler() http.Handler {{
\treturn s.router
}}

func (s *Server) routes() {{
\ts.router.Get("/health", s.health)
\ts.router.Get("/api/greeting", s.greeting)
}}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {{
\tw.Header().Set("Content-Type", "application/json")
\tjson.NewEncoder(w).Encode(map[string]string{{"status": "ok"}})
}}

func (s *Server) greeting(w http.ResponseWriter, r *http.Request) {{
\tw.Header().Set("Content-Type", "application/json")
\tjson.NewEncoder(w).Encode(map[string]string{{
\t\t"app":    "{spec.project_slug}",
\t\t"status": "ok",
\t}})
}}
"""


def _server_test_go(spec: ScaffoldSpec) -> str:
    return """// Auto-gerado pelo GCA — smoke tests dos endpoints básicos. [gca:auto]
package server

import (
\t"net/http"
\t"net/http/httptest"
\t"strings"
\t"testing"
)

func TestHealthEndpoint(t *testing.T) {
\tsrv := New()
\treq := httptest.NewRequest(http.MethodGet, "/health", nil)
\tw := httptest.NewRecorder()
\tsrv.Handler().ServeHTTP(w, req)

\tif w.Code != http.StatusOK {
\t\tt.Fatalf("expected 200, got %d", w.Code)
\t}
\tif !strings.Contains(w.Body.String(), "ok") {
\t\tt.Fatalf("expected body to contain 'ok', got %q", w.Body.String())
\t}
}

func TestGreetingEndpoint(t *testing.T) {
\tsrv := New()
\treq := httptest.NewRequest(http.MethodGet, "/api/greeting", nil)
\tw := httptest.NewRecorder()
\tsrv.Handler().ServeHTTP(w, req)

\tif w.Code != http.StatusOK {
\t\tt.Fatalf("expected 200, got %d", w.Code)
\t}
}
"""


def _gitignore_go() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
# Binaries
*.exe
*.exe~
*.dll
*.so
*.dylib
bin/
dist/

# Test binary, built with `go test -c`
*.test

# Output of `go test -coverprofile`
*.out

# Go workspace
go.work

# IDE
.idea/
.vscode/

# OS
.DS_Store
"""


def _readme(spec: ScaffoldSpec) -> str:
    db = f"- {spec.database}" if spec.database else ""
    redis = "- Redis (go-redis/v9)" if spec.requires_redis else ""
    return f"""# {spec.project_name}

> Scaffold inicial **Go** gerado pelo GCA. Edite normalmente — apenas
> arquivos com cabeçalho `[gca:auto]` podem ser sobrescritos em
> regenerações futuras.

## Stack

- Go {spec.java_version if spec.java_version != "21" else _GO_VERSION_DEFAULT}
- chi/v5 (router HTTP)
{db}
{redis}

## Como rodar

```bash
go mod download
go run ./cmd/server
```

App em `http://localhost:8080`. Endpoints:
- `GET /health`
- `GET /api/greeting`

## Testes

```bash
go test ./...
```

## Variáveis de ambiente

- `PORT` (default: 8080)
{"- `DATABASE_URL` (driver pgx)" if (spec.database or "").lower().startswith("postgres") else ""}
{"- `REDIS_URL`" if spec.requires_redis else ""}
"""


def scaffold_go(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial de um app Go com chi + layout cmd/internal."""
    return [
        ScaffoldFile("go.mod", _go_mod(spec)),
        ScaffoldFile(".gitignore", _gitignore_go()),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile("cmd/server/main.go", _main_go(spec)),
        ScaffoldFile("internal/server/server.go", _server_go(spec)),
        ScaffoldFile("internal/server/server_test.go", _server_test_go(spec)),
    ]
