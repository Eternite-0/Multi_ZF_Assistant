# mock_server.py (V17 - 最终性能优化版)
import http.server
import socketserver
import json
import time
import base64
import os
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
KEY_FILE = "mock_key.json"

# --- V17核心改进1：预生成并保存/加载密钥，避免重复生成 ---
def get_or_create_public_key():
    """如果密钥文件不存在，则创建；否则直接读取。"""
    if not os.path.exists(KEY_FILE):
        print("首次启动，正在生成新的RSA密钥对并保存...")
        key_pair = RSA.generate(1024)
        modulus_b64 = base64.b64encode(long_to_bytes(key_pair.n)).decode('utf-8')
        exponent_b64 = base64.b64encode(long_to_bytes(key_pair.e)).decode('utf-8')
        key_data = {"modulus": modulus_b64, "exponent": exponent_b64}
        with open(KEY_FILE, 'w') as f:
            json.dump(key_data, f)
        print(f"✅ 密钥已成功保存到 {KEY_FILE}，未来启动将提速。")
        return key_data
    else:
        print(f"✅ 从 {KEY_FILE} 文件中快速加载密钥。")
        with open(KEY_FILE, 'r') as f:
            return json.load(f)

mock_public_key_final = get_or_create_public_key()

# --- 其他模拟数据保持不变 ---
mock_full_course_db = {
    # 课程0：党政机关公文写作 (由用户提供的真实数据)
    "0AB870AEB80570D6E06315C6A8C0E9A1": [
        {
            "kcmc": "党政机关公文写作", "kch_id": "0AB870AEB80570D6E06315C6A8C0E9A1", "jxb_id": "real_jxb_001",
            "do_jxb_id": "65ded6b25e3bb189179992dccb85ecdfbc782dfdf05c59d298e9fa2e5bb75eb241fe2948f4d85429e1eb1f19fbcd162e3b437561e9c3afc5ac39aa60526e95231a8ca0a3142d0f66713d1ef744583ac5a8051d9dc1faeac38cc5f194f8b3b24f6c8d3d79786a468ad14313c1bb2e3d7e8f1b4d4a62e07daad127f03706049e24",
            "jsxx": "沈洪涛(副教授)", "kklxdm": "10", "xkkz_id": "470D3AB2FD34328CE06315C6A8C0F51D", "kch": "66172392",
            "xnm": "2025", "xqm": "12", "sksj": "星期二第9-10节{1-8周}", "jxdd": "5A-103社", "xf": "1.0",
            "kcsxmc": "专业选修课", "jxbrl": 120, "yxzrs": 0,
            "cxbj": "0", "fxbj": "0", "jsxm": "沈洪涛",
        }
    ],
    # 课程1：计算机网络 (kch_id: COURSE_ID_001) 有两个教学班
    "COURSE_ID_001": [
        {
            "kcmc": "【专业选修】计算机网络", "kch_id": "COURSE_ID_001", "jxb_id": "jxb_id_01",
            "do_jxb_id": "jxb_id_01", # <--- 补全关键字段
            "jsxx": "张三(教授)", "kklxdm": "10", "xkkz_id": "470D3AB2FD34328CE06315C6A8C0F51D", "kch": "C001",
            "xnm": "2025", "xqm": "12", "sksj": "1-16周 周二第3,4节", "jxdd": "信息楼201", "xf": "3.0",
            "kcsxmc": "专业核心课", "jxbrl": 60, "yxzrs": 42, # <--- 使用正确的容量/已选字段名
            "cxbj": "0", "fxbj": "0", # <--- 重修标记和辅修标记
            "jsxm": "张三",  # <--- 教师姓名（用于返回教学班信息）
        }
    ]
}

