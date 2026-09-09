# 贡献指南

感谢您对岭南师范学院教务管理助手项目的关注！我们欢迎各种形式的贡献。

## 🤝 如何贡献

### 报告问题

如果您发现了 bug 或有功能建议，请：

1. 检查 [Issues](../../issues) 确保问题尚未被报告
2. 创建新的 Issue，包含：
   - 清晰的标题和描述
   - 重现步骤（如果是 bug）
   - 期望的行为
   - 实际的行为
   - 系统环境信息

### 提交代码

1. **Fork 项目**
   ```bash
   git clone https://github.com/your-username/zfn-assistant.git
   cd zfn-assistant
   ```

2. **创建开发环境**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # 或
   .venv\Scripts\activate     # Windows
   
   pip install -r requirements.txt
   python scripts/dev.py install
   ```

3. **创建功能分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **开发和测试**
   ```bash
   # 格式化代码
   python scripts/dev.py format
   
   # 代码检查
   python scripts/dev.py lint
   
   # 运行测试
   python scripts/dev.py test
   ```

5. **提交更改**
   ```bash
   git add .
   git commit -m "feat: 添加新功能描述"
   git push origin feature/your-feature-name
   ```

6. **创建 Pull Request**
   - 提供清晰的标题和描述
   - 引用相关的 Issues
   - 确保所有检查通过

## 📝 代码规范

### Python 代码风格

- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 规范
- 使用 [Black](https://black.readthedocs.io/) 进行代码格式化
- 使用 [Flake8](https://flake8.pycqa.org/) 进行代码检查
- 使用 [MyPy](https://mypy.readthedocs.io/) 进行类型检查

### 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<类型>[可选的作用域]: <描述>

[可选的正文]

[可选的脚注]
```

类型包括：
- `feat`: 新功能
- `fix`: 错误修复
- `docs`: 文档更新
- `style`: 代码格式（不影响代码运行的变动）
- `refactor`: 重构（既不是新增功能，也不是修复错误的代码变动）
- `test`: 增加测试
- `chore`: 构建过程或辅助工具的变动

示例：
```
feat(api): 添加成绩查询缓存功能

- 实现本地缓存机制
- 减少网络请求次数
- 提升查询速度

Closes #123
```

### 文档规范

- 所有公共函数和类都应该有文档字符串
- 使用中文编写注释和文档
- 保持 README 和其他文档的更新

### 测试规范

- 新功能必须包含相应的测试
- 确保测试覆盖率不降低
- 测试文件命名为 `test_*.py`
- 使用 pytest 框架

## 🔧 开发工具

项目提供了便捷的开发脚本：

```bash
# 安装开发依赖
python scripts/dev.py install

# 格式化代码
python scripts/dev.py format

# 代码检查
python scripts/dev.py lint

# 运行测试
python scripts/dev.py test

# 构建可执行文件
python scripts/dev.py build

# 清理临时文件
python scripts/dev.py clean

# 执行完整流程
python scripts/dev.py all
```

## 📋 开发流程

1. 在开始开发前，请先与维护者讨论您的想法
2. 确保您的代码通过所有检查
3. 添加必要的测试
4. 更新相关文档
5. 提交 Pull Request

## 🎯 优先级

我们特别欢迎以下类型的贡献：

- 🐛 Bug 修复
- 📚 文档改进
- 🧪 测试覆盖率提升
- 🚀 性能优化
- 🎨 用户界面改进
- 🔒 安全性增强

## 📞 联系方式

如果您有任何问题，可以通过以下方式联系我们：

- 创建 [Issue](../../issues)
- 发送邮件到 [developer@example.com](mailto:developer@example.com)

再次感谢您的贡献！🎉