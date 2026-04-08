# High-Quality OCG Example - E-Commerce Platform

This example shows what a high-quality OCG looks like with improved prompts (Opus reasoning applied).

## Project Context

```json
{
  "project_name": "E-Commerce Platform",
  "project_type": "web_app",
  "team_size": 8,
  "timeline_months": 12,
  "budget_level": "medium"
}
```

---

## Sample OCG Output (Improved Prompts)

### 1. Composite Score & Approval

```json
{
  "composite_score": {
    "overall": 78,
    "status": "NEEDS_REVIEW",
    "is_blocking": false,
    "explanation": "Strong business case and architecture (P1=85, P5=82) but security requires hardening before launch (P7=68 - below threshold). Recommend 2-week security sprint.",
    "pillar_scores": {
      "P1_Business": 85,
      "P2_Rules": 75,
      "P3_Features": 80,
      "P4_NFR": 72,
      "P5_Architecture": 82,
      "P6_Data": 76,
      "P7_Security": 68
    }
  }
}
```

### 2. Critical Findings (High Severity Only)

```json
{
  "critical_findings": [
    {
      "pillar": "P7_Security",
      "severity": "critical",
      "finding": "Authentication uses custom JWT implementation instead of OAuth2 - increases vulnerability surface",
      "action_required": "Switch to Auth0 or AWS Cognito (industry standard, battle-tested)",
      "before_codegen": true,
      "impact": "Can delay launch by 2-3 weeks if not fixed before development"
    },
    {
      "pillar": "P2_Rules",
      "severity": "critical",
      "finding": "LGPD/GDPR compliance strategy incomplete - no data retention or deletion policy defined",
      "action_required": "Define data retention (how long keep user data?), implement automated deletion after N days",
      "before_codegen": true,
      "impact": "Legal risk - cannot accept Brazilian/EU users without this"
    },
    {
      "pillar": "P4_NFR",
      "severity": "warning",
      "finding": "Performance target (200ms P95) ambitious for checkout flow with 3 external APIs",
      "action_required": "Plan caching strategy: Redis for product catalog, async order processing",
      "before_codegen": false,
      "impact": "Performance will degrade without proper caching - plan infrastructure carefully"
    }
  ]
}
```

### 3. Stack Recommendations (Specific with Rationale)

```json
{
  "stack_recommendation": {
    "output_type": "web_app",
    "backend": {
      "language": "Node.js",
      "framework": "NestJS",
      "rationale": "Async-first (handles 5k concurrent users), TypeScript (type safety), proven scalability (used by Stripe, Discord)"
    },
    "frontend": {
      "framework": "React 19",
      "build_tool": "Vite",
      "rationale": "Team familiar with React, Vite provides <2s HMR (hot reload), SPA for responsive UX"
    },
    "database": {
      "primary": "PostgreSQL 15 (users, orders, payments)",
      "secondary": "MongoDB (product catalogs - flexible schema)",
      "cache": "Redis (session, product cache, leaderboard)",
      "rationale": "PostgreSQL for transactional ACID data (orders are critical), MongoDB for flexible product data, Redis for performance (P95 <200ms)"
    },
    "infrastructure": {
      "orchestration": "Kubernetes (AWS EKS)",
      "messaging": "RabbitMQ (async order processing, email notifications)",
      "cdn": "CloudFront (static assets, product images)",
      "search": "Elasticsearch (product search with filters)",
      "rationale": "Kubernetes enables horizontal scaling (2-10 pods based on load), RabbitMQ decouples order processing from web requests, CDN reduces latency"
    },
    "additional_services": [
      {
        "service": "Auth0",
        "purpose": "OAuth2 authentication with MFA (security best practice)",
        "cost_estimate": "$500/month for 100k users"
      },
      {
        "service": "Stripe",
        "purpose": "Payment processing (PCI-DSS compliant)",
        "cost_estimate": "2.2% + $0.30 per transaction"
      },
      {
        "service": "Sendgrid",
        "purpose": "Transactional emails (order confirmations, password resets)",
        "cost_estimate": "$50/month for 100k emails"
      },
      {
        "service": "DataDog or New Relic",
        "purpose": "APM monitoring (detect P95 latency violations)",
        "cost_estimate": "$800/month"
      }
    ]
  }
}
```

### 4. Testing Requirements (Actionable Per Pillar)

