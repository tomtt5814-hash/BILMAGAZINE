@echo off
rem 后台启动服务（无窗口）。环境变量来自用户级设置：
rem   LLM_PROVIDER / LLM_API_KEY / SCHEDULE_ENABLED / SCHEDULE_TIME
cd /d "%~dp0.."
pythonw scripts\start_server.py
