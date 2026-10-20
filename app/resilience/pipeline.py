"""Proteção usada pela rota de relatório.

Por enquanto, só o timeout.
"""

from app.config import settings
from app.resilience.timeout import with_timeout


async def run_protected(operation):
    return await with_timeout(operation, settings.timeout_ms / 1000)
