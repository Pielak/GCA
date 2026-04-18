"""DT-058 Sprint 3.2 — Scaffolder C# / ASP.NET Core 8.

Gera estrutura inicial Minimal API .NET 8 com xUnit. Não chama LLM.

Layout produzido:
    <Slug>.sln
    src/<Slug>.Api/<Slug>.Api.csproj
    src/<Slug>.Api/Program.cs
    src/<Slug>.Api/appsettings.json
    src/<Slug>.Api/appsettings.Development.json
    tests/<Slug>.Api.Tests/<Slug>.Api.Tests.csproj
    tests/<Slug>.Api.Tests/HealthEndpointTests.cs
    .gitignore
    README.md

Decisões:
- .NET 8 (LTS).
- Minimal API (introduzido no .NET 6, padrão atual do template
  `dotnet new web`) — menos boilerplate que MVC clássico.
- xUnit + Microsoft.AspNetCore.Mvc.Testing pra integration tests.
- EF Core + Npgsql se database=PostgreSQL.
- StackExchange.Redis se requires_redis.
"""
from typing import List

from .types import ScaffoldFile, ScaffoldSpec
from .java_spring import _class_name_from_slug


_DOTNET_TFM = "net8.0"


def _api_csproj(spec: ScaffoldSpec) -> str:
    deps = []
    if (spec.database or "").lower().startswith("postgres"):
        deps.append('    <PackageReference Include="Microsoft.EntityFrameworkCore.Design" Version="8.0.6" />')
        deps.append('    <PackageReference Include="Npgsql.EntityFrameworkCore.PostgreSQL" Version="8.0.4" />')
    if spec.requires_redis:
        deps.append('    <PackageReference Include="StackExchange.Redis" Version="2.7.33" />')
    if spec.requires_security:
        deps.append('    <PackageReference Include="Microsoft.AspNetCore.Authentication.JwtBearer" Version="8.0.6" />')

    deps_block = "\n".join(deps) if deps else ""

    return f"""<!-- Auto-gerado pelo GCA — não editar manualmente. [gca:auto] -->
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>{_DOTNET_TFM}</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>{_class_name_from_slug(spec.project_slug)}.Api</RootNamespace>
  </PropertyGroup>

  <ItemGroup>
{deps_block}
  </ItemGroup>
</Project>
"""


def _program_cs(spec: ScaffoldSpec) -> str:
    db_block = ""
    if (spec.database or "").lower().startswith("postgres"):
        db_block = """
// DbContext via Npgsql — configure connection string via appsettings ou env DB_CONN_STR.
// builder.Services.AddDbContext<AppDbContext>(opt =>
//     opt.UseNpgsql(builder.Configuration.GetConnectionString("Default")));
"""
    redis_block = ""
    if spec.requires_redis:
        redis_block = """
// Redis singleton — configure via appsettings:Redis ou env REDIS_URL.
// builder.Services.AddSingleton<IConnectionMultiplexer>(sp =>
//     ConnectionMultiplexer.Connect(builder.Configuration["Redis"] ?? "localhost:6379"));
"""
    auth_block = ""
    if spec.requires_security:
        auth_block = """
// JWT Bearer — configure issuer/audience via appsettings:Jwt.
// builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
//     .AddJwtBearer(opts => { /* configure */ });
// builder.Services.AddAuthorization();
"""
    use_auth = "app.UseAuthentication();\napp.UseAuthorization();" if spec.requires_security else ""

    return f"""// Auto-gerado pelo GCA — Minimal API entrypoint. [gca:auto]
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddHealthChecks();
{db_block}{redis_block}{auth_block}

var app = builder.Build();

{use_auth}

app.MapHealthChecks("/health");

app.MapGet("/api/greeting", () => Results.Ok(new
{{
    app = "{spec.project_slug}",
    status = "ok"
}}));

app.Run();

// Necessário pra WebApplicationFactory (integration tests)
public partial class Program {{ }}
"""


def _appsettings_json(spec: ScaffoldSpec) -> str:
    parts = ['  "Logging": {\n    "LogLevel": {\n      "Default": "Information",\n      "Microsoft.AspNetCore": "Warning"\n    }\n  }']
    parts.append('  "AllowedHosts": "*"')
    if (spec.database or "").lower().startswith("postgres"):
        parts.append('  "ConnectionStrings": {\n    "Default": "Host=localhost;Port=5432;Database=app;Username=app;Password=changeme"\n  }')
    if spec.requires_redis:
        parts.append('  "Redis": "localhost:6379"')

    body = ",\n".join(parts)
    return "{\n" + body + "\n}\n"


