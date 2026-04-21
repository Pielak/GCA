"""MVP 20 — Portas canônicas para integrações externas.

Cada arquivo define a interface (ABC) que adapters concretos
(Jira, Trello, Sonar, Snyk, Slack, …) devem implementar.

Tese arquitetural: GCA é hub que consome ferramentas externas via
adapter pattern. Portas são determinísticas, sem LLM no caminho crítico.
"""
