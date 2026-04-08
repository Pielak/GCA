# GCA Architecture

**Versão**: 0.1.0 | **Data**: 2026-04-05

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                             │
│  React 18 Admin Dashboard (localhost:5173)                      │
│  - 9 Pages (Users, Projects, Tickets, Alerts, etc)             │
│  - Real-time updates (React Query)                              │
│  - Dark theme (Tailwind CSS)                                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS/API calls
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                         │
│  Backend (localhost:8000) - 13 Endpoints                        │
│  - REST API (OpenAPI/Swagger)                                   │
│  - JWT Authentication                                            │
│  - RBAC (Admin, User)                                           │
│  - Error handling & logging                                     │
└──────────────────────┬──────────────────────────────────────────┘
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    Database      Cache          External
   PostgreSQL      Redis           Services
   async ORM      Session          SMTP, IA
   Tables:        Caching         Providers
   - users
   - projects
   - tickets
   - alerts
```

---

## 📁 File Structure

```
GCA/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app setup
│   │   ├── core/
│   │   │   ├── config.py           # Environment vars
│   │   │   ├── security.py         # JWT, password hashing
│   │   │   └── constants.py        # Enums, magic strings
│   │   ├── models/
│   │   │   ├── base.py             # SQLAlchemy base (User, Project, etc)
│   │   │   ├── onboarding.py       # ProjectRequest
│   │   │   └── pillar.py           # (optional)
│   │   ├── db/
│   │   │   ├── database.py         # AsyncSession setup
│   │   │   ├── migrations/         # Alembic migrations
│   │   │   └── seed.py             # Test data (optional)
│   │   ├── services/
│   │   │   ├── admin_service.py    # Core business logic
│   │   │   │   ├── list_users()
│   │   │   │   ├── lock_user()
│   │   │   │   ├── get_suspicious_access()
│   │   │   │   ├── get_tickets()
│   │   │   │   ├── respond_to_ticket()
│   │   │   │   ├── test_webhook()
│   │   │   │   ├── get_alerts()
│   │   │   │   └── get_metrics()
│   │   │   └── (future: codegen, evaluation, etc)
│   │   ├── routers/
│   │   │   ├── auth.py             # POST /auth/login
│   │   │   ├── admin.py            # 13 admin endpoints
│   │   │   └── (future: others)
│   │   ├── middleware/
│   │   │   └── auth.py             # JWT validation
│   │   └── tests/
│   │       ├── conftest.py         # Fixtures
│   │       ├── factories.py        # Test data factories
│   │       └── test_admin_service.py
│   ├── requirements.txt / pyproject.toml
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── UsersPage.tsx
│   │   │   ├── ProjectsPage.tsx
│   │   │   ├── SecurityPage.tsx
│   │   │   ├── TicketsPage.tsx
│   │   │   ├── IntegrationsPage.tsx
│   │   │   ├── AlertsPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   ├── components/
│   │   │   ├── common/
│   │   │   │   ├── Button.tsx
│   │   │   │   ├── Modal.tsx
│   │   │   │   ├── Table.tsx
│   │   │   │   └── (others)
│   │   │   ├── ProtectedRoute.tsx
│   │   │   └── ErrorBoundary.tsx
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useUsers.ts
│   │   │   ├── useProjects.ts
│   │   │   ├── useTickets.ts
│   │   │   └── (others)
│   │   ├── stores/
│   │   │   ├── authStore.ts
│   │   │   └── toastStore.ts
│   │   ├── lib/
│   │   │   └── api.ts             # Axios + interceptors
│   │   └── App.tsx                # Router setup
│   ├── package.json
│   └── Dockerfile
│
└── docker-compose.yml             # 4 services setup
```

---

## 🔄 Data Flow

### 1. User Login

```
Frontend (React)
      │
      ├─ User enters email/password
      │
      ▼
POST /api/v1/auth/login (Axios)
      │
      ▼
Backend (FastAPI)
      │
      ├─ Validate email format
      ├─ Query User by email (SQLAlchemy)
      ├─ Verify password (bcrypt)
      ├─ Generate JWT token
      │
      ▼
Return { access_token, token_type }
      │
      ▼
Frontend stores token in localStorage
      │
      ▼
All future requests include:
Authorization: Bearer <token>
```

### 2. Get Users (Protected)

```
Frontend (React)
      │
      ├─ useUsers hook (React Query)
      │
      ▼
GET /api/v1/admin/users
      + Header: Authorization: Bearer <token>
      │
      ▼
Backend (FastAPI)
      │
      ├─ Middleware validates JWT token
      ├─ Extract user_id from token
      ├─ Check is_admin=true
      ├─ Query users from PostgreSQL
      │   SELECT * FROM users WHERE is_active=true
      ├─ Cache result in Redis (5 min)
      │
      ▼
Return JSON { users: [...], count: N }
      │
      ▼
React Query stores & displays
```

### 3. Lock User

```
Frontend (React)
      │
      ├─ User clicks lock button
      ├─ Confirmation modal
      │
      ▼
