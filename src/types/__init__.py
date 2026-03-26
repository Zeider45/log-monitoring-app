from dataclasses import dataclass


@dataclass(frozen=True)
class AlertEvent:
	timestamp: str
	container_name: str
	message: str
	matched_keyword: str