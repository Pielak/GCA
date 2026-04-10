# FASE 5: Dashboard & Monitoring

## Overview

FASE 5 implements comprehensive monitoring, metrics aggregation, and dashboard endpoints for visualizing the entire GCA system. Real-time metrics track code generation costs, quality scores, system health, and project progress.

## Architecture

### Components

1. **MonitoringService** (`app/services/monitoring_service.py`)
   - Metrics aggregation and calculation
   - Cost tracking for multiple LLM providers
   - Quality assessment and trend analysis
   - Provider statistics and recommendations
   - Real-time dashboard data generation

2. **DashboardRouter** (`app/routers/dashboard.py`)
   - REST API endpoints for monitoring
   - Real-time metrics retrieval
   - Health checks and system status
   - Data export functionality

## Data Flow

```
Code Generation Events
        ↓
MonitoringService.track_generation()
        ↓
Database Artifact & Evaluation Records
        ↓
Metrics Aggregation:
  - Quality scores (7 pillars)
  - Cost calculations (per provider)
  - Timeline analysis
  - Project progress
        ↓
Dashboard API Endpoints
        ↓
Frontend/BI Tools Visualization
```

## File Structure

```
app/services/
  └── monitoring_service.py           # Metrics & monitoring logic

app/routers/
  └── dashboard.py                    # REST endpoints

app/tests/
  └── test_integration_dashboard_fase5.py  # Integration tests (11/11 passing)

FASE_5_DASHBOARD.md                   # This file
```

## REST API Endpoints

### 1. Dashboard Summary

```http
GET /api/v1/dashboard/summary
```

**Response:**
```json
{
  "timestamp": "2026-04-05T02:56:35Z",
  "projects": {
    "total": 32,
    "approved": 28,
    "pending": 4
  },
  "artifacts": {
    "total": 35,
    "evaluated": 21
  },
  "evaluations": {
    "total": 21,
    "average_score": 80.9,
    "p7_blocked": 3,
    "ready_for_codegen": 18
  },
  "system_health": {
    "status": "healthy",
    "last_update": "2026-04-05T02:56:35Z"
  }
}
```

**Use Case**: System overview dashboard, KPI tracking

### 2. Project Metrics

```http
GET /api/v1/dashboard/project/{project_id}
```

**Response:**
```json
{
  "project_id": "uuid",
  "project_name": "E-Commerce Platform",
  "project_slug": "ecommerce-platform",
  "status": "approved",
  "artifacts": {
    "total": 5
  },
  "evaluations": {
    "total": 5,
    "average_score": 82.4,
    "max_score": 88.0,
    "min_score": 75.0
  },
  "created_at": "2026-04-01T10:00:00Z",
  "approved_at": "2026-04-02T15:30:00Z"
}
```

**Use Case**: Project-specific metrics, progress tracking

### 3. Provider Statistics

```http
GET /api/v1/dashboard/providers
```

**Response:**
```json
{
  "timestamp": "2026-04-05T02:56:35Z",
  "providers": {
    "anthropic": {
      "cost_per_1k_tokens": {
        "input": 0.003,
        "output": 0.015
      },
      "estimated_latency_ms": {
        "min": 1500,
        "avg": 3000,
        "max": 10000
      },
      "recommended_for": "Best for quality code generation, recommended for production"
    },
    "openai": {...},
    "grok": {...},
    "deepseek": {...}
  },
  "recommendation": "Use Anthropic Claude for best quality, DeepSeek for lowest cost"
}
```

**Use Case**: Provider selection, cost optimization

### 4. Generation Timeline

```http
GET /api/v1/dashboard/timeline?days=7
```

**Response:**
```json
{
  "period_days": 7,
  "start_date": "2026-03-29T02:56:35Z",
  "end_date": "2026-04-05T02:56:35Z",
  "timeline": {
    "2026-03-29": 2,
    "2026-03-30": 4,
    "2026-04-01": 6,
    "2026-04-02": 8,
    "2026-04-03": 5,
    "2026-04-04": 7,
    "2026-04-05": 3
  },
  "total_in_period": 35
}
```

**Use Case**: Activity tracking, trend analysis, capacity planning

### 5. Quality Metrics

```http
GET /api/v1/dashboard/quality
```

