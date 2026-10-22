# Navby Platform — Especificación Táctica

> Convenciones obligatorias para escribir y documentar código del backend. La arquitectura general está en [navby-platform-documentation.md](navby-platform-documentation.md); las reglas de producto, en [navby-documentation.md](../navby-documentation.md).

## 1. Reglas de arquitectura

| # | Regla | En la práctica |
| :---: | :--- | :--- |
| 1 | **Dominio puro e inmutable** | Value objects y eventos con `@dataclass(frozen=True, slots=True)` y validación en `__post_init__`. El dominio no importa FastAPI, Pydantic, SQLAlchemy, Redis ni `httpx`. |
| 2 | **Agregados protegen sus invariantes** | El estado solo cambia mediante métodos del agregado (`wallet.debit(...)`), nunca asignando atributos desde afuera. |
| 3 | **Errores de negocio como valores** | Los handlers devuelven `Result[T]`. Las excepciones se reservan para fallas técnicas inesperadas. |
| 4 | **CQRS-lite** | Un handler por comando (escribe) o consulta (lee). Sin bus de comandos: el router llama al handler inyectado. |
| 5 | **Repositorios como contratos** | `typing.Protocol` en `domain/repositories/`. Implementación en `infrastructure/persistence/`. |
| 6 | **Aislamiento de datos** | Cada contexto tiene su propio esquema PostgreSQL. Sin claves foráneas entre contextos. |
| 7 | **Fachadas OHS** | La única forma síncrona de usar otro contexto es su fachada en `interfaces/acl/facade/`. Devuelve DTOs, nunca entidades. |
| 8 | **ACL para externos** | Cada proveedor (FlightAPI, Mercado Pago, Google, Resend) se usa mediante un puerto en `application/acl/ports/` y un adaptador en `infrastructure/adapters/`, con su mock para desarrollo. |
| 9 | **Outbox para eventos entre contextos** | El evento se guarda en `shared.outbox_events` en la misma transacción que el cambio de negocio. |
| 10 | **Contratos HTTP explícitos** | Schemas Pydantic v2 con `extra="forbid"`, errores RFC 7807 y documentación OpenAPI 3.1 generada por FastAPI. |

## 2. Nomenclatura

| Elemento | Patrón | Ejemplo |
| :--- | :--- | :--- |
| Comando / handler | `<Verbo><Objeto>Command`, `...Handler` | `SearchQuotesCommand`, `SearchQuotesHandler` |
| Consulta / handler | `Get<Objeto>Query`, `...Handler` | `GetWalletQuery`, `GetWalletHandler` |
| Evento de dominio | `<Objeto><Participio>` | `UserVerified`, `OrderApproved` |
| Repositorio (contrato) | `<Agregado>Repository` | `CreditWalletRepository` |
| Repositorio (implementación) | `SqlAlchemy<Agregado>Repository`, `Redis<Objeto>Repository` | `SqlAlchemyCreditWalletRepository` |
| Modelo ORM | `<Agregado>Model` | `CreditWalletModel` |
| Fachada OHS | `<Contexto>Facade` | `BillingFacade` |
| Puerto / adaptador ACL | `<Capacidad>` / `<Proveedor><Capacidad>` | `PaymentGateway` / `MercadoPagoPaymentGateway` |
| Schema HTTP | `<Acción>Request`, `<Objeto>Response` | `SearchQuotesRequest`, `PodiumResponse` |
| Archivos | `snake_case.py`, una clase pública por archivo | `credit_wallet.py` |
| Claves Redis | `navby:<contexto>:<objeto>:<id>` | `navby:quotes:search:{search_id}` |

En la documentación, las clases van en **negrita**, los métodos en *cursiva* con paréntesis y el código o las rutas entre `backticks`.

## 3. `Result` y errores

```python
@dataclass(frozen=True, slots=True)
class ApplicationError:
    code: str                 # p. ej. "INSUFFICIENT_CREDITS"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

class Result(Generic[T]):
    @staticmethod
    def success(value: T) -> "Result[T]": ...
    @staticmethod
    def failure(error: ApplicationError) -> "Result[T]": ...
    is_success: bool
    value: T                  # solo si is_success
    error: ApplicationError   # solo si no is_success
```

