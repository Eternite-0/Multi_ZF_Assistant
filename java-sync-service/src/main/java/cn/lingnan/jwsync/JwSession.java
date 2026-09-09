package cn.lingnan.jwsync;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.math.BigInteger;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.SecureRandom;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAPublicKeySpec;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.springframework.http.HttpStatus;

/** 一个学生的一次短时教务会话；仅在内存中保存 Cookie 和验证码挑战。 */
public final class JwSession {
    public static final String DEFAULT_WEBVPN_BASE = "https://csvpn.lingnan.edu.cn/http/"
            + "77726476706e69737468656265737421fae00f902e3e6f5e7f06c7a99c406d36a1/";
    private static final String WEBVPN_HOST = "csvpn.lingnan.edu.cn";
    private static final String AUTH_PATH = "/https/77726476706e69737468656265737421f1e2559434357a467b1ac7a0915b243badf0ae285e0ed5da36/authserver";
    private static final String WEBVPN_SERVICE = "https://csvpn.lingnan.edu.cn/login?cas_login=true";
    private static final String AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678";
    private static final Pattern NUMBER = Pattern.compile("\\d+");
    private static final ObjectMapper JSON = new ObjectMapper();

    private final String baseUrl;
    private final HttpClient http;
    private final Duration timeout = Duration.ofSeconds(20);
    private Challenge challenge;
    private boolean webvpnAuthenticated;
    private boolean academicAuthenticated;

    public JwSession(String requestedBaseUrl) {
        this.baseUrl = normalizeBaseUrl(requestedBaseUrl);
        this.http = HttpClient.newBuilder().cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .connectTimeout(timeout).followRedirects(HttpClient.Redirect.NORMAL).build();
    }

    public String baseUrl() { return baseUrl; }
    public boolean academicAuthenticated() { return academicAuthenticated; }

