@echo off
chcp 65001 >nul
echo ========================================
echo 岭南师范学院教务管理助手 - 打包脚本
echo ========================================
echo.

:: 检查Python环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python环境，请确保Python已正确安装并添加到PATH
    pause
    exit /b 1
)

:: 检查PyInstaller
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 未找到PyInstaller，正在安装...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [错误] PyInstaller安装失败
        pause
        exit /b 1
    )
)

:: 清理之前的构建文件
echo [信息] 清理之前的构建文件...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "__pycache__" rmdir /s /q "__pycache__"

:: 安装依赖
echo [信息] 检查并安装项目依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [警告] 依赖安装可能存在问题，继续构建...
)

:: 开始打包
echo [信息] 开始打包应用程序...
echo.
pyinstaller build_config.spec --clean --noconfirm

:: 检查打包结果
if exist "dist\岭南师范学院教务管理助手.exe" (
    echo.
    echo ========================================
    echo [成功] 打包完成！
    echo 可执行文件位置: dist\岭南师范学院教务管理助手.exe
    echo ========================================
    echo.
    
    :: 询问是否运行程序
    set /p choice="是否立即运行程序？(y/n): "
    if /i "%choice%"=="y" (
        start "" "dist\岭南师范学院教务管理助手.exe"
    )
    
    :: 询问是否打开文件夹
    set /p choice="是否打开输出文件夹？(y/n): "
    if /i "%choice%"=="y" (
        explorer "dist"
    )
) else (
    echo.
    echo ========================================
    echo [错误] 打包失败！
    echo 请检查上方的错误信息
    echo ========================================
)

echo.
pause