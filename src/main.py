from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.modules.billing.application.commands.expire_pending_orders import (
    ExpirePendingOrdersHandler,
)
from src.modules.billing.application.event_handlers.forfeit_wallet import (
    ForfeitWalletHandler,
)
from src.modules.billing.application.event_handlers.open_wallet import OpenWalletHandler
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_order_repository import (
    SqlAlchemyCreditOrderRepository,
)
from src.modules.billing.interfaces.rest.router import router as billing_router
from src.modules.iam.application.commands.purge_expired_tokens import (
    PurgeExpiredTokensHandler,
)
from src.modules.iam.domain.model.events.user_deleted import UserDeleted
from src.modules.iam.domain.model.events.user_verified import UserVerified
from src.modules.iam.infrastructure.persistence.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from src.modules.iam.interfaces.rest.router import router as iam_router
from src.modules.itineraries.application.event_handlers.delete_user_itineraries import (
    DeleteUserItinerariesHandler,
)
from src.modules.itineraries.interfaces.rest.router import router as itineraries_router
from src.modules.quotes.interfaces.rest.router import router as quotes_router
from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.infrastructure.persistence.graph_provider import (
    get_airport_graph,
    init_airport_graph,
)
from src.modules.routing.interfaces.rest.router import routing_router
from src.shared.infrastructure.database import close_database, get_engine, init_database
from src.shared.infrastructure.in_memory_event_bus import InMemoryEventBus
from src.shared.infrastructure.outbox_relay import OutboxRelay
from src.shared.infrastructure.periodic_tasks import PeriodicTasks
from src.shared.infrastructure.redis_client import RedisClient, get_shared_redis
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.shared.interfaces.http_errors import register_exception_handlers


class GraphHealthSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    nodes: int
    edges: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    postgres: str
    redis: str
    graph: GraphHealthSchema


def build_outbox_relay(
    session_factory: async_sessionmaker[AsyncSession],
) -> OutboxRelay:
    event_bus = InMemoryEventBus()
    event_bus.subscribe("iam.user_verified", OpenWalletHandler(session_factory))
    event_bus.subscribe("iam.user_deleted", ForfeitWalletHandler(session_factory))
    event_bus.subscribe("iam.user_deleted", DeleteUserItinerariesHandler(session_factory))
    relay = OutboxRelay(session_factory=session_factory, event_bus=event_bus)
    relay.register_event_type("iam.user_verified", UserVerified.from_payload)
    relay.register_event_type("iam.user_deleted", UserDeleted.from_payload)
    return relay


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    graph = init_airport_graph()
    app.state.airport_graph = graph

    _, session_factory = init_database()
    RedisClient.get()

    relay = build_outbox_relay(session_factory)
    app.state.outbox_relay = relay

    def _run_expire_orders() -> Any:
        uow = SqlAlchemyUnitOfWork(session_factory)
        return ExpirePendingOrdersHandler(
            uow=uow, order_repo=SqlAlchemyCreditOrderRepository(uow)
        ).handle()

    def _run_purge_tokens() -> Any:
        uow = SqlAlchemyUnitOfWork(session_factory)
        return PurgeExpiredTokensHandler(
            uow=uow, refresh_repo=SqlAlchemyRefreshTokenRepository(uow)
        ).handle()

    periodic = PeriodicTasks()
    periodic.register("outbox_relay", 2.0, relay.process_pending_batch)
    periodic.register("expire_pending_orders", 3600.0, _run_expire_orders)
    periodic.register("purge_expired_tokens", 86400.0, _run_purge_tokens)
    app.state.periodic_tasks = periodic

    try:
        yield
    finally:
        await periodic.stop_all()
        await RedisClient.close()
        await close_database()


health_router = APIRouter(prefix="/api/v1", tags=["Sistema"])


