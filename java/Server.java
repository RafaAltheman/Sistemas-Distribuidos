import org.zeromq.ZMQ;
import org.msgpack.core.*;

import java.io.*;
import java.nio.file.*;
import java.util.*;

public class Server {

    static Set<String> channels = new HashSet<>();
    static List<Map<String, Object>> logins = new ArrayList<>();

    static final String DATA_DIR = "data";
    static final String CHANNELS_FILE = DATA_DIR + "/channels.json";
    static final String LOGINS_FILE = DATA_DIR + "/logins.json";

    public static void main(String[] args) throws Exception {

        new File(DATA_DIR).mkdirs();

        loadData();

        ZMQ.Context context = ZMQ.context(1);
        ZMQ.Socket socket = context.socket(ZMQ.REP);

        socket.connect("tcp://broker:5556");

        System.out.println("[SERVER JAVA] Iniciado");

        while (true) {
            byte[] request = socket.recv();

            MessageUnpacker unpacker = MessagePack.newDefaultUnpacker(request);

            int mapSize = unpacker.unpackMapHeader();
            Map<String, Object> msg = new HashMap<>();

            for (int i = 0; i < mapSize; i++) {
                String key = unpacker.unpackString();

                switch (unpacker.getNextFormat().getValueType()) {
                    case STRING:
                        msg.put(key, unpacker.unpackString());
                        break;
                    case FLOAT:
                        msg.put(key, unpacker.unpackDouble());
                        break;
                    default:
                        unpacker.skipValue();
                }
            }

            String type = (String) msg.get("type");

            MessageBufferPacker packer = MessagePack.newDefaultBufferPacker();

            if ("login".equals(type)) {
                String user = (String) msg.get("user");

                Map<String, Object> login = new HashMap<>();
                login.put("user", user);
                login.put("timestamp", msg.get("timestamp"));

                logins.add(login);
                saveLogins();

                System.out.println("[LOGIN] " + user);

                packer.packMapHeader(3);
                packer.packString("status");
                packer.packString("ok");

                packer.packString("message");
                packer.packString("login realizado (" + user + ")");

                packer.packString("timestamp");
                packer.packDouble(now());
            }

            else if ("create_channel".equals(type)) {
                String ch = (String) msg.get("channel");

                if (channels.contains(ch)) {
                    System.out.println("[CREATE] exists: " + ch);

                    packer.packMapHeader(2);
                    packer.packString("status");
                    packer.packString("error");
                } else {
                    channels.add(ch);
                    saveChannels();

                    System.out.println("[CREATE] ok: " + ch);

                    packer.packMapHeader(2);
                    packer.packString("status");
                    packer.packString("ok");
                }
            }

            else if ("list_channels".equals(type)) {
                System.out.println("[LIST] total=" + channels.size());

                packer.packMapHeader(2);
                packer.packString("status");
                packer.packString("ok");

                packer.packString("channels");
                packer.packArrayHeader(channels.size());

                for (String ch : channels) {
                    packer.packString(ch);
                }
            }

            packer.close();
            socket.send(packer.toByteArray());
        }
    }

    static void loadData() {
        try {
            if (Files.exists(Paths.get(CHANNELS_FILE))) {
                String content = Files.readString(Paths.get(CHANNELS_FILE));
                if (!content.isEmpty()) {
                    String[] arr = content.replace("[", "").replace("]", "").replace("\"", "").split(",");
                    for (String c : arr) {
                        if (!c.trim().isEmpty())
                            channels.add(c.trim());
                    }
                }
            }

            if (Files.exists(Paths.get(LOGINS_FILE))) {
                String content = Files.readString(Paths.get(LOGINS_FILE));
            }

        } catch (Exception e) {
            System.out.println("Erro ao carregar dados");
        }
    }

    static void saveChannels() {
        try (FileWriter fw = new FileWriter(CHANNELS_FILE)) {
            fw.write("[");
            int i = 0;
            for (String ch : channels) {
                fw.write("\"" + ch + "\"");
                if (i++ < channels.size() - 1) fw.write(",");
            }
            fw.write("]");
        } catch (Exception e) {
            System.out.println("Erro ao salvar canais");
        }
    }

    static void saveLogins() {
        try (FileWriter fw = new FileWriter(LOGINS_FILE)) {
            fw.write("[\n");
            for (int i = 0; i < logins.size(); i++) {
                Map<String, Object> l = logins.get(i);
                fw.write(String.format(
                    "{\"user\":\"%s\",\"timestamp\":%s}",
                    l.get("user"), l.get("timestamp")
                ));
                if (i < logins.size() - 1) fw.write(",\n");
            }
            fw.write("\n]");
        } catch (Exception e) {
            System.out.println("Erro ao salvar logins");
        }
    }

    static double now() {
        return System.currentTimeMillis() / 1000.0;
    }
}