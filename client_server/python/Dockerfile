FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir pyzmq msgpack
COPY client.py server.py ./
RUN mkdir -p /app/data
CMD ["python", "client.py"]
