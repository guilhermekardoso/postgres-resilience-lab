"""Bulkhead: limita quantas operações rodam ao mesmo tempo.

Quem chega com todas as vagas ocupadas espera no máximo `max_wait` segundos.
Se nenhuma vaga abrir, recebe BulkheadFullError sem executar nada. Sem esse
limite de espera, o bulkhead seria só mais uma fila infinita.
"""

import asyncio


class BulkheadFullError(Exception):
    pass


class Bulkhead:
    def __init__(self, max_concurrent: int, max_wait: float):
        # Um único semáforo para todas as chamadas: é ele que impõe o limite.
        self._slots = asyncio.Semaphore(max_concurrent)
        self._max_wait = max_wait

    async def call(self, operation):
        try:
            await asyncio.wait_for(self._slots.acquire(), self._max_wait)
        except TimeoutError as exc:
            raise BulkheadFullError() from exc
        try:
            return await operation()
        finally:
            # finally, e não except Exception: a vaga precisa voltar também quando a
            # operação é cancelada, e CancelledError não herda de Exception.
            self._slots.release()
