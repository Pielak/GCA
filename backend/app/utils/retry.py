"""
GCA Self-Healing — Retry automático para operações assíncronas críticas.

Aplique @gca_retry() em qualquer serviço que chame LLM ou I/O externo.
Comportamento: até MAX_RETRIES tentativas com backoff exponencial (1s→2s→4s→max 60s).
Em falha total: reraise da exceção original (registrada no audit log pelo chamador).
"""
import os
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger("gca.retry")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))


def gca_retry():
    """
    Decorator de retry para serviços críticos do GCA.

    Uso:
        @gca_retry()
        async def analyze_document(self, ...):
            ...

    MAX_RETRIES (env): número de tentativas. Padrão 3. Máximo recomendado 5.
    """
    return retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=1, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
