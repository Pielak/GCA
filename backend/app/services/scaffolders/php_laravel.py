"""DT-058 Sprint 3.3 — Scaffolder PHP / Laravel.

Gera estrutura mínima de uma API Laravel 11. Não chama LLM.

Layout produzido:
    composer.json
    artisan
    .env.example
    .gitignore
    README.md
    public/index.php
    bootstrap/app.php
    routes/api.php
    app/Http/Controllers/HealthController.php
    config/app.php
    phpunit.xml
    tests/Feature/HealthEndpointTest.php

Decisões:
- Laravel 11.x — última major LTS no momento. Maior adoção no
  ecossistema PHP brasileiro (pesquisas StackOverflow + GitHub Insights
  BR mostram Laravel >> Symfony >> Slim/Lumen).
- PHP 8.2+ (requirement de Laravel 11).
- Estrutura simplificada vs full `laravel new` — só o necessário pro
  GP avançar e o LLM gerar controllers/services em cima depois.
- composer.json com deps mínimos: framework, sanctum (se security).
- Postgres via driver nativo do Laravel (`pgsql` em config/database).
"""
from typing import List

from .types import ScaffoldFile, ScaffoldSpec


def _composer_json(spec: ScaffoldSpec) -> str:
    deps = [
        '        "php": "^8.2",',
        '        "laravel/framework": "^11.0",',
        '        "laravel/tinker": "^2.9"',
    ]
    if spec.requires_security:
        deps.insert(2, '        "laravel/sanctum": "^4.0",')
    if spec.requires_redis:
        deps.append(',\n        "predis/predis": "^2.2"')

    deps_block = "\n".join(deps)

    return f"""{{
    "name": "{spec.package.replace('.', '/').lower()}/{spec.project_slug}",
    "type": "project",
    "description": "{spec.project_name} — Auto-gerado pelo GCA. [gca:auto]",
    "license": "proprietary",
    "require": {{
{deps_block}
    }},
    "require-dev": {{
        "fakerphp/faker": "^1.23",
        "phpunit/phpunit": "^11.0",
        "mockery/mockery": "^1.6"
    }},
    "autoload": {{
        "psr-4": {{
            "App\\\\": "app/",
            "Database\\\\Factories\\\\": "database/factories/",
            "Database\\\\Seeders\\\\": "database/seeders/"
        }}
    }},
    "autoload-dev": {{
        "psr-4": {{
            "Tests\\\\": "tests/"
        }}
    }},
    "scripts": {{
        "test": "vendor/bin/phpunit"
    }},
    "config": {{
        "optimize-autoloader": true,
        "preferred-install": "dist"
    }},
    "minimum-stability": "stable",
    "prefer-stable": true
}}
"""


def _artisan() -> str:
    return """#!/usr/bin/env php
<?php
// Auto-gerado pelo GCA — entrypoint CLI Laravel. [gca:auto]

define('LARAVEL_START', microtime(true));

require __DIR__.'/vendor/autoload.php';

$app = require_once __DIR__.'/bootstrap/app.php';

$status = $app->handleCommand(new Symfony\\Component\\Console\\Input\\ArgvInput);

exit($status);
"""


def _public_index_php() -> str:
    return """<?php
// Auto-gerado pelo GCA — entrypoint HTTP. [gca:auto]

use Illuminate\\Http\\Request;

define('LARAVEL_START', microtime(true));

require __DIR__.'/../vendor/autoload.php';

(require_once __DIR__.'/../bootstrap/app.php')
    ->handleRequest(Request::capture());
"""


def _bootstrap_app_php(spec: ScaffoldSpec) -> str:
    return """<?php
// Auto-gerado pelo GCA — bootstrap Laravel 11 (slim style). [gca:auto]

use Illuminate\\Foundation\\Application;
use Illuminate\\Foundation\\Configuration\\Exceptions;
use Illuminate\\Foundation\\Configuration\\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware) {
        // RBAC e middlewares custom vão aqui.
    })
    ->withExceptions(function (Exceptions $exceptions) {
        // Tratamento custom de exceptions vai aqui.
    })->create();
"""


def _routes_api_php(spec: ScaffoldSpec) -> str:
    return """<?php
// Auto-gerado pelo GCA — rotas da API. [gca:auto]

use App\\Http\\Controllers\\HealthController;
use Illuminate\\Support\\Facades\\Route;

Route::get('/health', [HealthController::class, 'index']);
Route::get('/greeting', [HealthController::class, 'greeting']);
"""


def _routes_console_php() -> str:
    return """<?php
// Auto-gerado pelo GCA — comandos artisan custom. [gca:auto]
"""


def _health_controller_php(spec: ScaffoldSpec) -> str:
    return f"""<?php
// Auto-gerado pelo GCA — controller exemplo de health. [gca:auto]

namespace App\\Http\\Controllers;

use Illuminate\\Http\\JsonResponse;

class HealthController extends Controller
{{
    public function index(): JsonResponse
    {{
        return response()->json(['status' => 'ok']);
    }}

    public function greeting(): JsonResponse
    {{
        return response()->json([
            'app'    => '{spec.project_slug}',
            'status' => 'ok',
        ]);
    }}
}}
"""


def _controller_base_php() -> str:
    return """<?php
// Auto-gerado pelo GCA — base controller (Laravel 11 slim). [gca:auto]

namespace App\\Http\\Controllers;

abstract class Controller
{
    //
}
"""


