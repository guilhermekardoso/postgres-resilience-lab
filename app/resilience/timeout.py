"""SEU CÓDIGO: timeout.

Contrato (verificado por tests/test_timeout.py):
- `operation` é uma função sem argumentos que devolve um awaitable (ex.: `lambda: db.region_report(1)`).
- Se a operação terminar dentro de `seconds`, devolve o resultado dela.
- Se passar do limite, lança `OperationTimeout`.
- A operação que estourou o tempo é cancelada; ela não continua rodando em segundo plano.
- Exceções lançadas pela própria operação passam sem alteração.
"""


class OperationTimeout(Exception):
    pass


async def with_timeout(operation, seconds: float):
    raise NotImplementedError("implemente with_timeout")
