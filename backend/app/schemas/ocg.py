"""OCG (Objeto Contexto Global) schemas - Agent request/response models"""
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ========== NESTED RESPONSE SCHEMAS ==========

class ProjectProfileSchema(BaseModel):
    """Project profile information"""
    name: str
    type: str  # web_app, mobile, api, desktop, daemon, executável, biblioteca
    team_size: int
    timeline_months: int
    budget_level: str  # low, medium, high
    description: Optional[str] = None


class PillarScoreDetail(BaseModel):
    """Individual pillar score with metadata"""
    score: float  # 0-100
    weight: float  # Weight in final calculation
    weighted_score: float
    maturity: str  # initial, developing, defined, managed, optimized
    risk_level: str  # low, medium, high, critical


class PillarScoresResponse(BaseModel):
    """All pillar scores"""
    P1_Business: PillarScoreDetail
    P2_Rules: PillarScoreDetail
    P3_Features: PillarScoreDetail
    P4_NFR: PillarScoreDetail
    P5_Architecture: PillarScoreDetail
    P6_Data: PillarScoreDetail
    P7_Security: PillarScoreDetail


class CompositeScoreResponse(BaseModel):
    """Final composite score"""
    overall: float
    status: str  # READY, NEEDS_REVIEW, AT_RISK, BLOCKED
    is_blocking: bool
    explanation: str


class StackRecommendationDetail(BaseModel):
    """Stack recommendation for specific layer"""
    language: Optional[str] = None
    framework: Optional[str] = None
    rationale: str


class StackRecommendation(BaseModel):
    """Complete stack recommendations"""
    output_type: str
    backend: StackRecommendationDetail
    frontend: Optional[StackRecommendationDetail] = None
    database: Dict[str, str]  # {primary, cache, etc}
    infrastructure: Dict[str, str]
    additional_services: List[Dict[str, str]] = []


class CriticalFinding(BaseModel):
    """Critical finding from analysis"""
    pillar: str
    severity: str  # info, warning, critical
    finding: str
    action_required: str
    before_codegen: bool
    impact: Optional[str] = None


class ComplianceChecklistItem(BaseModel):
    """Compliance requirement"""
    requirement: str
    status: str  # REQUIRED, CONDITIONAL, OPTIONAL
    implementation: List[str]


class TestingRequirementsDetail(BaseModel):
    """Testing type details"""
    coverage_target: str
    framework: Optional[str] = None
    tools: Optional[List[str]] = None
    priority: str


class TestingRequirements(BaseModel):
    """Complete testing requirements"""
    unit_tests: TestingRequirementsDetail
    integration_tests: TestingRequirementsDetail
    security_tests: Optional[TestingRequirementsDetail] = None
    performance_tests: Optional[TestingRequirementsDetail] = None
    automation: Dict[str, str]


class ArchitectureComponent(BaseModel):
    """Architecture component detail"""
    name: str
    responsibility: str
    technologies: Optional[str] = None


class ArchitectureOverview(BaseModel):
    """System architecture overview"""
    diagram: Optional[str] = None
    components: List[ArchitectureComponent]
    patterns: List[str]


class RiskItem(BaseModel):
    """Risk analysis item"""
    area: str
    risk: str
    mitigation: str


class RiskAnalysis(BaseModel):
    """Risk analysis"""
    high_risk_areas: List[RiskItem]
    dependencies: List[str]
    timeline_risks: List[str]


class ApprovalStatus(BaseModel):
    """Approval status"""
    can_proceed_to_codegen: bool
    admin_review_needed: bool
    blockers: List[str]
    recommendations: List[str]
    next_steps: List[str]


class DeliverableInfo(BaseModel):
    """Deliverable information"""
    code_structure: Dict[str, Any]
    documentation: List[Dict[str, str]]
    infrastructure: List[Dict[str, str]]
    tests: Dict[str, Any]


# ========== AGENT REQUEST/RESPONSE SCHEMAS ==========