**Response:**
```json
{
  "timestamp": "2026-04-05T02:56:35Z",
  "evaluation_status": {
    "approved": 15,
    "needs_review": 4,
    "blocked": 2
  },
  "pillar_averages": {
    "P1_Business": 85.3,
    "P2_Rules": 82.1,
    "P3_Functional": 84.7,
    "P4_NonFunctional": 81.5,
    "P5_Architecture": 86.2,
    "P6_Data": 83.9,
    "P7_Security": 79.8
  },
  "quality_assessment": "Good - Most pillars adequate"
}
```

**Use Case**: Quality assessment, pillar analysis, improvement areas

### 6. System Health

```http
GET /api/v1/dashboard/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-05T02:56:35Z",
  "projects": 32,
  "evaluations": 21,
  "message": "System healthy with 32 projects and 21 evaluations"
}
```

**Use Case**: Quick health check, uptime monitoring

### 7. Export Summary

```http
GET /api/v1/dashboard/export/summary
```

**Response:**
```json
{
  "export_timestamp": "2026-04-05T02:56:35Z",
  "dashboard_summary": {...},
  "quality_metrics": {...},
  "provider_statistics": {...}
}
```

**Use Case**: BI integration, reporting, data warehouse sync

## Key Features

### 1. Multi-Provider Cost Tracking

```python
Provider         Input/1K    Output/1K    Recommendation
─────────────────────────────────────────────────────────
Anthropic        $0.003      $0.015      Production (best quality)
OpenAI           $0.005      $0.015      Advanced reasoning
Grok             $0.002      $0.010      Fast & cost-effective
DeepSeek         $0.0005     $0.002      Lowest cost (volume)
```

**Dynamic Cost Calculation**:
- Estimates 70% input tokens, 30% output tokens per generation
- Returns estimated USD cost per generation
- Enables cost-aware provider selection

### 2. Quality Assessment

```
Pillar            Description                Default Weight
─────────────────────────────────────────────────────────
P1_Business       Business alignment        1.0
P2_Rules          Business rules            1.0
P3_Functional     Functional requirements   1.0
P4_NonFunctional  Performance/scalability   1.0
P5_Architecture   Architecture patterns     1.0
P6_Data           Data modeling             1.0
P7_Security       Security/compliance       1.0 (BLOCKER)
```

**Quality Levels**:
- **≥ 85**: Excellent - All pillars strong
- **75-84**: Good - Most pillars adequate
- **65-74**: Acceptable - Some pillars need improvement
- **< 65**: Needs Review - Multiple pillars below threshold

### 3. Performance Metrics

**Estimated Latency by Provider**:
```
Provider      Min (s)   Avg (s)   Max (s)
─────────────────────────────────────────
Grok          0.5       1.5       5.0      ← Fastest
DeepSeek      1.0       2.0       6.0
OpenAI        1.0       2.5       8.0
Anthropic     1.5       3.0       10.0     ← Most reliable
```

### 4. System Health Indicators

```
Status        Condition
──────────────────────────────────────
healthy       Projects approved, evaluations active
initializing  No projects yet, system starting up
degraded      Would indicate performance issues
```

## Metrics Explained

### Project Count

- **Total**: All projects in system
- **Approved**: Projects that passed admin review
- **Pending**: Awaiting admin approval
- **Ready for CodeGen**: Approved AND P7 not blocked

### Artifact Metrics

- **Total**: All artifacts created
- **Evaluated**: Artifacts with evaluations completed
- **Average Score**: Mean of all evaluation scores

### Evaluation Status

- **Approved** (≥80 avg): Ready for code generation
- **Needs Review** (60-79 avg): Requires refinement
- **Blocked** (<60 avg OR P7<70): Cannot proceed to codegen

## Usage Examples

### Get System Overview

```bash
curl http://localhost:8000/api/v1/dashboard/summary | jq .
```

### Monitor Project Progress

```bash
PROJECT_ID="uuid-here"
curl http://localhost:8000/api/v1/dashboard/project/$PROJECT_ID | jq '.evaluations'
```

### Compare Provider Costs

```bash
curl http://localhost:8000/api/v1/dashboard/providers | jq '.providers | map({name: .cost_per_1k_tokens})'
```

### Track 30-Day Activity

```bash
curl "http://localhost:8000/api/v1/dashboard/timeline?days=30" | jq '.timeline'
```

