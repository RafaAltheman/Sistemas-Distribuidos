FROM debian:bookworm-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config libzmq3-dev libmsgpack-dev libsqlite3-dev sqlite3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY main.c ./
RUN gcc -O2 -Wall -o bbs main.c $(pkg-config --cflags libzmq sqlite3 msgpack) $(pkg-config --libs libzmq sqlite3 msgpack) -lmsgpackc
RUN mkdir -p /app/data
CMD ["/app/bbs"]
