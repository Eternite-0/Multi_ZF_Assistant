package cn.lingnan.jwsync;

import java.util.Base64;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Java 后端调用的教务同步入口。sessionId 是短时不透明令牌，不能写入日志或前端持久化存储。
 */
@RestController
@RequestMapping("/api/v1/jw")
public class JwController {
    private final SessionStore sessions;
    public JwController(SessionStore sessions) { this.sessions = sessions; }

    @PostMapping("/sessions/webvpn/challenge")
    public Map<String, Object> webvpnChallenge(@RequestBody BaseUrlRequest request) {
        JwSession session = new JwSession(request.baseUrl());
        String id = sessions.add(session);
        return Map.of("sessionId", id, "captchaBase64", session.beginWebvpn(), "captchaEncoding", "base64");
    }

    @PostMapping("/sessions/{id}/webvpn")
    public Map<String, Object> webvpnLogin(@PathVariable String id, @RequestBody WebvpnLoginRequest request) {
        JwSession session = sessions.get(id);
        session.completeWebvpn(request.username(), request.password(), request.captcha());
        return Map.of("sessionId", id, "webvpnAuthenticated", true, "nextStep", "调用 academic 登录教务系统");
    }

    @PostMapping("/sessions/campus")
    public Map<String, Object> campusLogin(@RequestBody AcademicLoginRequest request) {
        JwSession session = new JwSession(request.baseUrl());
        session.loginAcademic(request.username(), request.password());
        return Map.of("sessionId", sessions.add(session), "academicAuthenticated", true);
    }

    @PostMapping("/sessions/{id}/academic")
    public Map<String, Object> academicLogin(@PathVariable String id, @RequestBody AcademicLoginRequest request) {
        JwSession session = sessions.get(id);
        session.loginAcademic(request.username(), request.password());
        return Map.of("sessionId", id, "academicAuthenticated", true);
    }

    @GetMapping("/sessions/{id}/info")
    public Map<String, Object> info(@PathVariable String id) { return sessions.get(id).info(); }
    @GetMapping("/sessions/{id}/gpa")
    public Map<String, Object> gpa(@PathVariable String id) { return sessions.get(id).gpa(); }
    @GetMapping("/sessions/{id}/grades/{year}/{term}")
    public Map<String, Object> grades(@PathVariable String id, @PathVariable int year, @PathVariable int term) { return sessions.get(id).grades(year, term); }
    @GetMapping("/sessions/{id}/schedule/{year}/{term}")
    public Map<String, Object> schedule(@PathVariable String id, @PathVariable int year, @PathVariable int term) { return sessions.get(id).schedule(year, term); }

    @GetMapping("/sessions/{id}/transcript/{studentId}.pdf")
    public ResponseEntity<byte[]> transcript(@PathVariable String id, @PathVariable String studentId) {
        byte[] pdf = sessions.get(id).transcriptPdf(studentId);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=transcript.pdf").body(pdf);
    }

    @DeleteMapping("/sessions/{id}")
    public ResponseEntity<Void> logout(@PathVariable String id) { sessions.remove(id); return ResponseEntity.noContent().build(); }

    public record BaseUrlRequest(String baseUrl) { }
    public record WebvpnLoginRequest(String username, String password, String captcha) { }
    public record AcademicLoginRequest(String baseUrl, String username, String password) { }
}
