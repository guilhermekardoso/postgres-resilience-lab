"""SEU CÓDIGO: circuit breaker.

Contrato (verificado por tests/test_circuit_breaker.py, em níveis; veja docs/ROTEIRO.md):
- `call(operation)` executa `await operation()` conforme o estado do circuito.
- `state` devolve "closed", "open" ou "half_open".
- No estado aberto, `call` lança `CircuitOpenError` SEM executar a operação.
- Toda exceção lançada pela operação conta como falha e é relançada para quem chamou.
- A passagem de "open" para "half_open" acontece na primeira chamada feita depois de
  `recovery_timeout` segundos. Antes dessa chamada, `state` pode continuar "open".
- Para medir tempo, use `self.clock()` (por padrão `time.monotonic`), nunca `time` direto:
  os testes trocam o relógio para controlar o tempo sem precisar esperar.

Dica de observabilidade: chame `app.metrics.report_breaker_state(novo_estado)` em cada
transição para o estado aparecer no Grafana.
"""

import time
from typing import Callable

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: float,
                 clock: Callable[[], float] = time.monotonic):
        raise NotImplementedError("implemente CircuitBreaker")

    @property
    def state(self) -> str:
        raise NotImplementedError("implemente CircuitBreaker.state")

    async def call(self, operation):
        raise NotImplementedError("implemente CircuitBreaker.call")
