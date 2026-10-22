# Navby Webapp

> SPA donde el usuario busca vuelos, ve la ruta en un mapa 2D y recibe el podio de 3 recomendaciones. Las reglas de producto están en [navby-documentation.md](../navby-documentation.md) y los contratos de la API, en [navby-endpoints.md](../backend-documentation/navby-endpoints.md).

## 1. Pantallas

Todas las rutas cuelgan de `https://navby.andeva.tech/app` (Vite con `base: "/app/"` y React Router con `basename="/app"`). La API se llama siempre con rutas relativas `/api/v1/...`: en producción las atiende el proxy de Vercel y en local el proxy de Vite (`server.proxy["/api"] = "http://localhost:8000"`). Ver [entornos y dominios](../backend-documentation/navby-environments-and-deployment.md).

| Ruta | Pantalla | Acceso |
| :--- | :--- | :---: |
| `/` | Buscador + mapa + panel lateral con el podio | Público (cotizar exige sesión) |
| `/login`, `/register`, `/verify-email` | Autenticación (correo y contraseña, o botón de Google). El registro tiene la casilla obligatoria «Acepto los Términos y la Política de Privacidad» (RL-01). | Público |
| `/forgot-password`, `/reset-password?token=` | Recuperación de contraseña | Público |
| `/itineraries`, `/itineraries/:id` | Itinerarios guardados | Sesión |
| `/billing` | Saldo, historial y compra de paquetes. Precios en soles; el equivalente en USD aparece solo como referencia. | Sesión |
| `/billing/result` | Retorno desde Mercado Pago (consulta el estado de la orden; si sigue `PENDING`, reintenta cada 3 s durante 1 min) | Sesión |
| `/account` | Perfil y **Eliminar mi cuenta** (escribe «ELIMINAR» para confirmar, RL-02) | Sesión |

El pie de página de todas las pantallas enlaza a los Términos y la Política de Privacidad del website. Toda tarifa muestra el aviso `price_disclaimer` (RL-03).

La búsqueda vive en la URL (`/app/?trip=ROUND_TRIP&from=LIM&to=HND,NRT&dep=2026-11-01&ret=2026-11-15&ad=2&ch=1&in=0&cabin=ECONOMY&cur=USD&profile=BALANCED`) para poder compartirla y recargarla.

## 2. Flujo de búsqueda

1. **Ciudades.** El usuario escribe una ciudad y el autocompletado consulta `GET /routing/cities`. Elige la **ciudad**, no un aeropuerto: la webapp guarda internamente sus códigos IATA (Tokio → `HND`, `NRT`) y nunca obliga a verlos. Un desplegable opcional «Aeropuertos de Tokio» permite desmarcar alguno. El servidor decide qué combinaciones cotizar (RN-06 y RN-14).
2. **Encuadre.** Al enviar, el mapa ejecuta `fitBounds([origen, destino])`.
3. **Dos peticiones en paralelo:**
   - `GET /routing/preview` → en milisegundos se dibuja la **ruta preliminar de A\*** como arco punteado animado, con el texto «Ruta física más rápida: ~X h».
   - `POST /quotes/search` → mientras responde (normalmente entre 2 y 15 s) el panel muestra *skeletons*.
4. **Podio.** Llega la respuesta: la ruta preliminar se desvanece y se dibujan las 3 rutas reales. Cada tarjeta muestra el puesto, la **afinidad** (`match_pct` %), el precio, la duración, las escalas, «+X h sobre el mínimo físico», las aerolíneas y el botón **Comprar** (abre el `deep_link` en otra pestaña).
5. **Preferencias.** El selector *Equilibrado / Ahorro / Rapidez / Personalizado* llama a `POST /quotes/{search_id}/rank` y reordena el podio sin costo. *Personalizado* abre tres controles deslizantes que siempre suman 100 %.
6. **Guardar.** Cada tarjeta tiene **Guardar** (`POST /itineraries`).

Casos especiales:

| Respuesta | Interfaz |
| :--- | :--- |
| `preview.reachable = false` o `422 ROUTE_NOT_REACHABLE` | Aviso «No hay rutas con 2 escalas o menos entre estas ciudades». No se cobra. |
| `409 SEARCH_IN_PROGRESS` | Se ignora: ya hay una búsqueda en curso y el botón **Buscar** está deshabilitado mientras tanto. |
| `402 INSUFFICIENT_CREDITS` | Toast con enlace a `/billing`. |
| `403 EMAIL_NOT_VERIFIED` | Redirección a `/verify-email`. |
| `503 PROVIDER_UNAVAILABLE` | Toast «No pudimos consultar precios. No se te cobró». |
| `partial: true` | Aviso discreto «Algunos aeropuertos no respondieron». |
| `podium: []` | «No hay vuelos disponibles para esa fecha. No se te cobró». |
| `credits_charged: 0` | Indicador «Resultado reciente: sin costo». |

## 3. Mapa

| Elemento | Implementación |
| :--- | :--- |
| Mapa base | MapLibre GL con el estilo CARTO Positron (o Dark Matter en modo oscuro). No requiere clave. |
| Arcos | deck.gl `ArcLayer` con `greatCircle: true` (arcos ortodrómicos reales), un arco por tramo entre aeropuertos consecutivos. |
| Ruta preliminar | Arco punteado gris con pulso animado. |
| Rutas del podio | Top 1 en `#604AFF`, Top 2 y Top 3 en tonos de la paleta. Al pasar el cursor sobre una tarjeta se resalta su ruta (y al revés). |
| Marcadores | Origen, destino y escalas con IATA y tiempo de conexión. |

