# Cómo está programado el sistema (paso a paso)

Este documento explica **cómo funciona internamente** el sistema de monitoreo de logs de Docker: qué archivos participan, qué hace cada módulo y cuál es el flujo desde que ejecutas el programa hasta que se generan y guardan las alertas.

> Idea general: el programa **se conecta a Docker**, sigue los logs en tiempo real de los contenedores configurados, **busca palabras clave** (ERROR/Exception/timeout, etc.) y cuando encuentra una coincidencia, **lanza una alerta** (consola + archivo JSONL).

---

## 1) Configuración del proyecto (variables de entorno)

**Archivo:** `src/config/settings.py`

1. Al iniciar, se calcula `BASE_DIR` (la raíz del repo) y se carga `.env` automáticamente con `python-dotenv`.
2. Se define un `Settings` (dataclass) con:
   - `containers`: lista de contenedores a monitorear.
   - `error_keywords`: lista de palabras clave que disparan alertas.
   - `alert_log_file`: ruta del archivo de salida de alertas.
3. La función `get_settings()` arma esa configuración leyendo variables de entorno:
   - `DOCKER_CONTAINERS` (CSV) → por defecto `['api']`
   - `ERROR_KEYWORDS` (CSV) → por defecto `DEFAULT_KEYWORDS`
   - `ALERT_LOG_FILE` → por defecto `alerts.log`

**Detalle importante:** la función `_parse_csv_env()` recorta espacios y evita valores vacíos. Si la variable está vacía o no existe, se usa el valor por defecto.

---

## 2) Punto de entrada: cómo arranca la aplicación

**Archivo:** `src/main.py`

Cuando ejecutas:

```bash
python -m src.main
```

pasa lo siguiente:

1. `settings = get_settings()` carga la configuración (ver sección 1).
2. Se instancia `AlertService` con el archivo de salida (`alert_log_file`).
3. Se instancia `LogParser` con las palabras clave (`error_keywords`).
4. Se instancia `LogMonitor` con:
   - `container_names=settings.containers`
   - `alert_service=alert_service`
   - `parser=parser`
5. Se imprimen por consola los contenedores monitoreados y las keywords.
6. Se llama `log_monitor.start_monitoring()` dentro de un `try/except` para manejar Ctrl+C (KeyboardInterrupt).

---

## 3) Monitor de Docker: seguimiento de logs en paralelo

**Archivo:** `src/monitors/log_monitor.py`

### 3.1 Creación de threads (1 por contenedor)

En `start_monitoring(daemon=False)`:

1. Se marca `is_monitoring = True` y se limpia `_stop_event`.
2. Si no se inyectó un cliente Docker, se crea con `docker.from_env()`.
3. Para cada `container_name` en `self.container_names`, se crea un `Thread` que ejecuta `_monitor_container(container_name)`.
4. Si `daemon=False` (por defecto), el hilo principal hace `join()` sobre todos los threads y queda “bloqueado” mientras monitorea (esto es intencional).

### 3.2 Conexión al contenedor y apertura del stream

En `_monitor_container(container_name)`:

1. Busca el contenedor por nombre:
   - `container = self.docker_client.containers.get(container_name)`
2. Abre un stream de logs con:
   - `stream=True`, `follow=True`
   - `stdout=True`, `stderr=True`
   - `timestamps=True`
   - `tail=0`
3. Guarda el stream en `self._streams` para poder cerrarlo al detener.
4. Llama a `_consume_stream(container_name, stream)` para procesar línea por línea.

### 3.3 Consumo del stream (loop principal)

En `_consume_stream(container_name, stream)`:

1. Itera `for raw_line in stream:`
2. Revisa si `_stop_event` está activado; si sí, rompe el loop.
3. Pasa la línea a `process_log_line(container_name, raw_line)`.

### 3.4 Detener el monitoreo

En `stop_monitoring()`:

1. Activa `_stop_event`.
2. Intenta cerrar cada stream si tiene método `close()`.

Esto evita que el programa quede colgado consumiendo streams.

### 3.5 Manejo de errores

- Si el contenedor no existe: captura `docker.errors.NotFound` e imprime `Container not found: ...`.
- Si hay un problema con Docker (daemon apagado, permisos, etc.): captura `docker.errors.DockerException` e imprime un mensaje.

---

## 4) Parser: cómo detecta coincidencias de palabras clave

**Archivo:** `src/parsers/log_parser.py`