### Check Quality Trends

```bash
curl http://localhost:8000/api/v1/dashboard/quality | jq '.pillar_averages'
```

### Export for BI Tools

```bash
curl http://localhost:8000/api/v1/dashboard/export/summary > metrics.json
```

## Testing

### Test Coverage (11/11 tests passing) ✅

1. ✅ MonitoringService initialization
2. ✅ Track generation event with cost calculation
3. ✅ Get project metrics
4. ✅ Get provider statistics (4 providers)
5. ✅ Get dashboard summary
6. ✅ Get generation timeline
7. ✅ Get quality metrics
8. ✅ Cost calculation for each provider
9. ✅ Quality assessment logic
10. ✅ Provider recommendations
11. ✅ Integration with database

### Running Tests

```bash
PYTHONPATH=/home/luiz/GCA/backend python3 app/tests/test_integration_dashboard_fase5.py
```

## Integration with Previous Phases

### FASE 2: Project Management
- Tracks project creation and approval status
- Monitors project workflow progress

### FASE 3: Artifact Evaluation
- Aggregates pillar scores across all evaluations
- Calculates quality metrics and assessments
- Tracks P7 blocker enforcement

### FASE 4: Code Generation
- Tracks generation events with timestamps
- Calculates estimated costs per generation
- Records provider usage statistics

## Real-Time Monitoring Capabilities

1. **Live Project Status**: Real-time project health
2. **Quality Trends**: Pillar score progression
3. **Cost Tracking**: Per-provider usage and cost
4. **Activity Timeline**: Generation timeline and volume
5. **System Health**: Overall system status

## Performance Considerations

- **Query Optimization**: Aggregation queries use database-level counting
- **Caching**: Dashboard summary cached per request (no cache layer yet)
- **Scalability**: Supports unlimited projects and evaluations
- **Concurrent Requests**: All endpoints async-safe

## Security

✅ **Access Control**: All endpoints authenticated (JWT in main app)
✅ **Data Privacy**: No sensitive data exposed in metrics
✅ **Audit Trail**: Structured logging of all events
✅ **Cost Transparency**: Visible cost metrics for transparency

## Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/gca

# API
API_PREFIX=/api/v1
HOST=0.0.0.0
PORT=8000
```

### Cost Calculations (Built-in)

Provider costs are hardcoded based on official pricing:
```python
PROVIDER_COSTS = {
    "anthropic": {"input": 0.003, "output": 0.015},
    "openai": {"input": 0.005, "output": 0.015},
    "grok": {"input": 0.002, "output": 0.010},
    "deepseek": {"input": 0.0005, "output": 0.002}
}
```

## Dashboarding Tips

### For Frontend Integration

1. **Real-time**: Poll `/api/v1/dashboard/summary` every 30 seconds
2. **Project View**: Load `/api/v1/dashboard/project/{id}` on demand
3. **Analytics**: Use `/api/v1/dashboard/export/summary` for BI tools
4. **Health Check**: Monitor `/api/v1/dashboard/health` for status

### Recommended Visualizations

1. **System KPIs**: Cards showing key metrics
2. **Timeline Chart**: Line chart of artifacts over time
3. **Pillar Radar Chart**: 7-point radar for quality assessment
4. **Provider Pie Chart**: Cost breakdown by provider
5. **Project Status**: Table with approval status and scores

### Alert Thresholds

Consider alerting when:
- System health changes from "healthy" to "degraded"
- Average quality score drops below 70
- P7 blockers exceed 30% of evaluations
- Generation timeline shows downward trend

## Next Steps (FASE 6+)

1. **Code Validation**
   - Syntax validation for generated code
   - Security scanning
   - Dependency resolution

2. **Enhanced Dashboard**
   - Frontend React/Vue dashboard
   - Real-time WebSocket updates
   - Custom report generation

3. **Analytics**
   - Predictive quality scoring
   - Cost optimization recommendations
   - Provider recommendation engine

## References

- MonitoringService: `app/services/monitoring_service.py` (350+ lines)
- DashboardRouter: `app/routers/dashboard.py` (300+ lines)
- Tests: `app/tests/test_integration_dashboard_fase5.py` (400+ lines)
- Integration: `app/main.py` (dashboard router registered)
