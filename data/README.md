# Datos del grafo

El backend carga estos cuatro archivos al arrancar (`lifespan`). Vienen del repositorio `navby-report` (`docs/backend-documentation/navby-datasets/`), donde está el pipeline completo de depuración de OpenFlights.

| Archivo | Registros | Uso |
| :--- | :---: | :--- |
| `airports.csv` | 3,354 | Vértices del grafo: aeropuertos comerciales con al menos una ruta. |
| `routes_unique.csv` | 37,326 | Aristas dirigidas únicas con distancia Haversine. |
| `city_aliases_es.csv` | 119 | Alias en español de ciudades (Tokio → Tokyo). |
| `airport_city_overrides.csv` | 1 | Corrige la ciudad de aeropuertos metropolitanos (EWR → New York). |

**Reglas:**
- `airports.csv` y `routes_unique.csv` **no se editan a mano**. Si cambian, se regeneran en `navby-report` y se copian aquí. El arranque valida los conteos 3,354 y 37,326.
- `city_aliases_es.csv` y `airport_city_overrides.csv` sí se editan a mano. Cada fila debe coincidir exactamente con `city` y `country` de `airports.csv`; una prueba automática lo verifica.

## Esquemas

### `airports.csv`

`airport_id, name, city, country, iata, icao, latitude, longitude, altitude, timezone, dst, tz_database_timezone`

| Columna | Uso en el backend |
| :--- | :--- |
| `iata` | Identificador del nodo (`^[A-Z]{3}$`). |
| `name`, `city`, `country` | Autocompletado y agrupación por ciudad. |
| `latitude`, `longitude` | Haversine y coordenadas del mapa. |
| `tz_database_timezone` | Zona IANA que se devuelve junto a cada aeropuerto. |

### `routes_unique.csv`

`source_airport, destination_airport, distance_km, operating_airlines, min_stops, equipment_types`

Solo se usan `source_airport`, `destination_airport` y `distance_km`. El peso de la arista se calcula al cargar: `minutes = distance_km / 800 · 60 + 30`.

### `city_aliases_es.csv`

`city, country, alias_es`

### `airport_city_overrides.csv`

`iata, city, country, reason`
