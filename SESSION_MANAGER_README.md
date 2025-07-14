# Session管理器使用指南

## 概述

新的Session管理器解决了正方教务系统token过期的问题，实现了：
- 自动维持登录状态
- 自动检测Session过期
- 自动重新登录
- 线程安全的Session管理

## 主要特性

### 1. 自动Session维持
- 使用`requests.Session`保持长连接
- 自动管理cookies和headers
- 无需手动维护Session状态

### 2. 智能过期检测
- 通过访问系统页面检测Session是否有效
- 自动识别登录页面返回
- 实时监控Session状态

### 3. 自动重新登录
- Session过期时自动重新登录
- 保存用户凭证用于自动登录
- 登录失败时提供详细错误信息

### 4. 线程安全
- 使用`threading.RLock`确保线程安全
- 支持多线程环境下的并发访问

## 使用方法

### 基本用法

```python
from api.zfn_api import Client

# 创建客户端
client = Client(base_url="https://your-school.edu.cn")

# 登录（会自动保存凭证用于后续自动重登录）
result = client.login("your_student_id", "your_password")
if result['code'] == 1000:
    print("登录成功")

# 使用API（会自动维持登录状态）
info = client.get_info()
grade = client.get_grade(2024, 1)
schedule = client.get_schedule(2024, 1)
```

### 检查登录状态

```python
# 获取登录状态信息
status = client.get_login_status()
print(f"是否已登录: {status['is_logged_in']}")
print(f"登录时间: {status['login_time']}")
print(f"Session有效: {status['session_valid']}")
```

### 手动Session管理

```python
# 获取SessionManager实例
session_manager = client.session_manager

# 检查Session是否有效
if session_manager.is_session_valid():
    print("Session有效")
else:
    print("Session无效")

# 强制重新登录
session_manager.ensure_login()

# 注销
session_manager.logout()
```

## 核心组件

### SessionManager类

位于`core/session_manager.py`，主要方法：

- `login(sid, password)`: 登录并保存凭证
- `is_session_valid()`: 检查Session是否有效
- `ensure_login()`: 确保登录状态，必要时自动重登录
- `request(method, url, **kwargs)`: 安全的请求方法
- `get(url, **kwargs)`: GET请求
- `post(url, **kwargs)`: POST请求
- `logout()`: 注销并清理Session

### Client类改进

位于`api/zfn_api.py`，主要改进：

- 集成SessionManager
- 添加`_safe_request()`方法
- 添加`get_login_status()`方法
- 自动处理Session过期

## 错误处理

### 登录错误

```python
result = client.login(sid, password)
if result['code'] != 1000:
    print(f"登录失败: {result['msg']}")
    # 处理登录错误
```

### API调用错误

```python
try:
    info = client.get_info()
    if info['code'] != 1000:
        print(f"API调用失败: {info['msg']}")
except Exception as e:
    print(f"请求异常: {e}")
```

## 配置选项

### 超时设置

```python
client = Client(base_url="https://your-school.edu.cn", timeout=15)
```

### 自定义headers

SessionManager会自动设置合适的headers，包括：
- User-Agent
- Accept
- Accept-Language
- Accept-Encoding
- Connection: keep-alive

## 注意事项

1. **凭证安全**: 登录凭证会保存在内存中用于自动重登录，请确保应用安全
2. **网络异常**: 网络不稳定时可能导致重登录失败，需要重新手动登录
3. **验证码**: 目前不支持需要验证码的自动重登录场景
4. **并发访问**: 在多线程环境中，SessionManager是线程安全的
5. **资源清理**: 应用结束前建议调用`logout()`方法清理资源

## 示例代码

参见`example_session_usage.py`文件，包含完整的使用示例。

## 更新日志

### v1.0.0
- 实现基本的Session管理功能
- 添加自动重新登录机制
- 集成到现有Client类中
- 添加线程安全支持

---

这个Session管理器大大简化了教务系统的使用，无需再手动管理Session状态和处理token过期问题！