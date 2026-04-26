#!/usr/bin/env python3
"""
Dashboard de Monitoramento para GCA v0.1

Monitora logs durante testes e fornece estatísticas em tempo real:
  - Tempo de M01Service (geração de questionnaire)
  - Tempo de PersonasConsolidator (validação)
  - Erros encontrados
  - Performance metrics

Uso:
  python monitoring_dashboard.py --log-file /var/log/gca/app.log
  python monitoring_dashboard.py --follow (tail -f style)
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple


class GCAMonitoringDashboard:
    """Dashboard de monitoramento para GCA v0.1"""

    def __init__(self):
        self.metrics = defaultdict(list)
        self.errors = []
        self.start_time = time.time()

    def parse_log_line(self, line: str) -> Dict:
        """Parseia uma linha de log estruturada"""
        try:
            # Tentar parsiar como JSON (structlog format)
            if "{" in line:
                json_str = line[line.index("{"):]
                return json.loads(json_str)
        except:
            pass

        # Fallback: regex patterns para logs não-JSON
        patterns = {
            "m01_duration": r"M01.*?duration=(\d+\.?\d*)s",
            "persona_duration": r"Persona.*?duration=(\d+\.?\d*)s",
            "error": r"ERROR|CRITICAL|Exception",
            "questionnaire_count": r"questionnaire.*?count=(\d+)",
            "persona_approved": r"approved",
            "persona_needs_clarification": r"needs_clarification",
        }

        result = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                if key.endswith("_duration") or key.endswith("_count"):
                    result[key] = float(match.group(1))
                else:
                    result[key] = match.group(0)

        return result

    def process_log_file(self, log_path: Path, follow: bool = False):
        """Processa arquivo de log"""
        print("\n" + "=" * 80)
        print("DASHBOARD DE MONITORAMENTO GCA v0.1")
        print("=" * 80)
        print(f"Log: {log_path}")
        print(f"Timestamp: {datetime.now().isoformat()}\n")

        if not log_path.exists():
            print(f"❌ Arquivo de log não encontrado: {log_path}")
            return

        try:
            with open(log_path, "r") as f:
                # Se follow=True, pula para o final
                if follow:
                    f.seek(0, 2)

                while True:
                    line = f.readline()
                    if not line:
                        if not follow:
                            break
                        time.sleep(0.5)
                        continue

                    parsed = self.parse_log_line(line)

                    # Coletar métricas
                    if "m01_duration" in parsed:
                        self.metrics["m01_durations"].append(parsed["m01_duration"])

                    if "persona_duration" in parsed:
                        self.metrics["persona_durations"].append(parsed["persona_duration"])

                    if "questionnaire_count" in parsed:
                        self.metrics["questionnaire_counts"].append(parsed["questionnaire_count"])

                    if "persona_approved" in parsed:
                        self.metrics["personas_approved"].append(1)

                    if "persona_needs_clarification" in parsed:
                        self.metrics["personas_needs_clarification"].append(1)

                    if "error" in parsed:
                        self.errors.append(line.strip())

                    # Exibir dashboard a cada 10 eventos
                    if (
                        len(self.metrics["m01_durations"])
                        + len(self.metrics["persona_durations"])
                    ) % 10 == 0:
                        self.render_dashboard()

                    if not follow:
                        break

        except KeyboardInterrupt:
            print("\n[Interrompido pelo usuário]")
        except Exception as e:
            print(f"❌ Erro ao processar log: {e}")

        # Renderizar dashboard final
        self.render_dashboard()

    def render_dashboard(self):
        """Renderiza o dashboard de monitoramento"""
        print("\r" + " " * 80, end="")  # Limpar linha
        print("\r", end="")

        print("\n" + "=" * 80)
        print(f"DASHBOARD — {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 80)

        # M01 Metrics
        if self.metrics["m01_durations"]:
            m01_times = self.metrics["m01_durations"]
            print(f"\n📊 M01SERVICE (Geração de Questionnaire)")
            print(f"  Execuções: {len(m01_times)}")
            print(f"  Tempo médio: {sum(m01_times) / len(m01_times):.2f}s")
            print(f"  Mínimo: {min(m01_times):.2f}s")
            print(f"  Máximo: {max(m01_times):.2f}s")

        # Persona Metrics
        if self.metrics["persona_durations"]:
            persona_times = self.metrics["persona_durations"]
            print(f"\n🤖 PERSONAS (Validação)")
            print(f"  Execuções: {len(persona_times)}")
            print(f"  Tempo médio: {sum(persona_times) / len(persona_times):.2f}s")
            print(f"  Mínimo: {min(persona_times):.2f}s")
            print(f"  Máximo: {max(persona_times):.2f}s")

        # Questionnaire Counts
        if self.metrics["questionnaire_counts"]:
            counts = self.metrics["questionnaire_counts"]
            print(f"\n📋 QUESTIONNAIRES")
            print(f"  Total gerado: {len(counts)}")
            print(f"  Média de questões: {sum(counts) / len(counts):.1f}")
            print(f"  Range: {min(counts):.0f} - {max(counts):.0f} questões")

        # Personas Approved
        approved = len(self.metrics.get("personas_approved", []))
        needs_clarif = len(self.metrics.get("personas_needs_clarification", []))
        if approved or needs_clarif:
            print(f"\n✅ DECISÕES PERSONAS")
            print(f"  Aprovadas: {approved}")
            print(f"  Needs clarification: {needs_clarif}")

        # Erros
        if self.errors:
            print(f"\n❌ ERROS ({len(self.errors)})")
            for i, error in enumerate(self.errors[-5:], 1):  # Últimos 5
                print(f"  {i}. {error[:70]}...")

        print("\n" + "=" * 80 + "\n")

    def summary(self) -> Dict:
        """Retorna sumário das métricas"""
        return {
            "m01_calls": len(self.metrics["m01_durations"]),
            "persona_calls": len(self.metrics["persona_durations"]),
            "questionnaire_total": len(self.metrics["questionnaire_counts"]),
            "error_count": len(self.errors),
            "uptime_seconds": time.time() - self.start_time,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Dashboard de Monitoramento GCA v0.1"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="/var/log/gca/app.log",
        help="Caminho do arquivo de log (default: /var/log/gca/app.log)"
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Modo follow (tail -f style)"
    )

    args = parser.parse_args()

    dashboard = GCAMonitoringDashboard()
    dashboard.process_log_file(Path(args.log_file), follow=args.follow)

    # Sumário final
    summary = dashboard.summary()
    print("\n" + "=" * 80)
    print("SUMÁRIO FINAL")
    print("=" * 80)
    print(f"Chamadas M01: {summary['m01_calls']}")
    print(f"Chamadas Personas: {summary['persona_calls']}")
    print(f"Questionnaires: {summary['questionnaire_total']}")
    print(f"Erros: {summary['error_count']}")
    print(f"Uptime: {summary['uptime_seconds']:.1f}s")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
