import os
import random
import sys
import time
from datetime import datetime, timezone


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    service_name = _env_str("SERVICE_NAME", "api")
    interval_seconds = _env_float("LOG_INTERVAL_SECONDS", 0.5)
    error_probability = _env_float("ERROR_PROBABILITY", 0.15)
    exception_probability = _env_float("EXCEPTION_PROBABILITY", 0.05)
    timeout_probability = _env_float("TIMEOUT_PROBABILITY", 0.05)
    seed = os.getenv("RANDOM_SEED")

    if seed:
        try:
            random.seed(int(seed))
        except ValueError:
            random.seed(seed)

    counter = 0
    while True:
        counter += 1
        r = random.random()
        timestamp = _now()

        if r < exception_probability:
            msg = f"{timestamp} Exception: simulated failure in {service_name} (count={counter})"
            print(msg, file=sys.stderr, flush=True)
        elif r < exception_probability + timeout_probability:
            msg = f"{timestamp} timeout while connecting to dependency (service={service_name}, count={counter})"
            print(msg, file=sys.stderr, flush=True)
        elif r < exception_probability + timeout_probability + error_probability:
            msg = f"{timestamp} ERROR: simulated error processing request (service={service_name}, count={counter})"
            print(msg, file=sys.stderr, flush=True)
        else:
            level = "INFO" if (counter % 10) else "WARN"
            msg = f"{timestamp} {level}: heartbeat ok (service={service_name}, count={counter})"
            print(msg, file=sys.stdout, flush=True)

        time.sleep(max(interval_seconds, 0.0))


if __name__ == "__main__":
    raise SystemExit(main())
