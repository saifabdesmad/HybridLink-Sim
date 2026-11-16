FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    iproute2 \
    iptables \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir pymavlink pydantic pyyaml

COPY src/ ./src/
COPY scenarios/ ./scenarios/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.netem.proxy"]
