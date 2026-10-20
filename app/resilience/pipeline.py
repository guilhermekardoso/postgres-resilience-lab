"""Proteção usada pela rota de relatório.

O bulkhead fica por fora: primeiro se decide se a requisição entra, depois se
cronometra só o trabalho no banco.
"""

from app.config import settings
from app.resilience.bulkhead import Bulkhead
from app.resilience.timeout import with_timeout

bulkhead = Bulkhead(settings.bulkhead_max_concurrent, settings.bulkhead_max_wait_ms / 1000)


async def run_protected(operation):
    return await bulkhead.call(lambda: with_timeout(operation, settings.timeout_ms / 1000))
