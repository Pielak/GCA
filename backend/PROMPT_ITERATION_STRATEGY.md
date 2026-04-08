# Prompt Iteration Strategy - Continuous Improvement

## Overview

The improved prompts (FASE 4) establish a strong baseline. This document outlines how to iteratively improve prompt quality through feedback loops and empirical validation.

---

## Feedback Loop Architecture

```
Real Projects
    ↓
Capture OCG Output & Results
    ↓
Analyze Gaps & Misclassifications
    ↓
Update Prompts
    ↓
A/B Test with New Questions
    ↓
Validate Improvements (metrics)
    ↓
Deploy Updated Prompts
    ↓
→ (repeat)
```

---

## Metrics to Track

### 1. Classification Accuracy
**What to measure:** How often does the Analyzer classify questions into the correct pillar?

**Collection method:**
```python
# In test_ocg_e2e.py - add validation after analyzer runs
def validate_classification(analyzer_result, expected_classification):
    actual = analyzer_result.classification
    accuracy = sum(
        1 for pillar in expected_classification 
        if actual.get(pillar) == expected_classification[pillar]
    ) / 7  # 7 pillars
    return accuracy
```

**Target:** 95%+ accuracy (currently estimated at 85-90%)

**Action if low:** Update ANALYZER_USER_PROMPT_TEMPLATE with more context cues

---

### 2. Blocking Issues Detection
**What to measure:** Does P7 (Security) identify all blocking issues? Does P2 (Compliance) catch LGPD/GDPR gaps?

**Collection method:**
```python
def validate_blocking_detection(consolidator_result, known_blockers):
    detected_blockers = [
        f for f in consolidator_result.critical_findings 
        if f['severity'] == 'critical' and f['finding'].lower() in 
           [b.lower() for b in known_blockers]
    ]
    recall = len(detected_blockers) / len(known_blockers)
    return recall
```

