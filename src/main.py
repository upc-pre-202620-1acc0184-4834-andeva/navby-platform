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


def create_app() -> FastAPI:
    app = FastAPI(
        title="Navby Platform API",
        version="0.1.0",
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
