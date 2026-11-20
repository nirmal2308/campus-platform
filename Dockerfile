FROM python:3.12-slim AS runtime
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} PYTHONUNBUFFERED=1 CAMPUS_DB_PATH=/data/campus.db
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
RUN useradd --system --uid 10001 campus && mkdir /data && chown campus /data
USER campus
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app.__main__:app"]