El mapa **no** dibuja el grafo completo ni permite elegir aeropuertos con clics: la selección se hace solo desde el buscador.

## 4. Arquitectura

```text
src/
├── app/              # Router, providers (QueryClient, i18n) y layout
├── features/
│   ├── search/       # Formulario, autocompletado y estado de la URL
│   ├── map/          # MapLibre + deck.gl
│   ├── podium/       # Tarjetas y selector de preferencias
│   ├── auth/         # Login, registro, verificación y recuperación
│   ├── itineraries/  # Guardados
│   ├── billing/      # Saldo, paquetes y resultado del pago
│   └── account/      # Perfil y eliminación de cuenta
└── shared/
    ├── api/          # Cliente fetch tipado y schemas Zod de respuestas
    └── ui/           # Componentes del design system
```

| Responsabilidad | Herramienta |
| :--- | :--- |
| Estado del servidor (preview, podio, saldo, guardados) | TanStack Query. El `search_id` y el perfil forman la query key del podio. |
| Estado de la URL (criterios de búsqueda) | React Router (`useSearchParams`). |
| Estado de UI (tarjeta resaltada, panel abierto) | Zustand. |
| Sesión | El access token vive solo en memoria. El refresh token lo maneja el navegador en una cookie `HttpOnly` que JavaScript no puede leer. Al cargar la app y ante un `401`, el cliente llama a `POST /auth/refresh` (con `credentials: "include"`) y reintenta una vez. |
| Validación | Zod: formulario (fechas, pasajeros RN-02, origen ≠ destino) y respuestas de la API. |

## 5. Internacionalización y accesibilidad

- **i18n**: `i18next` + `react-i18next`, idiomas `es` y `en`, detección por `?lang=`, `localStorage` y navegador. Precios con `Intl.NumberFormat` y horas con `Intl.DateTimeFormat` en la zona horaria de cada aeropuerto.
- **Accesibilidad (WCAG 2.1 AA)**:
  - El autocompletado usa `role="combobox"`.
  - El panel de resultados es una región `aria-live="polite"` («Buscando vuelos…», «3 recomendaciones listas»).
  - Hay una **lista textual** equivalente al mapa con cada tramo y escala, para lectores de pantalla.
  - Foco visible con `:focus-visible`.
  - Se respeta `prefers-reduced-motion`: sin vuelo de cámara ni pulsos.

## 6. Pruebas y despliegue

- **Pruebas**: Vitest + Testing Library (componentes), Playwright (buscar → ver podio → cambiar perfil → guardar) y `@axe-core/playwright` (accesibilidad).
- **Calidad**: ESLint 9 (`typescript-eslint`, `jsx-a11y`, `react-hooks`) y Prettier con `prettier-plugin-tailwindcss`.
- **Despliegue**: proyecto Vercel `navby-webapp` como SPA estática. Su `vercel.json` reescribe `/app/(.*)` a `/app/index.html`. El website publica la webapp bajo `navby.andeva.tech/app` mediante un rewrite.
- **Gestor de paquetes**: `pnpm`.

## 7. Dependencias

| Paquete | Versión | Uso |
| :--- | :--- | :--- |
| `react`, `react-dom` | `^19.0.0` | UI. |
| `react-router` | `^7.2.0` | Rutas y parámetros de URL. |
| `@tanstack/react-query` | `^5.66.0` | Estado del servidor. |
| `zustand` | `^5.0.3` | Estado de UI. |
| `maplibre-gl` | `^4.7.1` | Mapa 2D. |
| `react-map-gl` | `^7.1.8` | Integración de MapLibre con React. |
| `@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/mapbox` | `^9.1.0` | `ArcLayer` sobre MapLibre. |
| `react-hook-form`, `zod`, `@hookform/resolvers` | `^7.54.2`, `^3.24.2`, `^3.10.0` | Formularios y validación. |
| `react-day-picker` | `^9.5.1` | Selector de fechas. |
| `boneyard` | `^0.1.4` | Skeletons de carga. |
| `sileo` | `^0.1.5` | Notificaciones toast. |
| `i18next`, `react-i18next`, `i18next-browser-languagedetector` | `^24.2.2`, `^15.4.1`, `^8.0.2` | Internacionalización. |
| `lucide-react` | `^0.475.0` | Iconos. |
| `tailwindcss`, `@tailwindcss/vite` | `^4.0.0` | Estilos (el design system (repositorio `navby-report`)). |
| `typescript`, `vite`, `@vitejs/plugin-react` | `^5.7.3`, `^6.2.0`, `^4.3.4` | Compilación (dev). |
| `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom` | `^3.0.5`, `^16.2.0`, `^14.6.1`, `^6.6.3` | Pruebas (dev). |
| `@playwright/test`, `@axe-core/playwright` | `^1.50.1`, `^4.10.1` | E2E y accesibilidad (dev). |
| `eslint`, `eslint-plugin-jsx-a11y`, `prettier`, `prettier-plugin-tailwindcss` | `^9.20.0`, `^6.10.2`, `^3.5.1`, `^0.6.11` | Calidad (dev). |
