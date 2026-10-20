import asyncio

import pytest

from app.resilience.bulkhead import Bulkhead, BulkheadFullError


async def settle():
    """Dá algumas voltas no event loop para as tarefas criadas chegarem onde vão esperar."""
    for _ in range(10):
        await asyncio.sleep(0)


async def test_devolve_resultado_da_operacao():
    bulkhead = Bulkhead(2, 0.05)
    assert await bulkhead.call(lambda: asyncio.sleep(0, result=7)) == 7


async def test_nunca_passa_do_limite_de_concorrencia():
    bulkhead = Bulkhead(3, 0.01)
    active = peak = 0

    async def operation():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1

    results = await asyncio.gather(*(bulkhead.call(operation) for _ in range(20)),
                                   return_exceptions=True)
    assert peak == 3
    assert sum(isinstance(r, BulkheadFullError) for r in results) == 17
    assert active == 0


async def test_chamada_rejeitada_nao_executa_a_operacao():
    bulkhead = Bulkhead(1, 0.01)
    gate = asyncio.Event()
    executed = False

    async def other():
        nonlocal executed
        executed = True

    holder = asyncio.create_task(bulkhead.call(gate.wait))
    await settle()
    with pytest.raises(BulkheadFullError):
        await bulkhead.call(other)
    assert executed is False
    gate.set()
    await holder


async def test_espera_vaga_que_abre_dentro_do_max_wait():
    bulkhead = Bulkhead(1, 0.5)
    holder = asyncio.create_task(bulkhead.call(lambda: asyncio.sleep(0.05)))
    await settle()
    assert await bulkhead.call(lambda: asyncio.sleep(0, result="entrou")) == "entrou"
    await holder


async def test_devolve_a_vaga_depois_de_excecao():
    bulkhead = Bulkhead(1, 0.01)

    async def boom():
        raise ValueError()

    with pytest.raises(ValueError):
        await bulkhead.call(boom)
    assert await bulkhead.call(lambda: asyncio.sleep(0, result=1)) == 1


async def test_devolve_a_vaga_quando_a_operacao_e_cancelada():
    bulkhead = Bulkhead(1, 0.01)
    holder = asyncio.create_task(bulkhead.call(asyncio.Event().wait))
    await settle()
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder
    assert await bulkhead.call(lambda: asyncio.sleep(0, result=1)) == 1
