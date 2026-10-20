"""Gerador de carga com dois fluxos:

- normal: sempre ligado, taxa baixa, metade /accounts e metade /reports.
  É o "usuário comum" que você quer proteger, e é ele que fornece as chamadas de prova.
- burst: liga/desliga, só /reports, taxa alta. É o que derruba o banco.

Modelo aberto: as requisições saem no ritmo configurado mesmo que a API esteja lenta
(como usuários reais, que não esperam os outros terminarem). Assim a fila aparece de verdade.
"""

import asyncio
from contextlib import asynccontextmanager
import os
import random
import time

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

TARGET_URL = os.getenv("TARGET_URL", "http://localhost:8000")
MAX_INFLIGHT = 2000

REQUESTS = Counter("loadgen_requests_total", "Respostas recebidas", ["stream", "route", "outcome"])
LATENCY = Histogram(
    "loadgen_request_duration_seconds", "Latência vista pelo cliente", ["route"],
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30),
)
INFLIGHT = Gauge("loadgen_inflight", "Requisições aguardando resposta")
DROPPED = Counter("loadgen_dropped_total", "Disparos descartados por excesso de requisições em voo", ["stream"])
BURST_ACTIVE = Gauge("loadgen_burst_active", "Rajada ligada (1) ou desligada (0)")
CONFIGURED_RPS = Gauge("loadgen_configured_rps", "Taxa configurada", ["stream"])


class Control:
    def __init__(self):
        self.normal_rps = float(os.getenv("NORMAL_RPS", "4"))
        self.burst_rps = float(os.getenv("BURST_RPS", "15"))
        self.burst_active = False
        self.inflight = 0

    def publish(self):
        BURST_ACTIVE.set(int(self.burst_active))
        CONFIGURED_RPS.labels(stream="normal").set(self.normal_rps)
        CONFIGURED_RPS.labels(stream="burst").set(self.burst_rps if self.burst_active else 0)

    def status(self):
        return {"normal_rps": self.normal_rps, "burst_rps": self.burst_rps,
                "burst_active": self.burst_active, "inflight": self.inflight}


control = Control()
_tasks: set[asyncio.Task] = set()


def pick_normal():
    if random.random() < 0.5:
        return "accounts", f"/accounts/{random.randint(1, 10000)}"
    return "reports", f"/reports/regions/{random.randint(1, 20)}"


def pick_burst():
    return "reports", f"/reports/regions/{random.randint(1, 20)}"


async def fire(client: httpx.AsyncClient, stream: str, route: str, path: str):
    control.inflight += 1
    INFLIGHT.inc()
    start = time.perf_counter()
    try:
        response = await client.get(path)
        outcome = str(response.status_code)
    except httpx.TimeoutException:
        outcome = "client_timeout"
    except httpx.HTTPError:
        outcome = "connection_error"
    finally:
        control.inflight -= 1
        INFLIGHT.dec()
    REQUESTS.labels(stream=stream, route=route, outcome=outcome).inc()
    LATENCY.labels(route=route).observe(time.perf_counter() - start)


async def arrivals(client: httpx.AsyncClient, stream: str, rate, pick):
    next_at = time.monotonic()
    while True:
        rps = rate()
        if rps <= 0:
            await asyncio.sleep(0.2)
            next_at = time.monotonic()
            continue
        next_at += 1 / rps
        delay = next_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        elif delay < -1:
            next_at = time.monotonic()  # atrasou demais: não tenta compensar de uma vez
        if control.inflight >= MAX_INFLIGHT:
            DROPPED.labels(stream=stream).inc()
            continue
        route, path = pick()
        task = asyncio.create_task(fire(client, stream, route, path))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    control.publish()
    async with httpx.AsyncClient(
        base_url=TARGET_URL, timeout=30,
        limits=httpx.Limits(max_connections=MAX_INFLIGHT, max_keepalive_connections=100),
    ) as client:
        loops = [
            asyncio.create_task(arrivals(client, "normal", lambda: control.normal_rps, pick_normal)),
            asyncio.create_task(arrivals(
                client, "burst",
                lambda: control.burst_rps if control.burst_active else 0, pick_burst)),
        ]
        yield
        for task in [*loops, *_tasks]:
            task.cancel()


app = FastAPI(title="Gerador de carga", lifespan=lifespan)


class Config(BaseModel):
    normal_rps: float | None = Field(default=None, ge=0, le=500)
    burst_rps: float | None = Field(default=None, ge=0, le=500)


@app.get("/status")
async def status():
    return control.status()


@app.post("/burst/on")
async def burst_on():
    control.burst_active = True
    control.publish()
    return control.status()


@app.post("/burst/off")
async def burst_off():
    control.burst_active = False
    control.publish()
    return control.status()


@app.post("/config")
async def configure(body: Config):
    if body.normal_rps is not None:
        control.normal_rps = body.normal_rps
    if body.burst_rps is not None:
        control.burst_rps = body.burst_rps
    control.publish()
    return control.status()


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def panel():
    return PANEL_HTML


PANEL_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Gerador de carga</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { max-width: 520px; margin: 40px auto; padding: 0 16px; }
  button { font-size: 1.1rem; padding: 12px 20px; border-radius: 8px; border: 1px solid #888;
           cursor: pointer; }
  #toggle.on { background: #c0392b; color: #fff; border-color: #c0392b; }
  #toggle.off { background: #27ae60; color: #fff; border-color: #27ae60; }
  label { display: block; margin: 12px 0 4px; }
  input { font-size: 1rem; padding: 6px; width: 100px; }
  .row { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
  pre { background: rgba(127,127,127,.15); padding: 12px; border-radius: 8px; }
</style></head><body>
<h1>Gerador de carga</h1>
<p><button id="toggle">...</button></p>
<div class="row">
  <div><label>Normal (req/s)</label><input id="normal" type="number" min="0" step="1"></div>
  <div><label>Rajada (req/s)</label><input id="burst" type="number" min="0" step="1"></div>
  <div><button id="apply">Aplicar</button></div>
</div>
<pre id="status"></pre>
<p><a href="http://localhost:3000" target="_blank">Abrir Grafana</a></p>
<script>
  const $ = (id) => document.getElementById(id);
  let current = null;
  function render(s) {
    current = s;
    $('status').textContent = JSON.stringify(s, null, 2);
    $('toggle').textContent = s.burst_active ? 'Desligar rajada' : 'Ligar rajada';
    $('toggle').className = s.burst_active ? 'on' : 'off';
    if (document.activeElement !== $('normal')) $('normal').value = s.normal_rps;
    if (document.activeElement !== $('burst')) $('burst').value = s.burst_rps;
  }
  async function post(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                   body: body ? JSON.stringify(body) : undefined });
    render(await r.json());
  }
  $('toggle').onclick = () => post(current && current.burst_active ? '/burst/off' : '/burst/on');
  $('apply').onclick = () => post('/config', { normal_rps: Number($('normal').value),
                                               burst_rps: Number($('burst').value) });
  async function poll() { try { render(await (await fetch('/status')).json()); } catch (e) {} }
  poll(); setInterval(poll, 1000);
</script></body></html>
"""
