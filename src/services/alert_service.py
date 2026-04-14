from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from src.types import AlertEvent


class AlertService:
    def __init__(
        self,
        alert_log_file: str | Path | None = None,
        on_alert: Callable[[AlertEvent], None] | None = None,
    ):
        self.alerts: list[AlertEvent] = []
        self.alert_log_file = Path(alert_log_file) if alert_log_file else None
        self._on_alert = on_alert

    def send_alert(self, alert_event: AlertEvent) -> None:
        formatted_message = (
            f"[ALERT] [{alert_event.container_name}] "
            f"matched '{alert_event.matched_keyword}': {alert_event.message}"
        )
        print(formatted_message)
        self.alerts.append(alert_event)

        if self.alert_log_file is not None:
            self.alert_log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.alert_log_file.open("a", encoding="utf-8") as alert_file:
                alert_file.write(json.dumps(asdict(alert_event), ensure_ascii=False) + "\n")

        if self._on_alert is not None:
            try:
                self._on_alert(alert_event)
            except Exception as exc:
                print(f"Alert callback error: {exc}")

    def configure_alert(self, alert_condition: str) -> None:
        print(f"Alert condition configured: {alert_condition}")