```json
{
  "testing_requirements": {
    "unit_tests": {
      "coverage_target": "80%",
      "framework": "Jest (Node.js) + React Testing Library",
      "tools": ["Jest", "Sinon (mocking)", "SuperTest (API testing)"],
      "priority": "CRITICAL",
      "specific_areas": [
        "Order calculation logic (discounts, tax, shipping)",
        "Payment integration (Stripe webhook handling)",
        "User authentication (JWT validation, token refresh)",
        "LGPD compliance (data deletion, consent checks)"
      ]
    },
    "integration_tests": {
      "coverage_target": "60%",
      "framework": "Jest + Docker Compose (test databases)",
      "tools": ["Docker Compose", "Testcontainers", "SuperTest"],
      "priority": "CRITICAL",
      "specific_workflows": [
        "Complete checkout flow (add to cart → payment → confirmation)",
        "User registration with email verification",
        "Product search with filters and pagination",
        "Admin dashboard (create product, manage inventory)"
      ]
    },
    "security_tests": {
      "coverage_target": "OWASP Top 10",
      "framework": "SAST + DAST",
      "tools": ["Snyk (dependencies)", "SonarQube (code)", "OWASP ZAP (dynamic)", "npm audit"],
      "priority": "CRITICAL",
      "specific_tests": [
        "SQL injection (prepared statements validated)",
        "XSS prevention (input sanitization)",
        "CSRF protection (token validation)",
        "Authentication bypass attempts (JWT tampering)",
        "Authorization bypass (role-based access control)",
        "Encryption validation (TLS 1.3, AES-256)"
      ]
    },
    "performance_tests": {
      "coverage_target": "P95 <200ms",
      "framework": "Artillery or Locust",
      "tools": ["Artillery", "CloudWatch metrics"],
      "priority": "HIGH",
      "test_scenarios": [
        "Sustained 5k concurrent users (15 min duration)",
        "Spike test: 1k → 5k users in 30 seconds",
        "Slow network simulation (3G, 4G latency)",
        "Database query performance (1M+ product records)"
      ]
    },
    "compliance_tests": {
      "coverage_target": "LGPD/GDPR checklist",
      "framework": "Custom audit log analyzer",
      "tools": ["Audit logging", "Data classification tool"],
      "priority": "CRITICAL",
      "specific_checks": [
        "User consent captured (email, preferences)",
        "Data deletion works (GDPR 'right to be forgotten')",
        "Personal data export available (LGPD Article 19)",
        "Audit logs complete (who accessed what, when)"
      ]
    },
    "automation": {
      "ci_cd": "GitHub Actions (on every PR)",
      "schedule": "Nightly performance tests (11pm UTC)",
      "pre_deploy": "Security scan + unit tests (blocking)",
      "post_deploy": "Smoke tests (5 critical user flows)"
    }
  }
}
```

### 5. Compliance Checklist (from P2 Analysis)

```json
{
  "compliance_checklist": [
    {
      "requirement": "LGPD - Collect user consent before data processing",
      "status": "REQUIRED",
      "implementation": [
        "Add consent checkbox to registration form",
        "Store consent timestamp and version (audit trail)",
        "Implement preference center (email, marketing, analytics)",
        "Display privacy policy URL prominently"
      ]
    },
    {
      "requirement": "LGPD - Implement data deletion (right to be forgotten)",
      "status": "REQUIRED",
      "implementation": [
        "Add 'Delete my account' button in user settings",
        "Cascade delete: user → orders → order items → logs",
        "Anonymize for compliance: order history (keep for refunds), reviews (keep author name only)",
        "Document retention: 6 months after last activity for chargeback/fraud"
      ]
    },
    {
      "requirement": "LGPD - Data export functionality",
      "status": "REQUIRED",
      "implementation": [
        "Endpoint: /api/user/export-data (returns JSON)",
        "Include: profile, orders, addresses, preferences",
        "Download format: JSON or CSV (user choice)",
        "Delivery: immediate or email within 30 days"
      ]
    },
    {
      "requirement": "GDPR - Data residency (EU users)",
      "status": "CONDITIONAL",
      "implementation": [
        "If targeting EU: Database in EU region (eu-west-1 Ireland)",
        "For Brazil only: Can use us-east-1 with data residency clause",
        "Backup location: Same region or contractual restriction"
      ]
    },
    {
      "requirement": "PCI-DSS - Payment data handling",
      "status": "REQUIRED",
      "implementation": [
        "DO NOT store credit card data - use Stripe tokenization",
        "Accept Stripe tokens only in checkout",
        "Payment confirmation captured in logs (card last 4 digits only)",
        "Monthly PCI scanning (Stripe handles full PCI compliance)"
      ]
    }
  ]
}
```

### 6. Architecture Overview (from P5)

