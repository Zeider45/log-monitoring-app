# Monitor de logs de Docker

Este proyecto sirve para monitorear en tiempo real los logs de uno o varios contenedores Docker, detectar palabras clave “problemáticas” (por ejemplo `ERROR`, `Exception` o `timeout`) y generar alertas.

Las alertas se muestran en consola y también se guardan en un archivo local como JSON Lines.

## ¿Qué hace exactamente?

- Sigue (`docker logs --follow`) los logs de uno o varios contenedores.
- Revisa cada línea buscando palabras clave configurables.
- Cuando encuentra una coincidencia, imprime una alerta.
- Guarda cada alerta en un archivo (por defecto `alerts.log`) en formato JSONL (una alerta por línea).

## Project Structure

```
log-monitoring-app
├── src
│   ├── main.py
│   ├── config
│   │   └── settings.py
│   ├── monitors
│   │   └── log_monitor.py
│   ├── parsers
│   │   └── log_parser.py
│   ├── services
│   │   └── alert_service.py
│   └── types
│       └── __init__.py
├── tests
│   └── test_log_monitor.py
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.10+
- Docker Desktop or Docker Engine running
- access to `docker logs`

## Instalación

1. Instala dependencias:

   ```
   pip install -r requirements.txt
   ```

2. Configura el proyecto con el archivo `.env` en la raíz:

   ```
   DOCKER_CONTAINERS=api,worker
   ERROR_KEYWORDS=ERROR,CRITICAL,Exception,timeout,connection refused
   ALERT_LOG_FILE=alerts.log
   ```

   Puedes copiar los valores de `.env.example` o editar `.env` directamente.

## Ejecutar

Inicia el monitor con:

```
python -m src.main
```

Para iniciar la interfaz gráfica (Tkinter):

```
python -m src.main --gui
```

En la GUI puedes:

- Iniciar/detener el monitoreo.
- Ver gráficos en vivo (alertas por keyword y por contenedor).
- Cargar/guardar configuración en `.env` (containers, keywords y archivo de alertas).
- Detectar contenedores en ejecución desde Docker.

La aplicación carga automáticamente los valores desde `.env`.

## Generar logs de prueba (Docker)

Este repo incluye una imagen Docker separada que genera logs de forma continua (incluye `ERROR`, `Exception` y `timeout`) para que puedas probar el monitor sin depender de servicios reales.

Construye y levanta dos contenedores de ejemplo (`api` y `worker`) con Docker Compose:

```
docker compose -f docker/log-generator/docker-compose.yml up --build
```

Luego ejecuta el monitor (en otra terminal) usando tu `.env` (por defecto ya coincide con `api,worker`):

```
python -m src.main
```

Para detener los generadores de logs:

```
docker compose -f docker/log-generator/docker-compose.yml down
```

## Ejemplo

Si `DOCKER_CONTAINERS=api`, la app seguirá los logs del contenedor `api` y generará alertas para mensajes como:

- `ERROR: database unavailable`
- `Exception: request failed`
- `timeout while connecting to redis`

## Ejecutar pruebas

```
pytest
```

## Notas rápidas

- Si un contenedor no existe, verás un mensaje tipo “Container not found”.
- Si Docker no está disponible o hay permisos insuficientes, verás un error de Docker.
