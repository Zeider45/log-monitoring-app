from pathlib import Path

from src.monitors.log_monitor import LogMonitor
from src.parsers.log_parser import LogParser
from src.services.alert_service import AlertService
from src.types import AlertEvent


class FakeContainer:
    def __init__(self, lines):
        self._lines = lines

    def logs(self, **kwargs):
        return iter(self._lines)


class FakeContainerManager:
    def __init__(self, containers):
        self._containers = containers

    def get(self, container_name):
        return self._containers[container_name]


class FakeDockerClient:
    def __init__(self, containers):
        self.containers = FakeContainerManager(containers)


def test_process_log_line_triggers_alert(tmp_path: Path):
    alert_service = AlertService(alert_log_file=tmp_path / "alerts.jsonl")
    log_monitor = LogMonitor(
        container_names=["api"],
        alert_service=alert_service,
        parser=LogParser(["ERROR"]),
        docker_client=FakeDockerClient({"api": FakeContainer([])}),
    )

    alert_event = log_monitor.process_log_line("api", b"ERROR: database unavailable")

    assert alert_event is not None
    assert alert_event.container_name == "api"
    assert len(alert_service.alerts) == 1
    assert "database unavailable" in alert_service.alerts[0].message


def test_process_log_line_ignores_non_matching_entries(tmp_path: Path):
    alert_service = AlertService(alert_log_file=tmp_path / "alerts.jsonl")
    log_monitor = LogMonitor(
        container_names=["api"],
        alert_service=alert_service,
        parser=LogParser(["ERROR"]),
        docker_client=FakeDockerClient({"api": FakeContainer([])}),
    )

    alert_event = log_monitor.process_log_line("api", b"INFO: service started")

    assert alert_event is None
    assert alert_service.alerts == []


def test_monitor_container_stream_sends_alerts(tmp_path: Path):
    alert_service = AlertService(alert_log_file=tmp_path / "alerts.jsonl")
    docker_client = FakeDockerClient(
        {
            "api": FakeContainer(
                [
                    b"INFO: booting",
                    b"ERROR: first failure",
                    b"Exception: second failure",
                ]
            )
        }
    )
    log_monitor = LogMonitor(
        container_names=["api"],
        alert_service=alert_service,
        parser=LogParser(["ERROR", "Exception"]),
        docker_client=docker_client,
    )

    log_monitor.start_monitoring(daemon=True)
    for thread in log_monitor._threads:
        thread.join(timeout=1)

    assert len(alert_service.alerts) == 2


def test_alert_service_calls_callback(tmp_path: Path):
    called: list[AlertEvent] = []

    def on_alert(event: AlertEvent) -> None:
        called.append(event)

    alert_service = AlertService(alert_log_file=tmp_path / "alerts.jsonl", on_alert=on_alert)
    event = AlertEvent(
        timestamp="2026-01-01T00:00:00+00:00",
        container_name="api",
        message="ERROR: database unavailable",
        matched_keyword="ERROR",
    )

    alert_service.send_alert(event)

    assert called == [event]


def test_alert_service_records_multiple_alerts(tmp_path: Path):
    alert_service = AlertService(alert_log_file=tmp_path / "alerts.jsonl")

    event1 = AlertEvent(
        timestamp="2026-01-01T00:00:00+00:00",
        container_name="api",
        message="ERROR: one",
        matched_keyword="ERROR",
    )
    event2 = AlertEvent(
        timestamp="2026-01-01T00:00:00+00:00",
        container_name="api",
        message="ERROR: two",
        matched_keyword="ERROR",
    )

    alert_service.send_alert(event1)
    alert_service.send_alert(event2)

    assert len(alert_service.alerts) == 2