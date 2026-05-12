FROM python:3.11.11-slim

WORKDIR /backend

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
ENV PYTHONPATH="/backend:${PYTHONPATH}"

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY app ./app
COPY migration ./migration
COPY alembic.ini ./

EXPOSE 8000 9090
# 8000 = 사용자 트래픽 (FastAPI). 9090 = /metrics
# 9090 은 docker-compose 의 expose: 만 두고 ports: 절대 금지. monitoring-network 내부 / k8s NetworkPolicy 로만 도달.

# Run
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]