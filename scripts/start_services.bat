@echo off
cd /d C:\Users\user\Desktop\adscopre

:: Start backend (uvicorn)
start /B "" C:\Python314\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > logs\uvicorn.log 2>&1

:: Wait for backend to start
timeout /t 3 /nobreak > nul

:: Start frontend (Next.js production)
cd frontend
start /B "" npx next start -p 3001 > ..\logs\frontend.log 2>&1
cd ..

echo Services started.
