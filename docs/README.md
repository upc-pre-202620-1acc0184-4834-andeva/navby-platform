# Documentación del backend de Navby

Navby recomienda los 3 mejores vuelos entre dos ciudades combinando precio, duración y escalas en un único puntaje. Esta carpeta contiene todo lo necesario para construir el backend. La documentación completa del producto (website, design system, informe académico) vive en el repositorio `navby-report`.

## Orden de lectura

1. [navby-documentation.md](navby-documentation.md): **fuente de verdad del producto**. Contiene las reglas `RN-xx` y `RL-xx`, los algoritmos, los créditos y el alcance.
2. [navby-platform-documentation.md](backend-documentation/navby-platform-documentation.md): arquitectura, bounded contexts y variables de entorno.
3. [navby-backend-tactical-specification.md](backend-documentation/navby-backend-tactical-specification.md): convenciones de código, `Result`, catálogo de errores y outbox.
4. [technical-stories.md](backlog/technical-stories.md): qué construir y en qué orden (5 sprints).
5. El documento del bounded context de la historia que estés implementando.

## Mapa

| Documento | Contenido |
| :--- | :--- |
| [navby-documentation.md](navby-documentation.md) | Producto, flujo de búsqueda, BFS, A\*, motor multicriterio, reglas de negocio, créditos, alcance y requisitos legales. |
| [navby-platform-documentation.md](backend-documentation/navby-platform-documentation.md) | Stack, capas, estructura de carpetas, mapa de contextos, ciclo de vida y variables de entorno. |
| [navby-backend-tactical-specification.md](backend-documentation/navby-backend-tactical-specification.md) | Reglas de arquitectura, nomenclatura, errores, eventos, rate limiting y pruebas. |
| [navby-endpoints.md](backend-documentation/navby-endpoints.md) | Contratos REST: 27 endpoints con ejemplos y errores. |
| [navby-database-schema.md](backend-documentation/navby-database-schema.md) | DDL de PostgreSQL 16, débito atómico y claves de Redis 7. |
| [flight-api-documentation.md](backend-documentation/flight-api-documentation.md) | Integración con FlightAPI: endpoints, traducción a ofertas y manejo de fallas. |
| [navby-environments-and-deployment.md](backend-documentation/navby-environments-and-deployment.md) | Dominios, entornos local y producción, secretos, despliegue continuo y pruebas de humo. |
| [bounded-context-shared.md](backend-documentation/extended-bounded-contexts-description/bounded-context-shared.md) | Shared Kernel. |
| [bounded-context-iam.md](backend-documentation/extended-bounded-contexts-description/bounded-context-iam.md) | Cuentas, sesiones, Google, recuperación y eliminación de cuenta. |
| [bounded-context-routing.md](backend-documentation/extended-bounded-contexts-description/bounded-context-routing.md) | Grafo, BFS, A\*, ciudades y selección de pares. |
| [bounded-context-quotes.md](backend-documentation/extended-bounded-contexts-description/bounded-context-quotes.md) | Cotización, caché, motor multicriterio y podio. |
| [bounded-context-billing.md](backend-documentation/extended-bounded-contexts-description/bounded-context-billing.md) | Créditos, débitos, reembolsos y Mercado Pago. |
| [bounded-context-itineraries.md](backend-documentation/extended-bounded-contexts-description/bounded-context-itineraries.md) | Itinerarios guardados. |
| [user-stories.md](backlog/user-stories.md) | 34 historias de usuario en Gherkin. |
| [technical-stories.md](backlog/technical-stories.md) | 37 historias técnicas del backend: una por endpoint y por componente. |
| [navby-webapp-documentation.md](frontend-documentation/navby-webapp-documentation.md) | Referencia: cómo la webapp consume la API. |
| [../data/README.md](../data/README.md) | Datasets que carga el backend. |

## Si el código y la documentación no coinciden

La documentación es el contrato. Si al implementar descubres que algo no funciona como está escrito, primero se corrige el documento (y se avisa al equipo para replicarlo en `navby-report`) y luego el código. Nunca al revés en silencio.
