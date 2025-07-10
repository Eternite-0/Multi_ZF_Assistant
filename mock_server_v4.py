# mock_server.py (V10 - 最终完整版，包含所有隐藏字段和智能响应)
import http.server
import socketserver
import json
import time
import base64
from urllib.parse import parse_qs

# 确保 pycryptodome 库已安装 (pip install pycryptodome)
try:
    from Crypto.PublicKey import RSA
    from Crypto.Util.number import long_to_bytes
except ImportError:
    print("错误：未找到 pycryptodome 库。")
    print("请先通过命令 'pip install pycryptodome' 进行安装。")
    exit()

PORT = 9999

# 1. 动态生成有效的RSA密钥对，并进行正确的Base64编码
key_pair = RSA.generate(1024)
modulus_b64 = base64.b64encode(long_to_bytes(key_pair.n)).decode('utf-8')
exponent_b64 = base64.b64encode(long_to_bytes(key_pair.e)).decode('utf-8')
mock_public_key_final = {"modulus": modulus_b64, "exponent": exponent_b64}

# 2. 模拟的课程数据库，包含不同类型的课程
mock_full_course_db = [
    {"kcmc": "【专业选修】计算机网络", "kch_id": "COURSE_ID_001", "jxb_ids": "jxb_id_01", "jsxx": "张三", "kklxdm": "10", "xkkz_id": "xyz-123", "remind_count": 2, "kch": "C001"},
    {"kcmc": "【专业选修】操作系统", "kch_id": "COURSE_ID_002", "jxb_ids": "jxb_id_02", "jsxx": "李四", "kklxdm": "10", "xkkz_id": "xyz-123", "remind_count": 1, "kch": "C002"},
    {"kcmc": "【公共选修】艺术鉴赏", "kch_id": "COURSE_ID_101", "jxb_ids": "jxb_id_101", "jsxx": "王五", "kklxdm": "20", "xkkz_id": "xyz-123", "remind_count": 5, "kch": "G101"},
    {"kcmc": "【公共选修】音乐与人生", "kch_id": "COURSE_ID_102", "jxb_ids": "jxb_id_102", "jsxx": "赵六", "kklxdm": "20", "xkkz_id": "xyz-123", "remind_count": 0, "kch": "G102"},
]

# 3. 【核心】包含所有必需字段的、完整的隐藏域字典
mock_hidden_inputs = {
    # 在调试中发现的关键字段
    "firstKklxdm": "10",
    "firstXkkzId": "xyz-123",

    # 从您zfn_api.py中推断出的所有其他字段
    "rwlx": "1", "xklc": "1", "xkly": "1", "bklx_id": "0", "sfkkjyxdxnxq": "0",
    "kzkcgs": "0", "xqh_id": "2023-2024", "jg_id_1": "08", "zyh_id": "080901",
    "zyfx_id": "null", "txbsfrl": "0", "njdm_id": "2021", "bh_id": "21080901",
    "xbm": "1", "xslbdm": "11", "mzm": "01", "xz": "4", "ccdm": "3", "xsbj": "0",
    "sfkknj": "0", "gnjkxdnj": "0", "sfkkzy": "0", "kzybkxy": "0", "sfznkx": "0",
    "zdkxms": "0", "sfkxq": "0", "sfkcfx": "0", "bbhzxjxb": "0", "kkbk": "0",
    "kkbkdj": "", "xkxnm": "2024", "xkxqm": "3", "xkxskcgskg": "0",
    "njdm_id_xs": "2021", "zyh_id_xs": "080901", "rlkz": "0", "cdrlkz": "0",
    "rlzlkz": "1", "jxbzcxskg": "0",
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
        content_length = int(self.headers.get('Content-Length', 0))
        post_data_raw = self.rfile.read(content_length)
        post_params = parse_qs(post_data_raw.decode('utf-8'))

        if "login" in self.path.lower():
            print("✅ [POST] 识别为提交登录信息，返回成功...")
            self._send_response(200, '{"result":"success", "msg":"登录成功(模拟)！"}')
            return

        if "zzxkyzbpartdisplay" in self.path.lower():
            print("✅ [POST] 识别为获取课程列表请求...")
            requested_kklxdm = post_params.get('kklxdm', [None])[0]
            if requested_kklxdm:
                print(f"   - 客户端请求的课程板块代码 (kklxdm) 是: {requested_kklxdm}")
                filtered_courses = [c for c in mock_full_course_db if c['kklxdm'] == requested_kklxdm]
                print(f"   - 已筛选出 {len(filtered_courses)} 门匹配的课程。")
            else:
                print("   - 警告：客户端请求中未找到kklxdm，将返回所有课程。")
                filtered_courses = mock_full_course_db
            
            response_data = {"rwRxkZlList": filtered_courses}
            self._send_response(200, json.dumps(response_data, ensure_ascii=False))
            return
            
        self._send_response(404, '{"error": "POST endpoint not found"}')

    def do_GET(self):
        self._log_request("GET")
        if "getpublickey" in self.path.lower():
            print("✅ [GET] 识别为获取公钥请求...")
            self._send_response(200, json.dumps(mock_public_key_final))
            return
        if "login" in self.path.lower():
            print("✅ [GET] 识别为访问登录页面请求...")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "JSESSIONID=mock_session_12345; Path=/")
            self.end_headers()
            self.wfile.write("<html><body><h1>模拟登录页面</h1></body></html>".encode("utf-8"))
            return
        # 通用处理，捕获所有访问选课相关页面的请求
        if "zzxkyz" in self.path.lower():
            print("✅ [GET] 识别为获取隐藏参数页面请求，返回包含【所有】字段的完整HTML...")
            inputs_html = "".join([f'<input type="hidden" name="{name}" value="{value}"/>\n' for name, value in mock_hidden_inputs.items()])
            self._send_response(200, f"<html><body><form>{inputs_html}</form></body></html>", "text/html")
            return
        self._send_response(404, '{"error": "GET endpoint not found"}')


Handler = MockAPIHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("\n=======================================================")
    print(f"✅ 模拟教务系统服务器已启动 (V10 - 最终完整版)")
    print(f"   - 密钥已动态生成并正确编码 (Base64)")
    print(f"   - API响应结构已修正")
    print(f"   - 隐藏字段已【全部】补全")
    print(f"   - 课程列表将根据请求的板块代码动态筛选")
    print("\n   请将你的程序教务系统地址设置为: http://localhost:8080")
    print(f"   服务器正在 http://localhost:{PORT} 上监听请求...")
    print("=======================================================\n")
    httpd.serve_forever()