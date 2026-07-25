FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV APP_DEBUG=false

COPY requirements.txt requirements-llm.txt ./
RUN apt-get update \
    && apt-get install --no-install-recommends --yes build-essential cmake libgomp1 \
    && pip install --no-cache-dir -r requirements.txt -r requirements-llm.txt \
    && apt-get purge --auto-remove --yes build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
