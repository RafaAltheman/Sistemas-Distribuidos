package bbs;

import org.msgpack.core.MessageBufferPacker;
import org.msgpack.core.MessagePack;
import org.msgpack.core.MessageUnpacker;
import org.msgpack.value.*;

import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.*;

public class Util {
    public static String isoNow() {
        return OffsetDateTime.now().toString();
    }

    public static byte[] packMap(Map<String, Object> map) throws IOException {
        MessageBufferPacker packer = MessagePack.newDefaultBufferPacker();
        packObject(packer, map);
        packer.close();
        return packer.toByteArray();
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> unpackMap(byte[] data) throws IOException {
        MessageUnpacker unpacker = MessagePack.newDefaultUnpacker(data);
        Value value = unpacker.unpackValue();
        return (Map<String, Object>) toJava(value);
    }

    private static void packObject(MessageBufferPacker p, Object obj) throws IOException {
        if (obj == null) {
            p.packNil();
        } else if (obj instanceof String s) {
            p.packString(s);
        } else if (obj instanceof Integer i) {
            p.packInt(i);
        } else if (obj instanceof Long l) {
            p.packLong(l);
        } else if (obj instanceof Boolean b) {
            p.packBoolean(b);
        } else if (obj instanceof List<?> list) {
            p.packArrayHeader(list.size());
            for (Object item : list) packObject(p, item);
        } else if (obj instanceof Map<?, ?> map) {
            p.packMapHeader(map.size());
            for (Map.Entry<?, ?> e : map.entrySet()) {
                p.packString(String.valueOf(e.getKey()));
                packObject(p, e.getValue());
            }
        } else {
            p.packString(String.valueOf(obj));
        }
    }

    private static Object toJava(Value v) {
        ValueType t = v.getValueType();
        return switch (t) {
            case NIL -> null;
            case BOOLEAN -> v.asBooleanValue().getBoolean();
            case INTEGER -> v.asIntegerValue().toLong();
            case FLOAT -> v.asFloatValue().toDouble();
            case STRING -> v.asStringValue().asString();
            case ARRAY -> {
                List<Object> list = new ArrayList<>();
                for (Value item : v.asArrayValue()) list.add(toJava(item));
                yield list;
            }
            case MAP -> {
                Map<String, Object> map = new LinkedHashMap<>();
                for (Map.Entry<Value, Value> e : v.asMapValue().entrySet()) {
                    map.put(e.getKey().toString().replaceAll("^\"|\"$", ""), toJava(e.getValue()));
                }
                yield map;
            }
            case BINARY -> Base64.getEncoder().encodeToString(v.asBinaryValue().asByteArray());
            case EXTENSION -> v.toString();
        };
    }

    public static void sleepMillis(long ms) {
        try { Thread.sleep(ms); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); }
    }
}
