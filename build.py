#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
岭南师范学院教务管理助手 - 自动化打包脚本

该脚本用于自动化构建和打包应用程序为可执行文件
支持Windows、macOS和Linux平台
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from typing import List, Optional


class BuildManager:
    """构建管理器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.build_dir = self.project_root / "build"
        self.dist_dir = self.project_root / "dist"
        self.spec_file = self.project_root / "build_config.spec"
        
    def print_header(self):
        """打印标题信息"""
        print("=" * 60)
        print("岭南师范学院教务管理助手 - 自动化打包脚本")
        print("=" * 60)
        print(f"Python版本: {sys.version}")
        print(f"操作系统: {platform.system()} {platform.release()}")
        print(f"项目路径: {self.project_root}")
        print("=" * 60)
        print()
    
    def check_python_version(self) -> bool:
        """检查Python版本"""
        if sys.version_info < (3, 8):
            print("[错误] 需要Python 3.8或更高版本")
            return False
        return True
    
    def check_dependencies(self) -> bool:
        """检查并安装依赖"""
        print("[信息] 检查项目依赖...")
        
        # 检查requirements.txt
        requirements_file = self.project_root / "requirements.txt"
        if not requirements_file.exists():
            print("[警告] 未找到requirements.txt文件")
            return True
        
        try:
            # 安装项目依赖
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
            ], check=True, capture_output=True, text=True)
            print("[成功] 项目依赖安装完成")
        except subprocess.CalledProcessError as e:
            print(f"[警告] 依赖安装可能存在问题: {e}")
            print("继续构建过程...")
        
        return True
    
    def check_pyinstaller(self) -> bool:
        """检查并安装PyInstaller"""
        try:
            import PyInstaller
            print(f"[信息] 找到PyInstaller版本: {PyInstaller.__version__}")
            return True
        except ImportError:
            print("[信息] 未找到PyInstaller，正在安装...")
            try:
                subprocess.run([
                    sys.executable, "-m", "pip", "install", "pyinstaller"
                ], check=True)
                print("[成功] PyInstaller安装完成")
                return True
            except subprocess.CalledProcessError as e:
                print(f"[错误] PyInstaller安装失败: {e}")
                return False
    
    def clean_build_files(self):
        """清理构建文件"""
        print("[信息] 清理之前的构建文件...")
        
        dirs_to_clean = [self.build_dir, self.dist_dir]
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"[信息] 已删除: {dir_path}")
        
        # 清理__pycache__文件夹
        for pycache in self.project_root.rglob("__pycache__"):
            if pycache.is_dir():
                shutil.rmtree(pycache)
        
        print("[成功] 构建文件清理完成")
    
    def build_executable(self) -> bool:
        """构建可执行文件"""
        print("[信息] 开始构建可执行文件...")
        print()
        
        if not self.spec_file.exists():
            print(f"[错误] 未找到spec文件: {self.spec_file}")
            return False
        
        try:
            # 运行PyInstaller
            cmd = [
                sys.executable, "-m", "PyInstaller",
                str(self.spec_file),
                "--clean",
                "--noconfirm"
            ]
            
            print(f"[信息] 执行命令: {' '.join(cmd)}")
            print()
            
            result = subprocess.run(cmd, cwd=self.project_root, text=True)
            
            if result.returncode == 0:
                print()
                print("[成功] 构建完成！")
                return True
            else:
                print()
                print(f"[错误] 构建失败，退出代码: {result.returncode}")
                return False
                
        except Exception as e:
            print(f"[错误] 构建过程中发生异常: {e}")
            return False
    
    def check_build_result(self) -> Optional[Path]:
        """检查构建结果"""
        if not self.dist_dir.exists():
            return None
        
        # 查找可执行文件
        exe_patterns = ["*.exe", "岭南师范学院教务管理助手*"]
        
        for pattern in exe_patterns:
            exe_files = list(self.dist_dir.glob(pattern))
            if exe_files:
                return exe_files[0]
        
        # 如果没找到特定名称，查找所有可执行文件
        all_files = list(self.dist_dir.iterdir())
        for file_path in all_files:
            if file_path.is_file() and (
                file_path.suffix.lower() == '.exe' or 
                os.access(file_path, os.X_OK)
            ):
                return file_path
        
        return None
    
    def print_build_summary(self, exe_path: Optional[Path]):
        """打印构建摘要"""
        print()
        print("=" * 60)
        
        if exe_path:
            print("[成功] 应用程序打包完成！")
            print(f"可执行文件: {exe_path}")
            print(f"文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
            
            # 显示dist目录内容
            print()
            print("输出目录内容:")
            for item in self.dist_dir.iterdir():
                size = ""
                if item.is_file():
                    size = f" ({item.stat().st_size / 1024 / 1024:.1f} MB)"
                print(f"  - {item.name}{size}")
        else:
            print("[失败] 未找到生成的可执行文件")
            print("请检查构建过程中的错误信息")
        
        print("=" * 60)
    
    def run(self):
        """运行完整的构建流程"""
        self.print_header()
        
        # 检查环境
        if not self.check_python_version():
            return False
        
        if not self.check_pyinstaller():
            return False
        
        if not self.check_dependencies():
            return False
        
        # 清理和构建
        self.clean_build_files()
        
        if not self.build_executable():
            return False
        
        # 检查结果
        exe_path = self.check_build_result()
        self.print_build_summary(exe_path)
        
        return exe_path is not None


def main():
    """主函数"""
    try:
        builder = BuildManager()
        success = builder.run()
        
        if success:
            print()
            print("构建完成！你可以在dist目录中找到可执行文件。")
        else:
            print()
            print("构建失败！请检查上述错误信息。")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print()
        print("[信息] 用户取消了构建过程")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 构建过程中发生未预期的错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()