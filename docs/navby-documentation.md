# Navby — Especificación de Producto (Fuente de Verdad)

> **Qué es este documento.** Define *qué hace* Navby y *con qué reglas*. Todo número, regla de negocio o algoritmo que aparezca en otro documento debe coincidir con este. Si hay contradicción, **este documento gana** y el otro se corrige.
>
> Mapa completo de la documentación: [docs/README.md](README.md).

---

## 1. Resumen en una línea

**Navby recomienda los 3 mejores vuelos entre dos ciudades combinando precio, duración y número de escalas en un único puntaje.**

No muestra categorías aisladas como «el más barato», «el más rápido» o «el de menos escalas». Las tres recomendaciones (el **podio**) salen del mismo puntaje combinado, ordenado de mejor a peor.

---

## 2. Problema que resuelve

Los buscadores de vuelos obligan al viajero a elegir entre extremos: ordenar por precio devuelve vuelos con escalas eternas y ordenar por duración devuelve tarifas impagables. El usuario termina comparando decenas de opciones a mano.

Navby evalúa las tres dimensiones a la vez y entrega solo las tres opciones con mejor balance, con enlace directo de compra a la aerolínea o agencia (*deep link*). Navby **no vende pasajes** ni cobra comisiones.

---

## 3. Glosario

| Término | Definición |
| :--- | :--- |
| **Búsqueda** | Consulta de un usuario: origen, destino, tipo de viaje, fechas, pasajeros, cabina y moneda. |
| **Par de aeropuertos** | Combinación concreta origen–destino (ej. `LIM`–`NRT`). Una ciudad con varios aeropuertos genera varios pares. |
| **Oferta** | Itinerario real devuelto por FlightAPI: precio total, duración real, escalas, segmentos y *deep link*. |
| **Frontera de Pareto** | Ofertas que no son superadas por ninguna otra en los tres criterios a la vez. |
| **Puntaje (S)** | Distancia ponderada de una oferta al punto ideal. Valor entre 0 y 1; **menor es mejor**. |
| **Afinidad** | `(1 − S) × 100` %. Es el puntaje mostrado al usuario; **mayor es mejor**. |
| **Podio** | Las 3 ofertas con menor S (Top 1, Top 2, Top 3). |
| **Perfil de preferencias** | Pesos de precio, duración y escalas usados en el puntaje. |
| **T_min** | Duración física mínima estimada por A\* sobre el grafo (sin esperas reales). Es una referencia, no un precio ni una oferta. |
| **Crédito Navby** | Unidad de consumo. Una búsqueda cuesta 5 créditos. |

---

## 4. Flujo de una búsqueda

```text
Usuario ──► Webapp ──┬──► GET  /routing/preview   (gratis, público)
                     │      BFS: ¿hay ruta con ≤ 2 escalas?  → mínimo de escalas
                     │      A*:  ruta física más rápida      → T_min + ruta preliminar en el mapa
                     │
                     └──► POST /quotes/search      (5 créditos, autenticado)
                            1. Validar entrada
                            2. BFS + A* sobre todos los pares de aeropuertos de ambas ciudades
                               (descarta pares sin ruta y elige los 2 mejores, costo cero)
                            3. Caché Redis por par (TTL 30 min)
                            4. Si algún par no está en caché: debitar 5 créditos
                            5. FlightAPI: 1 llamada por par elegido sin caché (máx. 2)
                            6. Motor multicriterio: Pareto → normalizar → puntaje → podio
                            7. Responder podio con segmentos, coordenadas y deep links
```

La webapp lanza ambas peticiones en paralelo. La ruta preliminar de A\* aparece en el mapa en milisegundos; cuando llega el podio, la ruta preliminar se desvanece y se dibujan las 3 rutas reales.

---

## 5. Algoritmos

Navby usa **exactamente tres algoritmos**. No existe ningún otro algoritmo en el producto ni en la documentación.