@health_router.get(
    "/health",
    summary="Verificar estado de salud de la plataforma",
    description=(
        "Comprueba en tiempo real la disponibilidad de **PostgreSQL 16**, **Redis 7** "
        "y la integridad del **grafo aéreo de OpenFlights** cargado en memoria "
        "(exactamente `3,354` aeropuertos IATA y `37,326` aristas dirigidas consolidadas).\n\n"
        "- Devuelve **`200 OK`** cuando los tres subsistemas están en estado `UP`.\n"
        "- Devuelve **`503 Service Unavailable`** si algún componente reporta `DOWN`."
    ),
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def get_health(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    redis: Annotated[Redis, Depends(get_shared_redis)],
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
) -> JSONResponse:
    pg_status = "UP"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pg_status = "DOWN"

    redis_status = "UP"
    try:
        pong = await redis.ping()
        if not pong:
            redis_status = "DOWN"
    except Exception:
        redis_status = "DOWN"

    nodes = len(graph.airports)
    edges = sum(len(edge_list) for edge_list in graph.adjacency.values())
    graph_status = "UP" if (nodes == 3354 and edges == 37326) else "DOWN"

    overall_up = pg_status == "UP" and redis_status == "UP" and graph_status == "UP"
    payload = HealthResponse(
        status="UP" if overall_up else "DOWN",
        postgres=pg_status,
        redis=redis_status,
        graph=GraphHealthSchema(status=graph_status, nodes=nodes, edges=edges),
    )
    return JSONResponse(
        status_code=200 if overall_up else 503,
        content=payload.model_dump(),
    )


OPENAPI_DESCRIPTION = (
    "Backend modular de **Navby**: recomienda el **podio de los 3 mejores vuelos** "
    "entre dos ciudades combinando **precio, duración y escalas** en un único puntaje "
    "multicriterio sobre la **Frontera de Pareto**, respaldado por el grafo mundial de "
    "**OpenFlights** en memoria (**BFS** y **A\\***).\n\n"
    "---\n\n"
    "### 🔐 Cómo autenticarse y probar endpoints protegidos en `/docs`\n\n"
    "1. Despliega **`POST /api/v1/auth/login`** (sección **iam**), haz clic en **Try it out** "
    "y presiona **Execute** (viene precargado con la cuenta verificada de demostración "
    "`demo.azure@mail.com` / `Viajar2026`).\n"
    '2. Copia el valor de `"access_token"` del JSON de respuesta (sin las comillas).\n'
    "3. Sube al botón **`Authorize 🔒`** (arriba a la derecha), pega el token en **Value** "
    "y haz clic en **Authorize**.\n"
    "4. ¡Listo! Todos los endpoints con candado 🔒 enviarán automáticamente el encabezado "
    "`Authorization: Bearer <access_token>`.\n\n"
    "---\n\n"
    "### 🧭 Contextos Delimitados (*Bounded Contexts*)\n\n"
    "- **Sistema (`/api/v1/health`):** estado de PostgreSQL 16, Redis 7 y el grafo de "
    "OpenFlights en memoria (`3,354` nodos, `37,326` aristas).\n"
    "- **iam (`/api/v1/auth`, `/api/v1/users`):** registro con código OTP, login con "
    "contraseña o Google OAuth, rotación de refresh tokens en cookie `HttpOnly` y "
    "gestión de cuenta.\n"
    "- **Routing (`/api/v1/routing`):** autocompletado de ciudades/aeropuertos con alias "
    "en español y vista previa de ruta óptima con **BFS** (mínimo de escalas) y **A\\*** "
    "(tiempo mínimo físico $T_{\\min}$ con distancia Haversine).\n"
    "- **quotes (`/api/v1/quotes`):** cotización real en **FlightAPI**, filtrado de "
    "**Frontera de Pareto** y ordenamiento multicriterio ponderado para elegir el "
    "**podio de 3 vuelos** (`BALANCED`, `BUDGET`, `FAST`, `DIRECT`, `CUSTOM`).\n"
    "- **billing (`/api/v1/billing`):** billetera de créditos (`free_credits` + "
    "`paid_credits`), historial de movimientos, catálogo de paquetes en soles (`PEN`) "
    "y órdenes de compra con **Mercado Pago Checkout Pro**.\n"
    "- **itineraries (`/api/v1/itineraries`):** persistencia de hasta 20 itinerarios "
    "favoritos por usuario a partir de una sesión de cotización activa.\n\n"
    "---\n\n"
    "### 💳 Reglas clave de Créditos y Errores\n\n"
    "- **Cuota mensual gratuita (`RN-14`):** todo usuario verificado recibe **10 créditos "
    "gratuitos al mes** (equivalentes a **5 búsquedas**).\n"
    "- **Costo por búsqueda (`RN-15` a `RN-18`):** cada `POST /api/v1/quotes/search` "
    "consume **2 créditos** solo cuando FlightAPI devuelve ofertas reales; si hay "
    "*cache hit* o fallo del proveedor, se cobran **0 créditos**.\n"
    "- **Reordenamiento gratuito (`RN-13`):** cambiar el perfil o los pesos con "
    "`POST /api/v1/quotes/{search_id}/rank` recalcula el podio en memoria sin consumir "
    "créditos.\n"
    "- **Formato de errores (`RFC 7807`):** cualquier error devuelve "
    "`application/problem+json` con `type`, `title`, `status`, `detail`, `instance`, "
    "`code` y `correlation_id`."
)

OPENAPI_TAGS = [
    {
        "name": "Sistema",
        "description": (
            "Monitoreo de salud de infraestructura (PostgreSQL, Redis y grafo "
            "OpenFlights en memoria)."
        ),
    },
    {
        "name": "iam",
        "description": (
            "**Identidad y Acceso (IAM):** registro de usuarios, verificación por OTP "
            "de 6 dígitos, inicio de sesión con contraseña o Google OAuth, rotación de "
            "sesión (`navby_refresh` cookie `HttpOnly`), recuperación de contraseña y "
            "eliminación de cuenta."
        ),
    },
    {
        "name": "Routing",
        "description": (
            "**Grafo Aéreo y Enrutamiento:** autocompletado de ciudades/aeropuertos IATA "
            "(con soporte de alias en español y sin tildes) y cálculo instantáneo en "
            "memoria de conectividad aérea mediante **BFS** (mínimo de escalas) y **A\\*** "
            "(ruta de tiempo mínimo físico $T_{\\min}$)."
        ),
    },
    {
        "name": "quotes",
        "description": (
            "**Cotización y Motor Multicriterio:** búsqueda de ofertas aéreas reales, "
            "cálculo de la **Frontera de Pareto** (precio, duración y escalas) y "
            "selección del **podio de los 3 mejores vuelos** con reordenamiento gratuito "
            "en tiempo real."
        ),
    },
    {
        "name": "billing",
        "description": (
            "**Billetera y Facturación:** consulta de saldo de créditos gratuitos y "
            "comprados, historial paginado de transacciones, catálogo de paquetes en "
            "soles (`PEN`) e integración con **Mercado Pago Checkout Pro** (creación de "
            "órdenes y webhook HMAC-SHA256)."
        ),
    },
    {
        "name": "itineraries",
        "description": (
            "**Itinerarios Guardados:** almacenamiento de ofertas del podio en la "
            "colección personal del viajero (máximo 20 itinerarios por usuario, con "
            "operación idempotente)."
        ),
    },
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Navby Platform API",
        version="0.12.5",
        description=OPENAPI_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        contact={
            "name": "Equipo ANDEVA — UPC",
            "url": "https://github.com/upc-pre-202620-1acc0184-4834-andeva/navby-platform",
        },
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(routing_router)
    app.include_router(iam_router, prefix="/api/v1")
    app.include_router(quotes_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(itineraries_router, prefix="/api/v1")
    return app


app = create_app()
