FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV YF_TRANSPORT=streamable-http
ENV YF_HTTP_HOST=0.0.0.0
ENV YF_HTTP_PORT=8000

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir .

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["python", "-m", "yfinance_mcp.server"]
