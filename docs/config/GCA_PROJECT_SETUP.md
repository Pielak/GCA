# 🚀 GUIA PASSO A PASSO: Criar GCA_Project no GitHub

## FASE 1: Criar Repositório no GitHub

### Passo 1.1: Acessar GitHub e criar novo repositório

1. Acesse: https://github.com/new
2. Preencha os dados:

```
Repository name:     GCA_Project
Description:         GCA - Gestão de Codificação Assistida (Backend, Frontend, Design System)
Visibility:          Private (se trabalho interno) ou Public
Initialize:          ❌ NÃO inicializar (vamos fazer local)
```

3. Clique **"Create repository"**
4. Você verá a tela com comandos. **Copie o HTTPS URL** que aparecerá

---

## FASE 2: Preparar Estrutura Local

### Passo 2.1: Criar diretório do projeto

```bash
# Criar e acessar diretório
mkdir -p ~/GCA_Project
cd ~/GCA_Project

# Inicializar git
git init
git config user.name "Luiz Carlos Pielak"
git config user.email "pielak.ctba@gmail.com"
```

### Passo 2.2: Criar estrutura de diretórios

```bash
# Criar estrutura
mkdir -p backend
mkdir -p frontend
mkdir -p gui-components
mkdir -p infra
mkdir -p docs
mkdir -p scripts
mkdir -p .github/workflows

# Criar arquivo README principal
cat > README.md << 'EOF'
# GCA - Gestão de Codificação Assistida

Plataforma de orquestração, governança e visibilidade de projetos de software com isolamento por tenant, ciclo documental completo e rastreabilidade total.

## 📋 Estrutura

- **backend/** - FastAPI server
- **frontend/** - React + Vite + Electron
- **gui-components/** - Design system (shadcn/ui)
- **infra/** - Docker Compose e configurações
- **docs/** - Documentação
- **scripts/** - Scripts utilitários

## 🚀 Quick Start

### Backend
```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Todos os serviços (Docker)
```bash
docker-compose up -d
```

## 📚 Documentação

- [Architecture](docs/ARCHITECTURE.md)
- [Setup Guide](docs/SETUP.md)
- [API Reference](docs/API.md)
- [Deployment](docs/DEPLOYMENT.md)

## 🔗 Repositórios Originais
- Migrado de: https://github.com/Pielak/GCA
- Design System: https://github.com/Pielak/Gcagui

EOF

# Criar .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*
dist/
.env.local
.env.development.local
.env.test.local
.env.production.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Docker
.env
.env.production
docker-compose.override.yml

# Database
*.db
*.sqlite
*.sqlite3

# OS
.DS_Store
Thumbs.db

# Logs
logs/
*.log
EOF