El router convierte un `Result` fallido en una respuesta RFC 7807 usando el catálogo de abajo:

```json
{
  "type": "https://navby.andeva.tech/errors/INSUFFICIENT_CREDITS",
  "title": "Créditos insuficientes",
  "status": 402,
  "detail": "Se requieren 5 créditos y la billetera tiene 3.",
  "instance": "/api/v1/quotes/search",
  "code": "INSUFFICIENT_CREDITS"
}
```

### Catálogo de códigos de error

| Código | HTTP | Contexto | Cuándo |
| :--- | :---: | :--- | :--- |
| `VALIDATION_ERROR` | 422 | Todos | El cuerpo o los parámetros no cumplen el schema. Incluye `invalid_params`. |
| `RATE_LIMITED` | 429 | Todos | Se superó el límite de peticiones. Incluye la cabecera `Retry-After`. |
| `UNAUTHENTICATED` | 401 | Todos | Falta el JWT o es inválido o expiró. |
| `INTERNAL_ERROR` | 500 | Todos | Falla inesperada. |
| `EMAIL_ALREADY_REGISTERED` | 409 | IAM | Registro con un correo existente. |
| `TERMS_NOT_ACCEPTED` | 422 | IAM | Registro sin aceptar los Términos y la Política de Privacidad (RL-01). |
| `DISPOSABLE_EMAIL` | 422 | IAM | Correo de un dominio desechable (RN-17). |
| `INVALID_CREDENTIALS` | 401 | IAM | Correo o contraseña incorrectos. |
| `EMAIL_NOT_VERIFIED` | 403 | IAM | Login o búsqueda sin correo verificado. |
| `INVALID_OTP` | 400 | IAM | Código incorrecto o expirado. |
| `OTP_ATTEMPTS_EXCEEDED` | 429 | IAM | 5 intentos fallidos. Hay que pedir un código nuevo. |
| `INVALID_RESET_TOKEN` | 400 | IAM | Token de recuperación inválido, usado o expirado. |
| `INVALID_REFRESH_TOKEN` | 401 | IAM | Refresh token inválido, expirado o reutilizado. |
| `INVALID_GOOGLE_TOKEN` | 401 | IAM | `id_token` de Google inválido. |
| `AIRPORT_NOT_FOUND` | 404 | Routing | Código IATA inexistente en el grafo. |
| `ROUTE_NOT_REACHABLE` | 422 | Quotes | Ningún par tiene ruta con ≤ 2 escalas (RN-07). En `/routing/preview` no es error: responde `200` con `reachable: false`. |
| `SEARCH_IN_PROGRESS` | 409 | Quotes | El usuario ya tiene una cotización en curso (RN-15). |
| `INVALID_WEIGHTS` | 422 | Quotes | Pesos fuera de [0, 1] o que no suman 1. |
| `INSUFFICIENT_CREDITS` | 402 | Quotes, Billing | Saldo menor a 5 créditos. |
| `PROVIDER_UNAVAILABLE` | 503 | Quotes | Todas las llamadas a FlightAPI fallaron y no había caché, o Redis no está disponible. Nunca se cobra (RN-09). |
| `SEARCH_NOT_FOUND` | 404 | Quotes, Itineraries | La búsqueda no existe, expiró o es de otro usuario. |
| `OFFER_NOT_FOUND` | 404 | Quotes, Itineraries | La oferta no pertenece a la búsqueda. |
| `ITINERARY_NOT_FOUND` | 404 | Itineraries | No existe o es de otro usuario (no se revela cuál). |
| `ITINERARY_LIMIT_REACHED` | 409 | Itineraries | El usuario ya tiene 50 itinerarios (RN-13). |
| `PACKAGE_NOT_FOUND` | 404 | Billing | Código de paquete inexistente. |
| `ORDER_NOT_FOUND` | 404 | Billing | Orden inexistente o de otro usuario. |
| `INVALID_WEBHOOK_SIGNATURE` | 401 | Billing | Firma `x-signature` de Mercado Pago inválida o con más de 300 s de antigüedad. |

