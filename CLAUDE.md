# CLAUDE.md

@AGENTS.md

## Flujo con Claude Code

Este repositorio declara el plugin **superpowers** en `.claude/settings.json`. Al abrir el proyecto, Claude Code ofrece instalarlo; acepta.

Para implementar una historia técnica, invoca la skill del proyecto **`navby-implement-story`** con el ID (`/navby-implement-story TS-14`). Esa skill encadena las de superpowers en este orden:

| Momento | Skill | Para qué |
| :--- | :--- | :--- |
| Antes de empezar | `superpowers:using-git-worktrees` | Aislar la historia en su propia rama y worktree. |
| Plan | `superpowers:writing-plans` | Convertir la historia técnica y su bounded context en un plan paso a paso. No uses `superpowers:brainstorming`: el diseño ya está decidido en `docs/`. Úsala solo si la historia deja algo sin definir. |
| Implementación | `superpowers:test-driven-development` | Cada escenario Gherkin se convierte en una prueba que falla antes del código. |
| Ejecución | `superpowers:executing-plans` (o `superpowers:subagent-driven-development` para historias grandes como TS-14) | Seguir el plan tarea por tarea. |
| Si algo falla | `superpowers:systematic-debugging` | Encontrar la causa raíz antes de parchear. |
| Antes de decir «listo» | `superpowers:verification-before-completion` | Ejecutar pruebas, Ruff y Mypy y mostrar la evidencia. |
| Antes del PR | `superpowers:requesting-code-review` | Revisar el diff contra la historia y la especificación táctica. |
| Cierre | `superpowers:finishing-a-development-branch` | Merge o PR y limpieza del worktree. |

Skills propias del proyecto (`.claude/skills/`):

- **`navby-implement-story`**: flujo completo para una historia técnica.
- **`navby-bounded-context`**: crea la estructura de carpetas de un contexto nuevo.
- **`navby-docs-sync`**: qué hacer cuando el código obliga a cambiar la documentación.

## Recordatorios para Claude

- Lee el documento del bounded context **antes** de escribir código del contexto.
- Si una decisión no está en `docs/`, pregunta en vez de suponer.
- No ejecutes nada que llame a FlightAPI, Mercado Pago o Resend reales.
