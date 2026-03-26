from src.config.settings import get_settings
from src.monitors.log_monitor import LogMonitor
from src.parsers.log_parser import LogParser
from src.services.alert_service import AlertService


def main() -> None:
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