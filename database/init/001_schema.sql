-- Contas: consulta leve por chave primária (rota "essencial").
CREATE TABLE accounts (
  id        integer PRIMARY KEY,
  name      text    NOT NULL,
  region_id integer NOT NULL
);

-- Transações: tabela grande e SEM índice em account_id, de propósito.
-- O relatório por região precisa ler a tabela inteira (rota "pesada").
CREATE TABLE transactions (
  id           bigint      PRIMARY KEY,
  account_id   integer     NOT NULL,
  amount_cents integer     NOT NULL,
  created_at   timestamptz NOT NULL
);

INSERT INTO accounts (id, name, region_id)
SELECT id, 'Conta ' || id, (id % 20) + 1
FROM generate_series(1, 10000) AS id;

INSERT INTO transactions (id, account_id, amount_cents, created_at)
SELECT id,
       ((id::bigint * 7919) % 10000) + 1,
       (id % 50000) + 100,
       TIMESTAMPTZ '2025-01-01 00:00:00+00' + ((id % 525600) * INTERVAL '1 minute')
FROM generate_series(1, 1000000) AS id;

ANALYZE;
