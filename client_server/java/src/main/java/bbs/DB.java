package bbs;

import java.sql.*;
import java.util.ArrayList;
import java.util.List;

public class DB {
    private final Connection conn;

    public DB(String path) throws Exception {
        Class.forName("org.sqlite.JDBC");
        this.conn = DriverManager.getConnection("jdbc:sqlite:" + path);
        try (Statement st = conn.createStatement()) {
            st.execute("PRAGMA journal_mode=WAL");
            st.execute("CREATE TABLE IF NOT EXISTS logins (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, ts TEXT)");
            st.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_by TEXT, ts TEXT)");
            st.execute("CREATE TABLE IF NOT EXISTS replication_events (event_id TEXT PRIMARY KEY, payload BLOB)");
        }
    }

    public synchronized void addLogin(String user, String ts) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement("INSERT INTO logins(user, ts) VALUES (?, ?)")) {
            ps.setString(1, user); ps.setString(2, ts); ps.executeUpdate();
        }
    }

    public synchronized boolean channelExists(String name) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement("SELECT 1 FROM channels WHERE name = ?")) {
            ps.setString(1, name);
            try (ResultSet rs = ps.executeQuery()) { return rs.next(); }
        }
    }

    public synchronized void addChannel(String name, String user, String ts) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement("INSERT OR IGNORE INTO channels(name, created_by, ts) VALUES (?, ?, ?)")) {
            ps.setString(1, name); ps.setString(2, user); ps.setString(3, ts); ps.executeUpdate();
        }
    }

    public synchronized List<String> listChannels() throws SQLException {
        List<String> result = new ArrayList<>();
        try (PreparedStatement ps = conn.prepareStatement("SELECT name FROM channels ORDER BY name"); ResultSet rs = ps.executeQuery()) {
            while (rs.next()) { String name = rs.getString(1); if (name != null && !name.isBlank()) result.add(name); }
        }
        return result;
    }

    public synchronized boolean seenEvent(String eventId) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement("SELECT 1 FROM replication_events WHERE event_id = ?")) {
            ps.setString(1, eventId);
            try (ResultSet rs = ps.executeQuery()) { return rs.next(); }
        }
    }

    public synchronized void saveEvent(String eventId, byte[] payload) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement("INSERT OR IGNORE INTO replication_events(event_id, payload) VALUES (?, ?)")) {
            ps.setString(1, eventId); ps.setBytes(2, payload); ps.executeUpdate();
        }
    }
}
