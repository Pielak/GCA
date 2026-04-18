"""DT-058 Sprint 3 ext — Scaffolder Node.js / Express minimalista.

Alternativa ao NestJS quando o cliente prefere setup leve, sem
decorators e DI. Não chama LLM.

Layout produzido:
    package.json
    tsconfig.json
    .gitignore
    .env.example
    README.md
    src/server.ts
    src/app.ts
    src/routes/health.ts
    src/__tests__/app.test.ts

Decisões:
- Express 4.x (estável, ecossistema maduro).
- TypeScript 5.x.
- Jest + Supertest.
- Postgres via `pg` (driver nativo) — sem ORM por default.
- Redis via `ioredis`.
"""
import json
from typing import List

from .types import ScaffoldFile, ScaffoldSpec


_TS_VERSION = "^5.5.0"
_EXPRESS_VERSION = "^4.19.2"
_JEST_VERSION = "^29.7.0"


def _package_json(spec: ScaffoldSpec) -> str:
    deps = {
        "express": _EXPRESS_VERSION,
        "helmet": "^7.1.0",
        "cors": "^2.8.5",
    }
    if (spec.database or "").lower().startswith("postgres"):
        deps["pg"] = "^8.12.0"
    if spec.requires_redis:
        deps["ioredis"] = "^5.4.1"
    if spec.requires_security:
        deps["jsonwebtoken"] = "^9.0.2"

    dev_deps = {
        "@types/cors": "^2.8.17",
        "@types/express": "^4.17.21",
        "@types/jest": _JEST_VERSION,
        "@types/node": "^20.14.0",
        "@types/supertest": "^6.0.2",
        "jest": _JEST_VERSION,
        "supertest": "^7.0.0",
        "ts-jest": _JEST_VERSION,
        "ts-node": "^10.9.2",
        "ts-node-dev": "^2.0.0",
        "typescript": _TS_VERSION,
    }
    if (spec.database or "").lower().startswith("postgres"):
        dev_deps["@types/pg"] = "^8.11.6"
    if spec.requires_security:
        dev_deps["@types/jsonwebtoken"] = "^9.0.6"

    pkg = {
        "name": spec.project_slug,
        "version": "0.1.0",
        "description": f"{spec.project_name} — Auto-gerado pelo GCA. [gca:auto]",
        "main": "dist/server.js",
        "scripts": {
            "build": "tsc",
            "start": "node dist/server.js",
            "dev": "ts-node-dev --respawn src/server.ts",
            "test": "jest",
            "test:cov": "jest --coverage",
        },
        "dependencies": deps,
        "devDependencies": dev_deps,
    }
    return json.dumps(pkg, indent=2) + "\n"


def _tsconfig_json() -> str:
    cfg = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "commonjs",
            "lib": ["ES2022"],
            "outDir": "./dist",
            "rootDir": "./src",
            "strict": True,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "forceConsistentCasingInFileNames": True,
            "resolveJsonModule": True,
            "declaration": False,
            "sourceMap": True,
        },
        "include": ["src/**/*"],
        "exclude": ["node_modules", "dist", "**/*.test.ts"],
    }
    return "// Auto-gerado pelo GCA. [gca:auto]\n" + json.dumps(cfg, indent=2) + "\n"


def _server_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — entrypoint HTTP. [gca:auto]
import {{ createApp }} from './app';

const port = Number(process.env.PORT ?? 3000);
const app = createApp();

app.listen(port, () => {{
  console.log(`{spec.project_slug} listening on port ${{port}}`);
}});
"""


def _app_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — factory pra app Express. [gca:auto]
import express, {{ Express }} from 'express';
import helmet from 'helmet';
import cors from 'cors';
import {{ healthRouter }} from './routes/health';

export function createApp(): Express {{
  const app = express();

  app.use(helmet());
  app.use(cors());
  app.use(express.json());

  app.use('/', healthRouter);

  app.get('/api/greeting', (_req, res) => {{
    res.json({{ app: '{spec.project_slug}', status: 'ok' }});
  }});

  return app;
}}
"""


def _routes_health_ts() -> str:
    return """// Auto-gerado pelo GCA — health endpoint. [gca:auto]
import { Router } from 'express';

export const healthRouter = Router();

healthRouter.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});
"""


def _app_test_ts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — smoke tests dos endpoints básicos. [gca:auto]
import request from 'supertest';
import {{ createApp }} from '../app';

const app = createApp();

describe('app endpoints', () => {{
  it('GET /health returns ok', async () => {{
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('ok');
  }});

  it('GET /api/greeting returns app name', async () => {{
    const res = await request(app).get('/api/greeting');
    expect(res.status).toBe(200);
    expect(res.body.app).toBe('{spec.project_slug}');
  }});
}});
"""


def _gitignore_node() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
node_modules/
dist/
coverage/
*.tsbuildinfo

.env
.env.local

logs/
*.log

.idea/
.vscode/
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
    db = "- PostgreSQL (driver pg nativo)" if (spec.database or "").lower().startswith("postgres") else ""
    redis = "- Redis (ioredis)" if spec.requires_redis else ""
    sec = "- JWT (jsonwebtoken)" if spec.requires_security else ""
    return f"""# {spec.project_name}

> Scaffold inicial **Express + TypeScript** gerado pelo GCA.

## Stack

- Node.js 20+
- Express 4.x
- TypeScript 5.x (strict)
- Helmet + CORS
- Jest + Supertest
{db}
{redis}
{sec}

## Como rodar

```bash
npm install
cp .env.example .env
npm run dev
```

App em `http://localhost:3000`. Endpoints:
- `GET /health`
- `GET /api/greeting`

## Testes

```bash
npm test
```
"""


def scaffold_nodejs_express(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial Express + TypeScript minimalista."""
    return [
        ScaffoldFile("package.json", _package_json(spec)),
        ScaffoldFile("tsconfig.json", _tsconfig_json()),
        ScaffoldFile(".gitignore", _gitignore_node()),
        ScaffoldFile(".env.example", _env_example(spec)),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile("src/server.ts", _server_ts(spec)),
        ScaffoldFile("src/app.ts", _app_ts(spec)),
        ScaffoldFile("src/routes/health.ts", _routes_health_ts()),
        ScaffoldFile("src/__tests__/app.test.ts", _app_test_ts(spec)),
    ]