### 4.1 Normalización del mensaje

`parse_log(container_name, log_entry)` primero hace:

- `message = _normalize_message(log_entry)`
  - si viene `bytes`, decodifica UTF-8 con `errors="replace"` (no revienta por caracteres raros)
  - luego hace `strip()`

Luego valida:

- `validate_log(message)` → asegura que no esté vacío.

### 4.2 Búsqueda de keywords (case-insensitive)

1. Convierte el mensaje a minúsculas.
2. Recorre las keywords normalizadas.
3. Si encuentra que la keyword está contenida en el mensaje, crea y retorna un `AlertEvent` con:
   - `timestamp` en UTC (`datetime.now(timezone.utc).isoformat()`)
   - `container_name`
   - `message` (ya normalizado)
   - `matched_keyword` (la keyword original)

Si no hay match, retorna `None`.

---

## 5) Servicio de alertas: consola + archivo JSONL

**Archivo:** `src/services/alert_service.py`

Cuando `LogMonitor` detecta un `AlertEvent`, llama:

- `alert_service.send_alert(alert_event)`

y este método:

1. Formatea un mensaje legible y lo imprime:
   - `[ALERT] [<container>] matched '<keyword>': <message>`
2. Guarda el evento en memoria en `self.alerts`.
3. Si `alert_log_file` está configurado:
   - crea el directorio padre si hace falta
   - abre el archivo en modo append (`"a"`)
   - escribe una línea JSON con `json.dumps(asdict(alert_event))`

**Por qué JSONL:** te permite tratar el archivo como un “stream” de eventos (una línea = un evento), fácil de parsear y de enviar a herramientas externas.

---

## 6) Tipo de evento de alerta

**Archivo:** `src/types/__init__.py`

Ahí se define el tipo `AlertEvent` (estructura de datos) que el parser produce y el servicio de alertas consume.

---

## 7) Flujo completo resumido (de extremo a extremo)

1. Ejecutas `python -m src.main`.
2. `settings.py` carga `.env` y arma `Settings`.
3. Se inicializan `AlertService`, `LogParser`, `LogMonitor`.
4. `LogMonitor` crea un thread por contenedor.
5. Cada thread abre `container.logs(... follow=True ...)`.
6. Por cada línea:
   - `LogParser.parse_log(...)` decide si hay alerta.
   - Si la hay: `AlertService.send_alert(...)` imprime y escribe en JSONL.
7. Con Ctrl+C, `main.py` llama `stop_monitoring()`.

---

## 8) Cómo probarlo con el generador de logs (Docker)

**Archivos:**

- `docker/log-generator/Dockerfile`
- `docker/log-generator/generate_logs.py`
- `docker/log-generator/compose.yml`

El generador crea contenedores que escriben logs continuamente a `stdout/stderr` con una probabilidad configurable de emitir `ERROR`, `Exception` y `timeout`.

Pasos típicos:

1. Levanta generadores (`api` y `worker`):

```bash
docker compose -f docker/log-generator/docker-compose.yml up --build
```

2. En otra terminal, ejecuta el monitor:

```bash
python -m src.main
```

3. Verás alertas en consola y un archivo `alerts.log` con eventos JSONL.

4. Para apagar generadores:

```bash
docker compose -f docker/log-generator/docker-compose.yml down
```

---

## 9) Pruebas automatizadas: cómo se testea sin Docker real

**Archivo:** `tests/test_log_monitor.py`

Las pruebas usan objetos “fake”:

- `FakeDockerClient` / `FakeContainerManager` / `FakeContainer`

Eso permite simular que un contenedor devuelve un iterable de líneas de log, sin depender de Docker real.

Se testea principalmente:

- Que una línea con keyword dispara una alerta.
- Que una línea sin keyword no dispara nada.
- Que el monitoreo de un stream con varias líneas produce la cantidad esperada de alertas.

---

## 10) Dónde cambiar comportamiento (puntos de extensión)

- Agregar/quitar keywords: editar `.env` (`ERROR_KEYWORDS=...`).
- Cambiar contenedores: editar `.env` (`DOCKER_CONTAINERS=...`).
- Cambiar destino del archivo de alertas: `.env` (`ALERT_LOG_FILE=...`).
- Cambiar lógica de matching (regex, severidades, etc.): `src/parsers/log_parser.py`.
- Cambiar formato/salida de alertas (por ejemplo enviar a HTTP/Slack): `src/services/alert_service.py`.
