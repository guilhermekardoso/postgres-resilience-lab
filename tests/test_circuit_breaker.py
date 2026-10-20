"""Especificação do circuit breaker, em níveis.

Rode um nível por vez:  python -m pytest tests/test_circuit_breaker.py -k Nivel1
"""

import asyncio

import pytest

from app.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError

THRESHOLD = 3
RECOVERY = 10.0


class FakeClock:
    """Relógio controlado pelo teste: o tempo só anda quando chamamos advance()."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def breaker(clock):
    return CircuitBreaker(THRESHOLD, RECOVERY, clock=clock)


async def ok():
    return "ok"


async def boom():
    raise ConnectionError("banco fora")


class Spy:
    """Operação que registra quantas vezes foi executada."""

    def __init__(self, result="ok"):
        self.calls = 0
        self.result = result

    async def __call__(self):
        self.calls += 1
        return self.result


class Gated:
    """Operação que fica parada até o teste liberar (para simular chamadas em andamento)."""

    def __init__(self, fail=False):
        self.gate = asyncio.Event()
        self.fail = fail
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        await self.gate.wait()
        if self.fail:
            raise ConnectionError("banco fora")
        return "ok"


async def settle():
    """Dá algumas voltas no event loop para as tarefas criadas chegarem onde vão esperar."""
    for _ in range(10):
        await asyncio.sleep(0)


async def fail(breaker, times):
    for _ in range(times):
        with pytest.raises(ConnectionError):
            await breaker.call(boom)


async def open_circuit(breaker):
    await fail(breaker, THRESHOLD)
    assert breaker.state == "open"


class TestNivel1Basico:
    async def test_comeca_fechado(self, breaker):
        assert breaker.state == "closed"

    async def test_fechado_devolve_o_resultado(self, breaker):
        assert await breaker.call(ok) == "ok"

    async def test_fechado_relanca_a_excecao_da_operacao(self, breaker):
        with pytest.raises(ConnectionError):
            await breaker.call(boom)
        assert breaker.state == "closed"

    async def test_nao_abre_antes_do_limite(self, breaker):
        await fail(breaker, THRESHOLD - 1)
        assert breaker.state == "closed"

    async def test_abre_ao_atingir_o_limite_de_falhas(self, breaker):
        await fail(breaker, THRESHOLD)
        assert breaker.state == "open"

    async def test_aberto_rejeita_sem_executar_a_operacao(self, breaker):
        await open_circuit(breaker)
        spy = Spy()
        with pytest.raises(CircuitOpenError):
            await breaker.call(spy)
        assert spy.calls == 0


class TestNivel2FalhasConsecutivas:
    async def test_sucesso_zera_a_contagem_de_falhas(self, breaker):
        await fail(breaker, THRESHOLD - 1)
        await breaker.call(ok)
        await fail(breaker, THRESHOLD - 1)
        assert breaker.state == "closed"

    async def test_continua_rejeitando_antes_do_tempo_de_recuperacao(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY - 0.1)
        with pytest.raises(CircuitOpenError):
            await breaker.call(ok)


class TestNivel3MeioAberto:
    async def test_depois_do_tempo_deixa_uma_prova_passar(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        spy = Spy()
        assert await breaker.call(spy) == "ok"
        assert spy.calls == 1

    async def test_fica_meio_aberto_enquanto_a_prova_roda(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        probe = Gated()
        task = asyncio.create_task(breaker.call(probe))
        await settle()
        assert breaker.state == "half_open"
        probe.gate.set()
        await task

    async def test_prova_com_sucesso_fecha_o_circuito(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        await breaker.call(ok)
        assert breaker.state == "closed"

    async def test_depois_de_fechar_a_contagem_recomeca(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        await breaker.call(ok)
        await fail(breaker, THRESHOLD - 1)
        assert breaker.state == "closed"

    async def test_prova_com_falha_reabre_o_circuito(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        with pytest.raises(ConnectionError):
            await breaker.call(boom)
        assert breaker.state == "open"
        with pytest.raises(CircuitOpenError):
            await breaker.call(ok)

    async def test_reabrir_reinicia_o_tempo_de_recuperacao(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        with pytest.raises(ConnectionError):
            await breaker.call(boom)
        clock.advance(RECOVERY - 0.1)
        with pytest.raises(CircuitOpenError):
            await breaker.call(ok)
        clock.advance(0.1)
        assert await breaker.call(ok) == "ok"


class TestNivel4UmaProvaPorVez:
    async def test_rejeita_outras_chamadas_durante_a_prova(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        probe = Gated()
        task = asyncio.create_task(breaker.call(probe))
        await settle()
        spy = Spy()
        with pytest.raises(CircuitOpenError):
            await breaker.call(spy)
        assert spy.calls == 0
        probe.gate.set()
        assert await task == "ok"
        assert breaker.state == "closed"

    async def test_muitas_chamadas_simultaneas_so_uma_vira_prova(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        operation = Gated()
        tasks = [asyncio.create_task(breaker.call(operation)) for _ in range(20)]
        await settle()
        operation.gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert operation.calls == 1
        assert results.count("ok") == 1
        assert sum(isinstance(r, CircuitOpenError) for r in results) == 19


class TestNivel5Cancelamento:
    async def test_prova_cancelada_nao_trava_o_circuito(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        task = asyncio.create_task(breaker.call(Gated()))
        await settle()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        clock.advance(RECOVERY)
        assert await breaker.call(ok) == "ok"
        assert breaker.state == "closed"

    async def test_prova_cancelada_nao_conta_como_sucesso(self, breaker, clock):
        await open_circuit(breaker)
        clock.advance(RECOVERY)
        task = asyncio.create_task(breaker.call(Gated()))
        await settle()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert breaker.state != "closed"


class TestNivel6ResultadosAtrasados:
    """Chamadas que começaram ANTES de o circuito abrir e só terminam depois."""

    async def test_sucesso_atrasado_nao_fecha_um_circuito_aberto(self, clock):
        breaker = CircuitBreaker(1, RECOVERY, clock=clock)
        slow = Gated()
        old_call = asyncio.create_task(breaker.call(slow))
        await settle()
        await fail(breaker, 1)
        assert breaker.state == "open"
        slow.gate.set()
        assert await old_call == "ok"
        assert breaker.state == "open"

    async def test_falha_atrasada_nao_derruba_a_prova_em_andamento(self, clock):
        breaker = CircuitBreaker(1, RECOVERY, clock=clock)
        slow = Gated(fail=True)
        old_call = asyncio.create_task(breaker.call(slow))
        await settle()
        await fail(breaker, 1)
        clock.advance(RECOVERY)
        probe = Gated()
        probe_call = asyncio.create_task(breaker.call(probe))
        await settle()
        slow.gate.set()
        with pytest.raises(ConnectionError):
            await old_call
        assert breaker.state == "half_open"
        probe.gate.set()
        assert await probe_call == "ok"
        assert breaker.state == "closed"