## 4. Transacciones, eventos y outbox

```text
Handler ──► UnitOfWork (una transacción PostgreSQL)
              ├── repositorio.save(agregado)
              ├── outbox.add(eventos de integración del agregado)
              └── commit
OutboxRelay (cada 2 s) ──► SELECT ... FOR UPDATE SKIP LOCKED
              └── InMemoryEventBus.publish(evento) ──► handlers suscritos ──► marcar processed_at
```

- Entrega **al menos una vez**: todo handler de eventos debe ser idempotente.
- Tras 5 fallos, el evento queda con `failed_at` y `last_error` para revisión manual.
- Los eventos de dominio que no salen del contexto se despachan dentro del mismo handler, sin outbox.

Eventos de integración vigentes:

| Evento | Productor | Consumidor | Efecto |
| :--- | :--- | :--- | :--- |
| `iam.user_verified` | IAM | Billing | Crea la billetera del usuario (idempotente por `user_id`). |
| `iam.user_deleted` | IAM | Billing, Itineraries | Billing anula los créditos y conserva las órdenes. Itineraries borra los itinerarios guardados. |

## 5. Autenticación en los routers

- `get_current_user()` (dependencia de FastAPI del Shared Kernel) valida el JWT y devuelve `CurrentUser(user_id, email, email_verified)`.
- `get_verified_user()` además exige correo verificado. La usan los tres endpoints de `/quotes`.
- Los handlers reciben `user_id` explícito y nunca leen el token.

## 6. Rate limiting

Contador de ventana fija en Redis (`navby:ratelimit:{scope}:{key}:{window}`), aplicado como dependencia de FastAPI.

| Scope | Clave | Límite |
| :--- | :--- | :---: |
| `register` | IP | 5 / min |
| `login` | IP | 10 / min |
| `otp` | IP | 10 / min |
| `forgot_password` | IP | 3 / min |
| `routing_preview` | IP | 30 / min |
| `quotes_search` | `user_id` | 10 / min |

## 7. Pruebas

| Nivel | Qué cubre | Herramientas |
| :--- | :--- | :--- |
| Unitarias de dominio | Value objects, agregados, BFS, A\* y motor multicriterio. Sin I/O. | `pytest` |
| Aplicación | Handlers con repositorios en memoria y mocks de puertos. | `pytest`, `pytest-asyncio` |
| Integración | Repositorios contra PostgreSQL y Redis reales (Docker Compose de pruebas). | `pytest`, `httpx.AsyncClient` |
| Contrato ACL | Adaptadores contra fixtures JSON grabadas de FlightAPI y Mercado Pago. | `pytest`, `respx` |
| Benchmark | Tiempos de BFS, A\* y del motor multicriterio (ver sección 9 de [navby-documentation.md](../navby-documentation.md)). | Script `benchmarks/run.py` |

Casos obligatorios del motor multicriterio: dominancia con empates, normalización con `x_max = x_min`, perfiles predeterminados, desempates, regla de diversidad y podio con menos de 3 ofertas.

## 8. Plantilla de documentación por bounded context

Cada archivo `bounded-context-<nombre>.md` tiene estas secciones, en este orden:

1. **Propósito y límites**: qué hace, qué no hace y las reglas `RN-xx` que implementa.
2. **Lenguaje ubicuo**: tabla de términos.
3. **Capa de dominio**: agregados, entidades, value objects, servicios, eventos y repositorios, con miembros clave e invariantes.
4. **Capa de aplicación**: comandos, consultas y handlers (entrada, salida y errores), y puertos.
5. **Capa de interfaces**: endpoints y fachada OHS.
6. **Capa de infraestructura**: persistencia, adaptadores y claves Redis.
7. **Diagrama de clases** (PlantUML) del dominio.
