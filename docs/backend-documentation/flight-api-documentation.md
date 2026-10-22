# Integración con FlightAPI

> FlightAPI ([flightapi.io](https://www.flightapi.io)) es la única fuente de precios, duraciones reales y *deep links*. Solo la usa el bounded context **Quotes**, mediante su Anti-Corruption Layer. Reglas de costo y caché: RN-06 a RN-10 en [navby-documentation.md](../navby-documentation.md).

## 1. Endpoints usados

| Endpoint | Ruta | Costo |
| :--- | :--- | :---: |
| Solo ida | `GET https://api.flightapi.io/onewaytrip/{api_key}/{from}/{to}/{date}/{adults}/{children}/{infants}/{cabin}/{currency}` | 2 créditos FlightAPI |
| Ida y vuelta | `GET https://api.flightapi.io/roundtrip/{api_key}/{from}/{to}/{date}/{return_date}/{adults}/{children}/{infants}/{cabin}/{currency}` | 2 créditos FlightAPI |

- `{from}` y `{to}` son **códigos IATA de aeropuerto**. La documentación oficial no contempla códigos de ciudad (`LON`, `TYO`). Por eso una ciudad con varios aeropuertos genera varios pares y varias llamadas (máximo 2 por búsqueda, RN-14). En ida y vuelta el par es simétrico: `/roundtrip/.../{from}/{to}/...` cotiza la ida `from → to` y el regreso `to → from` (RN-01).
- `/multitrip` **no se usa** (fuera de alcance).
- La clave solo existe en la variable de entorno `FLIGHT_API_KEY` del servidor. Nunca llega al navegador ni a los logs.

### Traducción de parámetros

| Navby | FlightAPI |
| :--- | :--- |
| `ECONOMY` | `Economy` |
| `PREMIUM_ECONOMY` | `Premium_Economy` |
| `BUSINESS` | `Business` |
| `FIRST` | `First` |
| `USD`, `PEN` | `USD`, `PEN` |

## 2. Respuesta (campos usados)

FlightAPI devuelve colecciones normalizadas que se referencian por ID:

```json
{
  "itineraries": [
    { "id": "itn_1", "leg_ids": ["leg_out", "leg_in"],
      "pricing_options": [
        { "price": { "amount": 420.50 },
          "items": [ { "agent_id": "agent_latam", "deep_link": "https://..." } ] } ] }
  ],
  "legs": [
    { "id": "leg_out", "departure": "2026-11-01T08:30:00", "arrival": "2026-11-01T14:45:00",
      "duration_in_minutes": 375, "stop_count": 0, "segment_ids": ["seg_1"] }
  ],
  "segments": [
    { "id": "seg_1", "departure": "2026-11-01T08:30:00", "arrival": "2026-11-01T14:45:00",
      "origin_station_code": "LIM", "destination_station_code": "MIA",
      "marketing_flight_number": "LA2510", "marketing_carrier_id": "carrier_la" }
  ],
  "carriers": [ { "id": "carrier_la", "name": "LATAM Airlines", "iata": "LA", "logo": "https://..." } ]
}
```

## 3. Traducción a una oferta de Navby

El adaptador convierte cada elemento de `itineraries[]` en un **FlightOffer** del dominio de Quotes:

| Campo de FlightOffer | Origen en FlightAPI |
| :--- | :--- |
| `offer_id` | Calculado, no copiado: los primeros 16 caracteres hexadecimales del SHA-256 de la secuencia de segmentos (`número de vuelo` + `salida`) y la cabina. La misma oferta tiene el mismo ID en búsquedas distintas, lo que permite deduplicar entre pares y guardar itinerarios sin duplicados. |
| `price` | El menor `pricing_options[].price.amount` (total de todos los pasajeros). |
| `deep_link` | `items[0].deep_link` de esa misma opción de precio. |
| `legs` | `leg_ids` → `legs[]` (ida y, si aplica, vuelta). |
| `duration_minutes` | Suma de `legs[].duration_in_minutes`. |
| `stops` | Suma de `legs[].stop_count`. |
| `segments` | `legs[].segment_ids` → `segments[]`: origen, destino, horas, número de vuelo y aerolínea. |
| `airlines` | `carriers[]` (nombre, IATA y logo) referenciados por los segmentos. |

Se descartan los itinerarios sin opciones de precio, sin *deep link* o con algún tramo con más de 2 escalas (RN-05). Ningún tipo de FlightAPI cruza la frontera del adaptador.

## 4. Puerto y adaptadores

```python
class FlightOffersProvider(Protocol):
    async def fetch_offers(self, pair: AirportPair, criteria: SearchCriteria) -> Result[list[FlightOffer]]: ...
```

| Adaptador | Cuándo se usa |
| :--- | :--- |
| `FlightApiOffersProvider` | Producción. Usa `httpx.AsyncClient` con timeout de 20 s por llamada. |
| `MockFlightOffersProvider` | Si `FLIGHT_API_KEY` no está definida. Lee fixtures JSON deterministas por par (costo cero). |

## 5. Manejo de fallas

| Situación | Comportamiento |
| :--- | :--- |
| Error de conexión o HTTP 5xx en menos de 5 s | 1 reintento inmediato. Si vuelve a fallar, el par cuenta como fallido. |
| Timeout (20 s) | Sin reintento: el par cuenta como fallido. |
| Sin turno en el semáforo global tras 10 s (RN-16) | El par cuenta como fallido sin llamar a FlightAPI. |
| HTTP 4xx (incluye 402 o 429 por cuota agotada) | Sin reintento. El par cuenta como fallido y se registra en el log con nivel `ERROR`. |
| Todas las llamadas fallan | Quotes reembolsa los 5 créditos. Si tampoco hay pares en caché, responde `503 PROVIDER_UNAVAILABLE`; si los hay, responde con ellos y `partial: true` (RN-09). |
| Solo algunos pares fallan | Se responde con los pares exitosos y `partial: true`. |

Las llamadas de una búsqueda se lanzan en paralelo (`asyncio.gather`). Cada búsqueda tiene un tiempo máximo total de 30 s: lo que no responda a tiempo cuenta como fallido. Toda llamada pasa por el semáforo global **ProviderGate** (máximo `FLIGHT_API_MAX_CONCURRENCY` simultáneas, RN-16). Las respuestas exitosas se guardan en caché por par durante 30 minutos (RN-10).
