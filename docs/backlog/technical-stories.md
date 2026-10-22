# Navby — Historias Técnicas

> Una historia por cada uno de los 27 endpoints (TS-01 a TS-23 y TS-29 a TS-32) y una por cada componente interno del backend (TS-24 a TS-28, TS-33 a TS-35, TS-37 y TS-38). Los números TS-36 (website) y TS-39 (webapp) no se usan: esas piezas se construyen en sus propios repositorios. Cada una tiene al menos dos escenarios verificables con pruebas automatizadas. Los contratos están en [navby-endpoints.md](../backend-documentation/navby-endpoints.md), los errores en el [catálogo](../backend-documentation/navby-backend-tactical-specification.md#catálogo-de-códigos-de-error) y las reglas en [navby-documentation.md](../navby-documentation.md).

## Definición de terminado (aplica a todas)

1. El código sigue la plantilla de capas y la nomenclatura de la [especificación táctica](../backend-documentation/navby-backend-tactical-specification.md).
2. Hay pruebas que cubren todos los escenarios de la historia: unitarias de dominio, de handler y de endpoint.
3. Ruff y Mypy pasan sin errores.
4. El endpoint aparece en `/docs` (OpenAPI 3.1) con sus ejemplos y respuestas de error.
5. Los errores responden RFC 7807 con el `code` del catálogo.

## Orden sugerido de construcción

| Sprint | Historias | Resultado |
| :---: | :--- | :--- |
| 1 | TS-33, TS-38, TS-23, TS-24, TS-25, TS-26, TS-12, TS-13, TS-37 | Plataforma base, grafo, BFS, A\*, ciudades, vista previa y benchmark. |
| 2 | TS-01 a TS-11, TS-34 | Cuentas, sesiones y eventos. |
| 3 | TS-27, TS-28, TS-14, TS-15, TS-16, TS-17 | Cotización, podio, perfiles y débito de créditos. |
| 4 | TS-18 a TS-22, TS-35 | Compras con Mercado Pago y tareas periódicas. |
| 5 | TS-29 a TS-32 | Itinerarios guardados. |

## Mapa con las historias de usuario

| Historia técnica | Historias de usuario |
| :--- | :--- |
| TS-01 a TS-11 | US-01 a US-10 |
| TS-12, TS-13 | US-11, US-12, US-14 |
| TS-14, TS-27, TS-28 | US-13 a US-18, US-25, US-31, US-34 |
| TS-15, TS-16 | US-19 a US-21 |
| TS-17 a TS-22 | US-25 a US-30 |
| TS-29 a TS-32 | US-22 a US-24 |

---

## IAM

### TS-01 · `POST /auth/register`

**Como** desarrollador **quiero** registrar usuarios con correo, contraseña y aceptación de términos **para** habilitar US-01.

Componentes: **RegisterUser**, **User.register_local**, **DisposableEmailPolicy**, **EmailSender**, **OneTimeCodeStore**. Rate limit `register`.

```gherkin
Escenario: Alta válida
  Dado un correo nuevo, una contraseña "Viajar2026", un nombre y accept_terms = true
  Cuando se envía POST /auth/register
  Entonces responde 201 con user_id y email_verified = false
  Y iam.users guarda password_hash bcrypt, terms_version = TERMS_VERSION y terms_accepted_at
  Y en Redis existe navby:iam:verify:{user_id} con el hash del OTP y TTL 600 s
  Y EmailSender recibió el código en claro
  Y no se escribió ningún evento en el outbox

Escenario: Validaciones de negocio
  Cuando accept_terms es false → 422 TERMS_NOT_ACCEPTED
  Cuando el dominio está en disposable_domains.txt → 422 DISPOSABLE_EMAIL
  Cuando el correo ya existe (sin distinguir mayúsculas) → 409 EMAIL_ALREADY_REGISTERED
  Cuando la contraseña tiene 7 caracteres o no tiene dígitos → 422 VALIDATION_ERROR

Escenario: Falla del proveedor de correo
  Dado que EmailSender lanza un error
  Cuando se registra un correo nuevo
  Entonces responde 201 igual y el usuario queda guardado
  Y se registra un log de nivel ERROR
```

### TS-02 · `POST /auth/verify-email`

**Como** desarrollador **quiero** validar el OTP y abrir la sesión **para** habilitar US-02.

Componentes: **VerifyEmail**, **User.verify_email**, **OneTimeCodeStore.check_otp**, **TokenIssuer**. Rate limit `otp`.

```gherkin
Escenario: OTP correcto
  Dado un usuario sin verificar con OTP "849201" vigente
  Cuando se envía POST /auth/verify-email con ese correo y código
  Entonces responde 200 con access_token y user.email_verified = true
  Y fija la cookie navby_refresh (HttpOnly, Secure, SameSite=Strict, Path=/api/v1/auth, 7 días)
  Y shared.outbox_events contiene iam.user_verified con el user_id, en la misma transacción
  Y la clave del OTP se borró

Escenario: Respuesta uniforme ante errores
  Cuando el código no coincide, el correo no existe o ya está verificado
  Entonces responde 400 INVALID_OTP en los tres casos

Escenario: Quinto intento fallido
  Dado un usuario con 4 intentos fallidos
  Cuando envía un código incorrecto
  Entonces responde 429 OTP_ATTEMPTS_EXCEEDED y la clave del OTP se borra
```

### TS-03 · `POST /auth/verify-email/resend`

**Como** desarrollador **quiero** reenviar el OTP con límite de frecuencia **para** habilitar US-03.

```gherkin
Escenario: Reenvío
  Dado un usuario sin verificar sin reenvío en el último minuto
  Cuando se envía POST /auth/verify-email/resend
  Entonces responde 202, reemplaza el OTP en Redis y fija navby:iam:verify_resend:{email_hash} con TTL 60 s

Escenario: Sin revelar información
  Cuando el correo no existe, ya está verificado o se reenvió hace menos de 60 s
  Entonces responde 202 sin enviar correo
```

### TS-04 · `POST /auth/login`

**Como** desarrollador **quiero** autenticar con contraseña **para** habilitar US-04.

Rate limit `login`.

```gherkin
Escenario: Login válido
  Dado un usuario verificado con contraseña
  Cuando se envía POST /auth/login con credenciales correctas
  Entonces responde 200 Session, crea una fila en iam.refresh_tokens con el hash del token y fija la cookie

Escenario: Credenciales inválidas
  Cuando el correo no existe, la contraseña es incorrecta, el usuario solo tiene Google o está eliminado
  Entonces responde 401 INVALID_CREDENTIALS
  Y el tiempo de respuesta no permite distinguir los casos (se compara contra un hash ficticio si no hay usuario)

Escenario: Correo sin verificar
  Dado un usuario no verificado con la contraseña correcta
  Entonces responde 403 EMAIL_NOT_VERIFIED
```

### TS-05 · `POST /auth/google`

**Como** desarrollador **quiero** autenticar con el `id_token` de Google aplicando las reglas de vinculación **para** habilitar US-05 sin permitir el secuestro de cuentas.

Componentes: **LoginWithGoogle**, **GoogleIdentityVerifier**. Rate limit `login`.

```gherkin
Escenario: Cuenta nueva
  Dado un id_token válido de un correo inexistente y accept_terms = true
  Entonces crea el usuario con email_verified = true y google_sub
  Y escribe iam.user_verified en el outbox y responde 200 Session

Escenario: Cuenta nueva sin términos
  Dado un id_token válido de un correo inexistente y accept_terms ausente o false
  Entonces responde 422 TERMS_NOT_ACCEPTED y no crea nada

Escenario: Vinculación segura
  Dado un usuario NO verificado con password_hash y el mismo correo
  Cuando entra con Google
  Entonces password_hash pasa a NULL, se guarda google_sub, email_verified = true y se escribe iam.user_verified

Escenario: Token inválido
  Cuando el id_token tiene otra audiencia, expiró o email_verified es false en Google
  Entonces responde 401 INVALID_GOOGLE_TOKEN
```

### TS-06 · `POST /auth/refresh`

**Como** desarrollador **quiero** rotar el refresh token con detección de reutilización y tolerancia entre pestañas **para** habilitar US-06.

```gherkin
Escenario: Rotación
  Dada una cookie con un refresh token activo
  Cuando se envía POST /auth/refresh
  Entonces responde 200 Session con una cookie nueva
  Y el token anterior queda con revoked_at y replaced_by_hash

Escenario: Carrera entre pestañas
  Dado un token revocado por rotación hace 10 s
  Cuando se presenta de nuevo
  Entonces responde 200 Session sin revocar otras sesiones

Escenario: Reutilización sospechosa
  Dado un token revocado hace 2 minutos
  Cuando se presenta
  Entonces revoca todos los refresh tokens del usuario, borra la cookie y responde 401 INVALID_REFRESH_TOKEN

Escenario: Sin cookie o token vencido
  Entonces responde 401 INVALID_REFRESH_TOKEN
```

### TS-07 · `POST /auth/logout`

**Como** desarrollador **quiero** revocar el refresh token de la cookie **para** habilitar US-07.

```gherkin
Escenario: Logout con cookie válida
  Entonces el token queda revocado, la cookie se borra y responde 204

Escenario: Logout idempotente
  Cuando no hay cookie o el token ya estaba revocado
  Entonces responde 204 sin error
```

### TS-08 · `POST /auth/forgot-password`

**Como** desarrollador **quiero** emitir un token de recuperación de un solo uso **para** habilitar US-08.

Rate limit `forgot_password`.

```gherkin
Escenario: Usuario existente
  Entonces guarda navby:iam:reset:{sha256(token)} con el user_id y TTL 1,800 s
  Y envía el enlace {WEBAPP_URL}/reset-password (con WEBAPP_URL = https://navby.andeva.tech/app)?token=... y responde 202

Escenario: Usuario inexistente o eliminado
  Entonces responde 202 sin enviar correo
```

### TS-09 · `POST /auth/reset-password`

**Como** desarrollador **quiero** cambiar la contraseña con el token de recuperación **para** completar US-08.

```gherkin
Escenario: Token válido
  Entonces actualiza password_hash, deja email_verified = true, borra la clave del token
  Y revoca todos los refresh tokens del usuario y responde 204

Escenario: Token inválido o usado
  Entonces responde 400 INVALID_RESET_TOKEN

Escenario: Contraseña débil
  Entonces responde 422 VALIDATION_ERROR y el token sigue vigente
```

### TS-10 · `GET /users/me`

**Como** desarrollador **quiero** exponer el perfil del usuario autenticado **para** habilitar US-09.

```gherkin
Escenario: Con JWT válido
  Entonces responde 200 con user_id, email, full_name, email_verified, has_password, has_google y created_at

Escenario: Sin JWT o vencido
  Entonces responde 401 UNAUTHENTICATED
```

### TS-11 · `DELETE /users/me`

**Como** desarrollador **quiero** anonimizar la cuenta y propagar la eliminación **para** cumplir RL-02 (US-10).

```gherkin
Escenario: Confirmación correcta
  Cuando se envía { "confirmation": "ELIMINAR" } con JWT válido
  Entonces email = deleted-{id}@navby.invalid, full_name = "Usuario eliminado", password_hash y google_sub en NULL, deleted_at fijado
  Y se revocan todos los refresh tokens, se borra la cookie y responde 204
  Y el outbox contiene iam.user_deleted

Escenario: Efecto en otros contextos
  Cuando el relay procesa iam.user_deleted
  Entonces Billing deja la billetera en 0 con una transacción ACCOUNT_DELETION
  Y Itineraries borra todos los itinerarios del usuario
  Y las órdenes de billing.credit_orders se conservan

Escenario: Confirmación incorrecta
  Entonces responde 422 VALIDATION_ERROR y nada cambia
```

---

## Routing

### TS-12 · `GET /routing/cities`

**Como** desarrollador **quiero** autocompletar ciudades en español e inglés **para** habilitar US-11.

Componentes: **SearchCities**, índice `cities` de **AirportGraph**.

```gherkin
Escenario: Búsqueda por alias, nombre o IATA
  Cuando q = "tok", "TOKYO" o "hnd"
  Entonces la respuesta contiene Tokyo (city_es "Tokio") con HND y NRT y sus coordenadas

Escenario: Normalización
  Cuando q = "bogota"
  Entonces encuentra "Bogota" con city_es "Bogotá"

Escenario: Agrupación metropolitana
  Entonces "New York" incluye JFK, LGA y EWR (por airport_city_overrides.csv)
  Y "Columbus" de Ohio y "Columbus" de Georgia aparecen como ciudades distintas

Escenario: Validación
  Cuando q tiene 1 carácter o limit > 20
  Entonces responde 422 VALIDATION_ERROR
```

### TS-13 · `GET /routing/preview`

**Como** desarrollador **quiero** devolver alcanzabilidad, escalas mínimas, T_min y ruta preliminar **para** habilitar US-12 y US-14.

Componentes: **PreviewRoute**, **PairSelector**. Rate limit `routing_preview`.

```gherkin
Escenario: Ruta alcanzable
  Cuando origins = LIM y destinations = HND,NRT
  Entonces responde 200 con reachable = true, a lo sumo 2 pares ordenados según RN-14
  Y best_route con aeropuertos y coordenadas, y telemetry con pairs_evaluated, bfs_ms, astar_ms y astar_nodes_expanded

Escenario: Ruta no alcanzable
  Cuando ningún par tiene ruta con ≤ 2 escalas
  Entonces responde 200 con reachable = false, pairs = [] y best_route = null

Escenario: Ida y vuelta
  Cuando trip_type = ROUND_TRIP
  Entonces solo se consideran pares alcanzables en ambos sentidos y t_min_minutes suma ida y vuelta

Escenario: Entradas inválidas
  Cuando un IATA no existe → 404 AIRPORT_NOT_FOUND
  Cuando hay más de 5 aeropuertos por lado o un aeropuerto en ambos lados → 422 VALIDATION_ERROR
```

---

## Quotes

### TS-14 · `POST /quotes/search`

**Como** desarrollador **quiero** orquestar candado, selección de pares, caché, débito, FlightAPI, reembolso y podio **para** habilitar US-13 a US-18.

Componentes: **SearchQuotes**, **SearchLock**, **RoutingFacade**, **OfferCache**, **BillingFacade**, **FlightOffersProvider**, **ProviderGate**, **QuoteSearch**. Rate limit `quotes_search`.

```gherkin
Escenario: Cotización sin caché
  Dado un usuario verificado con 10 créditos y un mock de FlightAPI con ofertas
  Cuando se envía una búsqueda válida
  Entonces responde 200 con podium de 1 a 3 ofertas, credits_charged = 5 y price_disclaimer
  Y existe un SEARCH_DEBIT con reference_id = search_id
  Y navby:quotes:search:{search_id} tiene TTL ≤ 1,800 s y las ofertas por par quedaron en caché

Escenario: Todo en caché
  Dado que todos los pares elegidos están en caché
  Entonces no se llama a FlightAPI ni a debit_search y credits_charged = 0

Escenario: Reembolsos (RN-09)
  Cuando todas las llamadas fallan y no hay caché → 503 PROVIDER_UNAVAILABLE y existe SEARCH_REFUND
  Cuando FlightAPI responde sin ofertas → 200 con podium = [], credits_charged = 0 y existe SEARCH_REFUND
  Cuando falla 1 de 2 pares → 200 con partial = true y credits_charged = 5

Escenario: Rechazos sin cobro
  Cuando ningún par es alcanzable → 422 ROUTE_NOT_REACHABLE
  Cuando el saldo es 3 y falta caché → 402 INSUFFICIENT_CREDITS
  Cuando ya hay una búsqueda del usuario en curso → 409 SEARCH_IN_PROGRESS
  Cuando el usuario no verificó su correo → 403 EMAIL_NOT_VERIFIED
  Cuando CUSTOM tiene pesos que no suman 1 → 422 INVALID_WEIGHTS
  Cuando las fechas no son ISO, la salida es anterior a hoy (Lima), el retorno es anterior a la salida o supera 330 días → 422 VALIDATION_ERROR
  Cuando los infantes superan a los adultos o el total de pasajeros supera 9 → 422 VALIDATION_ERROR
  Cuando la cabina o la moneda no están en RN-03 → 422 VALIDATION_ERROR
  Cuando Redis no responde → 503 PROVIDER_UNAVAILABLE
  Y en ningún caso existe SEARCH_DEBIT

Escenario: Doble envío concurrente
  Cuando llegan dos peticiones idénticas del mismo usuario al mismo tiempo
  Entonces una responde 200 y la otra 409, y hay un solo SEARCH_DEBIT
```

### TS-15 · `POST /quotes/{search_id}/rank`

**Como** desarrollador **quiero** reordenar la frontera de Pareto con otros pesos **para** habilitar US-20 y US-21.

```gherkin
Escenario: Cambio de perfil
  Dada una búsqueda vigente del usuario
  Cuando se envía { "profile": "SAVER" }
  Entonces responde 200 con el podio recalculado, credits_charged = 0 y el mismo expires_at
  Y el TTL en Redis no aumentó (KEEPTTL)

Escenario: Pesos inválidos
  Cuando CUSTOM suma 1.1 o tiene un peso negativo → 422 INVALID_WEIGHTS

Escenario: Búsqueda ajena o vencida
  Entonces responde 404 SEARCH_NOT_FOUND
```

### TS-16 · `GET /quotes/{search_id}`

**Como** desarrollador **quiero** releer una búsqueda vigente **para** habilitar US-19.

```gherkin
Escenario: Búsqueda propia vigente
  Entonces responde 200 PodiumResponse con los últimos pesos usados y credits_charged = 0

Escenario: Búsqueda ajena, vencida o inexistente
  Entonces responde 404 SEARCH_NOT_FOUND
```

### TS-27 · Motor multicriterio (componente)

**Como** desarrollador **quiero** implementar **ParetoFilter** y **MulticriteriaRanker** como dominio puro **para** calcular el podio según la sección 5.3.

```gherkin
Escenario: Dominancia
  Dadas A(100, 300 min, 1) y B(120, 320 min, 1)
  Entonces B queda fuera de la frontera
  Y ofertas idénticas en los tres criterios conservan la de menor offer_id

Escenario: Normalización y puntaje
  Dada una frontera con precios 100 y 200, duraciones 300 y 600 y escalas iguales
  Entonces las escalas aportan 0 (max = min) y S de la oferta (100, 600) con BALANCED es sqrt(0.3)

Escenario: Desempates y diversidad
  Dadas dos ofertas con igual S
  Entonces gana la de menor precio, luego menor duración, luego salida más temprana
  Y dos ofertas con la misma secuencia de aeropuertos y aerolíneas no aparecen juntas en el podio
  Y dos vuelos directos LIM-MIA de aerolíneas distintas sí pueden aparecer juntos

Escenario: Casos límite
  Dada una frontera vacía → podio []
  Dada una sola oferta → podio de 1 con score 0 y match_pct 100
```

### TS-28 · Adaptador de FlightAPI y semáforo global (componente)

**Como** desarrollador **quiero** traducir FlightAPI a **FlightOffer** con límites de tiempo y concurrencia **para** cotizar de forma segura (RN-16).

```gherkin
Escenario: Traducción
  Dado un fixture JSON real de /roundtrip
  Entonces cada itinerario produce un FlightOffer con precio mínimo, deep_link, legs OUTBOUND e INBOUND, duración y escalas sumadas
  Y offer_id es un hash determinista (el mismo fixture produce los mismos IDs)
  Y se descartan los itinerarios sin precio, sin deep_link o con un tramo de más de 2 escalas

Escenario: Fallas
  Cuando el proveedor responde 5xx → 1 reintento y luego el par se marca como fallido
  Cuando pasan 20 s sin respuesta → el par se marca como fallido sin reintento
  Cuando responde 402 o 429 → el par se marca como fallido y se registra un log ERROR

Escenario: Concurrencia
  Dado FLIGHT_API_MAX_CONCURRENCY = 5
  Cuando 8 llamadas se lanzan a la vez
  Entonces nunca hay más de 5 en curso y las que esperan más de 10 s se marcan como fallidas

Escenario: Modo desarrollo
  Dado que FLIGHT_API_KEY no está definida
  Entonces se usa MockFlightOffersProvider con fixtures por par y no hay llamadas HTTP
```

---

## Billing

### TS-17 · `GET /billing/wallet`

**Como** desarrollador **quiero** devolver el saldo proyectado sin efectos secundarios **para** habilitar US-25 y US-26.

```gherkin
Escenario: Recarga diaria proyectada
  Dada una billetera con free_credits = 0 y free_credits_date = ayer (Lima)
  Cuando se consulta el saldo
  Entonces free_credits = 10 en la respuesta y la fila en la base no cambia

Escenario: Usuario verificado sin billetera todavía
  Entonces responde 10 gratuitos y 0 comprados sin insertar filas

Escenario: Próximo reinicio
  Entonces free_credits_reset_at es la próxima medianoche de America/Lima en UTC (05:00Z)
```

### TS-18 · `GET /billing/transactions`

**Como** desarrollador **quiero** listar las transacciones de créditos paginadas **para** habilitar US-27.

```gherkin
Escenario: Paginación
  Dadas 25 transacciones
  Cuando page = 2 y page_size = 20
  Entonces responde 200 con 5 items, total = 25, ordenados por created_at descendente

Escenario: Aislamiento
  Entonces nunca devuelve transacciones de otro usuario
  Y page_size > 50 → 422 VALIDATION_ERROR
```

### TS-19 · `GET /billing/packages`

**Como** desarrollador **quiero** exponer el catálogo fijo en PEN **para** habilitar US-28.

```gherkin
Escenario: Catálogo
  Entonces responde 200 con currency = "PEN" y los 3 paquetes con price y usd_reference como texto con 2 decimales

Escenario: Acceso público
  Cuando se consulta sin JWT
  Entonces responde 200
```

### TS-20 · `POST /billing/orders`

**Como** desarrollador **quiero** crear la orden y la preferencia de Mercado Pago **para** habilitar US-29.

```gherkin
Escenario: Orden creada
  Dado un usuario verificado
  Cuando se envía { "package_code": "pack_100" }
  Entonces existe una orden PENDING de S/ 16.90 con expires_at = ahora + 24 h
  Y la preferencia se creó con currency_id PEN, external_reference = order_id y expiration_date_to = expires_at
  Y responde 201 con checkout_url

Escenario: Paquete inexistente
  Cuando se envía { "package_code": "pack_999" }
  Entonces responde 404 PACKAGE_NOT_FOUND y no se crea ninguna orden

Escenario: Usuario sin verificar
  Cuando el JWT tiene ev = false
  Entonces responde 403 EMAIL_NOT_VERIFIED
```

### TS-21 · `GET /billing/orders/{order_id}`

**Como** desarrollador **quiero** consultar el estado de una orden propia **para** habilitar US-30.

```gherkin
Escenario: Orden propia
  Entonces responde 200 con su status

Escenario: Orden ajena o inexistente
  Entonces responde 404 ORDER_NOT_FOUND
```

### TS-22 · `POST /billing/webhooks/mercadopago`

**Como** desarrollador **quiero** procesar notificaciones de pago de forma segura e idempotente **para** acreditar las compras (US-29).

```gherkin
Escenario: Pago aprobado
  Dado un webhook firmado con ts reciente y el pago aprobado por S/ 16.90 en PEN
  Entonces la orden pasa a APPROVED, se suman 100 paid_credits y existe una transacción PURCHASE
  Y responde 200

Escenario: Idempotencia
  Cuando el mismo pago se notifica 3 veces, incluso en paralelo
  Entonces los créditos se suman una sola vez

Escenario: Monto distinto
  Dado un pago aprobado por S/ 1.00 para una orden de S/ 16.90
  Entonces la orden sigue PENDING, no se acreditan créditos y se registra un log CRITICAL PAYMENT_MISMATCH

Escenario: Seguridad
  Cuando la firma no coincide o ts tiene más de 300 s → 401 INVALID_WEBHOOK_SIGNATURE
  Cuando type no es "payment" → 200 sin consultar Mercado Pago

Escenario: Reversión
  Dado una orden APPROVED
  Cuando el pago pasa a refunded
  Entonces la orden queda REVERSED y se restan hasta 100 paid_credits sin dejar saldo negativo
```

---

## Itineraries

### TS-29 · `POST /itineraries`

**Como** desarrollador **quiero** guardar una oferta leída del servidor, sin duplicados y respetando el límite **para** habilitar US-22.

```gherkin
Escenario: Guardado nuevo
  Dada una búsqueda vigente del usuario
  Cuando se envía search_id y offer_id
  Entonces responde 201 con la oferta congelada (incluye quoted_at), origin y destination del primer tramo

Escenario: Idempotencia
  Cuando se guarda el mismo offer_id otra vez
  Entonces responde 200 con el itinerario existente y no hay filas nuevas

Escenario: Límite concurrente
  Dado un usuario con 49 itinerarios
  Cuando llegan 2 guardados distintos al mismo tiempo
  Entonces uno responde 201 y el otro 409 ITINERARY_LIMIT_REACHED

Escenario: Búsqueda u oferta inválida
  Cuando la búsqueda venció o es ajena → 404 SEARCH_NOT_FOUND
  Cuando el offer_id no está en la frontera → 404 OFFER_NOT_FOUND
```

### TS-30 · `GET /itineraries`

**Como** desarrollador **quiero** listar itinerarios paginados **para** habilitar US-23.

```gherkin
Escenario: Orden y paginación
  Entonces responde 200 con los items por created_at descendente, page_size por defecto 20 y máximo 50

Escenario: Aislamiento
  Entonces nunca aparecen itinerarios de otro usuario
```

### TS-31 · `GET /itineraries/{id}`

**Como** desarrollador **quiero** devolver el detalle con su aviso de precio histórico **para** habilitar US-23 y US-31.

```gherkin
Escenario: Detalle propio
  Entonces responde 200 con la oferta congelada y price_disclaimer con la fecha de quoted_at

Escenario: Ajeno o inexistente
  Entonces responde 404 ITINERARY_NOT_FOUND
```

### TS-32 · `DELETE /itineraries/{id}`

**Como** desarrollador **quiero** borrar físicamente un itinerario propio **para** habilitar US-24.

```gherkin
Escenario: Borrado
  Entonces responde 204 y la fila ya no existe

Escenario: Ajeno o inexistente
  Entonces responde 404 ITINERARY_NOT_FOUND y nada se borra
```

---

## Plataforma (componentes)

### TS-23 · `GET /health`

**Como** operador **quiero** un chequeo de salud **para** que Caddy y el monitoreo detecten fallas.

```gherkin
Escenario: Todo operativo
  Entonces responde 200 con postgres, redis y graph en "UP", y nodes = 3354, edges = 37326

Escenario: Redis caído
  Entonces responde 503 con redis = "DOWN"
```

### TS-24 · Carga del grafo y del índice de ciudades

**Como** desarrollador **quiero** construir **AirportGraph** al arrancar **para** que Routing responda sin base de datos.

```gherkin
Escenario: Carga correcta
  Entonces el grafo tiene 3,354 nodos, 37,326 aristas con minutes = distance_km / 800 · 60 + 30 y out_degree por aeropuerto
  Y se aplicaron airport_city_overrides.csv y los 119 alias de city_aliases_es.csv

Escenario: Datos inconsistentes
  Cuando un CSV falta o los conteos no coinciden
  Entonces la aplicación no arranca y registra el motivo
```

### TS-25 · BFS con profundidad 3

**Como** desarrollador **quiero** implementar **BreadthFirstSearch** **para** filtrar rutas imposibles sin costo (RN-07).

```gherkin
Escenario: Escalas mínimas
  Entonces LIM→MIA devuelve min_stops = 0 y LIM→NRT devuelve min_stops = 1 o 2 según el grafo

Escenario: Límite de profundidad
  Dado un destino que requiere 3 escalas
  Entonces devuelve reachable = false sin explorar más allá del nivel 3
```

### TS-26 · A\* con límite de tramos y PairSelector

**Como** desarrollador **quiero** implementar **AStarSearch** y **PairSelector** **para** obtener T_min, la ruta preliminar y los 2 mejores pares (RN-14).

```gherkin
Escenario: Optimalidad
  Dada una muestra de 200 pares alcanzables
  Entonces el T_min de A* coincide con una búsqueda exhaustiva de rutas de hasta 3 tramos en todos los casos
  Y la ruta nunca tiene más de 3 tramos ni aeropuertos repetidos

Escenario: Penalización por escala
  Dado que existen una ruta directa y otra con escala ligeramente más corta en distancia
  Entonces T_min suma 60 min por la escala y prefiere la directa cuando corresponde

Escenario: Selección de pares
  Dado Londres (5 aeropuertos) hacia Lima
  Entonces se evalúan los 5 pares y se devuelven 2, ordenados por escalas mínimas, out_degree sumado y T_min
  Y en ida y vuelta se descartan los pares sin regreso
```

### TS-33 · Shared Kernel

**Como** desarrollador **quiero** las piezas comunes (**Result**, errores RFC 7807, *get_current_user*, *get_verified_user*, *rate_limit*, **UnitOfWork**) **para** que todos los contextos las reutilicen.

```gherkin
Escenario: Errores
  Cuando un handler devuelve Result.failure(INSUFFICIENT_CREDITS)
  Entonces la respuesta es 402 application/problem+json con code "INSUFFICIENT_CREDITS"
  Y una excepción no controlada responde 500 INTERNAL_ERROR sin traza

Escenario: Autenticación
  Cuando el JWT tiene otra firma o venció → 401 UNAUTHENTICATED
  Cuando get_verified_user recibe un token con ev = false → 403 EMAIL_NOT_VERIFIED

Escenario: Rate limiting
  Cuando una IP hace 11 logins en un minuto
  Entonces el undécimo responde 429 RATE_LIMITED con cabecera Retry-After
```

### TS-34 · Outbox, bus de eventos y consumidores

**Como** desarrollador **quiero** el relay del outbox y los handlers de `iam.user_verified` y `iam.user_deleted` **para** integrar contextos de forma confiable.

```gherkin
Escenario: Entrega
  Dado un evento pendiente
  Entonces el relay lo publica en menos de 5 s y marca processed_at

Escenario: Idempotencia de consumidores
  Cuando iam.user_verified se entrega dos veces
  Entonces existe una sola billetera

Escenario: Evento envenenado
  Cuando un handler falla 5 veces
  Entonces el evento queda con failed_at, se registra un log CRITICAL
  Y `uv run python -m src.shared.outbox retry <id>` lo vuelve a poner pendiente
```

### TS-35 · Tareas periódicas

**Como** desarrollador **quiero** **ExpirePendingOrders** y **PurgeExpiredTokens** **para** mantener el estado limpio sin intervención manual.

```gherkin
Escenario: Órdenes vencidas
  Dada una orden PENDING con expires_at hace 1 h
  Cuando corre ExpirePendingOrders
  Entonces la orden pasa a EXPIRED

Escenario: Tokens viejos
  Dados refresh tokens vencidos hace 31 días y hace 5 días
  Cuando corre PurgeExpiredTokens
  Entonces solo se borra el de 31 días
```

### TS-37 · Script de benchmark

**Como** equipo **quiero** medir los tres algoritmos del producto **para** la validación del informe (sección 9).

```gherkin
Escenario: Grafo
  Cuando se ejecuta `uv run python -m benchmarks.run --pairs 1000 --seed 42`
  Entonces genera un CSV con tiempo de BFS, tiempo de A*, nodos expandidos y min_stops por par
  Y la misma semilla produce la misma muestra

Escenario: Motor multicriterio
  Entonces genera un CSV con el tiempo del motor para N = 10, 50, 100, 500 y 1,000 ofertas sintéticas, 30 repeticiones cada una
```

### TS-38 · Despliegue

**Como** operador **quiero** el `docker-compose.yml`, el `Caddyfile` y las migraciones de Alembic **para** desplegar en la VM de Azure.

```gherkin
Escenario: Arranque limpio
  Dado un servidor nuevo con Docker
  Cuando se ejecuta docker compose up -d
  Entonces se aplican las migraciones, /health responde 200 vía HTTPS y solo los puertos 80, 443 y 22 están expuestos

Escenario: Un solo worker
  Entonces Uvicorn corre con --workers 1, CORS está desactivado y Caddy sirve navby-api.<región>.cloudapp.azure.com con TLS
```
