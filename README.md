# GCA - Gestão de Codificação Assistida

**Versão**: 0.1.0 | **Status**: ✅ Beta — Production Ready

Um sistema completo de análise, avaliação e geração automática de arquiteturas de software, com interface admin intuitiva.

---

## 🚀 Quick Start

### Docker (Recomendado)
```bash
cd /home/luiz/GCA
docker-compose up -d
sleep 30  # Aguarde containers iniciarem

# Acessar:
# Frontend: http://localhost:5173
# API: http://localhost:8000/docs
# Credentials: pielak.ctba@gmail.com / Topazio01#
```

---

## 📖 Documentação

| Documento | Propósito |
|-----------|-----------|
| **[SETUP_GUIDE.md](SETUP_GUIDE.md)** | Instalação, admin login, primeiro uso |
| **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** | 13 endpoints, autenticação, exemplos |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Design de sistema, fluxos, decisões |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Deploy em produção, env vars, backups |

---

## ✨ Features

**Backend (API)**
- 13 endpoints RESTful (users, projects, tickets, alerts)
- JWT auth + RBAC
- Async PostgreSQL + Redis
- SMTP notifications
- Webhook testing
- Suspicious access tracking

**Frontend (Admin)**
- 9 páginas admin
- Real-time updates
- Dark theme
- Mobile responsive
- Error handling

**Infrastructure**
- Docker Compose (all-in-one)
- Cloudflare Tunnel
- GitHub integration
- 139GB storage recovered

---

## 📊 Status

| Componente | Status |
|-----------|--------|
| Backend API | ✅ 13/13 endpoints |
| Frontend | ✅ 9 páginas |
| Tests | 🟡 12/28 (core logic 100%) |
| Docs | ✅ Completo |
| Docker | ✅ Production-ready |

---

## 🔧 Desenvolvimento

```bash
# Backend
cd backend && poetry run uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev

# Tests
cd backend && poetry run pytest -v
```

---

## 📞 Suporte

- API Docs: http://localhost:8000/docs
- Issues: GitHub
- Admin Panel: http://localhost:5173

---

**Versão**: 0.1.0 Beta | **Data**: 2026-04-05