POST /api/v1/admin/users/{id}/lock
      + Header: Authorization: Bearer <token>
      │
      ▼
Backend (FastAPI)
      │
      ├─ Validate JWT
      ├─ Check admin permission
      ├─ Update user.is_active = false
      ├─ Log action to audit table
      ├─ Invalidate Redis cache
      │
      ▼
Return { message: "User locked" }
      │
      ▼
Frontend
      │
      ├─ Refetch users list (React Query)
      ├─ Show success toast
      │
      ▼
UI updates immediately
```

---

## 🗄️ Database Schema

### Core Tables

```sql
users
├── id (UUID, PK)
├── email (VARCHAR, unique)
├── password_hash (VARCHAR)
├── full_name (VARCHAR)
├── is_admin (BOOLEAN)
├── is_active (BOOLEAN)
└── created_at (TIMESTAMP)

projects / project_requests
├── id (UUID, PK)
├── gp_id (FK → users)
├── project_name (VARCHAR)
├── project_slug (VARCHAR, unique)
├── description (TEXT)
├── status (ENUM: pending, approved, rejected, active)
└── created_at (TIMESTAMP)

support_tickets
├── id (UUID, PK)
├── user_id (FK → users)
├── project_id (FK → projects)
├── title (VARCHAR)
├── description (TEXT)
├── severity (ENUM: BAIXO, MÉDIO, ALTO, CRÍTICO)
├── status (ENUM: ABERTO, FECHADO)
├── resolved_at (TIMESTAMP, nullable)
└── created_at (TIMESTAMP)

access_attempts
├── id (UUID, PK)
├── user_id (FK → users)
├── project_id (FK → projects)
├── attempt_number (INT)
├── blocked (BOOLEAN)
├── blocked_at (TIMESTAMP, nullable)
└── created_at (TIMESTAMP)

system_alerts
├── id (UUID, PK)
├── alert_type (VARCHAR)
├── severity (ENUM: critical, warning, info)
├── title (VARCHAR)
├── message (TEXT)
├── status (ENUM: pending, acknowledged)
├── acknowledged_at (TIMESTAMP, nullable)
└── created_at (TIMESTAMP)
```

---

## 🔐 Security Model

### Authentication
- **JWT tokens** (HS256)
- 24-hour expiry
- Bearer token in Authorization header
- Refresh token flow (future)

### Authorization (RBAC)
- **is_admin** flag on User
- Admin-only endpoints checked in middleware
- Non-admin users get 403 Forbidden

### Password Security
- bcrypt hashing (cost=12)
- Salted automatically by passlib
- Never stored in plaintext

### API Security
- Rate limiting (future)
- CORS configured
- Input validation (Pydantic)
- SQL injection protected (SQLAlchemy ORM)
- XSS protected (React escapes by default)

---

## 🚀 Technology Choices

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | React 18 + TypeScript | Modern, typed, ecosystem |
| **Styling** | Tailwind CSS | Utility-first, dark theme |
| **State** | Zustand | Lightweight, simple |
| **Data Fetch** | React Query | Caching, refetch, loading |
| **Backend** | FastAPI | Async, auto-docs, fast |
| **Database** | PostgreSQL | Reliable, async-safe |
| **Cache** | Redis | Session, caching |
| **Auth** | JWT | Stateless, scalable |
| **ORM** | SQLAlchemy 2.0 | Typed, async-ready |
| **Validation** | Pydantic v2 | Auto-validation |

---

## 📊 Performance Optimizations

### Frontend
- Code splitting (React Router lazy)
- Gzipped bundle (297KB)
- React Query caching (5-30 min)
- Skeleton loaders

### Backend
- Async/await (asyncio)
- Connection pooling (SQLAlchemy)
- Redis caching
- Indexed database queries

### Database
- Indexes on frequently queried columns
- Foreign keys with ON CASCADE
- Timestamps with TZ awareness
- ENUM for status fields

---

## 🔄 Development Workflow

### Local Development

```bash
# Terminal 1: Backend
cd backend
poetry run uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev

# Terminal 3: Database
docker-compose up gca-postgres gca-redis
```

### Testing

```bash
cd backend
poetry run pytest -v
```

### Git Workflow

```bash
git checkout -b feature/my-feature
# ... make changes ...
git add -A
git commit -m "Add my feature"
git push origin feature/my-feature
# Create PR on GitHub
```

---

## 🎯 Scalability Considerations

### Current Limits
- Single instance: ~100 concurrent users
- Database: 1 PostgreSQL server
- Cache: 1 Redis instance

### To Scale Up
1. **Horizontal scaling** (Kubernetes)
   - Multiple backend instances
   - Load balancer (nginx)
   
2. **Database**
   - Read replicas
   - Connection pooling (PgBouncer)
   
3. **Cache**
   - Redis Cluster
   - Session replication

---

**Próximo**: Leia [DEPLOYMENT.md](DEPLOYMENT.md) para deploy em produção.
