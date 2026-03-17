package bbs;

public class Main {
    public static void main(String[] args) throws Exception {
        String role = System.getenv().getOrDefault("ROLE", "client");
        if ("server".equalsIgnoreCase(role)) new JavaServer().run();
        else new JavaClient().run();
    }
}
