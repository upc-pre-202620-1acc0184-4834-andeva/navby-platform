# Navby — Entornos, Dominios y Despliegue

> Define las URLs públicas, los entornos, el manejo de secretos y cómo se despliega y verifica el backend. Las variables de entorno están en [navby-platform-documentation.md](navby-platform-documentation.md#variables-de-entorno).

## 1. Dominios y URLs

Todo lo que ve el navegador vive bajo **un solo origen**: `https://navby.andeva.tech`. El backend no tiene subdominio propio de `andeva.tech`: Vercel actúa como proxy hacia la VM de Azure.

| Ruta pública | Qué sirve | Dónde vive realmente |
| :--- | :--- | :--- |
| `https://navby.andeva.tech/` | Website (Astro) | Proyecto Vercel `navby-website` |
| `https://navby.andeva.tech/app/*` | Webapp (React) | Proyecto Vercel `navby-webapp`, con `base: "/app/"` |
| `https://navby.andeva.tech/api/*` | API (FastAPI) | VM de Azure: `https://navby-api.<región>.cloudapp.azure.com/api/*` |

```text
Navegador ──► navby.andeva.tech (Vercel, proyecto navby-website)
                ├── /            → website (estático)
                ├── /app/**      → rewrite → navby-webapp.vercel.app/app/**
                └── /api/**      → rewrite → navby-api.<región>.cloudapp.azure.com/api/**
                                                   │
                                   Azure VM ──► Caddy (TLS) ──► Uvicorn :8000
Mercado Pago (webhook) ─────────────────────────────┘ (llega directo a la VM)
```

`vercel.json` del website:

```json
{
  "rewrites": [
    { "source": "/app", "destination": "https://navby-webapp.vercel.app/app" },
    { "source": "/app/:path*", "destination": "https://navby-webapp.vercel.app/app/:path*" },
    { "source": "/api/:path*", "destination": "https://navby-api.<región>.cloudapp.azure.com/api/:path*" }
  ]
}
```

### 1.1. URL del backend en Azure

La VM recibe una IP pública **estática** con una **etiqueta DNS** de Azure (gratis, sin dominio propio): `navby-api.<región>.cloudapp.azure.com`. Por ejemplo, `navby-api.eastus2.cloudapp.azure.com`. Caddy obtiene el certificado TLS de Let's Encrypt para ese nombre.

Esa URL **no se usa desde el navegador**. Solo la usan:
- el proxy de Vercel;
- Mercado Pago para el webhook;
- el equipo para diagnóstico.

### 1.2. Por qué un solo origen

| Ventaja | Explicación |
| :--- | :--- |
| Cookies de primera parte | La cookie `navby_refresh` pertenece a `navby.andeva.tech`. Si la webapp llamara directo a `cloudapp.azure.com`, sería una cookie de terceros que Safari y Chrome bloquean. |
| Sin CORS | Navegador y API comparten origen, así que no hay preflights ni configuración CORS en producción. |
| URL estable | Si la VM cambia, solo se actualiza el `vercel.json`; la webapp no se recompila. |

Alternativa equivalente, si más adelante se decide: crear el registro DNS `api.navby.andeva.tech → IP de la VM`. Eso eliminaría el proxy pero obligaría a manejar CORS y cookies entre subdominios.

### 1.3. Consecuencias técnicas

- **IP del cliente**: detrás del proxy, la API ve la IP de Vercel. El rate limiting usa la primera IP de `X-Forwarded-For` (variable `TRUST_PROXY_HEADERS=true`). Quien llame directo a la URL de Azure podría falsificar esa cabecera; es un riesgo aceptado para el MVP.
- **Tiempo máximo**: la búsqueda puede tardar hasta 30 s (RN-16 y timeouts de FlightAPI). Hay que verificar que el límite de tiempo del proxy de Vercel en el plan contratado sea mayor.
- **Webapp con prefijo**: Vite usa `base: "/app/"` y React Router usa `basename="/app"`. Los enlaces de correo y de Mercado Pago apuntan a `https://navby.andeva.tech/app/...`.

## 2. Entornos

| Entorno | Para qué | Backend | Integraciones externas | Quién tiene los secretos |
| :--- | :--- | :--- | :--- | :--- |
| **local** | Desarrollo diario | `http://localhost:8000` con Docker Compose (PostgreSQL y Redis) | Mocks y sandbox: FlightAPI mock, Mercado Pago sandbox, correo al log y Google OAuth de desarrollo | Cada desarrollador, en su `.env` (nunca se versiona) |
| **production** | Usuarios reales y demostración | VM de Azure | FlightAPI real, Mercado Pago (siempre sandbox, RL-04), Resend real y Google OAuth de producción | Solo el responsable del proyecto, en el `.env` de la VM y en los *secrets* de GitHub |

No hay un entorno *staging* separado: la VM de $100 USD de crédito no alcanza para dos. Mercado Pago opera **siempre en sandbox**, también en producción: las compras se simulan con una cuenta y tarjetas de prueba, no se cobra dinero real y por eso no se emiten boletas (RL-04).

### 2.1. Cómo se manejan los secretos (como en un equipo real)

1. **El repositorio solo tiene `.env.example`**, con todas las variables, valores de ejemplo y comentarios. `.env` está en `.gitignore`.
2. **En local, nadie necesita secretos de producción.** Con `APP_ENV=local` y sin `FLIGHT_API_KEY`, el backend usa los mocks. Para probar integraciones reales, cada desarrollador crea **sus propias credenciales de prueba**: su cuenta sandbox de Mercado Pago y su cliente OAuth de Google con origen `http://localhost:5173`.
3. **Los secretos de producción** viven en dos lugares, y solo el responsable los escribe:
   - el archivo `/opt/navby/.env` de la VM (permisos `600`);
   - los *secrets* del *environment* `production` de GitHub (solo la llave SSH de despliegue y el host).
4. **Quien desarrolla no ve los secretos, pero sí puede desplegar y verificar.** Hace merge a `main`; GitHub Actions entra a la VM con la llave SSH guardada como secret, actualiza el código, reconstruye los contenedores y ejecuta las pruebas de humo. El resultado y los logs quedan en la pestaña *Actions*.
5. **Rotación:** si un secreto se filtra, se cambia en el proveedor, en `/opt/navby/.env` y se redespliega. Ningún secreto se repite entre local y producción.

### 2.2. Verificar que producción funciona

Después de cada despliegue, el workflow ejecuta `scripts/smoke_test.py` contra `https://navby.andeva.tech/api/v1`:

| Prueba | Qué valida |
| :--- | :--- |
| `GET /health` = 200 | PostgreSQL, Redis y grafo cargado (3,354 nodos). |
| `GET /routing/cities?q=lim` | Grafo, alias en español y proxy de Vercel. |
| `GET /routing/preview?origins=LIM&destinations=MAD` | BFS y A\* con `reachable = true`. |
| Login con la cuenta de humo + `POST /quotes/search` | FlightAPI real, débito de créditos y podio. Consume 2 créditos de FlightAPI, así que corre solo en despliegues manuales (`workflow_dispatch`), no en cada merge. |
| `POST /billing/orders` con la cuenta de humo | Mercado Pago (sandbox) crea la preferencia. |

La cuenta de humo (`SMOKE_USER_EMAIL` y `SMOKE_USER_PASSWORD`) es una cuenta verificada de producción creada por el responsable; sus credenciales viven solo en los secrets de GitHub.

## 3. Configuración por servicio externo

| Servicio | Local | Producción |
| :--- | :--- | :--- |
| Google OAuth | Cliente propio con origen `http://localhost:5173` | Cliente con origen `https://navby.andeva.tech` |
| Mercado Pago | Credenciales `TEST-...` del desarrollador | Credenciales `TEST-...` del proyecto (siempre sandbox, RL-04). Webhook: `https://navby-api.<región>.cloudapp.azure.com/api/v1/billing/webhooks/mercadopago` |
| FlightAPI | Sin clave (mock) | Clave del plan LITE |
| Resend | Sin clave (correo al log) | Dominio `andeva.tech` verificado; remitente `no-reply@andeva.tech` |

## 4. Infraestructura de producción

| Recurso | Configuración |
| :--- | :--- |
| VM | Azure `Standard_B2s` (2 vCPU, 4 GB), Ubuntu 24.04, auto-apagado opcional fuera de horario de demostración. |
| Red | IP pública estática con etiqueta DNS `navby-api`. NSG abierto solo a 80, 443 y 22 (22 restringido a la IP de GitHub Actions o a la del responsable). |
| Servicios | `docker compose` con `platform`, `postgres`, `redis` y `caddy` (ver [plataforma](navby-platform-documentation.md#8-despliegue)). |
| Datos | Volúmenes Docker para PostgreSQL. Respaldo diario con `pg_dump` a un Azure Blob Storage. |
| Caddy | `navby-api.<región>.cloudapp.azure.com { reverse_proxy platform:8000 }`, con TLS automático. |

### 4.1. Despliegue continuo (`.github/workflows/deploy.yml`)

1. Se dispara con un push a `main` o manualmente.
2. Corre pruebas, Ruff y Mypy. Si fallan, no se despliega.
3. Entra por SSH a la VM, ejecuta `git pull`, `docker compose up -d --build` y `alembic upgrade head`.
4. Ejecuta `scripts/smoke_test.py`. Si falla, vuelve al commit anterior (`git checkout <sha previo>` + `docker compose up -d --build`) y marca el despliegue como fallido.
