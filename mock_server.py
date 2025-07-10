# mock_server.py (V4 - 终极版，支持公钥加密流程)
import http.server
import socketserver
import json
import time
from urllib.parse import parse_qs, urlparse

PORT = 9999

# --- 模拟的数据库 (不变) ---
mock_courses_db = {
    "jxb_id_01": { "kcmc": "【模拟】计算机网络", "kch_id": "COURSE_ID_001", "jxb_ids": "jxb_id_01", "jsxx": "张三", "kklxdm": "10", "xkkz_id": "xyz-123", "capacity": 2 },
    "jxb_id_02": { "kcmc": "【模拟】操作系统", "kch_id": "COURSE_ID_002", "jxb_ids": "jxb_id_02", "jsxx": "李四", "kklxdm": "10", "xkkz_id": "xyz-123", "capacity": 1 },
    "jxb_id_03": { "kcmc": "【模拟】数据结构", "kch_id": "COURSE_ID_003", "jxb_ids": "jxb_id_03", "jsxx": "王五", "kklxdm": "10", "xkkz_id": "xyz-123", "capacity": 0 },
    "jxb_id_04": { "kcmc": "【模拟】篮球", "kch_id": "COURSE_ID_004", "jxb_ids": "jxb_id_04", "jsxx": "赵六", "kklxdm": "50", "xkkz_id": "abc-456", "capacity": 5 },
}

mock_hidden_inputs = {
    "rwlx": "1", "xklc": "1", "xkly": "1", "bklx_id": "0", "sfkkjyxdxnxq": "0", "kzkcgs": "0", "xqh_id": "2023-2024",
    "jg_id_1": "08", "zyh_id": "080901", "zyfx_id": "null", "txbsfrl": "0", "njdm_id": "2021", "bh_id": "21080901",
    "xbm": "1", "xslbdm": "11", "mzm": "01", "xz": "4", "ccdm": "3", "xsbj": "0", "sfkknj": "0", "gnjkxdnj": "0",
    "sfkkzy": "0", "kzybkxy": "0", "sfznkx": "0", "zdkxms": "0", "sfkxq": "0", "sfkcfx": "0", "bbhzxjxb": "0",
    "kkbk": "0", "kkbkdj": "", "xkxnm": "2024", "xkxqm": "3", "xkxskcgskg": "0", "njdm_id_xs": "2021",
    "zyh_id_xs": "080901", "rlkz": "0", "cdrlkz": "0", "rlzlkz": "1", "jxbzcxskg": "0",
}

class MockAPIHandler(http.server.SimpleHTTPRequestHandler):
    def _log_request(self, method):
        print(f"\n--- 收到请求 ---\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n方法: {method}\n路径: {self.path}\n-----------------")

    def _send_response(self, status_code, content, content_type="application/json"):
        self.send_response(status_code)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_POST(self):
        self._log_request("POST")
        if "login" in self.path.lower():
            print("✅ [POST] 识别为提交账号密码请求，返回成功...")
            self._send_response(200, '{"result":"success", "msg":"登录成功(模拟)！"}')
            return
        if "zzxkyzbpartdisplay" in self.path.lower():
            print("✅ [POST] 识别为获取课程列表请求...")
            self._send_response(200, json.dumps(list(mock_courses_db.values()), ensure_ascii=False))
            return
        if "elect-check" in self.path.lower():
            print("✅ [POST] 识别为选课请求...")
            # ... (选课逻辑不变) ...
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = parse_qs(post_data.decode('utf-8'))
            jxb_id = params.get("jxb_ids", [None])[0]
            if not jxb_id or jxb_id not in mock_courses_db:
                self._send_response(200, '{"code": -1, "msg": "课程不存在(模拟)"}')
                return
            course = mock_courses_db[jxb_id]
            if course["capacity"] > 0:
                course["capacity"] -= 1
                self._send_response(200, f'{{"code": 1000, "msg": "选课成功！(模拟)"}}')
            else:
                self._send_response(200, '{"code": -1, "msg": "课程容量不足(模拟)"}')
            return
        self._send_response(404, '{"error": "POST endpoint not found"}')

    def do_GET(self):
        self._log_request("GET")

        # --- 【核心修正】新增对获取公钥请求的正确处理 ---
        if "getpublickey" in self.path.lower():
            print("✅ [GET] 识别为获取公钥请求，返回模拟公钥...")
            # 模拟一个真实的公钥响应格式，包含 modulus 和 exponent
            mock_key = {
                "modulus": "009c962b6ca21c33c30291c53e6d859b15c2e171343715a388539198b165500a4025d5d1c435a3b2a54d588960b73c4e833446b412239e5b323b4007b82f1ff5b2c5f59052b6b5952329241575a7f920f2e0c0f991f869a8f278d655ecf473e6b2067137b01b31525a81e344e1d30560938f6575ff5748a1c9359a34a04e4604e4028c31393694f4c4794e5a9733230d4750a9057d235c5c3e624177d853b946894569584852a3928a313b516c141e5a5913f0a5a3a5a9",
                "exponent": "10001"
            }
            self._send_response(200, json.dumps(mock_key))
            return

        if "login" in self.path.lower():
            print("✅ [GET] 识别为访问登录页面请求，返回页面和Cookie...")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "JSESSIONID=mock_session_12345; Path=/")
            self.end_headers()
            self.wfile.write("<html><body><h1>模拟登录页面</h1></body></html>".encode("utf-8"))
            return
        
        if "initmenu" in self.path.lower():
            print("✅ [GET] 识别为获取用户信息请求...")
            self._send_response(200, '<span class="user-info">你好, 模拟用户</span>', "text/html")
            return

        if "zzxkyzxk" in self.path.lower():
            print("✅ [GET] 识别为获取隐藏参数页面请求...")
            inputs_html = "".join([f'<input type="hidden" name="{name}" value="{value}"/>\n' for name, value in mock_hidden_inputs.items()])
            self._send_response(200, f"<html><body><form>{inputs_html}</form></body></html>", "text/html")
            return
            
        self._send_response(404, '{"error": "GET endpoint not found"}')

Handler = MockAPIHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"✅ 模拟教务系统服务器已启动 (V4 - 终极版)")
    print(f"   请将你的程序教务系统地址设置为: http://localhost:{PORT}")
    print(f"   服务器正在 http://localhost:{PORT} 上监听请求...")
    httpd.serve_forever()