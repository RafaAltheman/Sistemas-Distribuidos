#include <zmq.h>
#include <msgpack.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MAX_CHANNELS 1000
#define MAX_LOGINS 1000

char *channels[MAX_CHANNELS];
int channel_count = 0;

char *logins[MAX_LOGINS];
int login_count = 0;

const char *DATA_DIR = "data";
const char *CHANNELS_FILE = "data/channels.txt";
const char *LOGINS_FILE = "data/logins.txt";

// =========================
// Persistência
// =========================

void load_channels() {
    FILE *f = fopen(CHANNELS_FILE, "r");
    if (!f) return;

    char line[128];
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\n")] = 0;
        channels[channel_count++] = strdup(line);
    }
    fclose(f);
}

void save_channels() {
    FILE *f = fopen(CHANNELS_FILE, "w");
    if (!f) return;

    for (int i = 0; i < channel_count; i++) {
        fprintf(f, "%s\n", channels[i]);
    }
    fclose(f);
}

void load_logins() {
    FILE *f = fopen(LOGINS_FILE, "r");
    if (!f) return;

    char line[128];
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\n")] = 0;
        logins[login_count++] = strdup(line);
    }
    fclose(f);
}

void save_login(const char *user, double timestamp) {
    FILE *f = fopen(LOGINS_FILE, "a");
    if (!f) return;

    fprintf(f, "%s %.0f\n", user, timestamp);
    fclose(f);
}

// =========================

int channel_exists(char *name) {
    for (int i = 0; i < channel_count; i++) {
        if (strcmp(channels[i], name) == 0)
            return 1;
    }
    return 0;
}

void add_channel(char *name) {
    channels[channel_count++] = strdup(name);
    save_channels();
}

int main() {
    // criar pasta data
    system("mkdir -p data");

    load_channels();
    load_logins();

    void *context = zmq_ctx_new();
    void *socket = zmq_socket(context, ZMQ_REP);

    zmq_connect(socket, "tcp://broker:5556");

    printf("[SERVER C] Iniciado\n");

    while (1) {
        char buffer[4096];
        int size = zmq_recv(socket, buffer, sizeof(buffer), 0);

        msgpack_unpacked msg;
        msgpack_unpacked_init(&msg);
        msgpack_unpack_next(&msg, buffer, size, NULL);

        msgpack_object obj = msg.data;

        char type[32] = "";
        char user[64] = "";
        char channel[64] = "";
        double timestamp = 0;

        // extrair dados
        for (int i = 0; i < obj.via.map.size; i++) {
            msgpack_object_kv *kv = &obj.via.map.ptr[i];

            if (strncmp(kv->key.via.str.ptr, "type", kv->key.via.str.size) == 0) {
                snprintf(type, sizeof(type), "%.*s",
                    kv->val.via.str.size, kv->val.via.str.ptr);
            }

            if (strncmp(kv->key.via.str.ptr, "user", kv->key.via.str.size) == 0) {
                snprintf(user, sizeof(user), "%.*s",
                    kv->val.via.str.size, kv->val.via.str.ptr);
            }

            if (strncmp(kv->key.via.str.ptr, "channel", kv->key.via.str.size) == 0) {
                snprintf(channel, sizeof(channel), "%.*s",
                    kv->val.via.str.size, kv->val.via.str.ptr);
            }

            if (strncmp(kv->key.via.str.ptr, "timestamp", kv->key.via.str.size) == 0) {
                timestamp = kv->val.via.f64;
            }
        }

        msgpack_sbuffer sbuf;
        msgpack_sbuffer_init(&sbuf);
        msgpack_packer pk;
        msgpack_packer_init(&pk, &sbuf, msgpack_sbuffer_write);

        if (strcmp(type, "login") == 0) {
            save_login(user, timestamp);

            printf("[LOGIN] %s\n", user);

            msgpack_pack_map(&pk, 3);
            msgpack_pack_str(&pk, 6); msgpack_pack_str_body(&pk, "status", 6);
            msgpack_pack_str(&pk, 2); msgpack_pack_str_body(&pk, "ok", 2);

            msgpack_pack_str(&pk, 7); msgpack_pack_str_body(&pk, "message", 7);
            msgpack_pack_str(&pk, 15); msgpack_pack_str_body(&pk, "login realizado", 15);

            msgpack_pack_str(&pk, 9); msgpack_pack_str_body(&pk, "timestamp", 9);
            msgpack_pack_double(&pk, (double)time(NULL));
        }

        else if (strcmp(type, "create_channel") == 0) {
            if (channel_exists(channel)) {
                printf("[CREATE] exists: %s\n", channel);

                msgpack_pack_map(&pk, 2);
                msgpack_pack_str(&pk, 6); msgpack_pack_str_body(&pk, "status", 6);
                msgpack_pack_str(&pk, 5); msgpack_pack_str_body(&pk, "error", 5);
            } else {
                add_channel(channel);

                printf("[CREATE] ok: %s\n", channel);

                msgpack_pack_map(&pk, 2);
                msgpack_pack_str(&pk, 6); msgpack_pack_str_body(&pk, "status", 6);
                msgpack_pack_str(&pk, 2); msgpack_pack_str_body(&pk, "ok", 2);
            }
        }

        else if (strcmp(type, "list_channels") == 0) {
            printf("[LIST] total=%d\n", channel_count);

            msgpack_pack_map(&pk, 2);

            msgpack_pack_str(&pk, 6); msgpack_pack_str_body(&pk, "status", 6);
            msgpack_pack_str(&pk, 2); msgpack_pack_str_body(&pk, "ok", 2);

            msgpack_pack_str(&pk, 8); msgpack_pack_str_body(&pk, "channels", 8);
            msgpack_pack_array(&pk, channel_count);

            for (int i = 0; i < channel_count; i++) {
                msgpack_pack_str(&pk, strlen(channels[i]));
                msgpack_pack_str_body(&pk, channels[i], strlen(channels[i]));
            }
        }

        zmq_send(socket, sbuf.data, sbuf.size, 0);

        msgpack_sbuffer_destroy(&sbuf);
        msgpack_unpacked_destroy(&msg);
    }

    zmq_close(socket);
    zmq_ctx_destroy(context);
    return 0;
}