def _appsettings_dev_json() -> str:
    return """{
  "Logging": {
    "LogLevel": {
      "Default": "Debug",
      "Microsoft.AspNetCore": "Information"
    }
  }
}
"""


def _solution_file(spec: ScaffoldSpec) -> str:
    name = _class_name_from_slug(spec.project_slug)
    return f"""Microsoft Visual Studio Solution File, Format Version 12.00
# Auto-gerado pelo GCA. [gca:auto]
Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{name}.Api", "src\\{name}.Api\\{name}.Api.csproj", "{{11111111-1111-1111-1111-111111111111}}"
EndProject
Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{name}.Api.Tests", "tests\\{name}.Api.Tests\\{name}.Api.Tests.csproj", "{{22222222-2222-2222-2222-222222222222}}"
EndProject
Global
\tGlobalSection(SolutionConfigurationPlatforms) = preSolution
\t\tDebug|Any CPU = Debug|Any CPU
\t\tRelease|Any CPU = Release|Any CPU
\tEndGlobalSection
EndGlobal
"""


def _test_csproj(spec: ScaffoldSpec) -> str:
    name = _class_name_from_slug(spec.project_slug)
    return f"""<!-- Auto-gerado pelo GCA. [gca:auto] -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>{_DOTNET_TFM}</TargetFramework>
    <IsPackable>false</IsPackable>
    <Nullable>enable</Nullable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.10.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.1" />
    <PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" Version="8.0.6" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\\..\\src\\{name}.Api\\{name}.Api.csproj" />
  </ItemGroup>
</Project>
"""


def _health_test_cs(spec: ScaffoldSpec) -> str:
    return """// Auto-gerado pelo GCA — smoke test do health endpoint. [gca:auto]
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

public class HealthEndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public HealthEndpointTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory;
    }

    [Fact]
    public async Task Health_ReturnsHealthy()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync("/health");
        response.EnsureSuccessStatusCode();
    }

    [Fact]
    public async Task Greeting_ReturnsOk()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync("/api/greeting");
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadAsStringAsync();
        Assert.Contains("ok", body);
    }
}
"""


def _gitignore_csharp() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
bin/
obj/
out/
*.user
*.suo
.vs/
.vscode/

# Build results
[Dd]ebug/
[Rr]elease/
artifacts/

# .NET specific
*.dll
*.pdb

# OS
.DS_Store
"""


def _readme(spec: ScaffoldSpec) -> str:
    name = _class_name_from_slug(spec.project_slug)
    db = f"- {spec.database} (Npgsql + EF Core)" if (spec.database or "").lower().startswith("postgres") else ""
    redis = "- Redis (StackExchange.Redis)" if spec.requires_redis else ""
    sec = "- JWT Bearer (Microsoft.AspNetCore.Authentication.JwtBearer)" if spec.requires_security else ""
    return f"""# {spec.project_name}

> Scaffold inicial **C# / .NET 8** gerado pelo GCA.

## Stack

- .NET 8 (LTS)
- ASP.NET Core Minimal API
- xUnit + Microsoft.AspNetCore.Mvc.Testing
{db}
{redis}
{sec}

## Como rodar

```bash
dotnet restore
dotnet run --project src/{name}.Api
```

App em `http://localhost:5000` (ou conforme launchSettings).

## Testes

```bash
dotnet test
```
"""


def scaffold_csharp_aspnet(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial de um app C# / ASP.NET Core 8 Minimal API."""
    name = _class_name_from_slug(spec.project_slug)
    return [
        ScaffoldFile(f"{name}.sln", _solution_file(spec)),
        ScaffoldFile(f"src/{name}.Api/{name}.Api.csproj", _api_csproj(spec)),
        ScaffoldFile(f"src/{name}.Api/Program.cs", _program_cs(spec)),
        ScaffoldFile(f"src/{name}.Api/appsettings.json", _appsettings_json(spec)),
        ScaffoldFile(f"src/{name}.Api/appsettings.Development.json", _appsettings_dev_json()),
        ScaffoldFile(f"tests/{name}.Api.Tests/{name}.Api.Tests.csproj", _test_csproj(spec)),
        ScaffoldFile(f"tests/{name}.Api.Tests/HealthEndpointTests.cs", _health_test_cs(spec)),
        ScaffoldFile(".gitignore", _gitignore_csharp()),
        ScaffoldFile("README.md", _readme(spec)),
    ]