def _phpunit_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- Auto-gerado pelo GCA. [gca:auto] -->
<phpunit xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:noNamespaceSchemaLocation="vendor/phpunit/phpunit/phpunit.xsd"
         bootstrap="vendor/autoload.php"
         colors="true"
         processIsolation="false"
         stopOnFailure="false">
    <testsuites>
        <testsuite name="Feature">
            <directory>tests/Feature</directory>
        </testsuite>
        <testsuite name="Unit">
            <directory>tests/Unit</directory>
        </testsuite>
    </testsuites>
    <php>
        <env name="APP_ENV" value="testing"/>
        <env name="DB_CONNECTION" value="sqlite"/>
        <env name="DB_DATABASE" value=":memory:"/>
    </php>
</phpunit>
"""


def _health_test_php() -> str:
    return """<?php
// Auto-gerado pelo GCA — smoke test do endpoint /health. [gca:auto]

namespace Tests\\Feature;

use Tests\\TestCase;

class HealthEndpointTest extends TestCase
{
    public function test_health_returns_ok(): void
    {
        $response = $this->get('/api/health');
        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);
    }

    public function test_greeting_returns_app_name(): void
    {
        $response = $this->get('/api/greeting');
        $response->assertStatus(200);
        $response->assertJsonStructure(['app', 'status']);
    }
}
"""


def _testcase_php() -> str:
    return """<?php
// Auto-gerado pelo GCA — base TestCase. [gca:auto]

namespace Tests;

use Illuminate\\Foundation\\Testing\\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    use CreatesApplication;
}
"""


def _creates_application_php() -> str:
    return """<?php
// Auto-gerado pelo GCA — bootstrap pra TestCase. [gca:auto]

namespace Tests;

use Illuminate\\Contracts\\Console\\Kernel;

trait CreatesApplication
{
    public function createApplication()
    {
        $app = require __DIR__.'/../bootstrap/app.php';
        $app->make(Kernel::class)->bootstrap();
        return $app;
    }
}
"""


def _env_example(spec: ScaffoldSpec) -> str:
    lines = [
        "# Auto-gerado pelo GCA. [gca:auto]",
        f"APP_NAME=\"{spec.project_name}\"",
        "APP_ENV=local",
        "APP_KEY=",
        "APP_DEBUG=true",
        "APP_URL=http://localhost:8000",
        "",
        "LOG_CHANNEL=stack",
        "LOG_LEVEL=debug",
    ]
    if (spec.database or "").lower().startswith("postgres"):
        lines.extend([
            "",
            "DB_CONNECTION=pgsql",
            "DB_HOST=127.0.0.1",
            "DB_PORT=5432",
            f"DB_DATABASE={spec.project_slug.replace('-', '_')}",
            "DB_USERNAME=app",
            "DB_PASSWORD=changeme",
        ])
    if spec.requires_redis:
        lines.extend([
            "",
            "REDIS_HOST=127.0.0.1",
            "REDIS_PORT=6379",
            "REDIS_PASSWORD=null",
        ])
    return "\n".join(lines) + "\n"


def _gitignore_php() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
/vendor
/node_modules
.env
.env.backup
/storage/*.key
/public/storage
/public/hot
.phpunit.result.cache
.phpunit.cache
auth.json

# IDE
.idea/
.vscode/

# OS
.DS_Store
"""


def _readme(spec: ScaffoldSpec) -> str:
    db = f"- {spec.database} (driver pgsql)" if (spec.database or "").lower().startswith("postgres") else ""
    redis = "- Redis (predis)" if spec.requires_redis else ""
    sec = "- Laravel Sanctum (auth API)" if spec.requires_security else ""
    return f"""# {spec.project_name}

> Scaffold inicial **PHP / Laravel 11** gerado pelo GCA.

## Stack

- PHP 8.2+
- Laravel 11.x
- PHPUnit 11
{db}
{redis}
{sec}

## Como rodar

```bash
composer install
cp .env.example .env
php artisan key:generate
php artisan serve
```

App em `http://localhost:8000`. Endpoints:
- `GET /api/health`
- `GET /api/greeting`
- `GET /up` (health bundled do Laravel)

## Testes

```bash
composer test
# ou
vendor/bin/phpunit
```
"""


def scaffold_php_laravel(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial de uma API Laravel 11."""
    return [
        ScaffoldFile("composer.json", _composer_json(spec)),
        ScaffoldFile("artisan", _artisan(), executable=True),
        ScaffoldFile(".env.example", _env_example(spec)),
        ScaffoldFile(".gitignore", _gitignore_php()),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile("public/index.php", _public_index_php()),
        ScaffoldFile("bootstrap/app.php", _bootstrap_app_php(spec)),
        ScaffoldFile("routes/api.php", _routes_api_php(spec)),
        ScaffoldFile("routes/console.php", _routes_console_php()),
        ScaffoldFile("app/Http/Controllers/Controller.php", _controller_base_php()),
        ScaffoldFile("app/Http/Controllers/HealthController.php", _health_controller_php(spec)),
        ScaffoldFile("phpunit.xml", _phpunit_xml()),
        ScaffoldFile("tests/TestCase.php", _testcase_php()),
        ScaffoldFile("tests/CreatesApplication.php", _creates_application_php()),
        ScaffoldFile("tests/Feature/HealthEndpointTest.php", _health_test_php()),
    ]
