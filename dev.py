#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发工具脚本
提供代码格式化、检查和测试等功能
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def run_command(cmd: str, description: str) -> bool:
    """运行命令并显示结果"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, cwd=PROJECT_ROOT, check=True)
        print(f"✅ {description} 完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失败: {e}")
        return False


def format_code():
    """格式化代码"""
    return run_command("black .", "代码格式化")


def lint_code():
    """代码检查"""
    success = True
    success &= run_command("flake8 .", "代码风格检查")
    success &= run_command("mypy .", "类型检查")
    return success


def install_deps():
    """安装依赖"""
    success = True
    success &= run_command("pip install -r requirements.txt", "安装项目依赖")
    success &= run_command("pip install black flake8 mypy pytest pytest-qt", "安装开发依赖")
    return success


def run_tests():
    """运行测试"""
    return run_command("pytest tests/ -v", "运行测试")


def build_exe():
    """构建可执行文件"""
    return run_command("pyinstaller --onefile --windowed main.py", "构建可执行文件")


def clean():
    """清理临时文件"""
    import shutil
    
    patterns = [
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        ".pytest_cache",
        ".mypy_cache",
        "build",
        "dist",
        "*.egg-info"
    ]
    
    for pattern in patterns:
        for path in PROJECT_ROOT.rglob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
                print(f"🗑️  删除目录: {path}")
            elif path.is_file():
                path.unlink()
                print(f"🗑️  删除文件: {path}")
    
    print("✅ 清理完成")


def main():
    parser = argparse.ArgumentParser(description="开发工具脚本")
    parser.add_argument("command", choices=[
        "format", "lint", "test", "install", "build", "clean", "all"
    ], help="要执行的命令")
    
    args = parser.parse_args()
    
    if args.command == "format":
        format_code()
    elif args.command == "lint":
        lint_code()
    elif args.command == "test":
        run_tests()
    elif args.command == "install":
        install_deps()
    elif args.command == "build":
        build_exe()
    elif args.command == "clean":
        clean()
    elif args.command == "all":
        print("🚀 执行完整开发流程...")
        success = True
        success &= install_deps()
        success &= format_code()
        success &= lint_code()
        success &= run_tests()
        
        if success:
            print("🎉 所有检查通过！")
        else:
            print("❌ 存在问题需要修复")
            sys.exit(1)


if __name__ == "__main__":
    main()