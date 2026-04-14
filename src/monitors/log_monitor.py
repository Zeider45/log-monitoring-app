from __future__ import annotations

from threading import Event, Thread
from typing import Callable, Iterable

import docker
from docker.errors import DockerException, NotFound

from src.parsers.log_parser import LogParser
from src.services.alert_service import AlertService
from src.types import AlertEvent


class LogMonitor:
    def __init__(
        self,
        container_names: list[str],
        alert_service: AlertService,
        parser: LogParser | None = None,
        docker_client=None,
        on_info: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self.container_names = container_names
        self.alert_service = alert_service
        self.parser = parser or LogParser()
        self.docker_client = docker_client
        self._on_info = on_info
        self._on_error = on_error
        self.is_monitoring = False
        self._stop_event = Event()
        self._threads: list[Thread] = []
        self._streams: list[object] = []

    def start_monitoring(self, daemon: bool = False) -> None:
        self.is_monitoring = True
        self._stop_event.clear()

        if self.docker_client is None:
            self.docker_client = docker.from_env()

        self._threads = []
        for container_name in self.container_names:
            thread = Thread(
                target=self._monitor_container,
                args=(container_name,),
                daemon=daemon,
            )
            thread.start()
            self._threads.append(thread)

        if not daemon:
            for thread in self._threads:
                thread.join()

    def stop_monitoring(self) -> None:
        self.is_monitoring = False
        self._stop_event.set()

        for stream in self._streams:
            close_method = getattr(stream, "close", None)
            if callable(close_method):
                close_method()

    def process_log_line(self, container_name: str, raw_line: bytes | str) -> AlertEvent | None:
        alert_event = self.parser.parse_log(container_name=container_name, log_entry=raw_line)
        if alert_event is not None:
            self.alert_service.send_alert(alert_event)
        return alert_event

    def _monitor_container(self, container_name: str) -> None:
        try:
            container = self.docker_client.containers.get(container_name)
            stream = container.logs(
                stream=True,
                follow=True,
                stdout=True,
                stderr=True,
                timestamps=True,
                tail=0,
            )
            self._streams.append(stream)
            if self._on_info is not None:
                self._on_info(f"Connected to container: {container_name}")
            self._consume_stream(container_name, stream)
        except NotFound:
            message = f"Container not found: {container_name}"
            print(message)
            if self._on_error is not None:
                self._on_error(message)
        except DockerException as exc:
            message = f"Docker error while monitoring {container_name}: {exc}"
            print(message)
            if self._on_error is not None:
                self._on_error(message)

    def _consume_stream(self, container_name: str, stream: Iterable[bytes | str]) -> None:
        for raw_line in stream:
            if self._stop_event.is_set():
                break

            self.process_log_line(container_name=container_name, raw_line=raw_line)

    @staticmethod
    def _normalize_raw_line(raw_line: bytes | str) -> str:
        if isinstance(raw_line, bytes):
            return raw_line.decode("utf-8", errors="replace").strip()
        return str(raw_line).strip()