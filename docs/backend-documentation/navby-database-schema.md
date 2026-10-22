# Navby Platform — Persistencia (PostgreSQL 16 y Redis 7)

> PostgreSQL guarda todo lo durable. Redis guarda solo datos efímeros que pueden perderse sin dañar al usuario. Routing no persiste nada: su grafo se carga desde CSV al arrancar.

## 1. Mapa de almacenamiento

| Contexto | PostgreSQL (esquema) | Redis |
| :--- | :--- | :--- |
| IAM | `iam.users`, `iam.refresh_tokens` | OTP de verificación, control de reenvío y tokens de recuperación |
| Routing | — | — (grafo en RAM) |
| Quotes | — | Caché de ofertas por par, sesiones de búsqueda y candado de búsqueda en curso |
| Billing | `billing.credit_wallets`, `billing.credit_transactions`, `billing.credit_orders` | — |
| Itineraries | `itineraries.saved_itineraries` | — |
| Shared Kernel | `shared.outbox_events` | Contadores de rate limiting |

Reglas:

- Un esquema por contexto. **Sin claves foráneas entre esquemas**: `user_id` es un UUID lógico.
- Todas las marcas de tiempo son `TIMESTAMPTZ` en UTC. La única fecha en hora de Lima es `free_credits_date` (día de créditos).
- Lo que se elimina se borra físicamente, salvo el usuario eliminado, que se anonimiza (RL-02).

## 2. DDL (PostgreSQL 16)

```sql
CREATE SCHEMA iam;
CREATE SCHEMA billing;
CREATE SCHEMA itineraries;
CREATE SCHEMA shared;

-- ============================ IAM ============================
CREATE TABLE iam.users (
    id                 UUID PRIMARY KEY,
    email              VARCHAR(254) NOT NULL UNIQUE,         -- minúsculas; anonimizado al eliminar
    full_name          VARCHAR(100) NOT NULL,
    password_hash      VARCHAR(60),                          -- bcrypt; NULL si solo usa Google
    google_sub         VARCHAR(255) UNIQUE,
    email_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    terms_version      VARCHAR(20) NOT NULL,                 -- RL-01
    terms_accepted_at  TIMESTAMPTZ NOT NULL,
    deleted_at         TIMESTAMPTZ,                          -- RL-02
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_has_login_method CHECK (
        deleted_at IS NOT NULL OR password_hash IS NOT NULL OR google_sub IS NOT NULL)
);

CREATE TABLE iam.refresh_tokens (
    id                UUID PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES iam.users(id) ON DELETE CASCADE,
    token_hash        CHAR(64) NOT NULL UNIQUE,              -- SHA-256 del token opaco
    replaced_by_hash  CHAR(64),                              -- hash del token que lo reemplazó al rotar
    expires_at        TIMESTAMPTZ NOT NULL,                  -- emisión + 7 días
    revoked_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_tokens_user ON iam.refresh_tokens (user_id);
CREATE INDEX ix_refresh_tokens_expires ON iam.refresh_tokens (expires_at);

-- ========================== BILLING ==========================
CREATE TABLE billing.credit_wallets (
    user_id            UUID PRIMARY KEY,                     -- ID lógico de IAM (sin FK)
    free_credits       SMALLINT NOT NULL CHECK (free_credits BETWEEN 0 AND 10),
    free_credits_date  DATE NOT NULL,                        -- día de créditos en America/Lima
    paid_credits       INTEGER NOT NULL DEFAULT 0 CHECK (paid_credits >= 0),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE billing.credit_transactions (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL,
    type          VARCHAR(20) NOT NULL CHECK (type IN
                  ('SEARCH_DEBIT', 'SEARCH_REFUND', 'PURCHASE', 'PURCHASE_REVERSAL', 'ACCOUNT_DELETION')),
    free_delta    SMALLINT NOT NULL,                         -- negativo resta, positivo suma
    paid_delta    INTEGER NOT NULL,
    reference_id  VARCHAR(64) NOT NULL,                      -- search_id, order_id o user_id
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT credit_tx_idempotent UNIQUE (type, reference_id)
);
CREATE INDEX ix_credit_tx_user_created ON billing.credit_transactions (user_id, created_at DESC);

CREATE TABLE billing.credit_orders (
    id                UUID PRIMARY KEY,
    user_id           UUID NOT NULL,
    package_code      VARCHAR(16) NOT NULL CHECK (package_code IN ('pack_50', 'pack_100', 'pack_250')),
    credits           INTEGER NOT NULL CHECK (credits > 0),
    amount            NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    currency          CHAR(3) NOT NULL DEFAULT 'PEN' CHECK (currency = 'PEN'),
    status            VARCHAR(10) NOT NULL CHECK (status IN
                      ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'REVERSED')),
    expires_at        TIMESTAMPTZ NOT NULL,                  -- creación + 24 h
    mp_preference_id  VARCHAR(64) NOT NULL,
    mp_payment_id     VARCHAR(64) UNIQUE,                    -- idempotencia del webhook
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_credit_orders_user_created ON billing.credit_orders (user_id, created_at DESC);
CREATE INDEX ix_credit_orders_pending ON billing.credit_orders (expires_at) WHERE status = 'PENDING';

-- ======================== ITINERARIES ========================
CREATE TABLE itineraries.saved_itineraries (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL,
    offer_id        VARCHAR(40) NOT NULL,
    name            VARCHAR(80) NOT NULL,
    trip_type       VARCHAR(10) NOT NULL CHECK (trip_type IN ('ONE_WAY', 'ROUND_TRIP')),
    origin          CHAR(3) NOT NULL,                        -- primer aeropuerto de la ida
    destination     CHAR(3) NOT NULL,                        -- último aeropuerto de la ida
    departure_date  DATE NOT NULL,
    return_date     DATE,
    offer_snapshot  JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT return_matches_trip CHECK ((trip_type = 'ROUND_TRIP') = (return_date IS NOT NULL)),
    CONSTRAINT one_save_per_offer UNIQUE (user_id, offer_id)
);
CREATE INDEX ix_saved_itineraries_user_created ON itineraries.saved_itineraries (user_id, created_at DESC);

-- ========================== SHARED ===========================
CREATE TABLE shared.outbox_events (
    id            UUID PRIMARY KEY,
    event_type    VARCHAR(100) NOT NULL,                     -- p. ej. 'iam.user_verified'
    payload       JSONB NOT NULL,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    attempts      SMALLINT NOT NULL DEFAULT 0,
    failed_at     TIMESTAMPTZ,
    last_error    TEXT
);
CREATE INDEX ix_outbox_pending ON shared.outbox_events (occurred_at)
    WHERE processed_at IS NULL AND failed_at IS NULL;
```

