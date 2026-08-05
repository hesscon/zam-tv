# Deliberately update version and digest together when refreshing the base image.
FROM python:3.12.13-slim-trixie@sha256:646fb0bca3dd3ea1bcc6feb72c17ed16eed6e10cffc732fcc1478bd3e7f02d7b

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV APP_DEBUG=false

COPY requirements-llm.txt ./
RUN apt-get update \
    && apt-get install --no-install-recommends --yes build-essential cmake libgomp1 \
    && pip install --no-cache-dir -r requirements-llm.txt \
    && apt-get purge --auto-remove --yes build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
