"""Timeout para operações assíncronas.

O prazo vale para a operação inteira. Na rota de relatório isso inclui a espera
por uma conexão do pool, e não só a query: se cobrisse só a query, a fila do
pool continuaria sem limite.

Quando o prazo estoura, o asyncio.wait_for cancela a operação de verdade, e os
finally do caminho devolvem a conexão ao pool.
"""

import asyncio


class OperationTimeout(Exception):
    """O nosso prazo estourou. Diferente de um TimeoutError vindo do driver ou da rede."""


async def with_timeout(operation, seconds: float):
    try:
        return await asyncio.wait_for(operation(), seconds)
    except TimeoutError as exc:
        raise OperationTimeout() from exc
