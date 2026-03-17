package bbs;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import java.util.*;
import java.util.regex.Pattern;

public class JavaServer {
    private final String serverId = System.getenv().getOrDefault("SERVER_ID", "server_java");
    private final String dbPath = System.getenv().getOrDefault("DB_PATH", "/app/data/server_java.db");
    private final String peersRaw = System.getenv().getOrDefault("PEER_PUBS", "");
    private final int pubPort = Integer.parseInt(System.getenv().getOrDefault("PUB_PORT", "7001"));
    private final DB db;
    private static final Pattern CHANNEL_RE = Pattern.compile("[A-Za-z0-9_-]{1,32}");

    public JavaServer() throws Exception { this.db = new DB(dbPath); }

    public void run() throws Exception {
        try (ZContext context = new ZContext()) {
            ZMQ.Socket rep = context.createSocket(SocketType.REP);
            rep.connect("tcp://broker:5556");
            ZMQ.Socket pub = context.createSocket(SocketType.PUB);
            pub.bind("tcp://*:" + pubPort);
            ZMQ.Socket sub = context.createSocket(SocketType.SUB);
            sub.subscribe(new byte[0]);
            List<String> peers = new ArrayList<>();
            for (String p : peersRaw.split(",")) {
                if (!p.isBlank()) { peers.add(p.trim()); sub.connect(p.trim()); }
            }
            System.out.println("[" + serverId + "] Iniciado | broker=tcp://broker:5556 | db=" + dbPath + " | pub_port=" + pubPort + " | peers=" + peers);
            Util.sleepMillis(1000);
            ZMQ.Poller poller = context.createPoller(2);
            poller.register(rep, ZMQ.Poller.POLLIN);
            poller.register(sub, ZMQ.Poller.POLLIN);
            while (!Thread.currentThread().isInterrupted()) {
                poller.poll(1000);
                if (poller.pollin(0)) {
                    byte[] raw = rep.recv(0);
                    Map<String, Object> req = Util.unpackMap(raw);
                    System.out.println("[" + serverId + "] RECEBEU requisição: " + req);
                    Map<String, Object> resp = handle(pub, req);
                    System.out.println("[" + serverId + "] ENVIOU resposta: " + resp);
                    rep.send(Util.packMap(resp), 0);
                }
                if (poller.pollin(1)) {
                    byte[] raw = sub.recv(0);
                    Map<String, Object> event = Util.unpackMap(raw);
                    applyReplication(event, raw);
                }
            }
        }
    }

    private Map<String, Object> response(String op, String requestId, String status, Object data, Object error) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("type", "response"); r.put("operation", op); r.put("request_id", requestId);
        r.put("timestamp", Util.isoNow()); r.put("server_id", serverId); r.put("status", status);
        r.put("data", data); r.put("error", error);
        return r;
    }

    private void publishReplication(ZMQ.Socket pub, Map<String, Object> event) throws Exception {
        byte[] payload = Util.packMap(event);
        db.saveEvent((String) event.get("event_id"), payload);
        Util.sleepMillis(200);
        pub.send(payload, 0);
        System.out.println("[" + serverId + "] PUBLICOU replicação: " + event);
    }

    private void applyReplication(Map<String, Object> event, byte[] raw) throws Exception {
        String eventId = (String) event.get("event_id");
        if (eventId == null || db.seenEvent(eventId)) return;
        db.saveEvent(eventId, raw);
        if (serverId.equals(event.get("origin_server"))) return;
        String type = (String) event.get("event_type");
        if ("login".equals(type)) {
            db.addLogin((String) event.get("user"), (String) event.get("timestamp"));
        } else if ("create_channel".equals(type)) {
            String channel = (String) event.get("channel");
            if (channel != null && !channel.isBlank()) {
                db.addChannel(channel, (String) event.get("user"), (String) event.get("timestamp"));
            }
        }
        System.out.println("[" + serverId + "] RECEBEU replicação: " + event);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> handle(ZMQ.Socket pub, Map<String, Object> req) throws Exception {
        String op = (String) req.get("operation");
        String requestId = (String) req.get("request_id");
        String user = (String) req.getOrDefault("user", "");
        String timestamp = (String) req.getOrDefault("timestamp", Util.isoNow());
        if ("login".equals(op)) {
            if (user == null || user.isBlank()) return response(op, requestId, "error", null, "usuario obrigatorio");
            db.addLogin(user, timestamp);
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("event_type", "login"); event.put("event_id", UUID.randomUUID().toString());
            event.put("request_id", requestId); event.put("timestamp", timestamp);
            event.put("origin_server", serverId); event.put("user", user);
            publishReplication(pub, event);
            return response(op, requestId, "ok", Map.of("message", "login realizado para " + user), null);
        }
        if ("list_channels".equals(op)) {
            return response(op, requestId, "ok", Map.of("channels", db.listChannels()), null);
        }
        if ("create_channel".equals(op)) {
            Map<String, Object> data = (Map<String, Object>) req.getOrDefault("data", new LinkedHashMap<>());
            String channel = (String) data.getOrDefault("channel", "");
            if (!CHANNEL_RE.matcher(channel).matches()) return response(op, requestId, "error", null, "nome de canal invalido");
            if (db.channelExists(channel)) return response(op, requestId, "error", Map.of("channel", channel), "canal ja existe");
            db.addChannel(channel, user, timestamp);
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("event_type", "create_channel"); event.put("event_id", UUID.randomUUID().toString());
            event.put("timestamp", timestamp); event.put("origin_server", serverId);
            event.put("user", user); event.put("channel", channel);
            publishReplication(pub, event);
            return response(op, requestId, "ok", Map.of("channel", channel, "message", "canal criado"), null);
        }
        return response(op, requestId, "error", null, "operacao invalida");
    }
}