# 3. 完整的隐藏域字典 (根据您提供的最新抓包参数同步)
mock_hidden_inputs = {
    "firstKklxdm": "10",
    "firstXkkzId": "470D3AB2FD34328CE06315C6A8C0F51D",
    
    "rwlx": "2", 
    "xklc": "1", 
    "xkly": "0", 
    "bklx_id": "0", 
    "sfkkjyxdxnxq": "0", 
    "kzkcgs": "0", 
    "xqh_id": "1",
    "jg_id": "15", 
    "zyh_id": "1550", 
    "zyfx_id": "wfx", 
    "txbsfrl": "0", 
    "njdm_id": "2025", 
    "bh_id": "2025155048",
    "xbm": "2", 
    "xslbdm": "1", 
    "mzm": "01", 
    "xz": "4", 
    "ccdm": "3", 
    "xsbj": "0", 
    "sfkknj": "0", 
    "gnjkxdnj": "0",
    "sfkkzy": "0", 
    "kzybkxy": "0", 
    "sfznkx": "0", 
    "zdkxms": "0", 
    "sfkxq": "0", 
    "sfkcfx": "0", 
    "bbhzxjxb": "0",
    "kkbk": "0", 
    "kkbkdj": "0", 
    "bklbkcj": "0",
    "xkxnm": "2025", 
    "xkxqm": "12", 
    "xkxskcgskg": "1", 
    "rlkz": "0", 
    "cdrlkz": "0", 
    "rlzlkz": "1", 
    "jxbzcxskg": "0",
}

class MockAPIHandler(http.server.SimpleHTTPRequestHandler):
    # 所有 do_GET, do_POST, _log_request, _send_response 函数保持不变
    # 这里为了简洁省略，请使用您之前版本中完整的函数代码
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
        post_params = parse_qs(self.rfile.read(content_length).decode('utf-8'))
        if "login" in self.path.lower():
            self._send_response(200, '{"result":"success", "msg":"登录成功(模拟)！"}')
        elif "partdisplay" in self.path.lower():
            requested_kklxdm = post_params.get('kklxdm', [None])[0]
            overview_courses = [v[0] for k, v in mock_full_course_db.items() if v and v[0].get('kklxdm') == requested_kklxdm]
            self._send_response(200, json.dumps({"tmpList": overview_courses}, ensure_ascii=False))
        elif "withkch" in self.path.lower():
            requested_kch_id = post_params.get('kch_id', [None])[0]
            self._send_response(200, json.dumps(mock_full_course_db.get(requested_kch_id, []), ensure_ascii=False))
        elif "xkbcz" in self.path.lower():
            jxb_id = post_params.get("jxb_ids", [None])[0]
            target_class = next((c for classes in mock_full_course_db.values() for c in classes if c.get('jxb_id') == jxb_id), None)
            if target_class and int(target_class.get("yxzrs", 0)) < int(target_class.get("jxbrl", 0)):
                self._send_response(200, json.dumps({"flag": "1", "msg": "选课成功！"}))
            else:
                self._send_response(200, json.dumps({"flag": "-1", "msg": "该课程选课人数已满！"}))
        else:
            self._send_response(404, '{"error": "POST endpoint not found"}')
    def do_GET(self):
        self._log_request("GET")
        if "getpublickey" in self.path.lower():
            self._send_response(200, json.dumps(mock_public_key_final))
        elif "login" in self.path.lower():
            self._send_response(200, "<html><body>...</body></html>", "text/html")
        elif "zzxkyz" in self.path.lower():
            inputs_html = "".join([f'<input type="hidden" name="{name}" value="{value}"/>\n' for name, value in mock_hidden_inputs.items()])
            self._send_response(200, f"<html><body><form>{inputs_html}</form></body></html>", "text/html")
        else:
            self._send_response(404, '{"error": "GET endpoint not found"}')

# --- V17核心改进2：使用多线程服务器 ---
class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

if __name__ == "__main__":
    # 使用新的多线程服务器来启动
    with ThreadingTCPServer(("", PORT), MockAPIHandler) as httpd:
        print("\n=======================================================")
        print(f"✅ 模拟教务系统服务器已启动 (V17 - 性能优化版)")
        print(f"   - 服务器类型: 多线程 (ThreadingTCPServer)")
        print("\n   请将你的程序教务系统地址设置为: http://localhost:8080")
        print(f"   服务器正在 http://localhost:{PORT} 上监听请求...")
        print("=======================================================\n")
        httpd.serve_forever()