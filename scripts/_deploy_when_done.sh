#!/bin/bash
# 두 작업 완료 후 자동 배포

ARCHIVE_PID=435
ENRICH_PID=554
LOG="/c/Users/user/Desktop/adscopre/logs/auto_deploy.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 모니터 시작 (archive=$ARCHIVE_PID, enrich=$ENRICH_PID)" >> "$LOG"

# archive_crawl 완료 대기
while kill -0 $ARCHIVE_PID 2>/dev/null; do
    sleep 60
done
echo "[$(date '+%Y-%m-%d %H:%M:%S')] archive_crawl 완료" >> "$LOG"

# enrich_brand_purpose 완료 대기
while kill -0 $ENRICH_PID 2>/dev/null; do
    sleep 30
done
echo "[$(date '+%Y-%m-%d %H:%M:%S')] enrich_brand_purpose 완료" >> "$LOG"

cd /c/Users/user/Desktop/adscopre

# 백엔드 배포
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백엔드 배포 시작..." >> "$LOG"
railway service adscope >> "$LOG" 2>&1
railway up -d >> "$LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백엔드 배포 완료" >> "$LOG"

# 프론트엔드 배포
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 프론트엔드 배포 시작..." >> "$LOG"
railway service frontend >> "$LOG" 2>&1
railway up -d >> "$LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 프론트엔드 배포 완료" >> "$LOG"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 전체 배포 완료" >> "$LOG"
