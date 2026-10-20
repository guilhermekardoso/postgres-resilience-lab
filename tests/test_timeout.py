import asyncio
import time

import pytest

from app.resilience.timeout import OperationTimeout, with_timeout


async def test_devolve_resultado_quando_termina_a_tempo():
    async def fast():
        return 42

    assert await with_timeout(fast, 0.5) == 42


async def test_lanca_operation_timeout_quando_passa_do_limite():
    async def slow():
        await asyncio.sleep(1)

    with pytest.raises(OperationTimeout):
        await with_timeout(slow, 0.05)


async def test_desiste_no_tempo_certo_sem_esperar_a_operacao():
    async def very_slow():
        await asyncio.sleep(5)

    start = time.perf_counter()
    with pytest.raises(OperationTimeout):
        await with_timeout(very_slow, 0.05)
    assert time.perf_counter() - start < 0.5


async def test_operacao_lenta_e_cancelada():
    events = []

    async def slow():
        try:
            await asyncio.sleep(0.2)
            events.append("terminou")
        except asyncio.CancelledError:
            events.append("cancelada")
            raise

    with pytest.raises(OperationTimeout):
        await with_timeout(slow, 0.05)
    await asyncio.sleep(0.3)
    assert events == ["cancelada"]


async def test_excecao_da_operacao_passa_sem_alteracao():
    async def boom():
        raise ValueError("erro da operação")

    with pytest.raises(ValueError, match="erro da operação"):
        await with_timeout(boom, 0.5)
