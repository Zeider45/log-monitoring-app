from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


DEFAULT_KEYWORDS = ["ERROR", "CRITICAL", "Exception", "timeout", "connection refused"]


@dataclass(frozen=True)
class Settings:
	containers: list[str]
	error_keywords: list[str]
	alert_log_file: Path


def _parse_csv_env(name: str, default_values: list[str]) -> list[str]:
	raw_value = os.getenv(name)
	if not raw_value:
		return default_values

	parsed_values = [item.strip() for item in raw_value.split(",") if item.strip()]
	return parsed_values or default_values


def get_settings() -> Settings:
	containers = _parse_csv_env("DOCKER_CONTAINERS", ["api"])
	error_keywords = _parse_csv_env("ERROR_KEYWORDS", DEFAULT_KEYWORDS)
	alert_log_file = Path(os.getenv("ALERT_LOG_FILE", "alerts.log"))

	return Settings(
		containers=containers,
		error_keywords=error_keywords,
		alert_log_file=alert_log_file,
	)