class AnalyzerRequest(BaseModel):
    """Request to Agent 0: Analyzer"""
    questionnaire_id: UUID
    answers: List[Dict[str, Any]]
    project_metadata: Optional[Dict[str, Any]] = None


class ClassificationResult(BaseModel):
    """Classification of questions by pillar"""
    classification: Dict[str, List[str]]  # {P1: [Q1, Q2...], P2: [...]}
    extracted_info: Dict[str, Any]
    anomalies: List[Dict[str, Any]] = []


class AnalyzerResponse(BaseModel):
    """Response from Agent 0: Analyzer"""
    questionnaire_id: UUID
    classification: Dict[str, Any] = {}
    extracted_info: Any = {}
    anomalies: Any = []

    class Config:
        extra = "allow"


class PillarAgentRequest(BaseModel):
    """Request to Agents 1-7: Pillar Specialists"""
    pillar_id: int
    questionnaire_id: UUID
    questions: List[Dict[str, str]]
    responses: Dict[str, Any]
    project_metadata: Dict[str, Any]


class PillarFinding(BaseModel):
    """Finding from pillar agent - flexible structure"""
    class Config:
        extra = "allow"  # Allow additional fields from agents


class PillarAgentResponse(BaseModel):
    """Response from Agents 1-7: Pillar Specialists"""
    pillar_id: int
    score: float  # 0-100
    adherence_level: str  # LOW, MEDIUM, HIGH, CRITICAL, EXCELLENT, GOOD, POOR
    classification: Any = {}  # Flexible format
    findings: Any = []  # Can be list or dict
    stack_implications: Any = {}  # Flexible format
    checklist: Any = []  # Flexible format
    is_blocking: bool = False  # P7 (Security) can set this

    class Config:
        extra = "allow"  # Allow additional fields from agents


class ConsolidatorRequest(BaseModel):
    """Request to Agent 8: Consolidator"""
    questionnaire_id: UUID
    project_id: Optional[UUID] = None
    analyzer_output: AnalyzerResponse
    pillar_results: List[PillarAgentResponse]
    project_metadata: Dict[str, Any]


# ========== FINAL OCG RESPONSE ==========

class OCGResponse(BaseModel):
    """Complete OCG (Objeto Contexto Global) response"""
    ocg_id: UUID
    questionnaire_id: UUID
    project_id: Optional[UUID] = None
    generated_at: datetime

    # Flexible fields to accept any OCG structure from agents
    PROJECT_PROFILE: Any = {}
    PILLAR_SCORES: Any = {}
    COMPOSITE_SCORE: Any = {}
    STACK_RECOMMENDATION: Any = {}
    CRITICAL_FINDINGS: Any = []
    TESTING_REQUIREMENTS: Any = {}
    COMPLIANCE_CHECKLIST: Any = []
    DELIVERABLES: Any = {}
    ARCHITECTURE_OVERVIEW: Any = {}
    RISK_ANALYSIS: Any = {}
    APPROVAL_STATUS: Any = {}
    # DT-076 Fase 1 — modelo de dados derivado do stack + profile.
    # Inferência determinística via data_model_inference.infer_data_model.
    # Alimenta ddl_generator_service (Fase 2) e scaffolders (Fase 3).
    DATA_MODEL: Any = {}
    # MVP 19 Fase 19.1 — regras de negócio canônicas do domínio.
    # Lista de dicts com {id, title, description, source, created_at}
    # populada pelo GP manualmente ou pelo agente Consolidator quando
    # inferível do questionário/ingestão. Default [] preserva compat
    # com OCGs pré-19 — nenhum consumidor é obrigado a ter BUSINESS_RULES
    # populado. Alimenta a seção 3.3 do ERS (Fase 19.2).
    BUSINESS_RULES: Any = []

    class Config:
        from_attributes = True
        extra = "allow"


class OCGDetailResponse(BaseModel):
    """OCG with metadata (for GET requests)"""
    ocg: OCGResponse
    generated_by: Optional[str] = None
    generated_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    status: str
