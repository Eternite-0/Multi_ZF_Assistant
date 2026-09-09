#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速打包脚本 - 岭南师范学院教务管理助手
一键打包，简化操作流程
"""

import os
import sys
import subprocess
from pathlib import Path


def quick_build():
    """快速打包函数"""
    print("🚀 岭南师范学院教务管理助手 - 快速打包")
    print("=" * 50)
    
    # 检查PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("📦 正在安装PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # 检查spec文件
    spec_file = Path("build_config.spec")
    if not spec_file.exists():
        print("❌ 错误：未找到build_config.spec文件")
        return False
    
    # 安装依赖
    print("📋 安装项目依赖...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                  capture_output=True)
    
    # 开始打包
    print("🔨 开始打包...")
    result = subprocess.run([
        sys.executable, "-m", "PyInstaller", 
        "build_config.spec", "--clean", "--noconfirm"
    ])
    
    if result.returncode == 0:
        print("✅ 打包成功！")
        print("📁 可执行文件位于: dist/岭南师范学院教务管理助手.exe")
        return True
    else:
        print("❌ 打包失败！")
        return False


if __name__ == "__main__":
    try:
        success = quick_build()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹️ 用户取消打包")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 打包过程出错: {e}")
        sys.exit(1)