**Target:** 95%+ recall (don't miss critical issues)

**Action if low:** Add explicit blocker examples to P7 and P2 prompts

---

### 3. Finding Specificity & Actionability
**What to measure:** Are findings specific and actionable, or generic?

**Scoring system:**
```python
# 1 = Generic ("Security needs work")
# 3 = Specific ("Custom JWT implementation increases vulnerability")
# 5 = Actionable ("Switch to Auth0, estimated 2-3 weeks, cost $500/mo")

def score_finding_specificity(finding):
    has_specific_problem = 1 if len(finding) > 50 else 0
    has_solution = 1 if "recommend" in finding.lower() or "migrate" in finding.lower() else 0
    has_estimate = 1 if any(x in finding for x in ["week", "month", "hour", "day", "$"]) else 0
    
    return has_specific_problem + has_solution + has_estimate
```

**Target:** Average score 4.5+ (mostly actionable)

**Action if low:** Add examples with specific recommendations to prompts

---

### 4. Stack Recommendation Quality
**What to measure:** Do stack recommendations align with project requirements?

**Validation criteria:**
- ✅ Backend matches project type (web_app gets web framework, daemon gets Go/Rust)
- ✅ Database choice justified for data type (transactional → PostgreSQL, flexible → MongoDB)
- ✅ Scaling approach matches team size and timeline
- ✅ Cost estimates within stated budget

**Collection method:**
```python
def validate_stack_recommendation(stack_rec, project_context):
    checks = {
        'backend_matches_type': stack_rec.backend.framework in approved_frameworks[project_context.type],
        'database_justified': 'rationale' in stack_rec.database and len(stack_rec.database.rationale) > 50,
        'cost_within_budget': estimate_cost(stack_rec) <= project_context.budget,
        'team_capability': stack_rec.backend.language in project_context.team_skills
    }
    return sum(checks.values()) / len(checks)
```

**Target:** 90%+ validation score

**Action if low:** Add project_type context to P5 prompt, add cost estimation examples

---

### 5. User Satisfaction
**What to measure:** Do developers/architects find OCG useful for code generation?

**Collection method:**
```python
# Post-OCG survey (1-5 scale)
feedback = {
    'findings_useful': 4.2,           # "How actionable were the findings?"
    'stack_matches_project': 4.1,     # "Does stack align with needs?"
    'would_use_again': 4.5,           # "Would you use OCG for next project?"
    'time_to_implement': "15 days",   # How long from OCG to MVP?
}
```

**Target:** 4.0+ average (useful), < 20 days to MVP

**Action if low:** Gather qualitative feedback on what was missing

---

### 6. Implementation Success Rate
**What to measure:** How often do projects succeed using the recommended stack?

**Success criteria:**
- ✅ Project launched on time
- ✅ Performance targets met
- ✅ No critical security issues found
- ✅ Team productivity within estimates

**Tracking:**
```python
def project_success_metrics(project_id):
    return {
        'launched_on_time': timeline_variance < 10,
        'performance_met': p95_latency <= target_latency,
        'security_score': penetration_test_score > 80,
        'team_velocity': actual_sprint_velocity >= estimated_velocity
    }
```

**Target:** 80%+ success rate

**Action if low:** Review failed projects for prompt blind spots

---

## Continuous Improvement Cycles

### Weekly: Quick Wins (15 min)
```
1. Check for classification errors in last N OCGs
2. Review any support tickets about unclear recommendations
3. Update 1-2 prompt examples based on patterns
4. A/B test with next 5 projects
```

### Monthly: Deep Analysis (2-4 hours)
```
1. Analyze all OCGs generated in the month
2. Calculate metrics (accuracy, blocker detection, satisfaction)
3. Identify top 3 areas for improvement
4. Refine corresponding prompts with examples
5. Test with historical questionnaires
6. Deploy if scores improve
```

### Quarterly: Major Iteration (1 day)
```
1. Gather feedback from all users (developers, architects, PMs)
2. Analyze failed projects - what was missed?
3. Review expert recommendations (security audits, code reviews)
4. Add new pillar-specific examples based on learnings
5. Test complete pipeline with diverse projects
6. Document changes in PROMPT_IMPROVEMENTS_LOG.md
```

---

## Specific Improvement Areas (Backlog)

### P1 (Business) - Current Quality: Good (85+)
- [ ] Add example for non-profit/open-source projects (different ROI metrics)
- [ ] Add example for B2B SaaS (longer sales cycle, different success metrics)
- [ ] Clarify stakeholder prioritization (who breaks ties?)

### P2 (Compliance) - Current Quality: Good (75+)
- [ ] Add more detailed HIPAA example (healthcare projects)
- [ ] Add PCI-DSS implementation examples (payment systems)
- [ ] Add cross-border data flow examples (GDPR + LGPD)

### P3 (Features) - Current Quality: Good (80+)
- [ ] Add MVP definition for mobile-first projects
- [ ] Add scope creep examples (feature bloat patterns)
- [ ] Add integration testing complexity guide

### P4 (NFR) - Current Quality: Fair (72)
- [ ] Add latency benchmarks by industry (e-commerce vs social media)
- [ ] Add concurrency examples (5k simultaneous vs 50k+)
- [ ] Add SLA/uptime examples with cost trade-offs

### P5 (Architecture) - Current Quality: Excellent (82)
- [ ] Add serverless architecture example (Lambda, Vercel)
- [ ] Add edge computing example (Cloudflare Workers)
- [ ] Add hybrid cloud example (on-prem + cloud)

### P6 (Data) - Current Quality: Good (76)
- [ ] Add sharding strategy for 100M+ records
- [ ] Add data warehouse example (BI, analytics)
- [ ] Add real-time data pipeline example (streaming)

### P7 (Security) - Current Quality: Fair (68)
- [ ] Add OAuth2 vs SAML comparison
- [ ] Add zero-trust security example
- [ ] Add vulnerability scanning integration examples

---

## Example: Monthly Improvement Cycle

### Month 1 - Baseline
```
Metrics:
- Classification accuracy: 87%
- Blocker detection recall: 92%
- Finding specificity: 3.8/5
- User satisfaction: 3.9/5
- Success rate: 75%

Top issues from feedback:
- "P4 recommends overkill for small team" (P5 doesn't adjust for team size)
- "Security findings too generic" (P7 needs more specific examples)
- "Stack doesn't mention testing tools" (P5 should include test frameworks)
```

### Month 2 - Updates
```
Changes made:
1. P5 prompt: Add "Team size constraint - for 5-person team, avoid microservices"
2. P7 prompt: Add 3 new specific security vulnerability examples
3. P5 prompt: Add "Include testing frameworks: Jest, pytest, Playwright"

Testing:
- A/B test with 20 new projects (10 old prompt, 10 new prompt)
- New prompt scores: 91% accuracy, 94% recall, 4.2/5 specificity, 4.2/5 satisfaction

Decision: Deploy new prompts
```

### Month 3 - Monitor & Adjust
```
Metrics improving:
- Classification accuracy: 91% (was 87%) ✅
- Finding specificity: 4.2/5 (was 3.8/5) ✅
- User satisfaction: 4.2/5 (was 3.9/5) ✅

Still needs work:
- Stack recommendations still 85% accuracy (need better P5 context)
- 1-2 projects per month still have "missed security issue" feedback

New hypothesis:
- P7 needs more context about project_type (web_app security ≠ mobile security)
- Consolidator might not be weighing P7 heavily enough

Next iteration:
- Add project_type context to P7 prompt
- Update Consolidator to increase P7 weight from 10% to 15%
```

---

## Testing Strategy

### Before Deploying New Prompts

1. **Regression Test**: Run against last 50 questionnaires
   - Ensure scores don't drop significantly
   - Check that blockers are still detected

2. **Golden Test Set**: Curate 10 diverse projects
   ```python
   test_projects = [
       "E-Commerce (web_app, 8 people, $150k budget)",
       "Mobile Game (mobile, 12 people, $500k budget)",
       "Enterprise API (api, 20 people, $1M budget)",
       "IoT Device (embedded, 4 people, $50k budget)",
       "SaaS Platform (web_app, 6 people, $200k budget)",
       # ... etc
   ]
   ```
   - Run with old and new prompts
   - Manual review of differences
   - Only deploy if new prompt is better for 8+/10 projects

3. **Metric Validation**:
   - New prompt must improve at least 2 metrics
   - Must not regress any metric by >5%
   - User satisfaction must stay 4.0+

---

## Tools & Infrastructure

### Metrics Dashboard (TODO - Nice to Have)
```python
# Pseudo-code for metrics collection
class OCGMetrics:
    def __init__(self, ocg_response, project_config, user_feedback=None):
        self.ocg = ocg_response
        self.project = project_config
        self.feedback = user_feedback
    
    def classification_accuracy(self, ground_truth):
        # Check Analyzer output
        pass
    
    def blocker_detection_recall(self, known_blockers):
        # Check P7 and P2 findings
        pass
    
    def finding_specificity_score(self):
        # Analyze critical_findings text
        pass
    
    def stack_validation_score(self):
        # Validate stack_recommendation against project
        pass
    
    def record_metrics(self):
        # Save to database for trending
        pass
```

### Versioning Prompts
```python
# app/services/agent_prompts.py should include version numbers
ANALYZER_SYSTEM_PROMPT_V2 = """..."""  # Current version (2.0)
ANALYZER_SYSTEM_PROMPT_V1 = """..."""  # Previous version (for rollback)

# Use config to select version
CURRENT_ANALYZER_VERSION = 2
ANALYZER_SYSTEM_PROMPT = globals()[f'ANALYZER_SYSTEM_PROMPT_V{CURRENT_ANALYZER_VERSION}']
```

---

## Long-Term Vision

### 6 Months
- Classification accuracy: 95%+
- All blockers detected (100% recall)
- Average finding specificity: 4.5/5
- 80%+ success rate for projects using OCG

### 12 Months
- Few-shot learning: OCG quality from context of previous projects
- Domain-specific prompts: Healthcare, Finance, E-Commerce variants
- Real-time feedback loop: User corrections → immediate prompt updates
- Integration with Code Generator: Stack recommendations validated against generated code

---

## Summary

The improved prompts are a solid foundation. Continuous iteration will compound improvements:

| Month | Classification | Blockers | Specificity | Satisfaction | Success |
|-------|-----------------|----------|-------------|--------------|---------|
| 1 | 87% | 92% | 3.8/5 | 3.9/5 | 75% |
| 3 | 91% | 94% | 4.2/5 | 4.2/5 | 78% |
| 6 | 94% | 96% | 4.5/5 | 4.4/5 | 82% |
| 12 | 96%+ | 99%+ | 4.7/5 | 4.6/5 | 85%+ |

**Key:** Collect metrics, identify patterns, refine prompts, validate improvements, deploy.
