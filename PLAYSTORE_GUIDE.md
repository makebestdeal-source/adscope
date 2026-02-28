# AdScope Google Play Store 등록 가이드

## 현재 완료된 작업

| 항목 | 파일 |
|------|------|
| PWA Manifest | `frontend/public/manifest.json` |
| Service Worker | `frontend/public/sw.js` |
| 앱 아이콘 (192/512, maskable) | `frontend/public/icons/` |
| PWA 메타태그 (layout.tsx) | viewport + manifest + appleWebApp |
| SW 등록 컴포넌트 | `frontend/src/components/ServiceWorkerRegister.tsx` |
| 오프라인 페이지 | `frontend/src/app/offline/page.tsx` |
| Digital Asset Links | `frontend/public/.well-known/assetlinks.json` (SHA256 미입력) |
| TWA 설정 | `frontend/twa/twa-manifest.json` |
| 개인정보처리방침 | `frontend/src/app/privacy/page.tsx` |
| 아이콘 생성 스크립트 | `frontend/scripts/generate-icons.js` (sharp 사용) |
| 프로덕션 빌드 | 26페이지 성공 확인 |

## 등록 절차

### 1. 사전 준비
- [ ] Google Play 개발자 계정 등록 ($25 일회성)
- [ ] 조직 계정이면 D-U-N-S 번호 필요 (2026.09 의무화)
- [ ] HTTPS 도메인 배포 (`adscope.kr`)

### 2. 배포 후 확인
- [ ] Lighthouse 성능 점수 80+ (TWA 필수 조건)
- [ ] `https://adscope.kr/.well-known/assetlinks.json` 접근 가능 확인
- [ ] `https://adscope.kr/manifest.json` 접근 가능 확인

### 3. TWA 빌드
```bash
# JDK 17+, Android SDK 필요
npm install -g @nicolo-ribaudo/chokidar-2
npm install -g bubblewrap

# twa/ 디렉토리에서
cd frontend/twa
npx bubblewrap init --manifest=https://adscope.kr/manifest.json
npx bubblewrap build
# → app-release-signed.aab 생성
```

### 4. assetlinks.json SHA256 입력
```bash
# 서명키 SHA256 추출
keytool -list -v -keystore adscope-keystore.jks -alias adscope
# SHA256 값을 frontend/public/.well-known/assetlinks.json에 입력
```

### 5. Play Console 제출 필요 항목
- [ ] 앱 아이콘 512x512 PNG
- [ ] 피처 그래픽 1024x500 JPEG/PNG
- [ ] 스크린샷 최소 2장 (16:9)
- [ ] 앱 이름 (30자): `AdScope`
- [ ] 짧은 설명 (80자): `한국 디지털 광고 모니터링 인텔리전스 플랫폼`
- [ ] 상세 설명 (4000자)
- [ ] 개인정보처리방침 URL: `https://adscope.kr/privacy`
- [ ] IARC 콘텐츠 등급 설문
- [ ] 데이터 안전 섹션 (수집: 이메일, 이름, 회사명, 연락처, IP, 기기정보)
- [ ] 대상 연령 설정

### 6. 주의사항
- `assetlinks.json` 검증 실패 = 가장 흔한 리젝 사유
- Lighthouse 80점 미만 = Bubblewrap 빌드 시 경고
- 내부 테스트 트랙 먼저 업로드 → 검증 후 프로덕션 제출
- 웹 수정 시 앱 자동 반영 (AAB 재제출 불필요)
- 패키지명: `kr.adscope.app`
