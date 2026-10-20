"""SEU CÓDIGO: bulkhead.

Contrato (verificado por tests/test_bulkhead.py):
- No máximo `max_concurrent` operações executam ao mesmo tempo dentro do bulkhead.
- Uma chamada que encontra o bulkhead cheio espera uma vaga por até `max_wait` segundos.
  Se a vaga não aparecer, lança `BulkheadFullError` sem executar a operação.
- A vaga é devolvida quando a operação termina, com sucesso OU com exceção.
- O resultado e as exceções da operação passam sem alteração.
"""


class BulkheadFullError(Exception):
    pass


class Bulkhead:
    def __init__(self, max_concurrent: int, max_wait: float):
        raise NotImplementedError("implemente Bulkhead")

    async def call(self, operation):
        raise NotImplementedError("implemente Bulkhead.call")
