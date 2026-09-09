@echo off
setlocal
set "APP_ROOT=%~dp0"
set "INTERNAL=%APP_ROOT%_internal"
set "QT_BIN=%INTERNAL%\PyQt6\Qt6\bin"
set "QT_PLUGINS=%INTERNAL%\PyQt6\Qt6\plugins"
set "PATH=%QT_BIN%;%INTERNAL%;%APP_ROOT%;%PATH%"
set "QT_PLUGIN_PATH=%QT_PLUGINS%"
start "" "%APP_ROOT%岭南师范学院教务管理助手.exe"
endlocal
