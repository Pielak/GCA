"""DT-058 Sprint 3 ext — Scaffolder Node.js / NestJS.

Gera estrutura inicial NestJS 10 + TypeScript 5. Não chama LLM.

Layout produzido:
    package.json
    tsconfig.json
    nest-cli.json
    .gitignore
    .env.example
    README.md
    src/main.ts
    src/app.module.ts
    src/app.controller.ts
    src/app.service.ts
    src/app.controller.spec.ts

Decisões:
- NestJS 10.x — convenção dominante em backend Node.js corporativo
  (decorators, módulos, DI), parecido com Spring Boot do mundo Java.
- TypeScript 5.x strict.
- Jest pra testes (padrão NestJS).
- Postgres via TypeORM + pg quando database=PostgreSQL.
- Redis via @nestjs/cache-manager + cache-manager-ioredis se requires_redis.
- Passport-jwt se requires_security.
"""
import json
from typing import List

from .types import ScaffoldFile, ScaffoldSpec


_NEST_VERSION = "^10.4.0"
_TS_VERSION = "^5.5.0"
_JEST_VERSION = "^29.7.0"


def _package_json(spec: ScaffoldSpec) -> str:
    deps = {
        "@nestjs/common": _NEST_VERSION,
        "@nestjs/core": _NEST_VERSION,
        "@nestjs/platform-express": _NEST_VERSION,
        "@nestjs/terminus": "^10.2.0",
        "reflect-metadata": "^0.2.2",
        "rxjs": "^7.8.1",
    }
    if (spec.database or "").lower().startswith("postgres"):
        deps["@nestjs/typeorm"] = "^10.0.2"
        deps["typeorm"] = "^0.3.20"
        deps["pg"] = "^8.12.0"
    if spec.requires_redis:
        deps["@nestjs/cache-manager"] = "^2.2.2"
        deps["cache-manager"] = "^5.7.0"
        deps["ioredis"] = "^5.4.1"
    if spec.requires_security:
        deps["@nestjs/passport"] = "^10.0.3"
        deps["@nestjs/jwt"] = "^10.2.0"
        deps["passport"] = "^0.7.0"
        deps["passport-jwt"] = "^4.0.1"

    dev_deps = {
        "@nestjs/cli": _NEST_VERSION,
        "@nestjs/schematics": _NEST_VERSION,
        "@nestjs/testing": _NEST_VERSION,
        "@types/express": "^4.17.21",
        "@types/jest": _JEST_VERSION,
        "@types/node": "^20.14.0",
        "@types/supertest": "^6.0.2",
        "jest": _JEST_VERSION,
        "supertest": "^7.0.0",
        "ts-jest": _JEST_VERSION,
        "ts-loader": "^9.5.1",
        "ts-node": "^10.9.2",
        "tsconfig-paths": "^4.2.0",
        "typescript": _TS_VERSION,
    }

    pkg = {
        "name": spec.project_slug,
        "version": "0.1.0",
        "description": f"{spec.project_name} — Auto-gerado pelo GCA. [gca:auto]",
        "private": True,
        "scripts": {
            "build": "nest build",
            "start": "nest start",
            "start:dev": "nest start --watch",
            "start:prod": "node dist/main",
            "test": "jest",
            "test:watch": "jest --watch",
            "test:cov": "jest --coverage",
            "test:e2e": "jest --config ./test/jest-e2e.json",
        },
        "dependencies": deps,
        "devDependencies": dev_deps,
    }
    return json.dumps(pkg, indent=2) + "\n"


def _tsconfig_json() -> str:
    cfg = {
        "compilerOptions": {
            "module": "commonjs",
            "declaration": True,
            "removeComments": True,
            "emitDecoratorMetadata": True,
            "experimentalDecorators": True,
            "allowSyntheticDefaultImports": True,
            "target": "ES2022",
            "sourceMap": True,
            "outDir": "./dist",
            "baseUrl": "./",
            "incremental": True,
            "skipLibCheck": True,
            "strictNullChecks": True,
            "noImplicitAny": True,
            "strictBindCallApply": True,
            "forceConsistentCasingInFileNames": True,
            "noFallthroughCasesInSwitch": True,
            "esModuleInterop": True,
        },
    }
    return "// Auto-gerado pelo GCA. [gca:auto]\n" + json.dumps(cfg, indent=2) + "\n"


def _nest_cli_json(spec: ScaffoldSpec) -> str:
    return json.dumps({
        "$schema": "https://json.schemastore.org/nest-cli",
        "collection": "@nestjs/schematics",
        "sourceRoot": "src",
    }, indent=2) + "\n"


def _main_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — entrypoint NestJS. [gca:auto]
import {{ NestFactory }} from '@nestjs/core';
import {{ AppModule }} from './app.module';

