"""Proteção usada pela rota de relatório.

A ordem, de fora para dentro, é bulkhead, circuit breaker, timeout e operação:

- o bulkhead fica por fora para que uma recusa por excesso de carga não conte
  como falha do banco no circuit breaker;
- o timeout fica por dentro para que um prazo estourado chegue ao breaker como
  uma falha comum (OperationTimeout), e não como um cancelamento.
"""

from app.config import settings
from app.resilience.bulkhead import Bulkhead
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.timeout import with_timeout

bulkhead = Bulkhead(settings.bulkhead_max_concurrent, settings.bulkhead_max_wait_ms / 1000)
breaker = CircuitBreaker(settings.breaker_failure_threshold, settings.breaker_recovery_ms / 1000)


async def run_protected(operation):
    return await bulkhead.call(
        lambda: breaker.call(
            lambda: with_timeout(operation, settings.timeout_ms / 1000)
        )
    )