| Algoritmo | Pregunta que responde | Dónde corre | Complejidad |
| :--- | :--- | :--- | :---: |
| **BFS** | ¿Existe ruta con ≤ 2 escalas? ¿Cuál es el mínimo de escalas? | Routing, en memoria | O(V + E) |
| **A\*** | ¿Cuál es la ruta físicamente más rápida (≤ 2 escalas)? | Routing, en memoria | O(K · E log(K · V)), K = 3 |
| **Multicriterio** | ¿Cuáles son las 3 mejores ofertas reales? | Quotes, en memoria | O(N²) |

V = 3,354 aeropuertos, E = 37,326 rutas, N = ofertas recibidas (decenas a cientos).

### 5.1. BFS — filtro de costo cero

- Recorre el grafo por niveles desde el origen y se detiene en **profundidad 3** (3 tramos = 2 escalas).
- Si el destino no aparece, el par se descarta **antes** de gastar créditos o llamar a FlightAPI.
- El nivel donde aparece el destino es el **mínimo teórico de escalas**.

### 5.2. A\* — referencia física y ruta preliminar

Peso de cada tramo (minutos):

$$w(u, v) = \frac{d_H(u, v)}{800\ \text{km/h}} \cdot 60 + 30$$

Penalización de conexión: **+60 min por cada escala** (se suma al expandir desde un aeropuerto que no es el origen).

Heurística (minutos):

$$h(u) = \frac{d_H(u, \text{destino})}{800\ \text{km/h}} \cdot 60$$

- `d_H` es la distancia Haversine (R = 6,371 km). La heurística mide desde el **aeropuerto actual** hasta el destino.
- Es **admisible y consistente**: ningún vuelo es más corto que el círculo máximo ni más rápido que la velocidad de crucero, y no incluye maniobras ni conexiones.
- El estado de búsqueda es `(aeropuerto, tramos usados)` con máximo 3 tramos, de modo que T_min es comparable con las ofertas (≤ 2 escalas).

Salidas:

1. **T_min**: duración física mínima. Se muestra en cada oferta del podio como «+X h sobre el mínimo físico».
2. **Ruta preliminar**: secuencia de aeropuertos con coordenadas, dibujada mientras carga la cotización.
3. **Selección de pares**: en ciudades con varios aeropuertos, BFS y A\* ordenan todas las combinaciones y solo se cotizan las 2 mejores (RN-14).

T_min **no** se usa para normalizar el puntaje (ver 5.3).

### 5.3. Motor multicriterio — el podio

Criterios por oferta: **precio total** (todos los pasajeros), **duración total** (minutos, suma de ida y vuelta) y **escalas totales** (suma de ida y vuelta).

1. **Filtro de Pareto.** Se descarta toda oferta dominada. *a* domina a *b* si *a* es menor o igual en los tres criterios y estrictamente menor en al menos uno.
2. **Normalización min–max** sobre la frontera de Pareto, por criterio:
   $$x' = \frac{x - x_{\min}}{x_{\max} - x_{\min}}$$
   0 = mejor oferta real disponible, 1 = peor. Si `x_max = x_min`, entonces `x' = 0`.
