# Circuit Breaker Lab

Ambiente pronto para **implementar à mão** timeout, bulkhead e circuit breaker em Python (FastAPI + asyncpg) e ver o efeito de cada peça num banco que realmente não aguenta a carga.

A infraestrutura já está pronta. A lógica de resiliência fica por sua conta.

## O cenário

```
                       ┌──────────── API (FastAPI) ─────────────┐
gerador de carga ──►   │ /accounts/{id}        ─────────────────┼──► pool (10 conexões) ──► Postgres fraco
 normal: sempre on     │ /reports/regions/{id} ─► run_protected ┼──►        ▲                (0,5 CPU, 256 MB)
 rajada: on/off        └──────────────────────────(SEU CÓDIGO)──┘        │
                                                                   as duas rotas dividem o pool
```

- **`/accounts/{id}`**: consulta leve, por chave primária. É a rota "essencial" e não passa pela sua proteção.
- **`/reports/regions/{id}`**: consulta pesada (lê 1 milhão de linhas, ~120 ms com o banco ocioso). Passa por `run_protected`.
- O banco processa cerca de **8 relatórios/s**. O tráfego normal pede ~2/s e a rajada pede mais 15/s.

Sem proteção, a rajada enche o pool, a rota leve entra na mesma fila e tudo fica lento, inclusive o que não tem nada a ver com o relatório.

## O que é seu e o que é infraestrutura

| Arquivo | Dono |
|---|---|
| `app/resilience/timeout.py` | **você** |
| `app/resilience/bulkhead.py` | **você** |
| `app/resilience/circuit_breaker.py` | **você** |
| `app/resilience/pipeline.py` | **você** (composição das três peças) |
| `tests/` | especificação: os testes dizem o que cada peça precisa fazer |
| `app/main.py`, `app/db.py`, `app/metrics.py`, `app/config.py` | infraestrutura |
| `loadgen/`, `observability/`, `database/`, `docker-compose.yml` | infraestrutura |

Cada arquivo seu começa com o **contrato** (o que precisa fazer) e lança `NotImplementedError`.

## Subir

Pré-requisito: Docker Desktop. Para os testes, Python 3.11 ou mais novo.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

Na primeira vez, o Postgres leva ~30 s para criar 1 milhão de linhas.

| O quê | Onde |
|---|---|
| Painel do gerador de carga (botão on/off) | <http://localhost:8001> |
| Grafana (sem login) | <http://localhost:3000> |
| API e Swagger | <http://localhost:8000/docs> |
| Prometheus | <http://localhost:9090> |

A rajada também pode ser controlada por linha de comando:

```powershell
Invoke-RestMethod -Method Post http://localhost:8001/burst/on
Invoke-RestMethod -Method Post http://localhost:8001/burst/off
```

## Ciclo de trabalho

1. Escreva o código em `app/resilience/`.
2. Rode os testes localmente:
   ```powershell
   python -m pip install -r requirements-dev.txt
   python -m pytest tests/test_timeout.py
   python -m pytest tests/test_circuit_breaker.py -k Nivel1
   ```
3. A API recarrega sozinha quando você salva um arquivo de `app/` (o diretório é montado no container). O recarregamento zera o estado do breaker e as métricas da API.
4. Ligue a rajada e observe o Grafana.

O passo a passo completo, em fases, está em **[docs/ROTEIRO.md](docs/ROTEIRO.md)**.

## Ajustes

Tudo fica no `.env`. Depois de mudar, recrie o serviço:

| Variável | Efeito | Aplicar com |
|---|---|---|
| `PG_CPUS`, `PG_MEM`, `PG_MAX_CONNECTIONS` | quão fraco é o banco | `docker compose up -d postgres` |
| `POOL_MAX_SIZE` | conexões da API | `docker compose up -d api` |
| `TIMEOUT_MS`, `BULKHEAD_*`, `BREAKER_*` | parâmetros do seu código (`app.config.settings`) | `docker compose up -d api` |
| `NORMAL_RPS`, `BURST_RPS` | carga inicial (também ajustável no painel) | `docker compose up -d loadgen` |

## Quando travar

- **A API ficou presa numa fila enorme** (acontece de propósito sem proteção): `docker compose restart api`.
- **Recriar o banco do zero**: `docker compose down -v` e depois `docker compose up -d`.
- **CPU e memória do Postgres em tempo real**: `docker stats circuit_breaker-postgres-1`.
