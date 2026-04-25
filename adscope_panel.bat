@echo off
chcp 65001 >nul
title AdScope Control Panel
cd /d C:\Users\user\Desktop\adscopre
set PATH=C:\Python314;C:\Python314\Scripts;%PATH%
set PYTHONPATH=C:\Users\user\Desktop\adscopre
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe scripts\adscope_panel.py
