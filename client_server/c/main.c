#include <zmq.h>
#include <msgpack.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <regex.h>

#define BUF_SIZE 8192

static char *env_or(const char *name, const char *fallback) {
    char *v = getenv(name);
    return v ? v : (char *)fallback;
}

static void iso_now(char *buf, size_t size) {
    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);
    strftime(buf, size, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

static void uuid_like(char *buf, size_t size) {
    snprintf(buf, size, "%08x-%04x-%04x-%04x-%08x",
             rand(), rand() & 0xffff, rand() & 0xffff, rand() & 0xffff, rand());
}

static int db_exec(sqlite3 *db, const char *sql) {
    char *err = NULL;
    int rc = sqlite3_exec(db, sql, NULL, NULL, &err);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "sqlite error: %s\n", err ? err : "unknown");
        sqlite3_free(err);
    }
    return rc;
}

static sqlite3 *db_open(const char *path) {
    sqlite3 *db = NULL;
    if (sqlite3_open(path, &db) != SQLITE_OK) {
        fprintf(stderr, "erro abrindo db\n");
        exit(1);
    }
    db_exec(db, "PRAGMA journal_mode=WAL;");
    db_exec(db, "CREATE TABLE IF NOT EXISTS logins (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, ts TEXT);");
    db_exec(db, "CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_by TEXT, ts TEXT);");
    db_exec(db, "CREATE TABLE IF NOT EXISTS replication_events (event_id TEXT PRIMARY KEY, payload BLOB);");
    return db;
}

