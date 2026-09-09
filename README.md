# 岭南师范学院教务管理助手

一个基于 PyQt6 的桌面 GUI 工具，用于登录正方教务系统并查看常用教务信息。

## 功能

- 多账号登录与会话管理
- 校内及 WebVPN 登录
- 查询个人信息、成绩、考试安排和课程表
- 浏览课程、管理意愿课程和辅助选课
- 导出课程表与成绩相关数据

## 运行环境

- Python 3.8 或更新版本
- Windows、macOS 或 Linux

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

首次登录时，在界面内输入教务系统地址、账号和密码。账号、愿望课程及本地配置只保存在本机，且已被 Git 忽略，不会提交到仓库。

## 项目结构

```text
main.py                 程序入口
api/                    正方教务系统接口
core/                   配置、会话与 WebVPN 支持
ui/                     PyQt6 界面
utils/                  后台任务、课程匹配和课表工具
config.ini.example      配置示例
```

请仅在学校规则允许的范围内使用选课及查询功能，并妥善保护自己的账号信息。
