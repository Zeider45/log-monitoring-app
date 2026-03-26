# Requerimientos del sistema

Este documento describe los requerimientos funcionales y no funcionales del sistema de monitoreo de logs. Están derivados del comportamiento real del código del proyecto.

## Requerimientos funcionales

- Cargar configuración desde variables de entorno (a través de un archivo `.env` en la raíz del repo):
  - `DOCKER_CONTAINERS`: lista CSV de nombres de contenedores a monitorear.
  - `ERROR_KEYWORDS`: lista CSV de palabras clave que disparan alertas.
  - `ALERT_LOG_FILE`: ruta del archivo donde se guardan las alertas.
- Conectarse al Docker Engine local usando el SDK de Docker para Python.
- Monitorear uno o más contenedores por nombre, siguiendo sus logs en tiempo real.
- Consumir logs de `stdout` y `stderr` del contenedor.
- Normalizar cada entrada de log (decode si viene como bytes, `strip`) y descartar entradas vacías.
- Detectar coincidencias de palabras clave de forma _case-insensitive_ dentro del mensaje.
- Cuando exista match, generar un evento de alerta con:
  - timestamp UTC (ISO 8601)
  - nombre del contenedor
  - mensaje original normalizado
  - palabra clave que hizo match
- Emitir la alerta por consola con un formato legible.
- Persistir cada alerta en un archivo local como JSON Lines (una alerta por línea).
- Monitorear contenedores en paralelo (un hilo por contenedor) para no bloquear la lectura de logs entre contenedores.
- Permitir detener el monitoreo de forma controlada (por ejemplo Ctrl+C), deteniendo el consumo de streams.
- Manejar escenarios de error sin terminar abruptamente:
  - contenedor no encontrado
  - errores generales de Docker (conexión/permiso/daemon caído)

## Requerimientos no funcionales

- Compatibilidad:
  - Requiere Python 3.10+.
  - Requiere Docker Desktop o Docker Engine en ejecución y acceso a `docker logs`.
- Rendimiento:
  - Procesamiento en streaming (casi en tiempo real) y no por lotes.
  - Capacidad de monitorear múltiples contenedores simultáneamente.
- Confiabilidad y robustez:
  - Tolerancia a contenedores inexistentes y errores de Docker (debe reportar el problema y continuar en lo posible).
  - Parada “limpia” del monitoreo (evitar hilos/streams colgados).
- Configurabilidad:
  - Listas de contenedores y palabras clave configurables sin cambios de código.
  - Ruta de salida de alertas configurable.
- Observabilidad y trazabilidad:
  - Alertas visibles en consola para diagnóstico rápido.
  - Persistencia de alertas en archivo JSONL para auditoría/revisión posterior.
- Mantenibilidad y testabilidad:
  - Separación de responsabilidades (monitor, parser, servicio de alertas).
  - Posibilidad de pruebas unitarias usando dobles (fakes) de Docker client/containers.
