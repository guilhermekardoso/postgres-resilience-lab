from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("api_requests_total", "Requisições HTTP", ["route", "status"])
LATENCY = Histogram(
    "api_request_duration_seconds", "Latência HTTP medida na API", ["route"],
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30),
)

# "ok" ou o nome da exceção que saiu de run_protected (ex.: "CircuitOpenError").
REPORT_OUTCOMES = Counter("api_report_outcomes_total", "Resultado da rota de relatório", ["outcome"])

POOL_IN_USE = Gauge("api_pool_in_use", "Conexões do pool em uso")
POOL_WAITING = Gauge("api_pool_waiting", "Tarefas esperando uma conexão do pool")

BREAKER_STATE = Gauge("api_breaker_state", "Estado do circuit breaker: 0=closed 1=half_open 2=open")
_STATE_VALUES = {"closed": 0, "half_open": 1, "open": 2}


def report_breaker_state(state: str) -> None:
    """Chame isto do seu circuit breaker a cada transição para o estado aparecer no Grafana."""
    BREAKER_STATE.set(_STATE_VALUES[state])
