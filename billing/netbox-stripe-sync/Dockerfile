FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV WEBHOOK_LISTEN_HOST=0.0.0.0
ENV WEBHOOK_LISTEN_PORT=8080
ENV EVENT_STORE_PATH=/data/events.db

VOLUME ["/data"]
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host ${WEBHOOK_LISTEN_HOST} --port ${WEBHOOK_LISTEN_PORT}"]
