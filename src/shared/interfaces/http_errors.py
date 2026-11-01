import logging
from typing import Any, NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.interfaces.error_catalog import ERROR_CATALOG, ErrorDefinition
from src.shared.interfaces.problem_details import ProblemDetails

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
ERROR_TYPE_BASE = "https://navby.andeva.tech/errors"


class ProblemHttpError(Exception):
    def __init__(
        self,
        error: ApplicationError,
        instance: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(error.message)
        self.error = error
        self.instance = instance
        self.headers = headers or {}


def build_problem_response(
    error: ApplicationError,
    instance: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    defn = ERROR_CATALOG.get(
        error.code,
        ErrorDefinition("INTERNAL_ERROR", 500, "Error interno del servidor"),
    )
    invalid_params = error.details.get("invalid_params")
    problem = ProblemDetails(
        type=f"{ERROR_TYPE_BASE}/{defn.code}",
        title=defn.title,
        status=defn.status,
        detail=error.message,
        instance=instance,
        code=defn.code,
        invalid_params=invalid_params if isinstance(invalid_params, list) else None,
    )
    return JSONResponse(
        status_code=defn.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def to_http(
    result: Result[Any],
    request: Request | None = None,
    headers: dict[str, str] | None = None,
) -> ProblemHttpError:
    instance = request.url.path if request is not None else ""
    return ProblemHttpError(error=result.error, instance=instance, headers=headers)


def raise_for_error(
    error: ApplicationError,
    instance: str = "",
    headers: dict[str, str] | None = None,
) -> NoReturn:
    raise ProblemHttpError(error=error, instance=instance, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemHttpError)
    async def handle_problem_error(_request: Request, exc: ProblemHttpError) -> JSONResponse:
        instance = exc.instance or _request.url.path
        return build_problem_response(exc.error, instance=instance, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        invalid_params: list[dict[str, Any]] = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
            invalid_params.append(
                {
                    "name": loc or "request",
                    "reason": str(err.get("msg", "Invalid value")),
                }
            )
        app_err = ApplicationError(
            code="VALIDATION_ERROR",
            message="Los parámetros enviados no son válidos.",
            details={"invalid_params": invalid_params},
        )
        return build_problem_response(app_err, instance=request.url.path)

    @app.exception_handler(Exception)
    async def handle_unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception at %s: %s", request.url.path, type(exc).__name__)
        app_err = ApplicationError(
            code="INTERNAL_ERROR",
            message="Ocurrió un error inesperado en el servidor.",
        )
        return build_problem_response(app_err, instance=request.url.path)
