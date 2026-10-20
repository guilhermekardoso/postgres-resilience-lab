# Roteiro

Cada fase tem a mesma estrutura: **implementar → passar nos testes → ligar no pipeline → observar no Grafana → responder às perguntas**. Escreva as respostas em algum lugar antes de seguir; é aí que o aprendizado fica.

Um experimento padrão, usado em todas as fases:

1. Deixe o sistema 30 s só com o tráfego normal.
2. **Ligue a rajada** em <http://localhost:8001> e espere 60 s.
3. **Desligue a rajada** e observe por mais 60 s.

---

## Fase 0: sentir o problema (sem escrever código)

Rode o experimento padrão com `pipeline.py` do jeito que está.

**Observe no Grafana:**
- *Pool de conexões*: "em uso" trava em 10 e "esperando conexão" cresce sem parar.
- *Latência p95 vista pelo cliente*: a linha **accounts** sobe junto com **reports**.
- Depois de desligar a rajada, quanto tempo leva para tudo voltar ao normal?

**Perguntas:**
1. A rota `/accounts` não foi tocada pela rajada. Por que ela ficou lenta?
2. O banco processa ~8 relatórios/s e chegam ~17/s. A que ritmo a fila cresce? Confira no painel.
3. O cliente desiste depois de 30 s (`client_timeout`). O que acontece com a requisição dentro da API depois disso? (Dica: a fila continua diminuindo devagar mesmo com a rajada desligada.)
4. Por que o sistema demora tanto para se recuperar se a carga já voltou ao normal?

Se a API ficar presa, use `docker compose restart api`.

---

## Fase 1: timeout

**Implemente** `app/resilience/timeout.py` até `python -m pytest tests/test_timeout.py` passar.

**Ligue no pipeline**, só o timeout por enquanto:

```python
async def run_protected(operation):
    return await with_timeout(operation, settings.timeout_ms / 1000)
```

Rode o experimento padrão.

**Perguntas:**
1. A fila do pool ainda cresce sem limite? Por quê?
2. O timeout de 1 s cobre o quê: só a query, ou também a espera por uma conexão? Olhe `app/db.py`.
3. A rota `/accounts` melhorou? Ficou boa?
4. Quanto tempo a recuperação leva agora, comparando com a Fase 0?
5. O teste `test_operacao_lenta_e_cancelada` exige o cancelamento. O que aconteceria no banco se a operação não fosse cancelada?

---

## Fase 2: bulkhead

**Implemente** `app/resilience/bulkhead.py` até `python -m pytest tests/test_bulkhead.py` passar.

**Ligue no pipeline** junto com o timeout. Você decide a ordem: o bulkhead envolve o timeout, ou o contrário?

**Perguntas:**
1. Com `BULKHEAD_MAX_CONCURRENT=6` e um pool de 10, quantas conexões sobram para `/accounts`? Veja no Grafana se isso se confirma.
2. Em que ordem você compôs as peças, e por quê? Teste a outra ordem e compare o painel *Rota de relatório: resultado por tipo*.
3. Para que serve o `max_wait`? O que acontece com `BULKHEAD_MAX_WAIT_MS=0`? E com `5000`?
4. O que é melhor para o usuário do relatório: esperar 30 s ou receber 503 em 50 ms?
5. Por que o teste `test_devolve_a_vaga_quando_a_operacao_e_cancelada` existe? Quem cancela operações dentro do seu pipeline?

---

## Fase 3: circuit breaker

Implemente **um nível por vez** e só avance quando o nível atual passar:

```powershell
python -m pytest tests/test_circuit_breaker.py -k Nivel1
```

| Nível | O que exige |
|---|---|
| 1. Básico | CLOSED → OPEN depois de N falhas; OPEN rejeita sem executar |
| 2. Falhas consecutivas | um sucesso zera a contagem; OPEN respeita o tempo de recuperação |
| 3. Meio aberto | depois do tempo, uma prova passa; sucesso fecha, falha reabre e reinicia o tempo |
| 4. Uma prova por vez | durante a prova, as outras chamadas são rejeitadas |
| 5. Cancelamento | uma prova cancelada não pode deixar o circuito travado |
| 6. Resultados atrasados | chamadas que começaram antes da abertura e terminam depois não bagunçam o estado |

Os níveis 5 e 6 só fazem sentido depois do 4. Uma implementação sem a trava de prova passa no nível 5 por acaso, porque não tem o que travar.

Chame `report_breaker_state(estado)` (de `app.metrics`) a cada transição para o painel *Estado do circuit breaker* funcionar.

**Ligue no pipeline** com as outras duas peças e rode o experimento padrão.

**Perguntas:**
1. Quantas falhas levaram para o circuito abrir? Bate com `BREAKER_FAILURE_THRESHOLD`?
2. Com o circuito aberto, quanto tempo leva uma resposta de `/reports`? E o que acontece com a CPU do banco (`docker stats`)?
3. Você consegue ver as provas no gráfico de estado durante a rajada? Por que o estado `half_open` quase não aparece?
4. Depois de desligar a rajada, quanto tempo levou para fechar? Qual parâmetro controla isso?
5. Que exceções devem contar como falha? Um `BulkheadFullError` deveria contar? E um `OperationTimeout`?
6. Você precisou de `asyncio.Lock`? Por quê, ou por que não? (Pense em onde existem `await` dentro do seu `call`.)

---

## Fase 4: a ordem da composição

Monte as duas versões e compare no painel *Rota de relatório: resultado por tipo*:

- A: bulkhead → breaker → timeout → operação
- B: breaker → bulkhead → timeout → operação

**Perguntas:**
1. Em qual delas o circuito abre só porque o bulkhead está cheio, mesmo com o banco respondendo?
2. Em qual delas um timeout conta como falha do banco?
3. Qual composição você escolheria, e qual é o argumento?

---

## Fase 5: outros tipos de falha

Até aqui a falha era **lentidão**. Teste outros tipos com o tráfego normal ligado:

| Experimento | Como |
|---|---|
| Banco caiu | `docker compose stop postgres` e, depois de um tempo, `docker compose start postgres` |
| Banco ainda mais fraco | `PG_CPUS=0.25` no `.env` e depois `docker compose up -d postgres` |
| Pouca memória | `PG_MEM=128m` e depois `docker compose up -d postgres` (veja se o container reinicia) |
| Timeout mais curto que a query | `TIMEOUT_MS=100` e depois `docker compose up -d api` |

**Perguntas:**
1. Com o banco fora, as falhas são lentas ou rápidas? Que exceção aparece? O breaker ainda ajuda?
2. Com `TIMEOUT_MS=100`, o banco está "doente"? O que o seu breaker acha disso?
3. O pool se recupera sozinho quando o Postgres volta?

---

## Desafios extras

- **Fallback**: guarde a última resposta boa de cada região e devolva com `"stale": true` quando o circuito estiver aberto.
- **Janela deslizante**: abra o circuito por *taxa* de erro (por exemplo, 50% nas últimas 20 chamadas) em vez de falhas consecutivas. Compare com a versão atual.
- **Exceções ignoradas**: deixe configurável quais exceções contam como falha.
- **Métricas próprias**: crie contadores para rejeições e provas e adicione painéis no Grafana.
- **Múltiplos workers**: rode a API com `--workers 2`. O que acontece com o estado do circuito? Como você resolveria isso?

## Leitura

- Martin Fowler, *CircuitBreaker*: <https://martinfowler.com/bliki/CircuitBreaker.html>
- Michael Nygard, *Release It!*, capítulo sobre padrões de estabilidade (é a origem do padrão).
