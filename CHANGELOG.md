# Changelog

All notable changes to GCA will be documented in this file.

## [0.1.0-beta] - 2026-04-05

### Added

#### Backend (FastAPI)
- 13 admin endpoints (users, projects, tickets, alerts, integrations)
- JWT authentication with role-based access control
- Async PostgreSQL ORM with SQLAlchemy 2.0
- Redis caching layer
- SMTP email notifications
- Webhook testing (Teams, Slack, Discord)
- Suspicious access tracking with brute-force protection
- Support tickets with response system
- System alerts with severity levels
- Dashboard metrics endpoint
- OpenAPI/Swagger documentation

#### Frontend (React)
- 9 admin pages (Dashboard, Users, Projects, Security, Settings, Tickets, Integrations, Alerts)
- 12 reusable components (Button, Modal, Table, Badge, Card, Toast, etc)
- 10 custom hooks (useAuth, useUsers, useProjects, useTickets, etc)
- Zustand state management
- React Query data fetching & caching
- React Hook Form + Zod validation
- Error Boundary for error handling
- Protected routes with JWT validation
- Dark theme (Tailwind CSS)
- Mobile-responsive design
- Production build (297KB gzipped)

#### Infrastructure
- Docker Compose setup (4 services)
- Cloudflare Tunnel integration
- GitHub integration
- Database migrations
- Automated backups
- Health checks
- Comprehensive documentation (README, API, Architecture, Deployment, Setup)
- Production deployment configuration

#### Testing
- 12/28 backend service layer tests passing
- Test factories for database seeding
- Async test fixtures

### Changed
- Recovered 139GB NVMe space via data migration to SSD
- Optimized frontend bundle size (297KB gzipped)
- Async database operations for better performance

### Security
- bcrypt password hashing
- JWT token authentication
- CORS protection
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (React sanitization)
- RBAC (admin/user roles)

### Known Limitations
- Endpoint HTTP tests need pytest-asyncio configuration (foundation set)
- No refresh token mechanism (session dies on token expiry)
- No real-time updates (WebSocket support needed)
- No bulk operations

### Future (v0.2.0+)
- Refresh token mechanism
- WebSocket real-time updates
- Bulk user operations
- Advanced filtering (date range, text search)
- Full HTTP endpoint test coverage
- Performance monitoring dashboard

---

## [0.0.1] - 2026-03-20

Initial project setup with basic models and CLI.