La clave foránea `iam.refresh_tokens.user_id → iam.users.id` es válida porque ambas tablas pertenecen al mismo contexto.

### Débito atómico de créditos

El débito se resuelve en PostgreSQL dentro de una sola transacción, sin Redis:

```sql
BEGIN;
INSERT INTO billing.credit_wallets (user_id, free_credits, free_credits_date, paid_credits)
VALUES (:user_id, 10, :today_lima, 0) ON CONFLICT (user_id) DO NOTHING;     -- billetera perezosa
SELECT * FROM billing.credit_wallets WHERE user_id = :user_id FOR UPDATE;   -- bloquea la fila
-- En Python (agregado CreditWallet): si free_credits_date < hoy (Lima) → free_credits = 10.
-- Débito de 5: primero free_credits, el resto de paid_credits. Si no alcanza → INSUFFICIENT_CREDITS (ROLLBACK).
UPDATE billing.credit_wallets SET free_credits = :f, free_credits_date = :d, paid_credits = :p, updated_at = now()
 WHERE user_id = :user_id;
INSERT INTO billing.credit_transactions (id, user_id, type, free_delta, paid_delta, reference_id)
VALUES (:id, :user_id, 'SEARCH_DEBIT', -:from_free, -:from_paid, :search_id);  -- UNIQUE evita doble cobro
COMMIT;
```

El reembolso (`SEARCH_REFUND`) inserta los mismos deltas con signo positivo. Los créditos gratuitos solo se devuelven si el débito ocurrió el mismo día de créditos.

## 3. Redis 7

| Clave | Tipo | TTL | Contenido |
| :--- | :--- | :---: | :--- |
| `navby:quotes:offers:{pair_key}` | String (JSON) | 1,800 s | Ofertas normalizadas de un par. `pair_key` = `{trip}:{from}:{to}:{date}:{return\|-}:{cabin}:{adults}-{children}-{infants}:{currency}` |
| `navby:quotes:search:{search_id}` | String (JSON) | 1,800 s desde la creación | Sesión: `user_id`, criterios, frontera de Pareto, T_min y pesos actuales. Al reordenar se escribe con `KEEPTTL`. |
| `navby:quotes:lock:{user_id}` | String | 60 s | Candado de cotización en curso (RN-15). |
| `navby:iam:verify:{user_id}` | Hash | 600 s | `code_hash` (SHA-256 del OTP) e `attempts`. |
| `navby:iam:verify_resend:{email_hash}` | String | 60 s | Impide reenviar el OTP más de una vez por minuto. |
| `navby:iam:reset:{token_hash}` | String | 1,800 s | `user_id` dueño del token de recuperación. Se borra al usarlo. |
| `navby:ratelimit:{scope}:{key}:{window}` | String (contador) | 60 s | Contador de ventana fija (ver especificación táctica). |

Configuración: `maxmemory 256mb` y `maxmemory-policy volatile-ttl`, que expulsa primero las claves más próximas a vencer. Con unas 13,000 búsquedas al mes, la caché ocupa muy por debajo de ese límite.

No requiere persistencia en disco: perder Redis vacía cachés y sesiones, y obliga a pedir un OTP nuevo. Mientras Redis no esté disponible, `POST /quotes/search` responde `503` antes de cobrar.
