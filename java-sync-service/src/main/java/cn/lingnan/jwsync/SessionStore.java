package cn.lingnan.jwsync;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class SessionStore {
    private final ConcurrentHashMap<String, Entry> sessions = new ConcurrentHashMap<>();
    private final Duration ttl;

    public SessionStore(@Value("${jw.session-ttl-minutes:20}") long minutes) {
        this.ttl = Duration.ofMinutes(minutes);
    }
    public String add(JwSession session) {
        cleanup();
        String id = UUID.randomUUID().toString();
        sessions.put(id, new Entry(session, Instant.now().plus(ttl)));
        return id;
    }
    public JwSession get(String id) {
        Entry entry = sessions.get(id);
        if (entry == null || entry.expiresAt.isBefore(Instant.now())) {
            sessions.remove(id);
            throw new ApiException(HttpStatus.UNAUTHORIZED, "会话不存在或已过期，请重新登录");
        }
        return entry.session;
    }
    public void remove(String id) { sessions.remove(id); }
    private void cleanup() { sessions.entrySet().removeIf(e -> e.getValue().expiresAt.isBefore(Instant.now())); }
    private record Entry(JwSession session, Instant expiresAt) { }
}
