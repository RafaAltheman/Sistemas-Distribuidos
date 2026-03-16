# FROM python:3.13.7-alpine3.21

# WORKDIR /app

# RUN pip install pyzmq

# CMD ["python", "main.py"]
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir pyzmq msgpack

COPY broker.py cliente.py servidor.py README.md ./

RUN mkdir -p /app/data