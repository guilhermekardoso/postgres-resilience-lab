"""Circuit breaker com três estados.

- closed: tudo passa, e as falhas seguidas são contadas. No limite, abre.
- open: tudo é recusado na hora, sem tocar na dependência.
- half_open: passado o tempo de recuperação, uma única chamada vai como prova.
  Se ela der certo, fecha. Se falhar ou for cancelada, abre de novo.

Não há Lock: no asyncio uma tarefa só cede a vez num `await`, e todas as decisões
de estado abaixo acontecem sem nenhum `await` no meio.

O relógio é injetado (`clock`) para os testes controlarem o tempo. O padrão é
time.monotonic, que nunca anda para trás.
"""

import asyncio
import time
from typing import Callable

from app.metrics import report_breaker_state

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: float,
                 clock: Callable[[], float] = time.monotonic):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.clock = clock
        self._state = CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False
        # Muda a cada transição. Serve para ignorar resultados de chamadas que
        # começaram num estado anterior e só terminaram agora.
        self._generation = 0

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, new_state: str) -> None:
        self._state = new_state
        self._generation += 1
        report_breaker_state(new_state)

    def _open(self) -> None:
        self._opened_at = self.clock()
        self._failures = 0
        self._set_state(OPEN)

    async def call(self, operation):
        # Ninguém vigia o relógio: quem percebe que o tempo passou é a próxima chamada.
        if self._state == OPEN:
            if self.clock() - self._opened_at < self.recovery_timeout:
                raise CircuitOpenError()
            self._set_state(HALF_OPEN)

        # _probe_in_flight diz se existe uma prova rodando; is_probe diz se é esta chamada.
        is_probe = False
        if self._state == HALF_OPEN:
            if self._probe_in_flight:
                raise CircuitOpenError()
            self._probe_in_flight = True
            is_probe = True

        generation = self._generation
        try:
            result = await operation()
        except asyncio.CancelledError:
            # Cancelamento não diz nada sobre a dependência. Na dúvida, volta a esperar.
            if is_probe:
                self._probe_in_flight = False
                self._open()
            raise
        except Exception:
            if is_probe:
                self._probe_in_flight = False
                self._open()
            elif generation == self._generation:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._open()
            raise
        else:
            if is_probe:
                self._probe_in_flight = False
                self._set_state(CLOSED)
            elif generation == self._generation:
                self._failures = 0
            return result
