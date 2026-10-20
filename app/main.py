from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import settings
from app.db import Database
from app.metrics import LATENCY, REPORT_OUTCOMES, REQUESTS
from app.resilience.pipeline import run_protected

db = Database(settings.database_url, settings.pool_max_size)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="Circuit Breaker Lab", lifespan=lifespan)


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    REQUESTS.labels(route=path, status=str(response.status_code)).inc()
    LATENCY.labels(route=path).observe(time.perf_counter() - start)
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/accounts/{account_id}")
async def account(account_id: int):
    """Rota essencial e leve. Não passa pela sua proteção, mas divide o pool com o relatório."""
    try:
        data = await db.account(account_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=type(exc).__name__)
    if data is None:
        raise HTTPException(status_code=404, detail="account not found")
    return data


@app.get("/reports/regions/{region_id}")
async def region_report(region_id: int):
    """Rota pesada. Toda chamada ao banco passa por run_protected (o seu código)."""
    try:
        rows = await run_protected(lambda: db.region_report(region_id))
    except Exception as exc:
        # Qualquer exceção vira 503; o nome da classe aparece na resposta e no Grafana.
        outcome = type(exc).__name__
        REPORT_OUTCOMES.labels(outcome=outcome).inc()
        raise HTTPException(status_code=503, detail=outcome)
    REPORT_OUTCOMES.labels(outcome="ok").inc()
    return {"region_id": region_id, "months": rows}
