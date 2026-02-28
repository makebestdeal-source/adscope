# ADSCOPE — INVENTOR 실행 가이드

## 포트: API 8000 / Frontend 3000
## 스택: FastAPI + Next.js
## INVENTOR CMD: `inventor-start.bat`

### 실행 방식
- INVENTOR에서 Start 버튼 → inventor-start.bat 실행
  - 포트 8000, 3000 잔존 프로세스 자동 정리
  - Backend: `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000`
  - Frontend: `cd frontend && npm run dev` → http://localhost:3000
  - 브라우저 자동 오픈: http://localhost:3000

### 포트 설정 위치
- Backend: inventor-start.bat 내 `--port 8000`
- Frontend: Next.js 기본 포트 3000

### 주의사항
- inventor-start.bat은 `start /b`로 같은 프로세스 트리 유지 → Stop 시 전체 종료
- 기존 runstart.bat은 별도 창 생성 방식 (INVENTOR 비연동)
- 포트 8000, 3000은 이 프로젝트 전용 (port-registry.json 참고)
