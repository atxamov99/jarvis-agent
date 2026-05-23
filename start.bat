@echo off
chcp 65001 >nul
cd /d "D:\AI\jarvis-agent"
set PYTHONIOENCODING=utf-8
"C:\Python314\pythonw.exe" -W ignore main.py
