# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please email security@agilize.com.br instead of using the issue tracker.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Security Measures

### Authentication & Authorization
- JWT tokens (HS256, 24h expiry)
- Bcrypt password hashing (cost=12)
- Role-based access control (admin/user)
- Session timeout on 401 unauthorized

### Data Protection
- PostgreSQL with encryption at rest (depends on deployment)
- HTTPS/TLS for all communications
- Secrets in environment variables (not in code)
- No sensitive data in logs

### Input Validation
- Pydantic models for API validation
- SQLAlchemy ORM prevents SQL injection
- React sanitizes user input for XSS prevention
- CORS configured to restrict origins

### Infrastructure Security
- Docker containers with minimal base images
- Regular security updates
- Health checks and monitoring
- Automated backups with 30-day retention
- Audit logging (future)

### Known Issues
- None currently. Report any issues privately.

## Compliance
- GDPR-ready (user data management)
- OWASP Top 10 protections
- NIST cybersecurity framework aligned

## Security Updates
We recommend updating to the latest version regularly for security patches.

```bash
docker-compose down
docker pull gca-backend:latest
docker pull gca-frontend:latest
docker-compose up -d
```

---

**Last Updated**: 2026-04-05