```json
{
  "architecture_overview": {
    "diagram": "See detailed architecture in docs/ARCHITECTURE.md",
    "components": [
      {
        "name": "API Gateway (Kong or AWS ALB)",
        "responsibility": "Route requests, rate limiting, request logging",
        "technologies": "Kong, AWS WAF for DDoS protection"
      },
      {
        "name": "Backend Services (NestJS microservices)",
        "responsibility": "Users, Products, Orders, Payments, Inventory",
        "technologies": "Node.js, TypeScript, NestJS, GraphQL for queries"
      },
      {
        "name": "Message Queue (RabbitMQ)",
        "responsibility": "Decouple order processing, async email/notifications",
        "technologies": "RabbitMQ, or SQS for serverless option"
      },
      {
        "name": "Data Layer",
        "responsibility": "Persistence, caching, search indexing",
        "technologies": "PostgreSQL, MongoDB, Redis, Elasticsearch"
      },
      {
        "name": "Frontend (React)",
        "responsibility": "User interface, shopping flow, admin dashboard",
        "technologies": "React 19, Vite, TailwindCSS, Zustand state management"
      }
    ],
    "patterns": [
      "Event-driven: Order placement → payment → email confirmation",
      "CQRS: Separate read (search) and write (orders) models",
      "Circuit breaker: Stripe integration (fail gracefully if API down)",
      "Bulkhead: Separate thread pools for payment vs inventory operations"
    ]
  }
}
```

### 7. Risk Analysis

```json
{
  "risk_analysis": {
    "high_risk_areas": [
      {
        "area": "Security - Custom authentication",
        "risk": "Vulnerabilities in JWT implementation, token leaks, session hijacking",
        "mitigation": "Migrate to Auth0 (handled by experts), MFA enforcement, short token TTL"
      },
      {
        "area": "Performance - Checkout flow",
        "risk": "High latency (>500ms) during peak traffic → abandoned carts",
        "mitigation": "Redis caching, CDN for assets, async order processing, load testing before launch"
      },
      {
        "area": "Compliance - LGPD/GDPR",
        "risk": "Data handling violations → fines up to 2-6% of revenue",
        "mitigation": "Legal review before launch, automated compliance tests, data deletion scripts"
      }
    ],
    "dependencies": [
      "Stripe API availability (payment processing)",
      "Database availability (order records)",
      "Authentication provider (Auth0 uptime)",
      "Email delivery (SendGrid) for critical notifications"
    ],
    "timeline_risks": [
      "12-month timeline ambitious - recommend 6m MVP, 12m full feature launch",
      "Security hardening (P7=68) will add 2-3 weeks - plan accordingly",
      "LGPD implementation takes 2-3 weeks (legal review + coding + testing)"
    ]
  }
}
```

### 8. Approval Status & Next Steps

```json
{
  "approval_status": {
    "can_proceed_to_codegen": true,
    "admin_review_needed": false,
    "blockers": [],
    "recommendations": [
      "BEFORE development starts: Conduct 2-day security workshop (P7 = 68 → 80+ target)",
      "BEFORE development starts: Legal review of LGPD/GDPR compliance checklist",
      "During development: Weekly performance benchmarks (P95 latency target)",
      "End of MVP (6 months): Security audit and penetration testing"
    ],
    "next_steps": [
      "1. Code generator produces boilerplate (3 days)",
      "2. Security team implements Auth0 + encryption (1 week)",
      "3. Team reviews architecture and adjusts (3 days)",
      "4. Sprint 1: Core features (user, product, cart) - 2 weeks",
      "5. Sprint 2-3: Checkout + payments - 4 weeks",
      "6. Testing + security hardening - 2 weeks",
      "7. MVP launch at 6 months (50% features)"
    ]
  }
}
```

---

## Key Improvements in This Example

### vs. Generic/Old Prompts:

| Aspect | Old | Improved |
|--------|-----|----------|
| Findings | "Security needs work" | "Custom JWT is risky, switch to Auth0 (add 2-3 weeks)" |
| Stack | "Node.js, PostgreSQL" | Full 5-layer stack with rationale, cost estimates, alternatives |
| Testing | "80% coverage" | Specific test scenarios (SQL injection, 5k concurrent users, GDPR deletion) |
| Blockers | None identified | P7=68 (below 70 threshold), P2=75 (borderline) - both flagged with fixes |
| Next steps | "Start coding" | 7-step detailed roadmap with time estimates and dependencies |

---

## How These Prompts Produce This Quality

1. **Analyzer**: Correctly classified all responses → gives specialist agents complete context
2. **P7 (Security)**: Detailed prompt identified custom JWT as risk → specific recommendation (Auth0)
3. **P2 (Compliance)**: Explicit LGPD/GDPR rules → compliance checklist automatically generated
4. **P4 (NFR)**: Prompted for specific latency targets → identified tension with external APIs
5. **P5 (Architecture)**: Full stack template → produced 5-component architecture with rationale
6. **Consolidator**: Weighted scoring + blocker rules → correctly determined "NEEDS_REVIEW" status

---

## Document Locations

- **Improved Prompts**: `/home/luiz/GCA/backend/app/services/agent_prompts.py`
- **Improvements Log**: `/home/luiz/GCA/backend/PROMPT_IMPROVEMENTS_LOG.md`
- **This Example**: `/home/luiz/GCA/backend/OCG_QUALITY_EXAMPLE.md`
