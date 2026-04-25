@echo off
chcp 65001 >nul
title AdScope 자동 시작 제거

echo ============================================
echo   AdScope 자동 실행 완전 제거
echo   (관리자 권한 필요)
echo ============================================
echo.

echo [1/3] AdScopeScheduler 서비스 중지...
sc stop AdScopeScheduler >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo      OK - 서비스 중지됨
) else (
    echo      (이미 중지되어 있거나 없음)
)
timeout /t 2 /nobreak >nul

echo [2/3] AdScopeScheduler 서비스 삭제...
sc delete AdScopeScheduler >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo      OK - 서비스 삭제됨
) else (
    echo      (이미 없거나 삭제 실패 - 관리자 권한 확인)
)

echo [3/3] AdScope-DailyCrawl 작업 스케줄러 삭제 (있을 경우)...
schtasks /delete /tn "AdScope-DailyCrawl" /f >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo      OK - 스케줄 작업 삭제됨
) else (
    echo      (없음 - 정상)
)

echo.
echo ============================================
echo   완료! 이제 부팅 시 자동 실행되지 않습니다.
echo   앞으로는 adscope_panel.bat 로 수동 실행하세요.
echo ============================================
echo.
pause
