import org.zeromq.ZMQ;
import org.msgpack.core.MessageBufferPacker;
import org.msgpack.core.MessagePack;
import org.msgpack.core.MessageUnpacker;

import java.util.Random;

public class Client {
    public static void main(String[] args) throws Exception {
        ZMQ.Context context = ZMQ.context(1);
        ZMQ.Socket socket = context.socket(ZMQ.REQ);

        socket.connect("tcp://broker:5555");

        Random rand = new Random();
        String user = "bot_" + (rand.nextInt(9000) + 1000);

        System.out.println("[CLIENT JAVA] Iniciando como " + user);

        while (true) {
            System.out.println("\n--- NOVO CICLO ---");

            // LOGIN
            send(socket, packLogin(user));

            // CREATE CHANNEL
            String channel = "canal_" + (rand.nextInt(300) + 1);
            send(socket, packCreate(user, channel));

            // LIST CHANNELS
            send(socket, packList(user));

            Thread.sleep(1200);
        }
    }

    static void send(ZMQ.Socket socket, byte[] data) throws Exception {
        socket.send(data);

        byte[] reply = socket.recv();
        unpackAndPrint(reply);
    }

    static byte[] packLogin(String user) throws Exception {
        MessageBufferPacker packer = MessagePack.newDefaultBufferPacker();

        packer.packMapHeader(3);
        packer.packString("type");
        packer.packString("login");

        packer.packString("user");
        packer.packString(user);

        packer.packString("timestamp");
        packer.packDouble(System.currentTimeMillis() / 1000.0);

        packer.close();
        return packer.toByteArray();
    }

    static byte[] packCreate(String user, String channel) throws Exception {
        MessageBufferPacker packer = MessagePack.newDefaultBufferPacker();

        packer.packMapHeader(4);
        packer.packString("type");
        packer.packString("create_channel");

        packer.packString("user");
        packer.packString(user);

        packer.packString("channel");
        packer.packString(channel);

        packer.packString("timestamp");
        packer.packDouble(System.currentTimeMillis() / 1000.0);

        packer.close();
        return packer.toByteArray();
    }

    static byte[] packList(String user) throws Exception {
        MessageBufferPacker packer = MessagePack.newDefaultBufferPacker();

        packer.packMapHeader(3);
        packer.packString("type");
        packer.packString("list_channels");

        packer.packString("user");
        packer.packString(user);

        packer.packString("timestamp");
        packer.packDouble(System.currentTimeMillis() / 1000.0);

        packer.close();
        return packer.toByteArray();
    }

    static void unpackAndPrint(byte[] data) throws Exception {
        MessageUnpacker unpacker = MessagePack.newDefaultUnpacker(data);

        int mapSize = unpacker.unpackMapHeader();
        System.out.print("[RESPONSE] { ");

        for (int i = 0; i < mapSize; i++) {
            String key = unpacker.unpackString();
            System.out.print(key + ": ");

            ValueType type = unpacker.getNextFormat().getValueType();

            if (type == ValueType.STRING) {
                System.out.print(unpacker.unpackString());
            }
            else if (type == ValueType.FLOAT) {
                System.out.print(unpacker.unpackDouble());
            }
            else if (type == ValueType.INTEGER) {
                System.out.print(unpacker.unpackLong());
            }
            else if (type == ValueType.ARRAY) {
                int size = unpacker.unpackArrayHeader();
                System.out.print("[ ");

                for (int j = 0; j < size; j++) {
                    System.out.print(unpacker.unpackString() + " ");
                }

                System.out.print("]");
            }
            else {
                unpacker.skipValue();
                System.out.print("?");
            }

            System.out.print(", ");
        }

        System.out.println("}");
    }
}