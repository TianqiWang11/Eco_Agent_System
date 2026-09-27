@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到项目虚拟环境：.venv
  echo 请先完成Python依赖安装。
  pause
  exit /b 1
)

echo ==================================================
echo 车八岭生态数字孪生与AI智能分析平台
echo 门户地址：http://127.0.0.1:8000
echo 数据源模式：由 .env 配置
echo 按 Ctrl+C 停止服务
echo ==================================================

".venv\Scripts\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
