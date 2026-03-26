FROM python:3.11-slim

WORKDIR /app

COPY generate_logs.py /app/generate_logs.py

ENV PYTHONUNBUFFERED=1 \
    SERVICE_NAME=api \
    LOG_INTERVAL_SECONDS=0.5 \
    ERROR_PROBABILITY=0.15 \
    EXCEPTION_PROBABILITY=0.05 \
    TIMEOUT_PROBABILITY=0.05

CMD ["python", "/app/generate_logs.py"]
