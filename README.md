# 🏫 岭南师范学院教务管理助手

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-GUI-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)

*一个现代化的岭南师范学院正方教务系统便捷助手*

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [使用说明](#-使用说明) • [开发指南](#-开发指南)

</div>

---

## ✨ 功能特性

### 🔐 账户管理
- [x] **智能登录** - 自动识别验证码需求
- [x] **多账户支持** - 管理多个学生账户
- [x] **会话保持** - 自动维持登录状态

### 📊 学业查询
- [x] **个人信息** - 查看学生基本信息
- [x] **成绩查询** - 支持多种成绩查询接口
- [x] **考试安排** - 查看考试时间和地点
- [x] **课程表** - 查看当前学期课程安排
- [x] **学业生涯** - 完整的学业数据统计

### 📄 文档导出
- [x] **课程表 PDF** - 导出精美的课程表
- [x] **成绩单 PDF** - 导出学业成绩总表

### 🎯 选课功能
- [x] **课程浏览** - 查看可选课程列表
- [x] **智能抢课** - 自动选课功能
- [x] **课程管理** - 查看已选课程
- [x] **退课功能** - ⚠️ 谨慎使用，可能影响必选课

> **⚠️ 重要提醒**: 退课功能请谨慎使用，因为判断课程属性等逻辑均由教务系统前端执行，直接调用该接口甚至可以退掉必选课。

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Windows/macOS/Linux

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd zfn-assistant
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **运行程序**
   ```bash
   python main.py
   ```

## 📖 使用说明

### 首次使用
1. 启动程序后，点击"添加账户"
2. 输入教务系统URL、学号和密码
3. 点击"登录"进行身份验证
4. 登录成功后即可使用各项功能

### 主要功能操作
- **查看成绩**: 选择账户后点击"成绩查询"
- **查看课表**: 点击"课程表"查看当前学期安排
- **考试安排**: 查看即将到来的考试信息
- **选课操作**: 在选课期间使用"智能抢课"功能

## 🏗️ 项目结构

```
zfn-assistant/
├── api/                    # API接口层
│   └── zfn_api.py         # 教务系统API封装
├── core/                   # 核心业务逻辑
│   ├── config.py          # 配置管理
│   ├── models.py          # 数据模型
│   └── session_manager.py # 会话管理
├── ui/                     # 用户界面
│   ├── main_window.py     # 主窗口
│   ├── dialogs.py         # 对话框
│   └── assets.py          # 界面资源
├── utils/                  # 工具函数
│   └── workers.py         # 后台任务
├── main.py                # 程序入口
└── requirements.txt       # 依赖列表
```

## 📋 状态码

为了一些特殊的业务逻辑，如验证码错误后自动刷新页面获取等，使用了自定义状态码，详情如下：

| 状态码 | 内容                 |
| ------ | -------------------- |
| 998    | 网页弹窗未处理内容   |
| 999    | 接口逻辑或未知错误   |
| 1000   | 请求获取成功         |
| 1001   | （登录）需要验证码   |
| 1002   | 用户名或密码不正确   |
| 1003   | 请求超时             |
| 1004   | 验证码错误           |
| 1005   | 内容为空             |
| 1006   | cookies 失效或过期   |
| 1007   | 接口失效请更新       |
| 2333   | 系统维护或服务被 ban |


## 🛠️ 开发指南

### 开发环境设置

1. **安装开发依赖**
   ```bash
   pip install -r requirements.txt
   pip install black flake8 mypy  # 代码格式化和检查工具
   ```

2. **代码规范**
   - 使用 Black 进行代码格式化
   - 遵循 PEP 8 编码规范
   - 添加类型注解和文档字符串

3. **项目架构**
   - `api/` - 与教务系统的接口交互
   - `core/` - 核心业务逻辑和数据模型
   - `ui/` - PyQt6 用户界面组件
   - `utils/` - 通用工具函数

### 贡献指南

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🤝 致谢

- 感谢岭南师范学院提供的教务系统接口
- 感谢所有贡献者的支持和建议

## ⚠️ 免责声明

本工具仅供学习和研究使用，请遵守学校相关规定，合理使用教务系统资源。开发者不承担因使用本工具而产生的任何责任。

---

## 📊 数据字段说明

```json
{
  // 成绩
  "course_id": "课程号",
  "title": "课程标题",
  "teacher": "任课教师",
  "class_name": "教学班名称",
  "credit": "学分",
  "category": "课程类别",
  "nature": "课程性质",
  "grade": "成绩",
  "grade_point": "绩点",
  "grade_nature": "成绩性质",
  "start_college": "开课院系",
  "mark": "",
  // 课表
  "weekday": "星期几",
  "time": "上课时间",
  "sessions": "上课节数",
  "list_sessions": "开课节数列表",
  "weeks": "开课周数",
  "list_weeks": "开课周数列表",
  "evaluation_mode": "考核方式",
  "campus": "上课校区",
  "place": "上课场地",
  "hours_composition": "课程学时组成",
  "weekly_hours": "每周学时",
  "total_hours": "总学时",
  // 学业生涯
  "situation": "修读情况",
  "display_term": "修读学期",
  "max_grade": "最佳成绩",
  // 选课
  "class_id": "教学班ID",
  "do_id": "执行ID",
  "teacher_id": "教师ID",
  "kklxdm": "板块课ID",
  "capacity": "教学班容量",
  "selected_number": "已选人数",
  "optional": "是否自选",
  "waiting": "",
  // 考试日程
  "course_id": "课程号",
  "title": "课程名称",
  "time": "考试时间",
  "location": "考试地点",
  "xq": "考试校区",
  "zwh": "考试座号",
  "cxbj": "重修标记",
  "exam_name": "考试名称(如:2023-2024-1学期期末考试)",
  "teacher": "任课教师",
  "class_name": "教学班名称",
  "kkxy": "开课学院",
  "credit": "学分",
  "ksfs": "考试方式(如:笔试,开卷,机考)",
  "sjbh": "试卷编号",
  "bz": "备注",
}
```

