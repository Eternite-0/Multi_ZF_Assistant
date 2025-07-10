# mock_server.py (V15 - 最终完美版，完整支持抢课流程)
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

# 1. 动态生成有效的RSA密钥对并正确编码
key_pair = RSA.generate(1024)
modulus_b64 = base64.b64encode(long_to_bytes(key_pair.n)).decode('utf-8')
exponent_b64 = base64.b64encode(long_to_bytes(key_pair.e)).decode('utf-8')
mock_public_key_final = {"modulus": modulus_b64, "exponent": exponent_b64}

# 2. 【V15核心改进】模拟的、数据字段极度丰富的课程数据库
#    为每个教学班补充了 do_jxb_id, jxbrl, yxzrs 等所有关键字段
mock_full_course_db = {
    # 课程1：计算机网络 (kch_id: COURSE_ID_001) 有两个教学班
    "COURSE_ID_001": [
        {
            "kcmc": "【专业选修】计算机网络", "kch_id": "COURSE_ID_001", "jxb_id": "jxb_id_01",
            "do_jxb_id": "jxb_id_01", # <--- 补全关键字段
            "jsxx": "张三(教授)", "kklxdm": "10", "xkkz_id": "xyz-123", "kch": "C001",
            "xnm": "2025", "xqm": "3", "sksj": "1-16周 周二第3,4节", "jxdd": "信息楼201", "xf": "3.0",
            "kcsxmc": "专业核心课", "jxbrl": 60, "yxzrs": 42, # <--- 使用正确的容量/已选字段名
        },
        {
            "kcmc": "【专业选修】计算机网络", "kch_id": "COURSE_ID_001", "jxb_id": "jxb_id_01_b",
            "do_jxb_id": "jxb_id_01_b", # <--- 补全关键字段
            "jsxx": "张三(教授)", "kklxdm": "10", "xkkz_id": "xyz-123", "kch": "C001",
            "xnm": "2025", "xqm": "3", "sksj": "1-16周 周三第5,6节", "jxdd": "信息楼202", "xf": "3.0",
            "kcsxmc": "专业核心课", "jxbrl": 60, "yxzrs": 39, # <--- 容量已满
        }
    ],
    # 课程2：操作系统 (kch_id: COURSE_ID_002) 只有一个教学班
    "COURSE_ID_002": [
        {
            "kcmc": "【专业选修】操作系统", "kch_id": "COURSE_ID_002", "jxb_id": "jxb_id_02",
            "do_jxb_id": "jxb_id_02", # <--- 补全关键字段
            "jsxx": "李四(教授)", "kklxdm": "10", "xkkz_id": "xyz-123", "kch": "C002",
            "xnm": "2025", "xqm": "3", "sksj": "1-16周 周四第1,2节", "jxdd": "信息楼305", "xf": "3.0",
            "kcsxmc": "专业核心课", "jxbrl": 40, "yxzrs": 22,
        }
    ]
}

# 3. 完整的隐藏域字典
mock_hidden_inputs = { "firstKklxdm": "10", "firstXkkzId": "xyz-123", "rwlx": "1", "xklc": "1", "xkly": "1", "xkxnm": "2025", "xkxqm": "3", # ...等其他字段
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

        # --- 登录接口 ---
        if "login" in self.path.lower():
            print("✅ [POST] 识别为提交登录信息...")
            self._send_response(200, '{"result":"success", "msg":"登录成功(模拟)！"}')
            return

        # --- 响应第一步：获取课程“概览”列表 ---
        if "partdisplay" in self.path.lower():
            print("✅ [POST - Step 1] 识别为获取课程【概览】列表请求...")
            requested_kklxdm = post_params.get('kklxdm', [None])[0]
            overview_courses = [v[0] for k, v in mock_full_course_db.items() if v and v[0].get('kklxdm') == requested_kklxdm]
            response_data = {"tmpList": overview_courses}
            print(f"   - 已使用正确的键名 'tmpList' 返回 {len(overview_courses)} 门课程的概览。")
            self._send_response(200, json.dumps(response_data, ensure_ascii=False))
            return
            
        # --- 响应第二步：获取“教学班”详细信息 ---
        if "withkch" in self.path.lower():
            print("✅ [POST - Step 2] 识别为获取【教学班详情】请求...")
            requested_kch_id = post_params.get('kch_id', [None])[0]
            detailed_classes = mock_full_course_db.get(requested_kch_id, [])
            print(f"   - 已找到 {len(detailed_classes)} 个对应的教学班并返回。")
            self._send_response(200, json.dumps(detailed_classes, ensure_ascii=False))
            return

        # --- 【V15核心改进】响应第三步：处理最终的“选课”请求 ---
        if "xkbcz" in self.path.lower(): # 匹配 ...xkBcZyZzxkYzb.html
            print("✅ [POST - Step 3] 识别为【执行选课】请求...")
            jxb_id = post_params.get("jxb_ids", [None])[0]
            print(f"   - 正在尝试选择教学班ID: {jxb_id}")
            
            # 在整个数据库中找到这个教学班
            target_class = None
            for classes in mock_full_course_db.values():
                for c in classes:
                    if c.get('jxb_id') == jxb_id:
                        target_class = c
                        break
            
            if not target_class:
                response = {"flag": "-1", "msg": "错误：尝试选择一个不存在的教学班ID。"}
            else:
                capacity = int(target_class.get("jxbrl", 0))
                selected = int(target_class.get("yxzrs", 0))
                if selected < capacity:
                    # 模拟抢课成功
                    target_class["yxzrs"] += 1 # 已选人数+1
                    response = {"flag": "1", "msg": "选课成功！"}
                    print(f"   - ✅ 选课成功！《{target_class['kcmc']}》, 新的已选人数: {target_class['yxzrs']}")
                else:
                    # 模拟容量已满
                    response = {"flag": "-1", "msg": "该课程选课人数已满！"}
                    print(f"   - 💨 选课失败，容量已满。")

            self._send_response(200, json.dumps(response))
            return

        self._send_response(404, '{"error": "POST endpoint not found"}')

    def do_GET(self):
        # GET请求处理逻辑保持不变
        self._log_request("GET")
        if "getpublickey" in self.path.lower():
            self._send_response(200, json.dumps(mock_public_key_final))
            return
        if "login" in self.path.lower():
            self._send_response(200, "<html><body>...</body></html>", "text/html")
            return
        if "zzxkyz" in self.path.lower():
            inputs_html = "".join([f'<input type="hidden" name="{name}" value="{value}"/>\n' for name, value in mock_hidden_inputs.items()])
            self._send_response(200, f"<html><body><form>{inputs_html}</form></body></html>", "text/html")
            return
        self._send_response(404, '{"error": "GET endpoint not found"}')

Handler = MockAPIHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("\n=======================================================")
    print(f"✅ 模拟教务系统服务器已启动 (V15 - 最终完美版)")
    print(f"   - 已完整支持您程序的所有接口，包括最终的抢课操作")
    print("\n   请将你的程序教务系统地址设置为: http://localhost:8080")
    print(f"   服务器正在 http://localhost:{PORT} 上监听请求...")
    print("=======================================================\n")
    httpd.serve_forever()