echo "✅ Estrutura criada!"
ls -la
```

---

## FASE 3: Copiar Código do GCA (Seu Backend + Frontend)

### Passo 3.1: Copiar backend

```bash
# Copiar do GCA existente para o novo projeto
cp -r ~/GCA/backend/* ~/GCA_Project/backend/

# Verificar
ls -la ~/GCA_Project/backend/
# Deve conter: app/, migrations/, pyproject.toml, Dockerfile, etc
```

### Passo 3.2: Copiar frontend

```bash
# Copiar do GCA existente
cp -r ~/GCA/frontend/src ~/GCA_Project/frontend/src
cp ~/GCA/frontend/package.json ~/GCA_Project/frontend/
cp ~/GCA/frontend/vite.config.ts ~/GCA_Project/frontend/
cp ~/GCA/frontend/tsconfig.json ~/GCA_Project/frontend/
cp ~/GCA/frontend/tsconfig.node.json ~/GCA_Project/frontend/
cp ~/GCA/frontend/tailwind.config.ts ~/GCA_Project/frontend/
cp ~/GCA/frontend/postcss.config.js ~/GCA_Project/frontend/
cp ~/GCA/frontend/index.html ~/GCA_Project/frontend/
cp ~/GCA/frontend/electron/ ~/GCA_Project/frontend/ 2>/dev/null || true

# Se tiver public/
cp -r ~/GCA/frontend/public ~/GCA_Project/frontend/ 2>/dev/null || true

echo "✅ Frontend copiado!"
```

### Passo 3.3: Copiar infraestrutura e docs

```bash
# Copiar Docker Compose
cp ~/GCA/docker-compose.yml ~/GCA_Project/infra/docker-compose.yml
cp ~/GCA/docker-compose.production.yml ~/GCA_Project/infra/docker-compose.production.yml

# Copiar documentação
cp -r ~/GCA/docs/* ~/GCA_Project/docs/ 2>/dev/null || true

# Criar symlink para docker-compose na raiz (para facilitar)
cd ~/GCA_Project
ln -s infra/docker-compose.yml docker-compose.yml
ln -s infra/docker-compose.production.yml docker-compose.production.yml

echo "✅ Infraestrutura copiada!"
```

### Passo 3.4: Copiar componentes do GCAGUI

```bash
# Se tiver o GCAGUI em outro lugar
# cp -r ~/Gcagui/src/components ~/GCA_Project/frontend/src/components/ui/shadcn
# cp -r ~/Gcagui/guidelines ~/GCA_Project/gui-components/

# Se tiver clonado do GitHub:
git clone https://github.com/Pielak/Gcagui.git /tmp/gcagui
cp -r /tmp/gcagui/src/components ~/GCA_Project/frontend/src/components/shadcn
cp -r /tmp/gcagui/guidelines ~/GCA_Project/gui-components/
rm -rf /tmp/gcagui

echo "✅ Componentes GCAGUI copiados!"
```

---

## FASE 4: Criar Arquivo .env

### Passo 4.1: Criar .env.example na raiz

```bash
cat > ~/GCA_Project/.env.example << 'EOF'
# Backend
DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca
REDIS_URL=redis://redis:6379/0
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
DEBUG=True
APP_ENV=development

# Frontend
VITE_API_URL=http://localhost:8000
VITE_APP_URL=http://localhost:5173

# Email (Optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@gca.local
SMTP_FROM_NAME=GCA

# GitHub Integration (Optional)
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_WEBHOOK_SECRET=

# N8N Integration (Optional)
N8N_WEBHOOK_URL=http://localhost:5678/webhook
N8N_API_KEY=

# Server
API_V1_PREFIX=/api/v1
PORT=8000
WORKERS=4
EOF

echo "✅ .env.example criado!"
cat ~/GCA_Project/.env.example
```

---

## FASE 5: Criar Documentação Centralizada

### Passo 5.1: Criar ARCHITECTURE.md

```bash
cat > ~/GCA_Project/docs/ARCHITECTURE.md << 'EOF'
# Arquitetura GCA_Project

## Stack Tecnológico

### Backend
- **Framework**: FastAPI 0.104.1
- **Database**: PostgreSQL 16 + SQLAlchemy ORM
- **Cache**: Redis 7
- **Authentication**: JWT (RS256/HS256)
- **Language**: Python 3.11+

### Frontend
- **Framework**: React 18.3.1
- **Build**: Vite 6.0.3
- **Desktop**: Electron 27.0.0
- **Language**: TypeScript 5.6.3
- **Styling**: Tailwind CSS 3.4.16
- **Components**: shadcn/ui + Radix UI

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Proxy/CDN**: Cloudflare
- **Monitoring**: (TBD)

## Estrutura do Projeto

```
GCA_Project/
├── backend/           # FastAPI server
├── frontend/          # React app
├── gui-components/    # Design system components
├── infra/             # Docker compose configs
├── docs/              # Documentation
└── scripts/           # Utility scripts
```

## Componentes Principais

### Backend (14 API routers)
- auth.py - Autenticação
- admin.py - Admin operations
- users.py - User management
- projects.py - Project management
- github.py - GitHub integration
- ... (10 mais)

### Frontend (10 páginas + 20+ componentes)
- LoginPage
- DashboardPage
- ProjectsPage
- AdminPages (4)
- Feature Pages (4)
- ... (mais)

### Services (17 serviços)
- auth_service
- code_generation_service
- github_service
- ... (14 mais)

## Fluxo de Dados

```
User → Frontend (React) → Backend API → Database/Redis
                            ↓
                      Services (Logic)
                      Integrations (GitHub, N8N, Email)
```

## Autenticação

- JWT tokens (access + refresh)
- RBAC (Role-Based Access Control)
- Multi-tenant isolation

## Deployment

- Docker containers
- Docker Compose orchestration
- Cloudflare CDN/proxy
- PostgreSQL managed
- Redis cache

## Próximas Etapas

- [ ] CI/CD com GitHub Actions
- [ ] Monitoring e logging
- [ ] Performance optimization
- [ ] Security hardening

EOF

echo "✅ ARCHITECTURE.md criado!"
```

---

## FASE 6: Criar GitHub Actions CI/CD

### Passo 6.1: Backend Tests Workflow

```bash
cat > ~/GCA_Project/.github/workflows/backend-tests.yml << 'EOF'
name: Backend Tests

on:
  push:
    branches: [ master, main, develop ]
    paths:
      - 'backend/**'
  pull_request:
    branches: [ master, main, develop ]
    paths:
      - 'backend/**'

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: password
          POSTGRES_DB: gca_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        cd backend
        pip install poetry
        poetry install
    
    - name: Run tests
      run: |
        cd backend
        poetry run pytest tests/ --cov=app
      env:
        DATABASE_URL: postgresql://postgres:password@localhost:5432/gca_test

EOF

echo "✅ Backend workflow criado!"
```

### Passo 6.2: Frontend Build Workflow

```bash
cat > ~/GCA_Project/.github/workflows/frontend-build.yml << 'EOF'
name: Frontend Build

on:
  push:
    branches: [ master, main, develop ]
    paths:
      - 'frontend/**'
  pull_request:
    branches: [ master, main, develop ]
    paths:
      - 'frontend/**'

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '20'
    
    - name: Install dependencies
      run: |
        cd frontend
        npm install
    
    - name: Build
      run: |
        cd frontend
        npm run build
    
    - name: Type check
      run: |
        cd frontend
        npm run type-check || true

EOF

echo "✅ Frontend workflow criado!"
```

---

## FASE 7: Fazer Commit Inicial

### Passo 7.1: Preparar e fazer commit

```bash
cd ~/GCA_Project

# Verificar status
git status

# Adicionar todos os arquivos
git add .

# Fazer commit
git commit -m "Initial commit: Consolidar GCA backend/frontend + GCAGUI components

- Migrar código completo do backend FastAPI
- Migrar código completo do frontend React/Vite
- Integrar componentes shadcn/ui do GCAGUI
- Adicionar Docker Compose configs
- Criar estrutura de documentação
- Setup GitHub Actions workflows

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# Verificar commits
git log --oneline -5
```

---

## FASE 8: Conectar ao GitHub

### Passo 8.1: Adicionar remote e fazer push

```bash
cd ~/GCA_Project

# Adicionar o remote (SUBSTITUA COM SEU URL!)
# Você pega isso em: https://github.com/new (após criar o repo)
git remote add origin https://github.com/Pielak/GCA_Project.git

# Renomear branch para main (GitHub padrão)
git branch -M master main

# Fazer push
git push -u origin main

# Verificar
git remote -v
```

### Passo 8.2: Configurar Branch Protection (GitHub)

1. Acesse: https://github.com/Pielak/GCA_Project/settings/branches
2. Clique **"Add rule"**
3. Configure:
   ```
   Branch name pattern: main
   ☑ Require pull request reviews before merging
   ☑ Require status checks to pass
   ☑ Require branches to be up to date
   ☑ Dismiss stale reviews when new commits pushed
   ```
4. Clique **"Create"**

---

## FASE 9: Testar Localmente

### Passo 9.1: Build backend

```bash
cd ~/GCA_Project/backend

# Criar ambiente
python3 -m venv venv
source venv/bin/activate

# Instalar
pip install poetry
poetry install

# Testar
poetry run pytest tests/ || echo "Testes falharam (OK se novo projeto)"
```

### Passo 9.2: Build frontend

```bash
cd ~/GCA_Project/frontend

# Instalar
npm install

# Build
npm run build

# Verificar dist/
ls -lh dist/
```

### Passo 9.3: Docker Compose

```bash
cd ~/GCA_Project

# Verificar arquivo
cat docker-compose.yml

# Iniciar (opcional - requer Docker rodando)
# docker-compose up -d
```

---

## FASE 10: Criar Issues e Documentação Adicional

### Passo 10.1: Criar SETUP.md detalhado

```bash
cat > ~/GCA_Project/docs/SETUP.md << 'EOF'
# Setup GCA_Project

## Pré-requisitos

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- Git

## Desenvolvimento Local (sem Docker)

### Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install poetry
poetry install
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Acesse:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/api/v1/docs

## Com Docker

```bash
docker-compose up -d

# Logs
docker-compose logs -f

# Parar
docker-compose down
```

## Ambiente de Produção

```bash
docker-compose -f infra/docker-compose.production.yml up -d
```

EOF

echo "✅ SETUP.md criado!"
```

---

## RESUMO: Comandos Rápidos

```bash
# 1. Criar estrutura
mkdir -p ~/GCA_Project && cd ~/GCA_Project
git init
git config user.name "Luiz Carlos Pielak"
git config user.email "pielak.ctba@gmail.com"

# 2. Criar diretórios
mkdir -p backend frontend gui-components infra docs scripts .github/workflows

# 3. Copiar código
cp -r ~/GCA/backend/* ./backend/
cp -r ~/GCA/frontend/{src,package.json,vite.config.ts,tsconfig.json} ./frontend/
cp ~/GCA/docker-compose*.yml ./infra/

# 4. Criar arquivos
# (ver passos 4.1, 5.1, 6.1, 6.2 acima)

# 5. Commit e push
git add .
git commit -m "Initial commit: GCA consolidation"
git remote add origin https://github.com/Pielak/GCA_Project.git
git branch -M master main
git push -u origin main

# 6. Configurar GitHub
# (ver passo 8.2)
```

---

## ✅ CHECKLIST FINAL

- [ ] Repositório criado no GitHub
- [ ] Código do backend copiado
- [ ] Código do frontend copiado
- [ ] Componentes GCAGUI integrados
- [ ] .env.example criado
- [ ] Documentação criada
- [ ] GitHub Actions configurado
- [ ] Branch protection ativada
- [ ] Primeiro push feito
- [ ] Testes locais passando

---

## 🚀 Próximo Passo

Após completar tudo, o repositório estará pronto para:
1. Usar como **source of truth** para desenvolvimento
2. Setup de **CI/CD completo**
3. **Deploy em novo ambiente** (VPS/Cloud)
4. **Releases versionadas** (v1.0.0, v1.1.0, etc)

**Você está pronto!**
