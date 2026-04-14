import argparse

from src.config.settings import get_settings
from src.monitors.log_monitor import LogMonitor
from src.parsers.log_parser import LogParser
from src.services.alert_service import AlertService


def main(argv: list[str] | None = None) -> None:
    arg_parser = argparse.ArgumentParser(description="Docker log monitor")
    arg_parser.add_argument("--gui", action="store_true", help="Start the Tkinter GUI")
    args = arg_parser.parse_args(argv)

    if args.gui:
        try:
            from src.gui.tk_app import run_gui
        except Exception as exc:
            raise SystemExit(f"Failed to start GUI: {exc}") from exc

        run_gui()
        return

    settings = get_settings()
    alert_service = AlertService(alert_log_file=settings.alert_log_file)
    parser = LogParser(keywords=settings.error_keywords)
    log_monitor = LogMonitor(
        container_names=settings.containers,
        alert_service=alert_service,
        parser=parser,
    )

    print(f"Monitoring Docker containers: {', '.join(settings.containers)}")
    print(f"Alert keywords: {', '.join(settings.error_keywords)}")

    try:
        log_monitor.start_monitoring()
    except KeyboardInterrupt:
        print("Stopping Docker log monitor...")
        log_monitor.stop_monitoring()


if __name__ == "__main__":
    main()