    public String beginWebvpn() {
        if (!isWebvpnUrl(baseUrl)) throw new ApiException(HttpStatus.BAD_REQUEST, "当前地址不是受支持的岭南 WebVPN 教务地址");
        String loginUrl = authLoginUrl();
        HttpResponse<String> page = sendText(GET(loginUrl, null));
        ensure2xx(page, "无法打开 WebVPN 登录页");
        Document doc = Jsoup.parse(page.body());
        Element form = doc.selectFirst("#pwdFromId");
        Element salt = doc.selectFirst("#pwdEncryptSalt");
        if (form == null || salt == null || form.attr("action").isBlank()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "WebVPN 登录页面结构已变化");
        }
        Map<String, String> hidden = new LinkedHashMap<>();
        for (Element input : form.select("input[type=hidden][name]")) hidden.put(input.attr("name"), input.val());
        HttpResponse<byte[]> image = sendBytes(GET(resolve(page.uri(), "getCaptcha.htl?" + System.currentTimeMillis()), null));
        ensure2xx(image, "无法获取 WebVPN 验证码");
        this.challenge = new Challenge(resolve(page.uri(), form.attr("action")), hidden, salt.val(), image.body());
        return Base64.getEncoder().encodeToString(image.body());
    }

    public void completeWebvpn(String username, String password, String captcha) {
        if (challenge == null) throw new ApiException(HttpStatus.BAD_REQUEST, "请先获取 WebVPN 验证码");
        Map<String, String> form = new LinkedHashMap<>(challenge.hidden);
        form.put("username", username);
        form.put("password", encryptWebvpnPassword(password, challenge.salt));
        form.put("captcha", captcha == null ? "" : captcha.trim());
        URI uri = URI.create(challenge.postUrl + "?service=" + enc(WEBVPN_SERVICE));
        HttpResponse<String> response = sendText(POST(uri, form, authLoginUrl()));
        challenge = null;
        String text = response.body();
        String error = visibleLoginError(text);
        if (error.contains("验证码") || error.toLowerCase().contains("verification code"))
            throw new ApiException(HttpStatus.UNAUTHORIZED, "WebVPN 验证码错误");
        if (error.contains("用户名") || error.contains("密码"))
            throw new ApiException(HttpStatus.UNAUTHORIZED, "WebVPN 用户名或密码错误");
        if (response.statusCode() >= 400)
            throw new ApiException(HttpStatus.UNAUTHORIZED, "WebVPN 认证被拒绝（HTTP " + response.statusCode() + "）");
        webvpnAuthenticated = true;
        // 与浏览器回跳后的访问顺序一致，激活目标教务系统的会话 Cookie。
        sendText(GET(URI.create(baseUrl), WEBVPN_SERVICE));
        sendText(GET(URI.create(join("xtgl/index_initMenu.html?jsdm=xs&_t=" + System.currentTimeMillis() + "&echarts=1")), baseUrl));
    }

    public void loginAcademic(String username, String password) {
        if (isWebvpnUrl(baseUrl) && !webvpnAuthenticated)
            throw new ApiException(HttpStatus.UNAUTHORIZED, "请先完成 WebVPN 登录");
        String loginUrl = join("xtgl/login_slogin.html");
        HttpResponse<String> page = sendText(GET(URI.create(loginUrl), loginUrl));
        ensure2xx(page, "无法打开教务系统登录页");
        Document doc = Jsoup.parse(page.body());
        String csrf = value(doc, "#csrftoken");
        JsonNode key = json(GET(URI.create(join("xtgl/login_getPublicKey.html")), loginUrl));
        if (csrf == null || key.path("modulus").isMissingNode() || key.path("exponent").isMissingNode())
            throw new ApiException(HttpStatus.BAD_GATEWAY, "教务登录页面结构已变化");
        Map<String, String> form = Map.of("csrftoken", csrf, "yhm", username,
                "mm", encryptAcademicPassword(password, key.path("modulus").asText(), key.path("exponent").asText()));
        HttpResponse<String> login = sendText(POST(URI.create(loginUrl), form, loginUrl));
        ensure2xx(login, "教务系统登录失败");
        String tip = Jsoup.parse(login.body()).select("p#tips").text();
        if (!tip.isBlank()) throw new ApiException(HttpStatus.UNAUTHORIZED, tip);
        academicAuthenticated = true;
    }

    public Map<String, Object> info() {
        JsonNode data;
        try { data = json(GET(URI.create(join("xsxxxggl/xsxxwh_cxCkDgxsxx.html?gnmkdm=N100801")), join("xtgl/index_initMenu.html"))); }
        catch (ApiException ex) { return parseInfoHtml(); }
        if (!data.isObject()) return parseInfoHtml();
        return mapOf("sid", data.path("xh").asText(null), "name", data.path("xm").asText(null),
                "collegeName", text(data, "zsjg_id", "jg_id"), "majorName", text(data, "zszyh_id", "zyh_id"),
                "className", text(data, "bh_id", "xjztdm"), "status", data.path("xjztdm").asText(null),
                "phoneNumber", data.path("sjhm").asText(null), "email", data.path("dzyx").asText(null));
    }

    public Map<String, Object> grades(int year, int term) {
        Map<String, String> form = queryForm(year, term);
        JsonNode data = json(POST(URI.create(join("cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005")), form, join("cjcx/")));
        List<Map<String, Object>> courses = new ArrayList<>();
        for (JsonNode row : data.path("items")) courses.add(mapOf("courseId", row.path("kch_id").asText(null),
                "title", row.path("kcmc").asText(null), "teacher", row.path("jsxm").asText(null), "className", row.path("jxbmc").asText(null),
                "credit", decimal(row.path("xf").asText()), "category", row.path("kclbmc").asText(null), "nature", row.path("kcxzmc").asText(null),
                "grade", numberOrText(row.path("cj").asText()), "gradePoint", decimal(row.path("jd").asText()), "gradeNature", row.path("ksxz").asText(null)));
        return mapOf("sid", first(data, "xh"), "name", first(data, "xm"), "year", year, "term", term, "count", courses.size(), "courses", courses);
    }

    public Map<String, Object> schedule(int year, int term) {
        Map<String, String> form = Map.of("xnm", String.valueOf(year), "xqm", String.valueOf(termCode(term)));
        JsonNode data = json(POST(URI.create(join("kbcx/xskbcx_cxXsKb.html?gnmkdm=N2151")), form, join("kbcx/")));
        List<Map<String, Object>> courses = new ArrayList<>();
        for (JsonNode row : data.path("kbList")) courses.add(mapOf("courseId", row.path("kch_id").asText(null), "title", row.path("kcmc").asText(null),
                "teacher", row.path("xm").asText(null), "className", row.path("jxbmc").asText(null), "weekday", numberOrText(row.path("xqj").asText()),
                "sessions", row.path("jc").asText(null), "weeks", row.path("zcd").asText(null), "place", row.path("cdmc").asText(null), "campus", row.path("xqmc").asText(null)));
        return mapOf("sid", data.path("xsxx").path("XH").asText(null), "name", data.path("xsxx").path("XM").asText(null), "year", year, "term", term, "count", courses.size(), "courses", courses);
    }

    public Map<String, Object> gpa() {
        HttpResponse<String> response = sendText(GET(URI.create(join("xsxy/xsxyqk_cxXsxyqkIndex.html?gnmkdm=N105515&layout=default")), join("xtgl/index_initMenu.html")));
        ensureAcademic(response);
        String content = Jsoup.parse(response.body()).text().replaceAll("\\s", "");
        Matcher matcher = Pattern.compile("平均学分绩点\\(GPA\\):([0-9.]+)").matcher(content);
        if (!matcher.find()) throw new ApiException(HttpStatus.BAD_GATEWAY, "无法从教务页面解析 GPA");
        return mapOf("gpa", new BigDecimalSafe(matcher.group(1)).value());
    }

    public byte[] transcriptPdf(String studentId) {
        String ref = join("bysxxcx/xscjzbdy_cxXscjzbdyIndex.html");
        HttpResponse<String> view = sendText(POST(URI.create(join("bysxxcx/xscjzbdy_dyXscjzbdyView.html?gnmkdm=N558020&dyly=dy")), Map.of(), ref));
        ensureAcademic(view);
        Element option = Jsoup.parse(view.body()).selectFirst("#gsdygx option");
        if (option == null) throw new ApiException(HttpStatus.BAD_GATEWAY, "无法获取成绩单打印格式");
        Map<String, String> form = transcriptForm(studentId, option.val());
        HttpResponse<String> count = sendText(POST(URI.create(join("bysxxcx/xscjzbdy_cxXsCount.html")), form, ref));
        if (!count.body().contains("可打印")) throw new ApiException(HttpStatus.BAD_GATEWAY, "教务系统不允许打印成绩单");
        HttpResponse<String> file = sendText(POST(URI.create(join("bysxxcx/xscjzbdy_dyList.html")), form, ref));
        if (!file.body().contains("成功")) throw new ApiException(HttpStatus.BAD_GATEWAY, "成绩单生成失败");
        String path = file.body().trim().split("#")[0].replace("\"", "").replace("\\", "/").trim();
        HttpResponse<byte[]> pdf = sendBytes(GET(URI.create(join(path.replaceFirst("^/", ""))), ref));
        if (!pdf.headers().firstValue("Content-Type").orElse("").toLowerCase().contains("application/pdf"))
            throw new ApiException(HttpStatus.BAD_GATEWAY, "教务系统未返回 PDF 文件");
        return pdf.body();
    }

    private Map<String, Object> parseInfoHtml() {
        HttpResponse<String> response = sendText(GET(URI.create(join("xsxxxggl/xsgrxxwh_cxXsgrxx.html?gnmkdm=N100801")), join("xtgl/index_initMenu.html")));
        ensureAcademic(response);
        Document doc = Jsoup.parse(response.body()); Map<String, String> fields = new LinkedHashMap<>();
        for (Element group : doc.select("div.form-group")) fields.put(group.select("label").text(), group.select("p.form-control-static").text());
        if (!fields.containsKey("学号：")) throw new ApiException(HttpStatus.BAD_GATEWAY, "无法解析个人信息页面");
        return mapOf("sid", fields.get("学号："), "name", fields.get("姓名："), "collegeName", fields.get("学院名称："),
                "majorName", fields.get("专业名称："), "className", fields.get("班级名称："), "phoneNumber", fields.get("手机号码："), "email", fields.get("电子邮箱："));
    }

    private JsonNode json(HttpRequest request) { try { HttpResponse<String> r = sendText(request); ensureAcademic(r); return JSON.readTree(r.body()); } catch (IOException e) { throw new ApiException(HttpStatus.BAD_GATEWAY, "教务系统返回了无效 JSON"); } }
    private HttpRequest GET(String url, String referer) { return GET(URI.create(url), referer); }
    private HttpRequest GET(URI uri, String referer) { HttpRequest.Builder b = request(uri).GET(); if (referer != null) b.header("Referer", referer); return b.build(); }
    private HttpRequest POST(URI uri, Map<String, String> form, String referer) { return request(uri).header("Referer", referer).header("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8").POST(HttpRequest.BodyPublishers.ofString(formEncode(form))).build(); }
    private HttpRequest.Builder request(URI uri) { return HttpRequest.newBuilder(uri).timeout(timeout).header("User-Agent", "Mozilla/5.0").header("Accept-Language", "zh-CN,zh;q=0.9"); }
    private HttpResponse<String> sendText(HttpRequest request) { try { return http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)); } catch (Exception e) { throw new ApiException(HttpStatus.BAD_GATEWAY, "无法连接教务系统"); } }
    private HttpResponse<byte[]> sendBytes(HttpRequest request) { try { return http.send(request, HttpResponse.BodyHandlers.ofByteArray()); } catch (Exception e) { throw new ApiException(HttpStatus.BAD_GATEWAY, "无法连接教务系统"); } }
    private void ensure2xx(HttpResponse<?> response, String message) { if (response.statusCode() < 200 || response.statusCode() >= 300) throw new ApiException(HttpStatus.BAD_GATEWAY, message + "（HTTP " + response.statusCode() + "）"); }
    private void ensureAcademic(HttpResponse<String> r) { ensure2xx(r, "教务系统请求失败"); String t = r.body(); if (r.uri().getPath().contains("login_slogin") || (t.contains("用户登录") && t.contains("csrftoken"))) { academicAuthenticated = false; throw new ApiException(HttpStatus.UNAUTHORIZED, "教务系统会话已失效，请重新登录"); } }
    private String join(String path) { return baseUrl + path; }
    private String authLoginUrl() { return "https://" + WEBVPN_HOST + AUTH_PATH + "/login?service=" + enc(WEBVPN_SERVICE); }
    private static URI resolve(URI base, String path) { return base.resolve(path); }
    private static boolean isWebvpnUrl(String url) { return URI.create(url).getHost().equalsIgnoreCase(WEBVPN_HOST) && URI.create(url).getPath().contains("/http/"); }
    private static String normalizeBaseUrl(String value) { String url = value == null || value.isBlank() ? DEFAULT_WEBVPN_BASE : value.trim(); return url.endsWith("/") ? url : url + "/"; }
    private static String value(Document d, String selector) { Element e = d.selectFirst(selector); return e == null ? null : e.val(); }
    private static String enc(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8); }
    private static String formEncode(Map<String, String> map) { return map.entrySet().stream().map(e -> enc(e.getKey()) + "=" + enc(e.getValue())).reduce((a,b) -> a + "&" + b).orElse(""); }
    private static String visibleLoginError(String html) { Document d = Jsoup.parse(html); return d.select("#showErrorTip,.form-error,.item-error-tip").text(); }
    private static String encryptWebvpnPassword(String password, String salt) {
        try { byte[] iv = random(16).getBytes(StandardCharsets.UTF_8); Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding"); cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(salt.getBytes(StandardCharsets.UTF_8), "AES"), new IvParameterSpec(iv)); return Base64.getEncoder().encodeToString(cipher.doFinal((random(64) + password).getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new ApiException(HttpStatus.BAD_GATEWAY, "WebVPN 密码加密失败"); }
    }
    private static String encryptAcademicPassword(String password, String modulus, String exponent) {
        try { BigInteger n = new BigInteger(1, Base64.getDecoder().decode(modulus)); BigInteger e = new BigInteger(1, Base64.getDecoder().decode(exponent)); RSAPublicKey key = (RSAPublicKey) KeyFactory.getInstance("RSA").generatePublic(new RSAPublicKeySpec(n, e)); Cipher cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding"); cipher.init(Cipher.ENCRYPT_MODE, key); return Base64.getEncoder().encodeToString(cipher.doFinal(password.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception ex) { throw new ApiException(HttpStatus.BAD_GATEWAY, "教务系统密码加密失败"); }
    }
    private static String random(int length) { SecureRandom r = new SecureRandom(); StringBuilder s = new StringBuilder(length); for (int i=0;i<length;i++) s.append(AES_CHARS.charAt(r.nextInt(AES_CHARS.length()))); return s.toString(); }
    private static int termCode(int term) { return term == 0 ? 0 : term * term * 3; }
    private static Map<String, String> queryForm(int year, int term) { Map<String,String> m = new LinkedHashMap<>(); m.put("xnm", String.valueOf(year)); m.put("xqm", term == 0 ? "" : String.valueOf(termCode(term))); m.put("_search","false"); m.put("nd",String.valueOf(System.currentTimeMillis())); m.put("queryModel.showCount","100"); m.put("queryModel.currentPage","1"); m.put("queryModel.sortName",""); m.put("queryModel.sortOrder","asc"); m.put("time","0"); return m; }
    private static Map<String, String> transcriptForm(String studentId, String format) { Map<String,String> f = new LinkedHashMap<>(); f.put("gsdygx",format); f.put("ids",studentId); f.put("wjlx","pdf"); for (String k : List.of("jg_id","njdm_id","zyh_id","bh_id","xh","bmlbdm","sfby_dm","sfzx","shzt","xwshzt","dyrq","bdykc","btmc","bwnr","dyfsdkc","zdyjgcj","dyzgcj","bkalsftj","cxalsftj","bdycxbkcj","bxsbylwtm","xwrdkcxtj","bkcxbj","sfdysljcj","sfdylnpjxfjd","sfxsfx","sfgz","kcxzjcbj","sfdypjf","sfdypjjd","BdykcmcDms","startxq","endxq","sfqshr","sfazjhnkctjxs","sfzxszkcj","bdykcxzDms","cytjkcxzDms","cytjkclbDms","cytjkcgsDms","bjgbdykcxzDms","bjgbdyxxkcxzDms","djksxmDms","cjbzmcDms","zdyfsxmDms","cjdySzxs")) f.put(k, ""); return f; }
    private static String text(JsonNode n, String... names) { for (String name : names) if (!n.path(name).isMissingNode() && !n.path(name).asText().isBlank()) return n.path(name).asText(); return null; }
    private static String first(JsonNode root, String name) { return root.path("items").isArray() && root.path("items").size()>0 ? root.path("items").get(0).path(name).asText(null) : null; }
    private static Object numberOrText(String value) { try { return Integer.valueOf(value); } catch (Exception e) { return value == null || value.isBlank() ? null : value; } }
    private static Object decimal(String value) { try { return new BigDecimalSafe(value).value(); } catch (Exception e) { return null; } }
    private static Map<String,Object> mapOf(Object... values) { Map<String,Object> map = new LinkedHashMap<>(); for (int i=0;i<values.length;i+=2) if (values[i+1] != null) map.put((String)values[i],values[i+1]); return map; }
    private record Challenge(URI postUrl, Map<String,String> hidden, String salt, byte[] image) { }
    private record BigDecimalSafe(String raw) { java.math.BigDecimal value() { return new java.math.BigDecimal(raw); } }
}
