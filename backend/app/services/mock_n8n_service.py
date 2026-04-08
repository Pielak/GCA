"""
Mock N8N Service
Simula N8N webhook e workflow execution para testes e demos
"""
import structlog
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4
import asyncio

logger = structlog.get_logger(__name__)


class MockN8NService:
    """Mock N8N service for testing workflow orchestration"""

    def __init__(self):
        self.workflows = {}  # workflow_id -> workflow state
        self.webhooks = {}  # webhook_id -> webhook data

    async def trigger_workflow(
        self,
        project_slug: str,
        language: str,
        architecture: str,
        onboarding_id: str
    ) -> Dict[str, Any]:
        """
        Simula trigger de workflow N8N

        Simula execução de pipeline:
        1. Webhook received
        2. Piloter API called
        3. Results cached
        4. Workflow completed
        """

        workflow_id = str(uuid4())
        execution_id = str(uuid4())

        logger.info("n8n.workflow_triggered",
                   workflow_id=workflow_id,
                   project_slug=project_slug,
                   language=language,
                   architecture=architecture)

        # Simulate async workflow execution
        self.workflows[workflow_id] = {
            "id": workflow_id,
            "execution_id": execution_id,
            "status": "running",
            "project_slug": project_slug,
            "language": language,
            "architecture": architecture,
            "onboarding_id": onboarding_id,
            "started_at": datetime.now(timezone.utc),
            "progress": 0,
            "result": None,
            "error": None
        }

        # Simulate workflow execution in background
        asyncio.create_task(self._simulate_workflow_execution(workflow_id))

        return {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "status": "triggered",
            "project_slug": project_slug,
            "estimated_completion_seconds": 2
        }

    async def _simulate_workflow_execution(self, workflow_id: str):
        """Simula execução async do workflow"""

        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return

        try:
            # Step 1: Receive webhook (0.2s)
            workflow["progress"] = 20
            workflow["status"] = "processing"
            await asyncio.sleep(0.2)

            # Step 2: Call Piloter API (1.0s)
            workflow["progress"] = 40
            recommendations = await self._fetch_stack_recommendations(
                workflow["language"],
                workflow["architecture"]
            )
            await asyncio.sleep(0.5)

            # Step 3: Process results (0.5s)
            workflow["progress"] = 60
            await asyncio.sleep(0.3)

            # Step 4: Cache results (0.2s)
            workflow["progress"] = 80
            await asyncio.sleep(0.1)

            # Step 5: Complete (0.1s)
            workflow["progress"] = 100
            workflow["status"] = "completed"
            workflow["result"] = {
                "stack": recommendations["stack"],
                "recommendations": recommendations["recommendations"],
                "cached_at": datetime.now(timezone.utc).isoformat()
            }

            logger.info("n8n.workflow_completed",
                       workflow_id=workflow_id,
                       status="success")

        except Exception as e:
            workflow["status"] = "failed"
            workflow["error"] = str(e)
            logger.error("n8n.workflow_failed",
                        workflow_id=workflow_id,
                        error=str(e))

    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Poll workflow status"""

        workflow = self.workflows.get(workflow_id)

        if not workflow:
            return {
                "status": "not_found",
                "error": f"Workflow {workflow_id} not found"
            }

        result = {
            "workflow_id": workflow_id,
            "status": workflow["status"],
            "progress": workflow["progress"],
            "result": workflow["result"],
            "error": workflow["error"]
        }

        return result

    async def _fetch_stack_recommendations(
        self,
        language: str,
        architecture: str
    ) -> Dict[str, Any]:
        """Simula resposta do Piloter API"""

        recommendations = {
            "python-microservices": {
                "stack": {
                    "language": "Python",
                    "framework": "FastAPI",
                    "database": "PostgreSQL",
                    "frontend": "Vue.js",
                    "deployment": "Docker/Kubernetes",
                    "message_queue": "RabbitMQ",
                    "cache": "Redis"
                },
                "recommendations": [
                    "Use async/await for high concurrency",
                    "Implement database connection pooling",
                    "Use message queue for async tasks",
                    "Cache frequent queries with Redis"
                ],
                "score": 9.2
            },
            "python-monolith": {
                "stack": {
                    "language": "Python",
                    "framework": "Django",
                    "database": "PostgreSQL",
                    "frontend": "React",
                    "deployment": "Docker",
                    "cache": "Redis",
                    "message_queue": "Celery"
                },
                "recommendations": [
                    "Use Django ORM with select_related/prefetch_related",
                    "Implement caching strategy with Redis",
                    "Use Celery for background tasks",
                    "Consider Django REST Framework for APIs"
                ],
                "score": 8.8
            },
            "nodejs-microservices": {
                "stack": {
                    "language": "Node.js",
                    "framework": "NestJS",
                    "database": "MongoDB",
                    "frontend": "React",
                    "deployment": "Docker/Kubernetes",
                    "message_queue": "Apache Kafka",
                    "cache": "Redis"
                },
                "recommendations": [
                    "Use TypeScript for type safety",
                    "Implement proper error handling middleware",
                    "Use connection pooling for databases",
                    "Monitor performance with APM tools"
                ],
                "score": 8.9
            },
            "java-microservices": {
                "stack": {
                    "language": "Java",
                    "framework": "Spring Boot",
                    "database": "PostgreSQL",
                    "frontend": "Angular",
                    "deployment": "Docker/Kubernetes",
                    "message_queue": "Apache Kafka",
                    "cache": "Redis"
                },
                "recommendations": [
                    "Use Spring Cloud for microservices patterns",
                    "Implement circuit breakers with Hystrix/Resilience4j",
                    "Use Spring Data JPA for database access",
                    "Monitor with Spring Boot Actuator"
                ],
                "score": 9.0
            }
        }

        # Map language + architecture to recommendation
        key = f"{language.lower()}-{architecture.lower()}"

        if key in recommendations:
            result = recommendations[key].copy()
        else:
            # Default recommendation
            result = {
                "stack": {
                    "language": language,
                    "framework": "TBD",
                    "database": "PostgreSQL",
                    "frontend": "TBD",
                    "deployment": "Docker",
                    "cache": "Redis"
                },
                "recommendations": [
                    f"Review {language} best practices",
                    f"Apply {architecture} patterns",
                    "Implement proper monitoring",
                    "Use CI/CD pipeline"
                ],
                "score": 7.5
            }

        result["alternatives"] = [
            r for k, r in recommendations.items()
            if k != key
        ][:2]  # Top 2 alternatives

        return result

    def get_mock_data(self) -> Dict[str, Any]:
        """Retorna dados mock úteis para testes"""

        return {
            "project_stacks": {
                "python-microservices": {
                    "language": "Python",
                    "framework": "FastAPI",
                    "database": "PostgreSQL",
                    "frontend": "Vue.js",
                    "deployment": "Kubernetes",
                    "description": "High-performance async microservices"
                },
                "nodejs-microservices": {
                    "language": "Node.js",
                    "framework": "NestJS",
                    "database": "MongoDB",
                    "frontend": "React",
                    "deployment": "Kubernetes",
                    "description": "JavaScript full-stack microservices"
                },
                "python-monolith": {
                    "language": "Python",
                    "framework": "Django",
                    "database": "PostgreSQL",
                    "frontend": "React",
                    "deployment": "Docker",
                    "description": "Traditional monolithic architecture"
                },
                "java-microservices": {
                    "language": "Java",
                    "framework": "Spring Boot",
                    "database": "PostgreSQL",
                    "frontend": "Angular",
                    "deployment": "Kubernetes",
                    "description": "Enterprise microservices with Spring Cloud"
                }
            },
            "technologies": {
                "frameworks": ["FastAPI", "Django", "NestJS", "Spring Boot", "Express"],
                "databases": ["PostgreSQL", "MongoDB", "MySQL", "Redis", "Elasticsearch"],
                "frontends": ["React", "Vue.js", "Angular", "Svelte"],
                "deployment": ["Docker", "Kubernetes", "AWS", "GCP", "Azure"]
            },
            "best_practices": {
                "microservices": [
                    "API Gateway pattern",
                    "Service discovery",
                    "Circuit breaker",
                    "Message queue",
                    "Distributed tracing"
                ],
                "monolith": [
                    "Modular architecture",
                    "Caching strategy",
                    "Database optimization",
                    "Background jobs",
                    "Load balancing"
                ]
            }
        }


# Singleton instance
_mock_n8n_instance = None


def get_mock_n8n_service() -> MockN8NService:
    """Get or create mock N8N service instance"""
    global _mock_n8n_instance
    if _mock_n8n_instance is None:
        _mock_n8n_instance = MockN8NService()
    return _mock_n8n_instance
