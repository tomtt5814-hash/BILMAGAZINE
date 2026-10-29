@echo off
rem Start bili-magazine server in background (no console window).
rem Env vars: LLM_PROVIDER / LLM_API_KEY / SCHEDULE_ENABLED / SCHEDULE_TIME
cd /d "%~dp0.."
pythonw scripts\start_server.py
