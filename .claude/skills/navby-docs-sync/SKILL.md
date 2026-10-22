---
name: navby-docs-sync
description: Use when implementation reveals that docs/ is wrong, incomplete or contradictory (a rule, contract, error code, table or story that cannot work as written), or when a behavior change is requested — updates the documentation contract before or together with the code. Triggers on "la documentación dice", "contradicción", "no coincide con docs", "cambiar el contrato".
---

# Mantener `docs/` como contrato

La documentación manda sobre el código. Un cambio de comportamiento sin cambio de documentación es un bug.

## Cuándo aplica

- Un escenario de una historia no se puede cumplir tal como está escrito.
- Dos documentos se contradicen (un endpoint, un código de error, una tabla o un número).
- Hace falta un código de error, una variable de entorno, una tabla o una regla nueva.
- El equipo decide cambiar un comportamiento.

## Pasos

1. **Detente y explica** el problema al usuario: archivo, línea, qué dice, por qué no funciona y una propuesta concreta. No cambies comportamiento sin aprobación.
2. Con la aprobación, actualiza **todos** los documentos afectados en el mismo PR que el código. Usa esta tabla para no olvidar ninguno:

| Si cambia… | Actualizar |
| :--- | :--- |
| Una regla de negocio, un número o un algoritmo | `docs/navby-documentation.md` (la regla `RN-xx`) y todo documento que la cite |
| Un endpoint (ruta, cuerpo, respuesta o error) | `navby-endpoints.md`, el documento del bounded context y la historia técnica |
| Un código de error | El catálogo en `navby-backend-tactical-specification.md` |
| Una tabla o clave de Redis | `navby-database-schema.md` y el documento del bounded context |
| Una variable de entorno | `navby-platform-documentation.md`, `.env.example` y, si aplica, `navby-environments-and-deployment.md` |
| Un comportamiento visible para el usuario | `docs/backlog/user-stories.md` |

3. Busca referencias antiguas con `grep -rn "<término viejo>" docs/` y corrígelas todas.
4. Agrega una nota en la descripción del PR: «Cambios de documentación: …», para que el responsable los replique en el repositorio `navby-report`.
