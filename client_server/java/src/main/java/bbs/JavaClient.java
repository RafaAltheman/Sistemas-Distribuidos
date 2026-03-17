package bbs;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import java.util.*;

public class JavaClient {
    private final String user = System.getenv().getOrDefault("CLIENT_USER", "bot_java");
    private final long startDelay = Long.parseLong(System.getenv().getOrDefault("START_DELAY", "6"));
    private final String channel = System.getenv().getOrDefault("CHANNEL_TO_CREATE", "java_room");

    public void run() throws Exception {
        System.out.println("[CLIENTE " + user + "] aguardando " + startDelay + "s para iniciar");
        Util.sleepMillis(startDelay * 1000L);
        try (ZContext context = new ZContext()) {
            ZMQ.Socket req = context.createSocket(SocketType.REQ);
            req.connect("tcp://broker:5555");
            send(req, "login", new LinkedHashMap<>());
            Util.sleepMillis(1000);
            Map<String, Object> list = send(req, "list_channels", new LinkedHashMap<>());
            Util.sleepMillis(1000);
            Object channelsObj = ((Map<String, Object>) list.getOrDefault("data", new LinkedHashMap<>())).get("channels");
            boolean exists = false;
            if (channelsObj instanceof List<?> channels) {
                for (Object c : channels) if (channel.equals(String.valueOf(c))) exists = true;
            }
            if (!exists) {
                send(req, "create_channel", Map.of("channel", channel));
                Util.sleepMillis(1000);
            }
            send(req, "list_channels", new LinkedHashMap<>());
            System.out.println("[CLIENTE " + user + "] fluxo concluído com sucesso");
        }
    }

    private Map<String, Object> send(ZMQ.Socket socket, String operation, Map<String, Object> data) throws Exception {
        Map<String, Object> req = new LinkedHashMap<>();
        req.put("type", "request"); req.put("operation", operation); req.put("request_id", UUID.randomUUID().toString());
        req.put("timestamp", Util.isoNow()); req.put("user", user); req.put("data", data);
        System.out.println("[CLIENTE " + user + "] ENVIANDO: " + req);
        socket.send(Util.packMap(req), 0);
        Map<String, Object> resp = Util.unpackMap(socket.recv(0));
        System.out.println("[CLIENTE " + user + "] RECEBEU: " + resp);
        return resp;
    }
}
