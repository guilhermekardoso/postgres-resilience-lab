"""SEU CÓDIGO: composição da proteção.

A rota /reports/regions/{id} chama `run_protected(operation)` para cada consulta ao banco.
Hoje a operação passa direto, sem proteção nenhuma. Esse é o cenário de referência.

Quando suas peças estiverem prontas, crie as instâncias aqui (uma vez, no nível do módulo)
e componha as três dentro de `run_protected`. A ORDEM da composição importa; descobrir
por que é um dos objetivos do laboratório.

Os parâmetros estão em `app.config.settings` (vêm do .env):
    settings.timeout_ms, settings.bulkhead_max_concurrent, settings.bulkhead_max_wait_ms,
    settings.breaker_failure_threshold, settings.breaker_recovery_ms
"""


async def run_protected(operation):
    return await operation()
