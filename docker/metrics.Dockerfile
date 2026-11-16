FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir pymavlink cryptography pydantic pyyaml pandas numpy scipy matplotlib

COPY src/ ./src/
COPY scenarios/ ./scenarios/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.metrics.main", "--runs", "30"]
