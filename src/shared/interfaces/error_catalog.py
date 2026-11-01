from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorDefinition:
    code: str
    status: int
    title: str


ERROR_CATALOG: dict[str, ErrorDefinition] = {
    "VALIDATION_ERROR": ErrorDefinition("VALIDATION_ERROR", 422, "Error de validación"),
    "RATE_LIMITED": ErrorDefinition("RATE_LIMITED", 429, "Límite de peticiones excedido"),
    "UNAUTHENTICATED": ErrorDefinition("UNAUTHENTICATED", 401, "No autenticado"),
    "INTERNAL_ERROR": ErrorDefinition("INTERNAL_ERROR", 500, "Error interno del servidor"),
    "EMAIL_ALREADY_REGISTERED": ErrorDefinition(
        "EMAIL_ALREADY_REGISTERED", 409, "Correo ya registrado"
    ),
    "TERMS_NOT_ACCEPTED": ErrorDefinition(
        "TERMS_NOT_ACCEPTED", 422, "Términos y condiciones no aceptados"
    ),
    "DISPOSABLE_EMAIL": ErrorDefinition(
        "DISPOSABLE_EMAIL", 422, "Correo de dominio desechable no permitido"
    ),
    "INVALID_CREDENTIALS": ErrorDefinition("INVALID_CREDENTIALS", 401, "Credenciales inválidas"),
    "EMAIL_NOT_VERIFIED": ErrorDefinition("EMAIL_NOT_VERIFIED", 403, "Correo no verificado"),
    "INVALID_OTP": ErrorDefinition("INVALID_OTP", 400, "Código de verificación inválido"),
    "OTP_ATTEMPTS_EXCEEDED": ErrorDefinition(
        "OTP_ATTEMPTS_EXCEEDED", 429, "Intentos de verificación agotados"
    ),
    "INVALID_RESET_TOKEN": ErrorDefinition(
        "INVALID_RESET_TOKEN", 400, "Token de recuperación inválido"
    ),
    "INVALID_REFRESH_TOKEN": ErrorDefinition(
        "INVALID_REFRESH_TOKEN", 401, "Refresh token inválido"
    ),
    "INVALID_GOOGLE_TOKEN": ErrorDefinition(
        "INVALID_GOOGLE_TOKEN", 401, "Token de Google inválido"
    ),
    "AIRPORT_NOT_FOUND": ErrorDefinition("AIRPORT_NOT_FOUND", 404, "Aeropuerto no encontrado"),
    "ROUTE_NOT_REACHABLE": ErrorDefinition("ROUTE_NOT_REACHABLE", 422, "Ruta no alcanzable"),
    "SEARCH_IN_PROGRESS": ErrorDefinition("SEARCH_IN_PROGRESS", 409, "Búsqueda en curso"),
    "INVALID_WEIGHTS": ErrorDefinition("INVALID_WEIGHTS", 422, "Pesos de preferencias inválidos"),
    "INSUFFICIENT_CREDITS": ErrorDefinition("INSUFFICIENT_CREDITS", 402, "Créditos insuficientes"),
    "PROVIDER_UNAVAILABLE": ErrorDefinition("PROVIDER_UNAVAILABLE", 503, "Proveedor no disponible"),
    "SEARCH_NOT_FOUND": ErrorDefinition("SEARCH_NOT_FOUND", 404, "Búsqueda no encontrada"),
    "OFFER_NOT_FOUND": ErrorDefinition("OFFER_NOT_FOUND", 404, "Oferta no encontrada"),
    "ITINERARY_NOT_FOUND": ErrorDefinition("ITINERARY_NOT_FOUND", 404, "Itinerario no encontrado"),
    "ITINERARY_LIMIT_REACHED": ErrorDefinition(
        "ITINERARY_LIMIT_REACHED", 409, "Límite de itinerarios alcanzado"
    ),
    "PACKAGE_NOT_FOUND": ErrorDefinition("PACKAGE_NOT_FOUND", 404, "Paquete no encontrado"),
    "ORDER_NOT_FOUND": ErrorDefinition("ORDER_NOT_FOUND", 404, "Orden no encontrada"),
    "INVALID_WEBHOOK_SIGNATURE": ErrorDefinition(
        "INVALID_WEBHOOK_SIGNATURE", 401, "Firma de webhook inválida"
    ),
}
