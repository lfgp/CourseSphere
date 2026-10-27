FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --upgrade pip==26.2.2 \
    && python -m pip install --only-binary=:all: -r requirements.txt \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
COPY --chown=10001:10001 endpoints.py firebase.py observability.py query_manager.py \
    rate_limiting.py security_headers.py structured_logging.py validation.py serve.py ./
USER 10001:10001
EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2).close()"]
ENTRYPOINT ["python", "serve.py"]
