@echo off
REM Lance le dashboard NEXORA (paper trading) et ouvre le navigateur.
cd /d "%~dp0"
title NEXORA - Dashboard
start "" http://localhost:8501
python -m streamlit run dashboard/app.py --server.headless true --server.port 8501
pause
