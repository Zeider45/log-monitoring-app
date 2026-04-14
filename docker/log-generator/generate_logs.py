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
    alert_every_seconds = _env_float("ALERT_EVERY_SECONDS", 20.0)
    allow_random_alerts = _env_int("ALLOW_RANDOM_ALERTS", 0) == 1
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
    forced_counter = 0
    next_forced_alert_at = time.monotonic() + max(alert_every_seconds, 0.0) if alert_every_seconds > 0 else float("inf")
    while True:
        counter += 1
        r = random.random()
        timestamp = _now()

        now_mono = time.monotonic()
        if now_mono >= next_forced_alert_at:
            forced_counter += 1
            variant = forced_counter % 3
            if variant == 1:
                msg = f"{timestamp} ERROR: forced periodic alert (service={service_name}, count={counter})"
            elif variant == 2:
                msg = f"{timestamp} Exception: forced periodic alert (service={service_name}, count={counter})"
            else:
                msg = (
                    f"{timestamp} timeout while connecting to dependency "
                    f"(service={service_name}, count={counter})"
                )

            print(msg, file=sys.stderr, flush=True)
            next_forced_alert_at = now_mono + max(alert_every_seconds, 0.0)
            time.sleep(max(interval_seconds, 0.0))
            continue

        if allow_random_alerts:
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
        else:
            level = "INFO" if (counter % 10) else "WARN"
            msg = f"{timestamp} {level}: heartbeat ok (service={service_name}, count={counter})"
            print(msg, file=sys.stdout, flush=True)

        time.sleep(max(interval_seconds, 0.0))


if __name__ == "__main__":
    raise SystemExit(main())
