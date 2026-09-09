# 岭南师范学院教务管理助手 - 打包说明

本文档说明如何将Python应用程序打包成独立的可执行文件。

## 📋 打包前准备

### 1. 环境要求
- Python 3.8 或更高版本
- 已安装项目依赖（运行 `pip install -r requirements.txt`）

### 2. 检查项目结构
确保以下文件存在：
- `main.py` - 主程序入口
- `requirements.txt` - 项目依赖
- `build_config.spec` - PyInstaller配置文件
- `build.py` 或 `build.bat` - 打包脚本

## 🚀 打包方法

### 方法一：使用Python脚本（推荐）

```bash
python build.py
```

**优点：**
- 跨平台支持
- 详细的错误处理和日志
- 自动检查和安装依赖
- 智能的构建结果验证

### 方法二：使用批处理脚本（Windows）

双击运行 `build.bat` 或在命令行中执行：

```cmd
build.bat
```

**优点：**
- 简单易用
- 交互式操作
- 自动打开结果文件夹

### 方法三：手动使用PyInstaller

```bash
# 安装PyInstaller
pip install pyinstaller

# 清理之前的构建
rmdir /s build dist

# 开始打包
pyinstaller build_config.spec --clean --noconfirm
```

## 📁 输出文件

打包完成后，可执行文件将位于：
```
dist/
└── 岭南师范学院教务管理助手.exe
```

## ⚙️ 配置说明

### build_config.spec 配置文件

主要配置项：

- **hiddenimports**: 隐藏导入的模块
- **datas**: 需要包含的数据文件
- **excludes**: 排除的模块（减小文件大小）
- **console**: 是否显示控制台窗口
- **icon**: 应用程序图标
- **upx**: 是否使用UPX压缩

### 自定义配置

如需修改打包配置，编辑 `build_config.spec` 文件：

```python
# 修改应用程序名称
name='你的应用名称'

# 添加图标
icon='path/to/your/icon.ico'

# 显示控制台（调试用）
console=True

# 添加额外的数据文件
datas=[('config.ini', '.'), ('assets/', 'assets/')]
```

## 🔧 常见问题

### 1. 打包失败

**可能原因：**
- 缺少依赖模块
- 路径问题
- 权限不足

**解决方法：**
```bash
# 重新安装依赖
pip install -r requirements.txt --force-reinstall

# 清理缓存
pip cache purge

# 使用管理员权限运行
```

### 2. 程序无法启动

**可能原因：**
- 缺少运行时库
- 路径配置错误
- 隐藏导入遗漏

**解决方法：**
- 在 `build_config.spec` 中添加缺少的模块到 `hiddenimports`
- 检查数据文件路径配置
- 使用 `console=True` 查看错误信息

### 3. 文件过大

**优化方法：**
```python
# 在spec文件中排除不需要的模块
excludes=[
    'tkinter',
    'matplotlib', 
    'numpy',
    'pandas',
    # 添加其他不需要的大型库
]

# 启用UPX压缩
upx=True
```

### 4. 缺少图标或资源文件

确保资源文件路径正确：
```python
# 检查图标文件是否存在
icon_path = 'ui/assets/icon.ico'
if os.path.exists(icon_path):
    icon = icon_path
```

## 📊 打包优化建议

### 1. 减小文件大小
- 排除不必要的模块
- 使用UPX压缩
- 移除调试信息

### 2. 提高启动速度
- 减少隐藏导入
- 优化代码结构
- 使用延迟导入

### 3. 提高兼容性
- 测试不同Windows版本
- 包含必要的运行时库
- 处理路径分隔符问题

## 🎯 发布清单

打包完成后，建议进行以下测试：

- [ ] 在干净的Windows系统上测试运行
- [ ] 检查所有功能是否正常
- [ ] 验证配置文件读取
- [ ] 测试网络连接功能
- [ ] 检查界面显示效果
- [ ] 验证文件读写权限

## 📞 技术支持

如果遇到打包问题，可以：

1. 查看构建日志中的错误信息
2. 检查Python和依赖版本兼容性
3. 参考PyInstaller官方文档
4. 在项目仓库提交Issue

---

**注意：** 首次打包可能需要较长时间，请耐心等待。建议在网络良好的环境下进行打包操作。