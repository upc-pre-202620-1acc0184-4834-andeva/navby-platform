# Navby Platform — Endpoints REST

> Base: `https://navby.andeva.tech/api/v1` (producción, vía el proxy de Vercel; ver [entornos](navby-environments-and-deployment.md)) y `http://localhost:8000/api/v1` (local). JSON UTF-8, fechas ISO 8601. Los errores siguen RFC 7807 con el catálogo de la [especificación táctica](navby-backend-tactical-specification.md#catálogo-de-códigos-de-error). Las reglas `RN-xx` y `RL-xx` están en [navby-documentation.md](../navby-documentation.md).

## 1. Resumen

| Contexto | Método y ruta | Acceso | Propósito |
| :--- | :--- | :---: | :--- |
| IAM | `POST /auth/register` | Público | Crear una cuenta y enviar el OTP. |
| IAM | `POST /auth/verify-email` | Público | Validar el OTP y abrir la sesión. |
| IAM | `POST /auth/verify-email/resend` | Público | Reenviar el OTP. |
| IAM | `POST /auth/login` | Público | Iniciar sesión con correo y contraseña. |
| IAM | `POST /auth/google` | Público | Iniciar sesión o registrarse con Google. |
| IAM | `POST /auth/refresh` | Cookie | Rotar el refresh token. |
| IAM | `POST /auth/logout` | Cookie | Cerrar la sesión. |
| IAM | `POST /auth/forgot-password` | Público | Enviar el enlace de recuperación. |
| IAM | `POST /auth/reset-password` | Público | Definir una contraseña nueva. |
| IAM | `GET /users/me` | JWT | Consultar el perfil propio. |
| IAM | `DELETE /users/me` | JWT | Eliminar la cuenta (RL-02). |
| Routing | `GET /routing/cities?q=` | Público | Autocompletar ciudades y sus aeropuertos. |
| Routing | `GET /routing/preview` | Público | Obtener BFS + A\*: alcanzabilidad, escalas mínimas, T_min y ruta preliminar. |
| Quotes | `POST /quotes/search` | JWT verificado | Cotizar y obtener el podio (5 créditos, RN-08). |
| Quotes | `POST /quotes/{search_id}/rank` | JWT verificado | Reordenar con otro perfil (gratis, RN-11). |
| Quotes | `GET /quotes/{search_id}` | JWT verificado | Volver a leer el podio vigente. |
| Billing | `GET /billing/wallet` | JWT | Consultar el saldo. |
| Billing | `GET /billing/transactions` | JWT | Ver el historial de movimientos de créditos. |
| Billing | `GET /billing/packages` | Público | Ver el catálogo de paquetes. |
| Billing | `POST /billing/orders` | JWT verificado | Crear una orden y la preferencia de Mercado Pago. |
| Billing | `GET /billing/orders/{order_id}` | JWT | Consultar el estado de una orden. |
| Billing | `POST /billing/webhooks/mercadopago` | Firma HMAC | Recibir la notificación de pago. |
| Itineraries | `POST /itineraries` | JWT | Guardar una oferta del podio. |
| Itineraries | `GET /itineraries` | JWT | Listar los itinerarios guardados. |
| Itineraries | `GET /itineraries/{id}` | JWT | Ver el detalle de un itinerario. |
| Itineraries | `DELETE /itineraries/{id}` | JWT | Eliminar un itinerario. |
| Sistema | `GET /health` | Público | Estado de PostgreSQL, Redis y grafo. |

**Autenticación:**
- **Access token**: cabecera `Authorization: Bearer <access_token>` (JWT HS256, 15 min).
- **Refresh token**: viaja solo en la cookie `navby_refresh` (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/v1/auth`). Como la webapp y la API comparten el origen `navby.andeva.tech`, la cookie es de primera parte y no hace falta CORS.

**Errores comunes** (no se repiten en cada endpoint):
- `401 UNAUTHENTICATED` en todo endpoint con acceso JWT o JWT verificado si falta el token o venció.
- `403 EMAIL_NOT_VERIFIED` en todo endpoint con acceso JWT verificado si el correo no está verificado.
- `422 VALIDATION_ERROR` en todo endpoint si el cuerpo o los parámetros no cumplen el schema (formato, rangos, límites de paginación, RN-01 a RN-04).
- `429 RATE_LIMITED` en todo endpoint con rate limit.

## 2. IAM

### `POST /auth/register`

```json
{ "email": "ana@mail.com", "password": "Viajar2026", "full_name": "Ana Torres", "accept_terms": true }
```

`201` → `{ "user_id": "uuid", "email": "ana@mail.com", "email_verified": false }`. Envía un OTP de 6 dígitos (10 min).

Errores:
- `409 EMAIL_ALREADY_REGISTERED`;
- `422 TERMS_NOT_ACCEPTED`;
- `422 DISPOSABLE_EMAIL`;
- `422 VALIDATION_ERROR` (contraseña de 8 a 72 caracteres con letras y números).

### `POST /auth/verify-email`

```json
{ "email": "ana@mail.com", "code": "849201" }
```

`200` → **Session** y cookie `navby_refresh`. Errores: `400 INVALID_OTP` (también si el correo no existe o ya está verificado) y `429 OTP_ATTEMPTS_EXCEEDED`.

**Session** (respuesta común de verify, login, google y refresh):

```json
{ "access_token": "eyJ...", "token_type": "Bearer", "expires_in": 900,
  "user": { "user_id": "uuid", "email": "ana@mail.com", "full_name": "Ana Torres", "email_verified": true } }
```

### `POST /auth/verify-email/resend`

`{ "email": "..." }` → `202` siempre (no revela si el correo existe). Como máximo un envío por minuto por correo.

### `POST /auth/login`

`{ "email": "...", "password": "..." }` → `200 Session`. Errores: `401 INVALID_CREDENTIALS` y `403 EMAIL_NOT_VERIFIED`.

### `POST /auth/google`

`{ "id_token": "eyJ...", "accept_terms": true }` → `200 Session`. Crea la cuenta si no existe (entonces `accept_terms` es obligatorio) o la vincula según las reglas de [IAM](extended-bounded-contexts-description/bounded-context-iam.md). Errores: `401 INVALID_GOOGLE_TOKEN` y `422 TERMS_NOT_ACCEPTED`.

### `POST /auth/refresh`

Sin cuerpo; lee la cookie. `200 Session` con una cookie nueva. Si la cookie es inválida, expiró o fue reutilizada fuera de la ventana de 30 s → `401 INVALID_REFRESH_TOKEN` y la cookie se borra.

### `POST /auth/logout`

Sin cuerpo. Revoca el refresh token de la cookie y la borra. `204` siempre.

### `POST /auth/forgot-password`

`{ "email": "..." }` → `202` siempre. Envía un enlace `{WEBAPP_URL}/reset-password?token=...` válido por 30 min.

### `POST /auth/reset-password`

`{ "token": "...", "new_password": "..." }` → `204`. Revoca todas las sesiones. Errores: `400 INVALID_RESET_TOKEN` y `422 VALIDATION_ERROR`.

### `GET /users/me`

`200` → `{ "user_id", "email", "full_name", "email_verified", "has_password", "has_google", "created_at" }`

### `DELETE /users/me`

`{ "confirmation": "ELIMINAR" }` → `204` y la cookie se borra. Anonimiza la cuenta, borra los itinerarios y anula los créditos; conserva las órdenes de compra. Error: `422 VALIDATION_ERROR` si la confirmación no es exacta.

## 3. Routing

### `GET /routing/cities?q=tok&limit=10`

`q` necesita al menos 2 caracteres y coincide por prefijo con:
- el nombre de la ciudad en inglés o su alias en español;
- el nombre del aeropuerto;
- el código IATA.

No distingue mayúsculas ni tildes. `limit` admite como máximo 20.

```json
{ "cities": [
  { "city": "Tokyo", "city_es": "Tokio", "country": "Japan",
    "airports": [ { "iata": "HND", "name": "Tokyo Haneda International Airport", "lat": 35.5523, "lon": 139.7800 },
                  { "iata": "NRT", "name": "Narita International Airport", "lat": 35.7647, "lon": 140.3864 } ] } ] }
```

### `GET /routing/preview?origins=LIM&destinations=HND,NRT&trip_type=ONE_WAY`

La webapp envía todos los aeropuertos de cada ciudad (1 a 5 por lado, sin aeropuertos en común). El servidor evalúa todas las combinaciones con BFS y A\* y devuelve:
- en `pairs`, los ≤ 2 pares que se cotizarían (RN-14);
- en `best_route`, la ruta de ida del par con menor T_min.

`trip_type` es opcional (`ONE_WAY` por defecto); con `ROUND_TRIP`, `t_min_minutes` suma ida y vuelta.

```json
{
  "reachable": true,
  "pairs": [
    { "origin": "LIM", "destination": "HND", "min_stops": 1, "t_min_minutes": 1215 },
    { "origin": "LIM", "destination": "NRT", "min_stops": 1, "t_min_minutes": 1248 }
  ],
  "best_route": {
    "t_min_minutes": 1215,
    "airports": [
      { "iata": "LIM", "lat": -12.0219, "lon": -77.1143 },
      { "iata": "LAX", "lat": 33.9425, "lon": -118.4081 },
      { "iata": "HND", "lat": 35.5523, "lon": 139.7800 }
    ]
  },
  "telemetry": { "pairs_evaluated": 2, "bfs_ms": 0.9, "astar_ms": 1.7, "astar_nodes_expanded": 214 }
}
```

Si ningún par tiene ruta: `200` con `"reachable": false`, `pairs: []` y `best_route: null`. `telemetry` suma todos los pares evaluados. Errores: `404 AIRPORT_NOT_FOUND` y `422 VALIDATION_ERROR`.

## 4. Quotes

### `POST /quotes/search`

```json
{
  "trip_type": "ROUND_TRIP",
  "origins": ["LIM"],
  "destinations": ["HND", "NRT"],
  "departure_date": "2026-11-01",
  "return_date": "2026-11-15",
  "passengers": { "adults": 2, "children": 1, "infants": 0 },
  "cabin": "ECONOMY",
  "currency": "USD",
  "preferences": { "profile": "BALANCED" }
}
```

`origins` y `destinations` son los aeropuertos de cada ciudad elegida (1 a 5 por lado). El servidor elige qué pares cotizar (RN-14). `preferences` es opcional (por defecto `BALANCED`). Con `"profile": "CUSTOM"` se agregan `"weights": { "price": 0.4, "duration": 0.4, "stops": 0.2 }`.

`200` → **PodiumResponse**:

```json
{
  "search_id": "srch_01J9Z...",
  "expires_at": "2026-10-15T15:30:00Z",
  "credits_charged": 5,
  "credits_remaining": 5,
  "partial": false,
  "pairs_quoted": [ { "origin": "LIM", "destination": "HND" }, { "origin": "LIM", "destination": "NRT" } ],
  "t_min_minutes": 2430,
  "offers_received": 87,
  "pareto_size": 9,
  "preferences": { "profile": "BALANCED", "weights": { "price": 0.5, "duration": 0.3, "stops": 0.2 } },
  "price_disclaimer": "Precio referencial obtenido de terceros; se confirma en el sitio del vendedor.",
  "podium": [
    {
      "rank": 1,
      "offer_id": "9f2c41ab07d3e655",
      "score": 0.1834,
      "match_pct": 82,
      "price": { "amount": "2140.30", "currency": "USD" },
      "duration_minutes": 3010,
      "extra_minutes_vs_t_min": 580,
      "stops": 2,
      "airlines": [ { "iata": "LA", "name": "LATAM Airlines", "logo": "https://..." } ],
      "legs": [
        { "direction": "OUTBOUND", "departure": "2026-11-01T08:30:00", "arrival": "2026-11-02T17:10:00",
          "duration_minutes": 1540, "stops": 1,
          "segments": [
            { "from": "LIM", "to": "LAX", "departure": "2026-11-01T08:30:00", "arrival": "2026-11-01T15:05:00",
              "flight_number": "LA2600", "airline": "LA" },
            { "from": "LAX", "to": "HND", "departure": "2026-11-01T18:20:00", "arrival": "2026-11-02T17:10:00",
              "flight_number": "NH105", "airline": "NH" }
          ] },
        { "direction": "INBOUND", "...": "..." }
      ],
      "airports": [
        { "iata": "LIM", "lat": -12.0219, "lon": -77.1143, "timezone": "America/Lima" },
        { "iata": "LAX", "lat": 33.9425, "lon": -118.4081, "timezone": "America/Los_Angeles" }
      ],
      "deep_link": "https://..."
    }
  ]
}
```

- `podium` tiene de 0 a 3 elementos, ordenados por `score` ascendente. Con 0, FlightAPI no tiene vuelos para esa fecha y `credits_charged` es `0` (RN-09).
- Las horas de `legs` y `segments` son hora local de cada aeropuerto. La zona de cada uno está en `airports[].timezone`.
- Los montos se serializan como texto con 2 decimales.
- `credits_charged` es `0` si todos los pares estaban en caché o si hubo reembolso.

Errores:
- `402 INSUFFICIENT_CREDITS`;
- `403 EMAIL_NOT_VERIFIED`;
- `409 SEARCH_IN_PROGRESS`;
- `422 ROUTE_NOT_REACHABLE`, `422 VALIDATION_ERROR`, `422 INVALID_WEIGHTS`;
- `503 PROVIDER_UNAVAILABLE`.

### `POST /quotes/{search_id}/rank`

`{ "profile": "FAST" }` o `{ "profile": "CUSTOM", "weights": { ... } }` → `200 PodiumResponse` con `credits_charged: 0` y la misma `expires_at`. Errores: `404 SEARCH_NOT_FOUND` y `422 INVALID_WEIGHTS`.

### `GET /quotes/{search_id}`

`200 PodiumResponse` con los pesos usados por última vez. Error: `404 SEARCH_NOT_FOUND`.

## 5. Billing

### `GET /billing/wallet`

```json
{ "free_credits": 10, "paid_credits": 45, "total_credits": 55, "searches_available": 11,
  "free_credits_reset_at": "2026-10-16T05:00:00Z" }
```

`free_credits_reset_at` es la próxima medianoche de Lima expresada en UTC.

### `GET /billing/transactions?page=1&page_size=20`

`200` → `{ "items": [ { "id", "type", "free_delta", "paid_delta", "reference_id", "created_at" } ], "page", "page_size", "total" }`. `page_size` admite como máximo 50. `type` ∈ `SEARCH_DEBIT`, `SEARCH_REFUND`, `PURCHASE`, `PURCHASE_REVERSAL`, `ACCOUNT_DELETION`.

### `GET /billing/packages`

```json
{ "currency": "PEN", "packages": [
  { "code": "pack_50", "name": "Escapada", "credits": 50, "searches": 10, "price": "9.90", "usd_reference": "2.49" },
  { "code": "pack_100", "name": "Viajero Frecuente", "credits": 100, "searches": 20, "price": "16.90", "usd_reference": "4.49" },
  { "code": "pack_250", "name": "Nómada", "credits": 250, "searches": 50, "price": "34.90", "usd_reference": "8.99" } ] }
```

Se cobra siempre en soles; `usd_reference` es solo informativo.

### `POST /billing/orders`

`{ "package_code": "pack_100" }` → `201`:

```json
{ "order_id": "uuid", "package_code": "pack_100", "credits": 100, "amount": "16.90", "currency": "PEN",
  "status": "PENDING", "expires_at": "2026-10-16T14:00:00Z",
  "checkout_url": "https://www.mercadopago.com.pe/checkout/v1/redirect?pref_id=..." }
```

Error: `404 PACKAGE_NOT_FOUND`.

### `GET /billing/orders/{order_id}`

`200` → la orden con su `status` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED` o `REVERSED`). Error: `404 ORDER_NOT_FOUND`.

### `POST /billing/webhooks/mercadopago`

Cuerpo emitido por Mercado Pago (`{ "type": "payment", "data": { "id": "123" } }`). Si `type` no es `payment`, responde `200` sin hacer nada. Si no:

1. Valida la cabecera `x-signature` y que `ts` no tenga más de 300 s. Si falla → `401 INVALID_WEBHOOK_SIGNATURE`.
2. Consulta el pago en la API de Mercado Pago, sin confiar en el cuerpo.
3. Aplica el cambio de estado una sola vez (ver [Billing](extended-bounded-contexts-description/bounded-context-billing.md)) y responde `200`.

## 6. Itineraries

### `POST /itineraries`

`{ "search_id": "srch_...", "offer_id": "9f2c41ab07d3e655", "name": "Japón 2026" }`. `name` es opcional; por defecto es `"LIM → HND · 2026-11-01"`.

`201` (nuevo) o `200` (ya estaba guardado) → **Itinerary**:

```json
{ "id": "uuid", "name": "Japón 2026", "trip_type": "ROUND_TRIP", "origin": "LIM", "destination": "HND",
  "departure_date": "2026-11-01", "return_date": "2026-11-15",
  "offer": { "...": "elemento de podium congelado, más profile, weights y quoted_at" },
  "price_disclaimer": "Precio del 2026-10-15; puede haber cambiado.",
  "created_at": "..." }
```

Errores: `404 SEARCH_NOT_FOUND`, `404 OFFER_NOT_FOUND` y `409 ITINERARY_LIMIT_REACHED`.

### `GET /itineraries?page=1&page_size=20`

`200` → lista paginada de **Itinerary**, del más reciente al más antiguo. `page_size` admite como máximo 50.

### `GET /itineraries/{id}`

`200 Itinerary`. Error: `404 ITINERARY_NOT_FOUND`.

### `DELETE /itineraries/{id}`

`204`. Error: `404 ITINERARY_NOT_FOUND`.

## 7. Sistema

### `GET /health`

`200` → `{ "status": "UP", "postgres": "UP", "redis": "UP", "graph": { "status": "UP", "nodes": 3354, "edges": 37326 } }`. Responde `503` si algún componente está caído.