3. **Puntaje**: distancia euclidiana ponderada al punto ideal (0, 0, 0):
   $$S = \sqrt{\alpha\, p'^2 + \beta\, t'^2 + \gamma\, e'^2}, \qquad \alpha + \beta + \gamma = 1$$
4. **Ordenamiento** ascendente por S. Desempates: menor precio, menor duración, salida más temprana y, por último, `offer_id`.
5. **Podio**: las 3 primeras ofertas, **saltando** las que tengan a la vez la misma secuencia de aeropuertos **y** las mismas aerolíneas que una oferta ya elegida. Así no se muestran tres horarios del mismo vuelo, pero sí vuelos directos de aerolíneas distintas. Si hay menos de 3 ofertas, el podio tiene 1 o 2. Si no hay ofertas, no se calcula nada y el podio queda vacío.

> **Por qué se normaliza con la mejor oferta real y no con T_min.** T_min no incluye esperas reales en aeropuertos. Si fuera el ideal, ninguna oferta llegaría a 0 en duración y el precio pesaría más de lo que dicen los pesos. Con la mejor oferta real, cada peso significa exactamente lo que declara.

### 5.4. Perfiles de preferencias

| Perfil | Código | α (precio) | β (duración) | γ (escalas) |
| :--- | :--- | :---: | :---: | :---: |
| Equilibrado (predeterminado) | `BALANCED` | 0.5 | 0.3 | 0.2 |
| Ahorro | `SAVER` | 0.7 | 0.2 | 0.1 |
| Rapidez | `FAST` | 0.2 | 0.6 | 0.2 |
| Personalizado | `CUSTOM` | libre | libre | libre |

- `CUSTOM` exige cada peso en [0, 1] y suma = 1 (tolerancia ± 0.001).
- Cambiar de perfil **reordena** la frontera de Pareto ya cotizada: no llama a FlightAPI y **no cuesta créditos** mientras la búsqueda siga en caché (30 min).

---

## 6. Reglas de negocio

| ID | Regla |
| :--- | :--- |
| **RN-01** | Viajes soportados: solo ida (`ONE_WAY`) e ida y vuelta (`ROUND_TRIP`). En ida y vuelta el regreso sale del aeropuerto de llegada y vuelve al de salida (sin combinaciones cruzadas). |
| **RN-02** | Pasajeros: 1–9 adultos, 0–8 niños (2–11 años), infantes (< 2 años) ≤ adultos. Total ≤ 9. |
| **RN-03** | Cabinas: `ECONOMY`, `PREMIUM_ECONOMY`, `BUSINESS`, `FIRST`. Moneda de las tarifas mostradas: `USD` o `PEN`. |
| **RN-04** | Fechas ISO `YYYY-MM-DD`. Salida ≥ hoy (hora de Lima). Retorno ≥ salida. Máximo 330 días a futuro. |
| **RN-05** | Máximo **2 escalas** por tramo (ida o vuelta). Coincide con lo que devuelve FlightAPI y con el límite de BFS y A\*. |
| **RN-06** | **Búsqueda por ciudad**: el usuario elige ciudades, no aeropuertos, y puede escribirlas en español o inglés (ver alias en la sección 8). Se usan todos los aeropuertos de la ciudad y el usuario puede, si quiere, desmarcar alguno. Una ciudad agrupa los aeropuertos con el mismo nombre de ciudad y país que estén a menos de 80 km entre sí. |
| **RN-07** | Los pares sin ruta según BFS se descartan sin costo. Si ningún par tiene ruta, la búsqueda se rechaza con `ROUTE_NOT_REACHABLE` y **no se cobra**. |
| **RN-08** | **Costo**: 5 créditos por búsqueda si al menos un par requiere llamar a FlightAPI. Si todos los pares están en caché, la búsqueda cuesta **0 créditos**. |
| **RN-09** | Los créditos se debitan **antes** de llamar a FlightAPI y se **reembolsan** si todas las llamadas fallan o si FlightAPI no devuelve ningún vuelo. Si falla solo un par, se responde con lo obtenido (`partial: true`) y no hay reembolso. |
| **RN-10** | Caché de ofertas por par: 30 min. La sesión de búsqueda dura 30 min desde su creación; reordenarla no extiende ese plazo. |
| **RN-11** | Reordenar con otro perfil es gratis y solo funciona sobre una búsqueda vigente del mismo usuario. |
| **RN-12** | Cotizar exige usuario autenticado con correo verificado. La vista previa de ruta es pública. |
| **RN-13** | Guardar un itinerario es gratis. Máximo 50 itinerarios guardados por usuario. |
| **RN-14** | **Selección de pares**: se evalúan con BFS y A\* todas las combinaciones origen–destino y se cotizan como máximo las **2 mejores**. Orden: menos escalas mínimas, luego más rutas directas sumadas de ambos aeropuertos (indica oferta comercial real) y luego menor T_min. El usuario no tiene que elegir aeropuertos. |
| **RN-15** | Un usuario solo puede tener **una cotización en curso**. Una segunda petición mientras la primera no termina se rechaza con `SEARCH_IN_PROGRESS` y no se cobra. |
| **RN-16** | Las llamadas simultáneas a FlightAPI de toda la plataforma no superan el límite del plan contratado (5 en LITE). Las que exceden esperan su turno hasta 10 s; si no consiguen turno, ese par cuenta como fallido. |
| **RN-17** | **Cuentas reales**: no se aceptan correos de dominios desechables (lista mantenida en el backend). La billetera con los créditos gratuitos se crea recién cuando el correo queda verificado (o al entrar con Google). |

---

## 7. Créditos y monetización

| Concepto | Valor |
| :--- | :--- |
| Costo por búsqueda | **5 créditos** (ver RN-08) |
| Créditos gratuitos | **10 por día** (2 búsquedas). No acumulables. Se renuevan a las **00:00 de Lima** (America/Lima, UTC−5). |
| Orden de consumo | Primero los gratuitos, luego los comprados. |
| Créditos comprados | Perpetuos y acumulables. |
| Pasarela | Mercado Pago Checkout Pro, **solo en soles (PEN)**. Pago único, sin suscripciones. Opera **siempre en modo sandbox**: las compras se simulan con tarjetas de prueba y no se cobra dinero real (RL-04). |

| Código | Nombre | Créditos | Búsquedas | Precio (cobro) | Referencia USD (solo informativa) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `pack_50` | Escapada | 50 | 10 | S/ 9.90 | ≈ $2.49 |
| `pack_100` | Viajero Frecuente | 100 | 20 | S/ 16.90 | ≈ $4.49 |
| `pack_250` | Nómada | 250 | 50 | S/ 34.90 | ≈ $8.99 |

### 7.1. Costo para la plataforma

| Concepto | Valor |
| :--- | :--- |
| Plan inicial de FlightAPI | LITE: $49 USD/mes por 30,000 créditos y 5 llamadas simultáneas. |
| Costo por llamada | 2 créditos FlightAPI ≈ $0.0033 USD. |
| Llamadas por búsqueda | 1 (98 % de las ciudades) o 2 (ciudades con varios aeropuertos, RN-14). |
| Capacidad del plan | ≈ 15,000 llamadas/mes, unas 13,000 búsquedas reales sin contar la caché. |
| Ingreso por búsqueda pagada | Entre S/ 0.70 y S/ 0.99 según el paquete. |

Si el volumen supera la capacidad del plan o las 5 llamadas simultáneas generan esperas frecuentes, se migra al plan STANDARD ($99 USD/mes, 100,000 créditos, 10 simultáneas) y se actualiza RN-16.

---

## 8. Datos del grafo

Fuente: OpenFlights, depurado en 5 fases (detalle en [data/README.md](../data/README.md)).

| Archivo | Registros | Rol |
| :--- | :---: | :--- |
| `airports.csv` | 3,354 | Vértices: aeropuertos comerciales con IATA, ciudad, país y coordenadas. |
| `routes_unique.csv` | 37,326 | Aristas dirigidas únicas con distancia Haversine. |
| `airport_city_overrides.csv` | 1 | Corrige la ciudad de aeropuertos que OpenFlights registra con otro nombre (Newark `EWR` → New York). |
| `city_aliases_es.csv` | 119 | Nombres en español de las ciudades que difieren del inglés (Tokio → Tokyo, Londres → London, Nueva York → New York). Lo usa el autocompletado (RN-06). |

El grafo **no tiene precios ni horarios**: solo dice qué rutas directas existen. Precios, duraciones reales y disponibilidad vienen siempre de FlightAPI.

---

## 9. Benchmarking

La validación académica mide **los tres algoritmos del producto**; no existen algoritmos de referencia adicionales.

- Un script offline (`uv run python -m benchmarks.run`) ejecuta BFS y A\* sobre una muestra de pares origen–destino y el motor multicriterio sobre conjuntos de ofertas de distinto tamaño (N).
- Mide tiempo de ejecución, nodos expandidos por A\* frente a V y crecimiento del motor multicriterio respecto a N, y exporta CSV para el informe.
- La respuesta de `/routing/preview` incluye una telemetría ligera (tiempo de BFS, tiempo de A\* y nodos expandidos) útil para la demostración.

---

## 10. Alcance

**Incluido:** búsqueda por ciudad (en español o inglés), vista previa de ruta, cotización real, podio multicriterio con perfiles de preferencias, guardado de itinerarios, créditos diarios y paquetes prepagados, registro con correo verificado y aceptación de términos, inicio de sesión con Google, recuperación de contraseña y eliminación de cuenta.

**Excluido:**

| Exclusión | Motivo |
| :--- | :--- |
| Viajes multidestino | FlightAPI exige 3–5 tramos fijos, cuesta 5 créditos por llamada y no es un problema de caminos sobre el grafo. |
| Venta de pasajes y emisión de boletos | La compra ocurre en la aerolínea o agencia vía *deep link*. |
| Cobro de dinero real y boletas electrónicas SUNAT | Mercado Pago opera solo en sandbox: no hay ventas reales, así que no se integra ningún facturador (ver RL-04 en la sección 12). |
| Suscripciones o cobros recurrentes | Solo pagos únicos prepagados. |
| Roles de administrador y perfiles públicos | No aportan a la recomendación. |
| Explorador de conectividad o del grafo completo | No aporta a la recomendación. |
| Globo 3D, rastreo de aeronaves en vivo, carga aérea, inventario de asientos | Fuera del objetivo del producto. |

---

## 11. Componentes del sistema

| Componente | Tecnología | Documento |
| :--- | :--- | :--- |
| Backend (Navby Platform) | Python 3.12+, FastAPI, PostgreSQL 16, Redis 7, Caddy 2 | [navby-platform-documentation.md](backend-documentation/navby-platform-documentation.md) |
| Webapp | React 19, TypeScript, Vite 6, MapLibre GL, deck.gl | [navby-webapp-documentation.md](frontend-documentation/navby-webapp-documentation.md) |
| Website | Astro 5, Tailwind CSS v4 | repositorio `navby-report` |

| Servicio externo | Uso |
| :--- | :--- |
| FlightAPI | Ofertas reales (`/onewaytrip`, `/roundtrip`). |
| Mercado Pago | Compra de paquetes de créditos. |
| Google Identity Services | Inicio de sesión con Google. |
| Resend | Correos de verificación, y recuperación de contraseña. |
| CARTO Basemaps | Mapa base de la webapp. |

---

## 12. Requisitos legales (Perú)

| ID | Requisito | Cómo se cumple |
| :--- | :--- | :--- |
| **RL-01** | Consentimiento para tratar datos personales (Ley 29733). | El registro, local o con Google, exige aceptar los Términos y la Política de Privacidad. Se guardan la fecha y la versión aceptada. |
| **RL-02** | Derecho a suprimir los datos personales (Ley 29733). | El usuario puede eliminar su cuenta. Se anonimizan nombre y correo, se borran sesiones e itinerarios, y se conservan las órdenes de compra por obligación tributaria. |
| **RL-03** | Precios referenciales. | Toda tarifa se muestra con el aviso «Precio referencial obtenido de terceros; se confirma en el sitio del vendedor». |
| **RL-04** | Comprobantes de pago (SUNAT). | **No aplica.** Mercado Pago opera siempre en modo sandbox, en local y en producción: las compras de paquetes se simulan con tarjetas de prueba y no se cobra dinero real, por lo que no se emiten boletas ni se integra un facturador. Si algún día se cobrara dinero real, integrar un facturador electrónico (Nubefact u otro) sería obligatorio antes de hacerlo. |
