from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import messagebox, ttk

from docker.errors import DockerException
from datetime import datetime

from src.config.settings import get_settings
from src.monitors.log_monitor import LogMonitor
from src.parsers.log_parser import LogParser
from src.services.alert_service import AlertService
from src.types import AlertEvent


def _parse_csv(value: str) -> list[str]:
    items = [part.strip() for part in value.split(",") if part.strip()]
    return items


def _env_escape(value: str) -> str:
    if not value:
        return value
    needs_quotes = any(ch.isspace() for ch in value) or "\"" in value
    if not needs_quotes:
        return value
    return '"' + value.replace('"', '\\"') + '"'


def _get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_env_lines(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    return env_path.read_text(encoding="utf-8").splitlines(keepends=True)


def _parse_env_to_dict(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1].replace('\\"', '"')
        result[key] = value
    return result


def _update_env_lines(existing_lines: list[str], updates: dict[str, str]) -> list[str]:
    updated_lines: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            updated_lines.append(f"{key}={_env_escape(updates[key])}\n")
            seen.add(key)
        else:
            updated_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            if updated_lines and not updated_lines[-1].endswith("\n"):
                updated_lines[-1] = updated_lines[-1] + "\n"
            updated_lines.append(f"{key}={_env_escape(value)}\n")

    return updated_lines


class LogMonitoringTkApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.master = master

        self._pad = 10

        settings = get_settings()

        self._event_queue: Queue[object] = Queue()
        self._log_monitor: LogMonitor | None = None
        self._alerts_received = 0

        self._keyword_counts: dict[str, int] = {}
        self._container_counts: dict[str, int] = {}

        self._max_rows = 2500
        self._row_count = 0

        self._project_root = _get_project_root()
        self._env_path = self._project_root / ".env"

        self.containers_var = tk.StringVar(value=",".join(settings.containers))
        self.keywords_var = tk.StringVar(value=",".join(settings.error_keywords))
        self.alert_file_var = tk.StringVar(value=str(settings.alert_log_file))
        self.status_var = tk.StringVar(value="Stopped")
        self.alert_count_var = tk.StringVar(value="Alerts: 0")
        self.docker_status_var = tk.StringVar(value="Docker: unknown")
        self.env_path_var = tk.StringVar(value=str(self._env_path))

        self._build_ui()
        self._set_controls_running(False)

        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        self.master.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.master.title("Docker Log Monitor")
        self.grid(row=0, column=0, sticky="nsew")
        self.master.rowconfigure(0, weight=1)
        self.master.columnconfigure(0, weight=1)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew", padx=self._pad, pady=self._pad)

        monitor_tab = ttk.Frame(notebook)
        config_tab = ttk.Frame(notebook)
        notebook.add(monitor_tab, text="Monitor")
        notebook.add(config_tab, text="Configuración")

        self._build_monitor_tab(monitor_tab)
        self._build_config_tab(config_tab)

    def _build_monitor_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(4, weight=1)
        parent.columnconfigure(0, weight=1)

        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(4, weight=1)

        self.start_button = ttk.Button(header, text="Start", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, sticky="w")

        self.stop_button = ttk.Button(header, text="Stop", command=self.stop_monitoring)
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.clear_button = ttk.Button(header, text="Clear", command=self.clear_output)
        self.clear_button.grid(row=0, column=2, sticky="w", padx=(8, 0))

        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Label(header, textvariable=self.alert_count_var).grid(row=0, column=5, sticky="e")

        status = ttk.Frame(parent)
        status.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, textvariable=self.docker_status_var).grid(row=0, column=0, sticky="w")

        ttk.Separator(parent).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        # Re-grid status below separator for cleaner spacing
        status.grid_forget()
        status.grid(row=2, column=0, sticky="ew")

        charts = ttk.Frame(parent)
        charts.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        charts.columnconfigure(0, weight=1)
        charts.columnconfigure(1, weight=1)

        keyword_group = ttk.LabelFrame(charts, text="Alertas por keyword")
        keyword_group.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        keyword_group.columnconfigure(0, weight=1)
        self.keyword_canvas = tk.Canvas(keyword_group, height=140, highlightthickness=0)
        self.keyword_canvas.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.keyword_canvas.bind("<Configure>", lambda _e: self._redraw_charts())

        container_group = ttk.LabelFrame(charts, text="Alertas por contenedor")
        container_group.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        container_group.columnconfigure(0, weight=1)
        self.container_canvas = tk.Canvas(container_group, height=140, highlightthickness=0)
        self.container_canvas.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.container_canvas.bind("<Configure>", lambda _e: self._redraw_charts())

        output_frame = ttk.Frame(parent)
        output_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)

        columns = ("timestamp", "container", "keyword", "message")
        self.table = ttk.Treeview(output_frame, columns=columns, show="headings")
        self.table.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(output_frame, orient="vertical", command=self.table.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=vsb.set)

        self.table.heading("timestamp", text="Timestamp")
        self.table.heading("container", text="Container")
        self.table.heading("keyword", text="Keyword")
        self.table.heading("message", text="Message")

        self.table.column("timestamp", width=210, stretch=False)
        self.table.column("container", width=110, stretch=False)
        self.table.column("keyword", width=120, stretch=False)
        self.table.column("message", width=600, stretch=True)

    def _build_config_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        runtime = ttk.LabelFrame(parent, text="Runtime")
        runtime.grid(row=0, column=0, sticky="ew")
        runtime.columnconfigure(1, weight=1)

        ttk.Label(runtime, text="Containers (CSV):").grid(row=0, column=0, sticky="w", padx=self._pad, pady=(self._pad, 0))
        ttk.Entry(runtime, textvariable=self.containers_var).grid(
            row=0, column=1, sticky="ew", padx=(0, self._pad), pady=(self._pad, 0)
        )
        ttk.Button(runtime, text="Detect running", command=self.detect_running_containers).grid(
            row=0, column=2, sticky="e", padx=(0, self._pad), pady=(self._pad, 0)
        )

        ttk.Label(runtime, text="Keywords (CSV):").grid(row=1, column=0, sticky="w", padx=self._pad, pady=(8, 0))
        ttk.Entry(runtime, textvariable=self.keywords_var).grid(
            row=1, column=1, sticky="ew", padx=(0, self._pad), pady=(8, 0), columnspan=2
        )

        ttk.Label(runtime, text="Alert log file:").grid(row=2, column=0, sticky="w", padx=self._pad, pady=(8, self._pad))
        ttk.Entry(runtime, textvariable=self.alert_file_var).grid(
            row=2, column=1, sticky="ew", padx=(0, self._pad), pady=(8, self._pad), columnspan=2
        )

        env_box = ttk.LabelFrame(parent, text="Environment (.env)")
        env_box.grid(row=1, column=0, sticky="ew", pady=(self._pad, 0))
        env_box.columnconfigure(1, weight=1)

        ttk.Label(env_box, text="Path:").grid(row=0, column=0, sticky="w", padx=self._pad, pady=self._pad)
        ttk.Entry(env_box, textvariable=self.env_path_var, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=(0, self._pad), pady=self._pad
        )

        buttons = ttk.Frame(env_box)
        buttons.grid(row=0, column=2, sticky="e", padx=(0, self._pad), pady=self._pad)
        ttk.Button(buttons, text="Load", command=self.load_from_env).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="Save", command=self.save_to_env).grid(row=0, column=1)

    def _set_controls_running(self, running: bool) -> None:
        self.start_button.configure(state=("disabled" if running else "normal"))
        self.stop_button.configure(state=("normal" if running else "disabled"))
        self.status_var.set("Running" if running else "Stopped")

    def _append_row(self, *, timestamp: str, container: str, keyword: str, message: str) -> None:
        self.table.insert("", "end", values=(timestamp, container, keyword, message))
        self._row_count += 1
        if self._row_count > self._max_rows:
            children = self.table.get_children("")
            if children:
                self.table.delete(children[0])
                self._row_count -= 1
        children = self.table.get_children("")
        if children:
            self.table.see(children[-1])

    def _append_info(self, message: str, *, container: str = "") -> None:
        ts = datetime.utcnow().replace(microsecond=0).isoformat() + "+00:00"
        self._append_row(timestamp=ts, container=container, keyword="INFO", message=message)

    def _append_error(self, message: str, *, container: str = "") -> None:
        ts = datetime.utcnow().replace(microsecond=0).isoformat() + "+00:00"
        self._append_row(timestamp=ts, container=container, keyword="ERROR", message=message)

    def _append_alert(self, event: AlertEvent) -> None:
        self._append_row(
            timestamp=event.timestamp,
            container=event.container_name,
            keyword=event.matched_keyword,
            message=event.message,
        )

    def _on_alert(self, alert_event: AlertEvent) -> None:
        self._event_queue.put(alert_event)

    def _on_info(self, message: str) -> None:
        self._event_queue.put(("INFO", message))

    def _on_error(self, message: str) -> None:
        self._event_queue.put(("ERROR", message))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._event_queue.get_nowait()
                if isinstance(event, AlertEvent):
                    self._alerts_received += 1
                    self._record_alert(event)
                    self._append_alert(event)
                    self.alert_count_var.set(f"Alerts: {self._alerts_received}")
                    self._redraw_charts()
                    continue

                if isinstance(event, tuple) and len(event) == 2:
                    level, message = event
                    if level == "ERROR":
                        self._append_error(message)
                    else:
                        self._append_info(message)
        except Empty:
            pass
        finally:
            self.master.after(100, self._poll_events)

    def clear_output(self) -> None:
        for item in self.table.get_children(""):
            self.table.delete(item)
        self._row_count = 0
        self._keyword_counts.clear()
        self._container_counts.clear()
        self._alerts_received = 0
        self.alert_count_var.set("Alerts: 0")
        self._redraw_charts()

    def _record_alert(self, event: AlertEvent) -> None:
        self._keyword_counts[event.matched_keyword] = self._keyword_counts.get(event.matched_keyword, 0) + 1
        self._container_counts[event.container_name] = self._container_counts.get(event.container_name, 0) + 1

    def _redraw_charts(self) -> None:
        self._draw_keyword_bars()
        self._draw_container_bars()

    def _draw_keyword_bars(self) -> None:
        canvas = self.keyword_canvas
        canvas.delete("all")

        width = max(int(canvas.winfo_width()), 320)
        height = max(int(canvas.winfo_height()), 120)
        padding = 10
        usable_w = width - padding * 2
        usable_h = height - padding * 2

        items = sorted(self._keyword_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
        if not items:
            canvas.create_text(padding, padding, anchor="nw", text="Sin alertas aún")
            return

        max_count = max(count for _, count in items) or 1
        row_h = max(int(usable_h / (len(items) + 1)), 18)
        label_w = int(usable_w * 0.45)
        bar_w = usable_w - label_w - 40

        # Title axis hint
        canvas.create_text(padding, padding, anchor="nw", text=f"Top keywords (max={max_count})")

        y = padding + row_h
        for label, count in items:
            # label
            canvas.create_text(padding, y, anchor="w", text=label)

            # bar
            x0 = padding + label_w
            x1 = x0 + max(int((count / max_count) * bar_w), 2)
            y0 = y - 6
            y1 = y + 6
            canvas.create_rectangle(x0, y0, x1, y1, outline="black")
            canvas.create_text(x0 + bar_w + 6, y, anchor="w", text=str(count))
            y += row_h

    def _draw_container_bars(self) -> None:
        canvas = self.container_canvas
        canvas.delete("all")

        width = max(int(canvas.winfo_width()), 320)
        height = max(int(canvas.winfo_height()), 120)
        padding = 10
        usable_w = width - padding * 2
        usable_h = height - padding * 2

        items = sorted(self._container_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
        if not items:
            canvas.create_text(padding, padding, anchor="nw", text="Sin alertas aún")
            return

        max_count = max(count for _, count in items) or 1
        row_h = max(int(usable_h / (len(items) + 1)), 18)
        label_w = int(usable_w * 0.45)
        bar_w = usable_w - label_w - 40

        canvas.create_text(padding, padding, anchor="nw", text=f"Top contenedores (max={max_count})")

        y = padding + row_h
        for label, count in items:
            canvas.create_text(padding, y, anchor="w", text=label)

            x0 = padding + label_w
            x1 = x0 + max(int((count / max_count) * bar_w), 2)
            y0 = y - 6
            y1 = y + 6
            canvas.create_rectangle(x0, y0, x1, y1, outline="black")
            canvas.create_text(x0 + bar_w + 6, y, anchor="w", text=str(count))
            y += row_h

    def start_monitoring(self) -> None:
        if self._log_monitor is not None and self._log_monitor.is_monitoring:
            return

        containers = _parse_csv(self.containers_var.get())
        keywords = _parse_csv(self.keywords_var.get())
        alert_file_raw = self.alert_file_var.get().strip()

        if not containers:
            messagebox.showerror("Invalid settings", "Please provide at least one container name.")
            return
        if not keywords:
            messagebox.showerror("Invalid settings", "Please provide at least one keyword.")
            return

        alert_log_file = Path(alert_file_raw) if alert_file_raw else None

        alert_service = AlertService(
            alert_log_file=alert_log_file,
            on_alert=self._on_alert,
        )
        parser = LogParser(keywords=keywords)
        self._log_monitor = LogMonitor(
            container_names=containers,
            alert_service=alert_service,
            parser=parser,
            on_info=self._on_info,
            on_error=self._on_error,
        )

        try:
            self._log_monitor.start_monitoring(daemon=True)
        except Exception as exc:
            self._log_monitor = None
            messagebox.showerror("Failed to start", str(exc))
            self._set_controls_running(False)
            return

        self._append_info(
            "Started monitoring: "
            + ", ".join(containers)
            + " | keywords: "
            + ", ".join(keywords)
            + (f" | alert file: {alert_log_file}" if alert_log_file else "")
        )
        self._update_docker_status()
        self._set_controls_running(True)

    def stop_monitoring(self) -> None:
        if self._log_monitor is None:
            self._set_controls_running(False)
            return

        self._log_monitor.stop_monitoring()
        self._log_monitor = None
        self._append_info("Stopped monitoring.")
        self._set_controls_running(False)

    def _update_docker_status(self) -> None:
        try:
            import docker

            client = docker.from_env()
            client.ping()
            self.docker_status_var.set("Docker: connected")
        except Exception as exc:
            self.docker_status_var.set(f"Docker: not available ({exc})")

    def detect_running_containers(self) -> None:
        try:
            import docker

            client = docker.from_env()
            containers = [c.name for c in client.containers.list()]
            if not containers:
                messagebox.showinfo("Detect running", "No running containers found.")
                return
            self.containers_var.set(",".join(containers))
            self._append_info("Detected running containers: " + ", ".join(containers))
            self._update_docker_status()
        except DockerException as exc:
            self._append_error(f"Docker error while detecting containers: {exc}")
            self._update_docker_status()
        except Exception as exc:
            self._append_error(f"Failed to detect containers: {exc}")
            self._update_docker_status()

    def load_from_env(self) -> None:
        lines = _read_env_lines(self._env_path)
        if not lines:
            messagebox.showinfo("Load .env", f"No .env found at: {self._env_path}")
            return
        data = _parse_env_to_dict(lines)

        containers = data.get("DOCKER_CONTAINERS")
        keywords = data.get("ERROR_KEYWORDS")
        alert_file = data.get("ALERT_LOG_FILE")

        if containers is not None:
            self.containers_var.set(containers)
        if keywords is not None:
            self.keywords_var.set(keywords)
        if alert_file is not None:
            self.alert_file_var.set(alert_file)

        self._append_info(f"Loaded configuration from {self._env_path}")

    def save_to_env(self) -> None:
        containers = _parse_csv(self.containers_var.get())
        keywords = _parse_csv(self.keywords_var.get())
        alert_file_raw = self.alert_file_var.get().strip()

        if not containers:
            messagebox.showerror("Invalid settings", "Please provide at least one container name.")
            return
        if not keywords:
            messagebox.showerror("Invalid settings", "Please provide at least one keyword.")
            return

        updates = {
            "DOCKER_CONTAINERS": ",".join(containers),
            "ERROR_KEYWORDS": ",".join(keywords),
            "ALERT_LOG_FILE": alert_file_raw or "alerts.log",
        }
        existing = _read_env_lines(self._env_path)
        new_lines = _update_env_lines(existing, updates)
        self._env_path.write_text("".join(new_lines), encoding="utf-8")
        self._append_info(f"Saved configuration to {self._env_path}")

    def _on_close(self) -> None:
        try:
            self.stop_monitoring()
        finally:
            self.master.destroy()


def run_gui() -> None:
    root = tk.Tk()
    LogMonitoringTkApp(root)
    root.minsize(860, 560)
    root.mainloop()
