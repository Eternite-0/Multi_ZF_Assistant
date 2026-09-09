# 正方教务同步 Java 服务

面向竞赛平台后端的 Spring Boot 3 / Java 17 服务。它将学校的 WebVPN 与正方教务会话保留在内存中，Java 主后端可通过 REST 调用同步学生数据。学生账号密码、验证码和 Cookie **不会写入日志、文件或数据库**。

## 构建与启动

```powershell
cd java-sync-service
mvn clean package
java -jar target/jw-sync-service-1.0.0.jar
```

默认监听 `8080`，会话有效期为 20 分钟。生产部署请设置 `PORT`、`JW_SESSION_TTL_MINUTES`，并通过网关为本服务添加竞赛平台的服务端鉴权、TLS、IP 白名单与访问审计。

也可将已构建的 JAR 制作镜像：

```powershell
docker build -t jw-sync-service .
docker run --rm -p 8080:8080 -e JW_SESSION_TTL_MINUTES=20 jw-sync-service
```

## 校外登录（WebVPN + 教务）

1. `POST /api/v1/jw/sessions/webvpn/challenge`

```json
{"baseUrl":"https://csvpn.lingnan.edu.cn/http/77726476706e69737468656265737421fae00f902e3e6f5e7f06c7a99c406d36a1/"}
```

返回 `sessionId` 和 `captchaBase64`。前端只展示验证码，不应持久化它。

2. `POST /api/v1/jw/sessions/{sessionId}/webvpn`

```json
{"username":"VPN账号","password":"VPN密码","captcha":"验证码"}
```

3. `POST /api/v1/jw/sessions/{sessionId}/academic`

```json
{"username":"教务账号","password":"教务密码"}
```

校内登录可直接调用 `POST /api/v1/jw/sessions/campus`，请求包含 `baseUrl`、`username`、`password`。

## 数据接口

所有接口都使用上述 `sessionId`，到期将返回 `401`：

| 接口 | 功能 |
| --- | --- |
| `GET /api/v1/jw/sessions/{id}/info` | 个人信息 |
| `GET /api/v1/jw/sessions/{id}/gpa` | GPA |
| `GET /api/v1/jw/sessions/{id}/grades/{year}/{term}` | 成绩；`term`: 0=全年、1=第一学期、2=第二学期 |
| `GET /api/v1/jw/sessions/{id}/schedule/{year}/{term}` | 课表 |
| `GET /api/v1/jw/sessions/{id}/transcript/{studentId}.pdf` | 成绩总表 PDF |
| `DELETE /api/v1/jw/sessions/{id}` | 立即销毁会话 |

仅应在学生明确授权后读取、同步或保存这些教育数据。成绩单 PDF 由教务系统权限控制，服务不会绕过该权限。