static void db_add_login(sqlite3 *db, const char *user, const char *ts) {
    sqlite3_stmt *stmt;
    sqlite3_prepare_v2(db, "INSERT INTO logins(user, ts) VALUES (?, ?)", -1, &stmt, NULL);
    sqlite3_bind_text(stmt, 1, user, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, ts, -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

static int db_channel_exists(sqlite3 *db, const char *name) {
    sqlite3_stmt *stmt;
    int exists = 0;
    sqlite3_prepare_v2(db, "SELECT 1 FROM channels WHERE name = ?", -1, &stmt, NULL);
    sqlite3_bind_text(stmt, 1, name, -1, SQLITE_TRANSIENT);
    if (sqlite3_step(stmt) == SQLITE_ROW) exists = 1;
    sqlite3_finalize(stmt);
    return exists;
}

static void db_add_channel(sqlite3 *db, const char *name, const char *user, const char *ts) {
    sqlite3_stmt *stmt;
    sqlite3_prepare_v2(db, "INSERT OR IGNORE INTO channels(name, created_by, ts) VALUES (?, ?, ?)", -1, &stmt, NULL);
    sqlite3_bind_text(stmt, 1, name, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, user, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, ts, -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

static int db_seen_event(sqlite3 *db, const char *event_id) {
    sqlite3_stmt *stmt;
    int exists = 0;
    sqlite3_prepare_v2(db, "SELECT 1 FROM replication_events WHERE event_id = ?", -1, &stmt, NULL);
    sqlite3_bind_text(stmt, 1, event_id, -1, SQLITE_TRANSIENT);
    if (sqlite3_step(stmt) == SQLITE_ROW) exists = 1;
    sqlite3_finalize(stmt);
    return exists;
}

static void db_save_event(sqlite3 *db, const char *event_id, const void *payload, int size) {
    sqlite3_stmt *stmt;
    sqlite3_prepare_v2(db, "INSERT OR IGNORE INTO replication_events(event_id, payload) VALUES (?, ?)", -1, &stmt, NULL);
    sqlite3_bind_text(stmt, 1, event_id, -1, SQLITE_TRANSIENT);
    sqlite3_bind_blob(stmt, 2, payload, size, SQLITE_TRANSIENT);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

static int valid_channel(const char *channel) {
    regex_t regex;
    int ok;
    regcomp(&regex, "^[A-Za-z0-9_-]{1,32}$", REG_EXTENDED);
    ok = regexec(&regex, channel, 0, NULL, 0) == 0;
    regfree(&regex);
    return ok;
}

static int recv_bytes(void *socket, char *buffer, int max_size) {
    int n = zmq_recv(socket, buffer, max_size, 0);
    if (n < 0) { perror("zmq_recv"); exit(1); }
    return n;
}

static void print_msgpack_map(const char *prefix, const char *buffer, size_t size) {
    msgpack_unpacked msg; msgpack_unpacked_init(&msg);
    size_t off = 0;
    if (msgpack_unpack_next(&msg, buffer, size, &off)) {
        msgpack_object_print(stdout, msg.data);
        printf("\n");
    } else {
        printf("%s <payload invalido>\n", prefix);
    }
    msgpack_unpacked_destroy(&msg);
}

static void pack_kv_str(msgpack_packer *pk, const char *k, const char *v) {
    msgpack_pack_str(pk, strlen(k)); msgpack_pack_str_body(pk, k, strlen(k));
    if (v) { msgpack_pack_str(pk, strlen(v)); msgpack_pack_str_body(pk, v, strlen(v)); }
    else msgpack_pack_nil(pk);
}

static int extract_string_key(msgpack_object map, const char *key, char *out, size_t out_size) {
    if (map.type != MSGPACK_OBJECT_MAP) return 0;
    for (uint32_t i = 0; i < map.via.map.size; i++) {
        msgpack_object_kv *kv = &map.via.map.ptr[i];
        if (kv->key.type == MSGPACK_OBJECT_STR && strncmp(kv->key.via.str.ptr, key, kv->key.via.str.size) == 0 && strlen(key) == kv->key.via.str.size) {
            if (kv->val.type == MSGPACK_OBJECT_STR) {
                size_t n = kv->val.via.str.size < out_size - 1 ? kv->val.via.str.size : out_size - 1;
                memcpy(out, kv->val.via.str.ptr, n); out[n] = '\0';
                return 1;
            }
            if (kv->val.type == MSGPACK_OBJECT_NIL) { out[0] = '\0'; return 1; }
        }
    }
    return 0;
}

static msgpack_object find_key(msgpack_object map, const char *key) {
    msgpack_object nil; nil.type = MSGPACK_OBJECT_NIL;
    if (map.type != MSGPACK_OBJECT_MAP) return nil;
    for (uint32_t i = 0; i < map.via.map.size; i++) {
        msgpack_object_kv *kv = &map.via.map.ptr[i];
        if (kv->key.type == MSGPACK_OBJECT_STR && strncmp(kv->key.via.str.ptr, key, kv->key.via.str.size) == 0 && strlen(key) == kv->key.via.str.size) return kv->val;
    }
    return nil;
}

static void send_response(void *rep, const char *server_id, const char *op, const char *request_id,
                          const char *status, const char *error, const char *message,
                          const char *channel) {
    char ts[64]; iso_now(ts, sizeof(ts));
    msgpack_sbuffer sbuf; msgpack_sbuffer_init(&sbuf);
    msgpack_packer pk; msgpack_packer_init(&pk, &sbuf, msgpack_sbuffer_write);
    msgpack_pack_map(&pk, 8);
    pack_kv_str(&pk, "type", "response");
    pack_kv_str(&pk, "operation", op);
    pack_kv_str(&pk, "request_id", request_id);
    pack_kv_str(&pk, "timestamp", ts);
    pack_kv_str(&pk, "server_id", server_id);
    pack_kv_str(&pk, "status", status);

    msgpack_pack_str(&pk, 4); msgpack_pack_str_body(&pk, "data", 4);
    if (channel && message) {
        msgpack_pack_map(&pk, 2);
        pack_kv_str(&pk, "channel", channel);
        pack_kv_str(&pk, "message", message);
    } else if (message) {
        msgpack_pack_map(&pk, 1);
        pack_kv_str(&pk, "message", message);
    } else {
        msgpack_pack_nil(&pk);
    }

    msgpack_pack_str(&pk, 5); msgpack_pack_str_body(&pk, "error", 5);
    if (error) { msgpack_pack_str(&pk, strlen(error)); msgpack_pack_str_body(&pk, error, strlen(error)); }
    else msgpack_pack_nil(&pk);

    printf("[%s] ENVIOU resposta: ", server_id); print_msgpack_map("", sbuf.data, sbuf.size);
    zmq_send(rep, sbuf.data, sbuf.size, 0);
    msgpack_sbuffer_destroy(&sbuf);
}

static void send_list_response(void *rep, sqlite3 *db, const char *server_id, const char *op, const char *request_id) {
    char ts[64]; iso_now(ts, sizeof(ts));
    msgpack_sbuffer sbuf; msgpack_sbuffer_init(&sbuf);
    msgpack_packer pk; msgpack_packer_init(&pk, &sbuf, msgpack_sbuffer_write);
    msgpack_pack_map(&pk, 8);
    pack_kv_str(&pk, "type", "response");
    pack_kv_str(&pk, "operation", op);
    pack_kv_str(&pk, "request_id", request_id);
    pack_kv_str(&pk, "timestamp", ts);
    pack_kv_str(&pk, "server_id", server_id);
    pack_kv_str(&pk, "status", "ok");
    msgpack_pack_str(&pk, 4); msgpack_pack_str_body(&pk, "data", 4);
    msgpack_pack_map(&pk, 1);
    msgpack_pack_str(&pk, 8); msgpack_pack_str_body(&pk, "channels", 8);
    sqlite3_stmt *stmt;
    sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM channels", -1, &stmt, NULL);
    int total = 0;
    if (sqlite3_step(stmt) == SQLITE_ROW) total = sqlite3_column_int(stmt, 0);
    sqlite3_finalize(stmt);
    msgpack_pack_array(&pk, total);
    sqlite3_prepare_v2(db, "SELECT name FROM channels ORDER BY name", -1, &stmt, NULL);
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        const unsigned char *name = sqlite3_column_text(stmt, 0);
        size_t len = strlen((const char *)name);
        msgpack_pack_str(&pk, len); msgpack_pack_str_body(&pk, (const char *)name, len);
    }
    sqlite3_finalize(stmt);
    msgpack_pack_str(&pk, 5); msgpack_pack_str_body(&pk, "error", 5);
    msgpack_pack_nil(&pk);
    printf("[%s] ENVIOU resposta: ", server_id); print_msgpack_map("", sbuf.data, sbuf.size);
    zmq_send(rep, sbuf.data, sbuf.size, 0);
    msgpack_sbuffer_destroy(&sbuf);
}

static void publish_event(void *pub, sqlite3 *db, const char *server_id, const char *event_type,
                          const char *user, const char *timestamp, const char *request_id, const char *channel) {
    char event_id[64]; uuid_like(event_id, sizeof(event_id));
    msgpack_sbuffer sbuf; msgpack_sbuffer_init(&sbuf);
    msgpack_packer pk; msgpack_packer_init(&pk, &sbuf, msgpack_sbuffer_write);
    int fields = channel ? 7 : 6;
    msgpack_pack_map(&pk, fields);
    pack_kv_str(&pk, "event_type", event_type);
    pack_kv_str(&pk, "event_id", event_id);
    if (request_id) pack_kv_str(&pk, "request_id", request_id); else pack_kv_str(&pk, "request_id", NULL);
    pack_kv_str(&pk, "timestamp", timestamp);
    pack_kv_str(&pk, "origin_server", server_id);
    pack_kv_str(&pk, "user", user);
    if (channel) pack_kv_str(&pk, "channel", channel);
    db_save_event(db, event_id, sbuf.data, sbuf.size);
    usleep(200000);
    zmq_send(pub, sbuf.data, sbuf.size, 0);
    printf("[%s] PUBLICOU replicação: ", server_id); print_msgpack_map("", sbuf.data, sbuf.size);
    msgpack_sbuffer_destroy(&sbuf);
}

static void apply_replication(sqlite3 *db, const char *server_id, const char *buffer, int size) {
    msgpack_unpacked msg; msgpack_unpacked_init(&msg);
    size_t off = 0;
    if (!msgpack_unpack_next(&msg, buffer, size, &off)) { msgpack_unpacked_destroy(&msg); return; }
    msgpack_object root = msg.data;
    char event_id[128] = {0}, origin[128] = {0}, event_type[64] = {0}, user[128] = {0}, ts[64] = {0}, channel[128] = {0};
    extract_string_key(root, "event_id", event_id, sizeof(event_id));
    if (event_id[0] == '\0' || db_seen_event(db, event_id)) { msgpack_unpacked_destroy(&msg); return; }
    db_save_event(db, event_id, buffer, size);
    extract_string_key(root, "origin_server", origin, sizeof(origin));
    if (strcmp(origin, server_id) == 0) { msgpack_unpacked_destroy(&msg); return; }
    extract_string_key(root, "event_type", event_type, sizeof(event_type));
    extract_string_key(root, "user", user, sizeof(user));
    extract_string_key(root, "timestamp", ts, sizeof(ts));
    extract_string_key(root, "channel", channel, sizeof(channel));
    if (strcmp(event_type, "login") == 0) db_add_login(db, user, ts);
    else if (strcmp(event_type, "create_channel") == 0) db_add_channel(db, channel, user, ts);
    printf("[%s] RECEBEU replicação: ", server_id); print_msgpack_map("", buffer, size);
    msgpack_unpacked_destroy(&msg);
}

static void run_server(void) {
    srand((unsigned int)time(NULL));
    const char *server_id = env_or("SERVER_ID", "server_c");
    const char *db_path = env_or("DB_PATH", "/app/data/server_c.db");
    const char *peer_pubs = env_or("PEER_PUBS", "");
    const char *pub_port = env_or("PUB_PORT", "7002");
    sqlite3 *db = db_open(db_path);
    void *ctx = zmq_ctx_new();
    void *rep = zmq_socket(ctx, ZMQ_REP);
    void *pub = zmq_socket(ctx, ZMQ_PUB);
    void *sub = zmq_socket(ctx, ZMQ_SUB);
    int linger = 0;
    zmq_setsockopt(rep, ZMQ_LINGER, &linger, sizeof(linger));
    zmq_setsockopt(pub, ZMQ_LINGER, &linger, sizeof(linger));
    zmq_setsockopt(sub, ZMQ_LINGER, &linger, sizeof(linger));
    zmq_connect(rep, "tcp://broker:5556");
    char bind_addr[64]; snprintf(bind_addr, sizeof(bind_addr), "tcp://*:%s", pub_port); zmq_bind(pub, bind_addr);
    zmq_setsockopt(sub, ZMQ_SUBSCRIBE, "", 0);
    char peers_copy[512]; snprintf(peers_copy, sizeof(peers_copy), "%s", peer_pubs);
    char *token = strtok(peers_copy, ",");
    while (token) { if (strlen(token) > 0) zmq_connect(sub, token); token = strtok(NULL, ","); }
    printf("[%s] Iniciado | broker=tcp://broker:5556 | db=%s | pub_port=%s | peers=%s\n", server_id, db_path, pub_port, peer_pubs);
    sleep(1);

    zmq_pollitem_t items[] = {{rep, 0, ZMQ_POLLIN, 0}, {sub, 0, ZMQ_POLLIN, 0}};
    for (;;) {
        zmq_poll(items, 2, 1000);
        if (items[0].revents & ZMQ_POLLIN) {
            char buffer[BUF_SIZE];
            int n = recv_bytes(rep, buffer, sizeof(buffer));
            printf("[%s] RECEBEU requisição: ", server_id); print_msgpack_map("", buffer, n);
            msgpack_unpacked msg; msgpack_unpacked_init(&msg);
            size_t off = 0;
            if (!msgpack_unpack_next(&msg, buffer, n, &off)) { msgpack_unpacked_destroy(&msg); continue; }
            msgpack_object root = msg.data;
            char operation[64] = {0}, request_id[128] = {0}, user[128] = {0}, timestamp[64] = {0};
            extract_string_key(root, "operation", operation, sizeof(operation));
            extract_string_key(root, "request_id", request_id, sizeof(request_id));
            extract_string_key(root, "user", user, sizeof(user));
            extract_string_key(root, "timestamp", timestamp, sizeof(timestamp));
            if (strcmp(operation, "login") == 0) {
                if (user[0] == '\0') send_response(rep, server_id, operation, request_id, "error", "usuario obrigatorio", NULL, NULL);
                else {
                    db_add_login(db, user, timestamp);
                    publish_event(pub, db, server_id, "login", user, timestamp, request_id, NULL);
                    char message[256]; snprintf(message, sizeof(message), "login realizado para %s", user);
                    send_response(rep, server_id, operation, request_id, "ok", NULL, message, NULL);
                }
            } else if (strcmp(operation, "list_channels") == 0) {
                send_list_response(rep, db, server_id, operation, request_id);
            } else if (strcmp(operation, "create_channel") == 0) {
                msgpack_object data_obj = find_key(root, "data");
                char channel[128] = {0};
                extract_string_key(data_obj, "channel", channel, sizeof(channel));
                if (!valid_channel(channel)) send_response(rep, server_id, operation, request_id, "error", "nome de canal invalido", NULL, NULL);
                else if (db_channel_exists(db, channel)) send_response(rep, server_id, operation, request_id, "error", "canal ja existe", NULL, channel);
                else {
                    db_add_channel(db, channel, user, timestamp);
                    publish_event(pub, db, server_id, "create_channel", user, timestamp, request_id, channel);
                    send_response(rep, server_id, operation, request_id, "ok", NULL, "canal criado", channel);
                }
            } else {
                send_response(rep, server_id, operation, request_id, "error", "operacao invalida", NULL, NULL);
            }
            msgpack_unpacked_destroy(&msg);
        }
        if (items[1].revents & ZMQ_POLLIN) {
            char buffer[BUF_SIZE];
            int n = recv_bytes(sub, buffer, sizeof(buffer));
            apply_replication(db, server_id, buffer, n);
        }
    }
}

static void send_req(void *req, const char *user, const char *operation, const char *channel) {
    char req_id[64], ts[64]; uuid_like(req_id, sizeof(req_id)); iso_now(ts, sizeof(ts));
    msgpack_sbuffer sbuf; msgpack_sbuffer_init(&sbuf);
    msgpack_packer pk; msgpack_packer_init(&pk, &sbuf, msgpack_sbuffer_write);
    msgpack_pack_map(&pk, 6);
    pack_kv_str(&pk, "type", "request");
    pack_kv_str(&pk, "operation", operation);
    pack_kv_str(&pk, "request_id", req_id);
    pack_kv_str(&pk, "timestamp", ts);
    pack_kv_str(&pk, "user", user);
    msgpack_pack_str(&pk, 4); msgpack_pack_str_body(&pk, "data", 4);
    if (channel) {
        msgpack_pack_map(&pk, 1);
        pack_kv_str(&pk, "channel", channel);
    } else {
        msgpack_pack_map(&pk, 0);
    }
    printf("[CLIENTE %s] ENVIANDO: ", user); print_msgpack_map("", sbuf.data, sbuf.size);
    zmq_send(req, sbuf.data, sbuf.size, 0);
    char buffer[BUF_SIZE];
    int n = recv_bytes(req, buffer, sizeof(buffer));
    printf("[CLIENTE %s] RECEBEU: ", user); print_msgpack_map("", buffer, n);
    msgpack_sbuffer_destroy(&sbuf);
}

static void run_client(void) {
    const char *user = env_or("CLIENT_USER", "bot_c");
    int start_delay = atoi(env_or("START_DELAY", "7"));
    const char *channel = env_or("CHANNEL_TO_CREATE", "c_room");
    printf("[CLIENTE %s] aguardando %ds para iniciar\n", user, start_delay);
    sleep(start_delay);
    void *ctx = zmq_ctx_new();
    void *req = zmq_socket(ctx, ZMQ_REQ);
    int linger = 0; zmq_setsockopt(req, ZMQ_LINGER, &linger, sizeof(linger));
    zmq_connect(req, "tcp://broker:5555");
    send_req(req, user, "login", NULL); sleep(1);
    send_req(req, user, "list_channels", NULL); sleep(1);
    send_req(req, user, "create_channel", channel); sleep(1);
    send_req(req, user, "list_channels", NULL);
    printf("[CLIENTE %s] fluxo concluído com sucesso\n", user);
}

int main(void) {
    const char *role = env_or("ROLE", "client");
    if (strcmp(role, "server") == 0) run_server();
    else run_client();
    return 0;
}
