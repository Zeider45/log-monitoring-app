from __future__ import annotations

from datetime import datetime, timezone

from src.types import AlertEvent


class LogParser:
    def __init__(self, keywords: list[str] | None = None):
        default_keywords = ["ERROR", "CRITICAL", "Exception", "timeout", "connection refused"]
        self.keywords = keywords or default_keywords
        self._normalized_keywords = [keyword.lower() for keyword in self.keywords]

    def parse_log(self, container_name: str, log_entry: bytes | str) -> AlertEvent | None:
        message = self._normalize_message(log_entry)
        if not self.validate_log(message):
            return None

        normalized_message = message.lower()
        for original_keyword, normalized_keyword in zip(self.keywords, self._normalized_keywords):
            if normalized_keyword in normalized_message:
                return AlertEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    container_name=container_name,
                    message=message,
                    matched_keyword=original_keyword,
                )

        return None

    def validate_log(self, log_entry: str) -> bool:
        return bool(log_entry and log_entry.strip())

    @staticmethod
    def _normalize_message(log_entry: bytes | str) -> str:
        if isinstance(log_entry, bytes):
            return log_entry.decode("utf-8", errors="replace").strip()
        return str(log_entry).strip()