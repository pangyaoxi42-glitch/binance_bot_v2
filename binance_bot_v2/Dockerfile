FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    ccxt>=4.2.0 \
    pandas>=2.0.0 \
    numpy>=1.24.0 \
    openai>=1.0.0 \
    httpx>=0.25.0 \
    python-dotenv>=1.0.0 \
    aiosqlite>=0.20.0 \
    loguru>=0.7.0

COPY config/ ./config/
COPY core/ ./core/
COPY strategy/ ./strategy/
COPY execution/ ./execution/
COPY risk/ ./risk/
COPY analytics/ ./analytics/
COPY main.py .

RUN mkdir -p /app/data
VOLUME ["/app/data"]

CMD ["python", "-u", "main.py"]