async function bootstrap() {{
  const app = await NestFactory.create(AppModule);
  const port = process.env.PORT ?? 3000;
  await app.listen(port);
  console.log(`{spec.project_slug} listening on port ${{port}}`);
}}
bootstrap();
"""


def _app_module_ts(spec: ScaffoldSpec) -> str:
    imports_extra = []
    module_imports = []

    imports_extra.append("import { TerminusModule } from '@nestjs/terminus';")
    module_imports.append("TerminusModule")

    if (spec.database or "").lower().startswith("postgres"):
        imports_extra.append("import { TypeOrmModule } from '@nestjs/typeorm';")
        module_imports.append("""TypeOrmModule.forRoot({
      type: 'postgres',
      url: process.env.DATABASE_URL ?? 'postgresql://app:changeme@localhost:5432/app',
      autoLoadEntities: true,
      synchronize: false,
    })""")
    if spec.requires_redis:
        imports_extra.append("import { CacheModule } from '@nestjs/cache-manager';")
        module_imports.append("CacheModule.register({ isGlobal: true })")

    extra_imports_block = "\n".join(imports_extra)
    modules_block = ",\n    ".join(module_imports)

    return f"""// Auto-gerado pelo GCA — root module. [gca:auto]
import {{ Module }} from '@nestjs/common';
{extra_imports_block}
import {{ AppController }} from './app.controller';
import {{ AppService }} from './app.service';

@Module({{
  imports: [
    {modules_block},
  ],
  controllers: [AppController],
  providers: [AppService],
}})
export class AppModule {{}}
"""


def _app_controller_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA. [gca:auto]
import {{ Controller, Get }} from '@nestjs/common';
import {{ HealthCheck, HealthCheckService }} from '@nestjs/terminus';
import {{ AppService }} from './app.service';

@Controller()
export class AppController {{
  constructor(
    private readonly appService: AppService,
    private readonly health: HealthCheckService,
  ) {{}}

  @Get('health')
  @HealthCheck()
  check() {{
    return this.health.check([]);
  }}

  @Get('api/greeting')
  greeting() {{
    return {{ app: '{spec.project_slug}', status: 'ok' }};
  }}

  @Get('api/info')
  info() {{
    return this.appService.info();
  }}
}}
"""


def _app_service_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA. [gca:auto]
import {{ Injectable }} from '@nestjs/common';

@Injectable()
export class AppService {{
  info(): {{ name: string; version: string }} {{
    return {{ name: '{spec.project_slug}', version: '0.1.0' }};
  }}
}}
"""


def _app_controller_spec_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — smoke test do controller. [gca:auto]
import {{ Test, TestingModule }} from '@nestjs/testing';
import {{ AppController }} from './app.controller';
import {{ AppService }} from './app.service';
import {{ TerminusModule }} from '@nestjs/terminus';

describe('AppController', () => {{
  let controller: AppController;

  beforeEach(async () => {{
    const module: TestingModule = await Test.createTestingModule({{
      imports: [TerminusModule],
      controllers: [AppController],
      providers: [AppService],
    }}).compile();

    controller = module.get<AppController>(AppController);
  }});

  it('greeting returns app name', () => {{
    const res = controller.greeting();
    expect(res.app).toBe('{spec.project_slug}');
    expect(res.status).toBe('ok');
  }});

  it('info returns name and version', () => {{
    const res = controller.info();
    expect(res.name).toBe('{spec.project_slug}');
    expect(res.version).toBeDefined();
  }});
}});
"""


def _gitignore_node() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
node_modules/
dist/
coverage/
*.tsbuildinfo

# Env
.env
.env.local

# Logs
logs/
*.log

# IDE
.idea/
.vscode/

# OS
.DS_Store
"""


def _env_example(spec: ScaffoldSpec) -> str:
    lines = ["# Auto-gerado pelo GCA. [gca:auto]", "PORT=3000"]
    if (spec.database or "").lower().startswith("postgres"):
        lines.append("DATABASE_URL=postgresql://app:changeme@localhost:5432/app")
    if spec.requires_redis:
        lines.append("REDIS_URL=redis://localhost:6379")
    if spec.requires_security:
        lines.append("JWT_SECRET=change-me-in-production")
    return "\n".join(lines) + "\n"


def _readme(spec: ScaffoldSpec) -> str:
    db = "- PostgreSQL (TypeORM + pg)" if (spec.database or "").lower().startswith("postgres") else ""
    redis = "- Redis (cache-manager + ioredis)" if spec.requires_redis else ""
    sec = "- JWT (passport-jwt)" if spec.requires_security else ""
    return f"""# {spec.project_name}

> Scaffold inicial **NestJS 10 + TypeScript** gerado pelo GCA.

## Stack

- Node.js 20+
- NestJS 10.x
- TypeScript 5.x (strict)
- Jest + Supertest
{db}
{redis}
{sec}

## Como rodar

```bash
npm install
cp .env.example .env
npm run start:dev
```

App em `http://localhost:3000`. Endpoints:
- `GET /health`
- `GET /api/greeting`
- `GET /api/info`

## Testes

```bash
npm test
npm run test:cov
```
"""


def scaffold_nodejs_nestjs(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial NestJS 10 + TypeScript."""
    return [
        ScaffoldFile("package.json", _package_json(spec)),
        ScaffoldFile("tsconfig.json", _tsconfig_json()),
        ScaffoldFile("nest-cli.json", _nest_cli_json(spec)),
        ScaffoldFile(".gitignore", _gitignore_node()),
        ScaffoldFile(".env.example", _env_example(spec)),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile("src/main.ts", _main_ts(spec)),
        ScaffoldFile("src/app.module.ts", _app_module_ts(spec)),
        ScaffoldFile("src/app.controller.ts", _app_controller_ts(spec)),
        ScaffoldFile("src/app.service.ts", _app_service_ts(spec)),
        ScaffoldFile("src/app.controller.spec.ts", _app_controller_spec_ts(spec)),
    ]
