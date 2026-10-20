from contextlib import asynccontextmanager

import asyncpg

from app.metrics import POOL_IN_USE, POOL_WAITING


class Database:
    """Acesso ao Postgres. As duas rotas da API dividem o MESMO pool."""

    def __init__(self, url: str, max_size: int):
        self.url = url
        self.max_size = max_size
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=self.max_size)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def _connection(self):
        # pool.acquire() não tem limite de espera: se o pool está cheio, a tarefa entra
        # numa fila sem fim. Repare em api_pool_waiting no Grafana.
        POOL_WAITING.inc()
        try:
            connection = await self.pool.acquire()
        finally:
            POOL_WAITING.dec()
        POOL_IN_USE.inc()
        try:
            yield connection
        finally:
            try:
                await self.pool.release(connection)
            finally:
                POOL_IN_USE.dec()

    async def account(self, account_id: int) -> dict | None:
        """Consulta leve: busca por chave primária."""
        async with self._connection() as connection:
            row = await connection.fetchrow(
                "SELECT id, name, region_id FROM accounts WHERE id = $1", account_id
            )
        return dict(row) if row else None

    async def region_report(self, region_id: int) -> list[dict]:
        """Consulta pesada: lê a tabela de transações inteira."""
        async with self._connection() as connection:
            rows = await connection.fetch(
                """
                SELECT date_trunc('month', t.created_at)::date AS month,
                       count(*)::int                         AS transactions,
                       sum(t.amount_cents)::bigint           AS total_cents
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE a.region_id = $1
                GROUP BY 1
                ORDER BY 1
                """,
                region_id,
            )
        return [dict(row) for row in rows]
