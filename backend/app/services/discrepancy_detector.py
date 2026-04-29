"""Detecção de discrepâncias entre avaliações de personas.

MVP C: Quando 2+ personas discordam sobre campo do OCG, detecta,
visualiza e permite team resolver via votação/override/arbitragem.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Set
from uuid import UUID
import json

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DiscrepancyFound:
    """Discrepância detectada entre personas"""
    field_path: str  # "escopo", "arquitetura.stack", "dados.retention"
    conflicting_personas: List[str]  # ["gp", "qa", "dev_sr"]
    conflicting_values: Dict[str, Any]  # {"gp": "crítico", "qa": "baixa"}
    severity: str  # low, medium, high, critical
    category: Optional[str] = None


class DiscrepancyDetector:
    """Detecta conflitos entre OCG deltas de personas"""

    def __init__(self):
        self.severity_rules = {
            "escopo": "high",
            "arquitetura": "high",
            "dados": "high",
            "performance": "medium",
            "segurança": "high",
        }

    def detect_discrepancies(
        self,
        persona_responses: Dict[str, Dict[str, Any]],
    ) -> List[DiscrepancyFound]:
        """
        Compara ocg_deltas de todas personas e detecta discrepâncias.

        Args:
            persona_responses: Dict de {persona_name: {"ocg_delta": {...}, ...}}
                Ex: {
                    "gp": {"ocg_delta": {"escopo": "crítico"}, ...},
                    "qa": {"ocg_delta": {"escopo": "médio"}, ...},
                    "dba": {"ocg_delta": {"dados.schema": "normalizado"}, ...},
                }

        Returns:
            List[DiscrepancyFound] com conflitos detectados
        """
        discrepancies = []

        # 1. Extrair todos os campos de todos os deltas
        all_fields = {}  # {field_path: {persona_name: value}}

        for persona_name, response in persona_responses.items():
            ocg_delta = response.get("ocg_delta", {})
            if not ocg_delta:
                continue

            # Flatten OCG delta
            flat_delta = self._flatten_dict(ocg_delta)
            for field_path, value in flat_delta.items():
                if field_path not in all_fields:
                    all_fields[field_path] = {}
                all_fields[field_path][persona_name] = value

        # 2. Detectar campos com múltiplos valores diferentes
        for field_path, persona_values in all_fields.items():
            if len(persona_values) < 2:
                continue  # Apenas uma persona mencionou esse campo

            # Verificar se há discrepância
            unique_values = set()
            for v in persona_values.values():
                # Normalizar valor para comparação
                normalized = self._normalize_for_comparison(v)
                unique_values.add(normalized)

            if len(unique_values) > 1:
                # Há discrepância!
                discrepancy = self._create_discrepancy(field_path, persona_values)
                discrepancies.append(discrepancy)

        logger.info(
            "discrepancies_detected",
            field_count=len(all_fields),
            discrepancy_count=len(discrepancies),
        )

        return discrepancies

    def _flatten_dict(self, d: Dict, parent_key: str = "") -> Dict[str, Any]:
        """Flatten nested dict with dot notation: {"a": {"b": 1}} → {"a.b": 1}"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _normalize_for_comparison(self, value: Any) -> str:
        """Normalize value for comparison (lower case, trim, etc)"""
        if isinstance(value, str):
            return value.lower().strip()
        elif isinstance(value, (list, dict)):
            return json.dumps(value, sort_keys=True).lower()
        else:
            return str(value).lower().strip()

    def _create_discrepancy(
        self, field_path: str, persona_values: Dict[str, Any]
    ) -> DiscrepancyFound:
        """Create DiscrepancyFound from field and persona values"""
        personas = list(persona_values.keys())
        values = {p: v for p, v in persona_values.items()}

        # Determine severity from field path
        severity = "medium"
        category = None

        for key in ["escopo", "arquitetura", "dados", "segurança"]:
            if key in field_path.lower():
                severity = self.severity_rules.get(key, "medium")
                category = key
                break

        return DiscrepancyFound(
            field_path=field_path,
            conflicting_personas=personas,
            conflicting_values=values,
            severity=severity,
            category=category,
        )

    @staticmethod
    def categorize_field(field_path: str) -> str:
        """Categorize field for better UI grouping"""
        path_lower = field_path.lower()

        categories = {
            "escopo": ["escopo", "objetivo", "requisito"],
            "arquitetura": ["arquitetura", "stack", "padrão", "deployment"],
            "dados": ["dados", "schema", "migration", "retenção", "backup"],
            "performance": ["performance", "latência", "throughput", "cache"],
            "segurança": ["segurança", "auth", "criptografia", "compliance"],
            "testes": ["teste", "test", "coverage", "qa"],
            "implementação": ["implementação", "timeline", "equipe", "skills"],
        }

        for category, keywords in categories.items():
            if any(kw in path_lower for kw in keywords):
                return category

        return "geral"


def detect_persona_discrepancies(
    persona_responses: Dict[str, Dict[str, Any]],
) -> List[DiscrepancyFound]:
    """Convenience function to detect discrepancies"""
    detector = DiscrepancyDetector()
    return detector.detect_discrepancies(persona_responses)
